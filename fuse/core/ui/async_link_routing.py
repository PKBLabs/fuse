# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.
#
# FUSE is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU General Public License for more details.
"""Background link-routing helpers for the model canvas.

Qt graphics items are not thread-safe, so ``ModelScene`` must snapshot link
geometry on the GUI thread. This module receives only plain numeric data,
computes orthogonal routes away from the GUI thread, and emits plain numeric
route points back to the scene for visualization.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import os

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from fuse.core.diagnostics import breadcrumb
from fuse.core.routing.routing import (
    RoutingConfig,
    route_orthogonal_path_tuples,
    simplify_point_tuples,
)


PointTuple = tuple[float, float]
RectTuple = tuple[float, float, float, float]


@dataclass(frozen=True)
class LinkRouteRequest:
    """Plain-data route request for one rendered link."""

    link_id: int
    source_center: PointTuple
    target_center: PointTuple
    source_exit: PointTuple
    target_exit: PointTuple
    lane_distance: float
    config: dict[str, float]


@dataclass(frozen=True)
class LinkRouteResult:
    """Plain-data route result for one rendered link."""

    link_id: int
    points: list[PointTuple]


class LinkRoutingWorkerSignals(QObject):
    """Signals emitted by ``LinkRoutingWorker`` on completion."""

    finished = Signal(int, object)
    failed = Signal(int, str)


def _route_one(
    request: LinkRouteRequest,
    obstacle_rects: list[RectTuple],
) -> LinkRouteResult:
    """Compute one link path using only copied numeric geometry."""

    config = RoutingConfig(**request.config)
    route = route_orthogonal_path_tuples(
        start=request.source_exit,
        end=request.target_exit,
        obstacle_rects=obstacle_rects,
        config=config,
        lane_distance=float(request.lane_distance),
    )

    full_route = simplify_point_tuples(
        [
            request.source_center,
            *route,
            request.target_center,
        ]
    )

    return LinkRouteResult(
        link_id=int(request.link_id),
        points=[(float(point[0]), float(point[1])) for point in full_route],
    )


class LinkRoutingWorker(QRunnable):
    """Compute a batch of link routes on a worker thread.

    The worker receives immutable primitive snapshots from the GUI thread. The
    optional per-batch worker count is intentionally capped by ``ModelScene`` so
    dense diagrams do not spawn unbounded nested routing threads while the scene
    is being mutated.
    """

    def __init__(
        self,
        generation: int,
        requests: list[LinkRouteRequest],
        obstacle_rects: list[RectTuple],
        max_workers: int | None = None,
        batch_id: int | None = None,
    ):
        super().__init__()
        self.generation = int(generation)
        self.batch_id = int(batch_id or generation)
        self.requests = list(requests)
        self.obstacle_rects = list(obstacle_rects)
        self.max_workers = max_workers
        self.signals = LinkRoutingWorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            if not self.requests:
                breadcrumb(
                    "async_router.worker.start",
                    generation=self.generation,
                    batch_id=self.batch_id,
                    link_count=0,
                    obstacle_count=len(self.obstacle_rects),
                    worker_count=0,
                )
                self.signals.finished.emit(self.generation, [])
                return

            max_workers = self.max_workers
            if max_workers is None:
                value = os.environ.get("FUSE_ASYNC_ROUTE_WORKERS", "1")
                try:
                    max_workers = int(value)
                except ValueError:
                    max_workers = 1

            max_workers = max(1, min(int(max_workers), len(self.requests)))

            breadcrumb(
                "async_router.worker.start",
                generation=self.generation,
                batch_id=self.batch_id,
                link_count=len(self.requests),
                obstacle_count=len(self.obstacle_rects),
                worker_count=max_workers,
            )

            if max_workers <= 1 or len(self.requests) <= 1:
                results = [
                    _route_one(request, self.obstacle_rects)
                    for request in self.requests
                ]
            else:
                results = []
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_request = {
                        executor.submit(
                            _route_one,
                            request,
                            self.obstacle_rects,
                        ): request
                        for request in self.requests
                    }

                    for future in as_completed(future_to_request):
                        results.append(future.result())

            results.sort(key=lambda item: item.link_id)
            breadcrumb(
                "async_router.worker.end",
                generation=self.generation,
                batch_id=self.batch_id,
                link_count=len(self.requests),
                obstacle_count=len(self.obstacle_rects),
                result_count=len(results),
                worker_count=max_workers,
            )
            self.signals.finished.emit(self.generation, results)
        except Exception as exc:  # pragma: no cover - defensive GUI fallback
            breadcrumb(
                "async_router.worker.failed",
                generation=self.generation,
                batch_id=self.batch_id,
                link_count=len(self.requests),
                obstacle_count=len(self.obstacle_rects),
                error=f"{type(exc).__name__}: {exc}",
            )
            self.signals.failed.emit(self.generation, str(exc))
