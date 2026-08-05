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
"""Orthogonal routing helpers for canvas link graphics.

The routing functions build simple Manhattan-style paths that avoid component
bounding boxes while keeping links readable during editing.

The worker-safe API uses plain ``(x, y)`` points and
``(left, top, right, bottom)`` rectangles. GUI callers can still use the
``QPointF``/``QRectF`` wrappers exposed by the original public functions.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Sequence

from PySide6.QtCore import QPointF, QRectF


PointTuple = tuple[float, float]
RectTuple = tuple[float, float, float, float]


@dataclass(frozen=True)
class RoutingConfig:
    """Tunable routing parameters used when computing orthogonal link paths."""
    route_clearance: float = 24.0
    exit_margin: float = 12.0
    lane_spacing: float = 12.0
    bend_penalty: float = 18.0
    fallback_margin: float = 240.0


def _point_tuple(point: QPointF | PointTuple | Sequence[float]) -> PointTuple:
    """Return a plain numeric tuple for a point-like value."""
    if hasattr(point, "x") and hasattr(point, "y"):
        return (float(point.x()), float(point.y()))

    return (float(point[0]), float(point[1]))


def _rect_tuple(rect: QRectF | RectTuple | Sequence[float]) -> RectTuple:
    """Return a plain numeric tuple for a rectangle-like value."""
    if hasattr(rect, "left") and hasattr(rect, "top"):
        return (
            float(rect.left()),
            float(rect.top()),
            float(rect.right()),
            float(rect.bottom()),
        )

    left, top, right, bottom = rect
    return (float(left), float(top), float(right), float(bottom))


def _qpoint(point: PointTuple) -> QPointF:
    """Convert a plain point tuple back to a Qt point on the GUI thread."""
    return QPointF(float(point[0]), float(point[1]))


def _normalise_points(points: Sequence[QPointF | PointTuple | Sequence[float]]) -> list[PointTuple]:
    return [_point_tuple(point) for point in points]


def _normalise_rects(rects: Sequence[QRectF | RectTuple | Sequence[float]]) -> list[RectTuple]:
    return [_rect_tuple(rect) for rect in rects]


def _parse_int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value == "":
        return default

    try:
        return int(value)
    except ValueError:
        return default


def routing_obstacle_limit() -> int:
    """Return the obstacle cap used before falling back to perimeter routing.

    ``FUSE_ROUTING_GRID_OBSTACLE_LIMIT=0`` disables the cap for debugging.
    """

    return _parse_int_env("FUSE_ROUTING_GRID_OBSTACLE_LIMIT", 48)


def same_x_tuple(a: PointTuple, b: PointTuple, tolerance: float = 0.001) -> bool:
    """Return whether two tuple points share the same x coordinate."""
    return abs(float(a[0]) - float(b[0])) < tolerance


def same_y_tuple(a: PointTuple, b: PointTuple, tolerance: float = 0.001) -> bool:
    """Return whether two tuple points share the same y coordinate."""
    return abs(float(a[1]) - float(b[1])) < tolerance


def same_x(a: QPointF | PointTuple, b: QPointF | PointTuple, tolerance: float = 0.001) -> bool:
    """Return whether two points share the same x coordinate within tolerance."""
    return same_x_tuple(_point_tuple(a), _point_tuple(b), tolerance)


def same_y(a: QPointF | PointTuple, b: QPointF | PointTuple, tolerance: float = 0.001) -> bool:
    """Return whether two points share the same y coordinate within tolerance."""
    return same_y_tuple(_point_tuple(a), _point_tuple(b), tolerance)


def is_orthogonal_segment_tuple(a: PointTuple, b: PointTuple) -> bool:
    """Return whether a tuple segment is horizontal or vertical."""
    return same_x_tuple(a, b) or same_y_tuple(a, b)


def is_orthogonal_segment(a: QPointF | PointTuple, b: QPointF | PointTuple) -> bool:
    """Return whether a segment is horizontal or vertical."""
    return is_orthogonal_segment_tuple(_point_tuple(a), _point_tuple(b))


def rect_contains_point_tuple(rect: RectTuple, point: PointTuple) -> bool:
    """Return whether a point is inside or on the edge of a tuple rectangle."""
    left, top, right, bottom = rect
    x, y = point
    return left <= x <= right and top <= y <= bottom


def segment_intersects_rect_tuple(a: PointTuple, b: PointTuple, rect: RectTuple) -> bool:
    """
    Return True if an orthogonal tuple segment crosses the interior of rect.

    Touching the boundary is allowed. Crossing through the interior is not.
    Non-orthogonal segments are treated as invalid/intersecting.
    """
    left, top, right, bottom = rect

    if same_x_tuple(a, b):
        x = a[0]
        y1 = min(a[1], b[1])
        y2 = max(a[1], b[1])

        return left < x < right and not (y2 <= top or y1 >= bottom)

    if same_y_tuple(a, b):
        y = a[1]
        x1 = min(a[0], b[0])
        x2 = max(a[0], b[0])

        return top < y < bottom and not (x2 <= left or x1 >= right)

    return True


def segment_intersects_rect(
    a: QPointF | PointTuple,
    b: QPointF | PointTuple,
    rect: QRectF | RectTuple,
) -> bool:
    """
    Return True if an orthogonal segment crosses the interior of rect.

    Touching the boundary is allowed. Crossing through the interior is not.
    Non-orthogonal segments are treated as invalid/intersecting.
    """
    return segment_intersects_rect_tuple(
        _point_tuple(a),
        _point_tuple(b),
        _rect_tuple(rect),
    )


def segment_is_clear_tuple(a: PointTuple, b: PointTuple, rects: Sequence[RectTuple]) -> bool:
    """Return whether one orthogonal tuple segment avoids all rectangles."""
    if not is_orthogonal_segment_tuple(a, b):
        return False

    return not any(segment_intersects_rect_tuple(a, b, rect) for rect in rects)


def segment_is_clear(
    a: QPointF | PointTuple,
    b: QPointF | PointTuple,
    rects: Sequence[QRectF | RectTuple],
) -> bool:
    """Return whether one orthogonal segment avoids all obstacle rectangles."""
    point_a = _point_tuple(a)
    point_b = _point_tuple(b)

    if not is_orthogonal_segment_tuple(point_a, point_b):
        return False

    rect_tuples = _normalise_rects(rects)
    return segment_is_clear_tuple(point_a, point_b, rect_tuples)


def route_is_clear_tuple(points: Sequence[PointTuple], rects: Sequence[RectTuple]) -> bool:
    """Return whether all tuple route segments avoid all rectangles."""
    for a, b in zip(points, points[1:]):
        if not segment_is_clear_tuple(a, b, rects):
            return False

    return True


def route_is_clear(
    points: Sequence[QPointF | PointTuple],
    rects: Sequence[QRectF | RectTuple],
) -> bool:
    """Return whether all segments in a route avoid all obstacle rectangles."""
    return route_is_clear_tuple(_normalise_points(points), _normalise_rects(rects))


def route_length_tuples(points: Sequence[PointTuple]) -> float:
    """Return Manhattan length for a tuple polyline route."""
    return sum(
        abs(a[0] - b[0]) + abs(a[1] - b[1])
        for a, b in zip(points, points[1:])
    )


def route_length(points: Sequence[QPointF | PointTuple]) -> float:
    """Return Manhattan length for a polyline route."""
    return route_length_tuples(_normalise_points(points))


def simplify_point_tuples(points: Sequence[PointTuple]) -> list[PointTuple]:
    """
    Remove duplicate points, collinear middle points, and A-B-A spikes.
    """
    if not points:
        return []

    simplified: list[PointTuple] = []

    for raw_point in points:
        point = (float(raw_point[0]), float(raw_point[1]))
        if not simplified:
            simplified.append(point)
            continue

        previous = simplified[-1]

        if same_x_tuple(previous, point) and same_y_tuple(previous, point):
            continue

        simplified.append(point)

        while len(simplified) >= 3:
            a = simplified[-3]
            b = simplified[-2]
            c = simplified[-1]

            # A -> B -> A spike.
            if same_x_tuple(a, c) and same_y_tuple(a, c):
                simplified.pop(-2)
                simplified.pop(-1)
                continue

            # Collinear middle point.
            if same_x_tuple(a, b) and same_x_tuple(b, c):
                simplified.pop(-2)
                continue

            if same_y_tuple(a, b) and same_y_tuple(b, c):
                simplified.pop(-2)
                continue

            break

    return simplified


def simplify_points(points: Sequence[QPointF | PointTuple]) -> list[QPointF]:
    """
    Remove duplicate points, collinear middle points, and A-B-A spikes.
    """
    return [_qpoint(point) for point in simplify_point_tuples(_normalise_points(points))]


def build_route_grid_tuples(
    start: PointTuple,
    end: PointTuple,
    obstacle_rects: Sequence[RectTuple],
    config: RoutingConfig,
    lane_distance: float = 0.0,
) -> tuple[
    dict[tuple[float, float], PointTuple],
    dict[tuple[float, float], list[tuple[float, float]]],
]:
    """
    Build a Manhattan visibility grid from obstacle edges plus start/end points.

    The graph nodes are intersections of useful x/y channels. Edges are created
    between adjacent points in the same row/column when that segment does not
    cross an obstacle rectangle.
    """
    offsets = [
        config.route_clearance,
        config.route_clearance + config.lane_spacing,
        config.route_clearance + lane_distance + config.lane_spacing,
        config.route_clearance + lane_distance + config.lane_spacing * 3,
    ]

    xs = {start[0], end[0]}
    ys = {start[1], end[1]}

    for rect in obstacle_rects:
        left, top, right, bottom = rect
        for offset in offsets:
            xs.add(left - offset)
            xs.add(right + offset)
            ys.add(top - offset)
            ys.add(bottom + offset)

    # Add local channels around the endpoints too.
    xs.update([start[0] - config.lane_spacing, start[0] + config.lane_spacing])
    xs.update([end[0] - config.lane_spacing, end[0] + config.lane_spacing])
    ys.update([start[1] - config.lane_spacing, start[1] + config.lane_spacing])
    ys.update([end[1] - config.lane_spacing, end[1] + config.lane_spacing])

    def key(point: PointTuple) -> tuple[float, float]:
        return (round(point[0], 3), round(point[1], 3))

    point_by_key: dict[tuple[float, float], PointTuple] = {}

    for x in sorted(xs):
        for y in sorted(ys):
            point = (float(x), float(y))

            if not any(rect_contains_point_tuple(rect, point) for rect in obstacle_rects):
                point_by_key[key(point)] = point

    point_by_key[key(start)] = start
    point_by_key[key(end)] = end

    neighbors: dict[tuple[float, float], list[tuple[float, float]]] = {
        item_key: [] for item_key in point_by_key
    }

    row_points: dict[float, list[PointTuple]] = {}
    col_points: dict[float, list[PointTuple]] = {}

    for point in point_by_key.values():
        row_points.setdefault(round(point[1], 3), []).append(point)
        col_points.setdefault(round(point[0], 3), []).append(point)

    for row in row_points.values():
        row.sort(key=lambda point: point[0])

        for a, b in zip(row, row[1:]):
            if segment_is_clear_tuple(a, b, obstacle_rects):
                neighbors[key(a)].append(key(b))
                neighbors[key(b)].append(key(a))

    for col in col_points.values():
        col.sort(key=lambda point: point[1])

        for a, b in zip(col, col[1:]):
            if segment_is_clear_tuple(a, b, obstacle_rects):
                neighbors[key(a)].append(key(b))
                neighbors[key(b)].append(key(a))

    return point_by_key, neighbors


def build_route_grid(
    start: QPointF | PointTuple,
    end: QPointF | PointTuple,
    obstacle_rects: Sequence[QRectF | RectTuple],
    config: RoutingConfig,
    lane_distance: float = 0.0,
) -> tuple[
    dict[tuple[float, float], QPointF],
    dict[tuple[float, float], list[tuple[float, float]]],
]:
    """
    Build a Manhattan visibility grid from obstacle edges plus start/end points.
    """
    point_by_key, neighbors = build_route_grid_tuples(
        start=_point_tuple(start),
        end=_point_tuple(end),
        obstacle_rects=_normalise_rects(obstacle_rects),
        config=config,
        lane_distance=lane_distance,
    )
    return {key: _qpoint(point) for key, point in point_by_key.items()}, neighbors


def find_grid_route_tuples(
    start: PointTuple,
    end: PointTuple,
    obstacle_rects: Sequence[RectTuple],
    config: RoutingConfig,
    lane_distance: float = 0.0,
) -> list[PointTuple] | None:
    """Find a clear grid-based tuple route between two points when possible."""
    import heapq
    from itertools import count

    def key(point: PointTuple) -> tuple[float, float]:
        return (round(point[0], 3), round(point[1], 3))

    def manhattan(a: PointTuple, b: PointTuple) -> float:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    point_by_key, neighbors = build_route_grid_tuples(
        start=start,
        end=end,
        obstacle_rects=obstacle_rects,
        config=config,
        lane_distance=lane_distance,
    )

    start_key = key(start)
    end_key = key(end)

    sequence = count()
    frontier = [(0.0, next(sequence), start_key, None)]
    came_from: dict[tuple[float, float], tuple[float, float] | None] = {
        start_key: None
    }
    cost_so_far = {start_key: 0.0}

    while frontier:
        _, _, current_key, previous_direction = heapq.heappop(frontier)

        if current_key == end_key:
            break

        current_point = point_by_key[current_key]

        for next_key in neighbors.get(current_key, []):
            next_point = point_by_key[next_key]
            direction = "h" if same_y_tuple(current_point, next_point) else "v"

            bend_penalty = 0.0
            if previous_direction is not None and direction != previous_direction:
                bend_penalty = config.bend_penalty

            segment_cost = manhattan(current_point, next_point)
            new_cost = cost_so_far[current_key] + segment_cost + bend_penalty

            if next_key not in cost_so_far or new_cost < cost_so_far[next_key]:
                cost_so_far[next_key] = new_cost
                priority = new_cost + manhattan(next_point, end)

                heapq.heappush(
                    frontier,
                    (priority, next(sequence), next_key, direction),
                )
                came_from[next_key] = current_key

    if end_key not in came_from:
        return None

    route_keys = []
    current = end_key

    while current is not None:
        route_keys.append(current)
        current = came_from[current]

    route_keys.reverse()

    return simplify_point_tuples([point_by_key[item] for item in route_keys])


def find_grid_route(
    start: QPointF | PointTuple,
    end: QPointF | PointTuple,
    obstacle_rects: Sequence[QRectF | RectTuple],
    config: RoutingConfig,
    lane_distance: float = 0.0,
) -> list[QPointF] | None:
    """Find a clear grid-based route between two points when possible."""
    route = find_grid_route_tuples(
        start=_point_tuple(start),
        end=_point_tuple(end),
        obstacle_rects=_normalise_rects(obstacle_rects),
        config=config,
        lane_distance=lane_distance,
    )
    if route is None:
        return None

    return [_qpoint(point) for point in route]


def fallback_route_tuples(
    start: PointTuple,
    end: PointTuple,
    obstacle_rects: Sequence[RectTuple],
    config: RoutingConfig,
    lane_distance: float = 0.0,
) -> list[PointTuple]:
    """
    Large outside perimeter fallback.

    This avoids expensive visibility-grid construction in dense diagrams and
    also handles rare cases where grid routing cannot find a clear path.
    """
    margin = (
        config.route_clearance
        + config.exit_margin
        + lane_distance
        + config.fallback_margin
    )

    if obstacle_rects:
        left = min(rect[0] for rect in obstacle_rects) - margin
        right = max(rect[2] for rect in obstacle_rects) + margin
        top = min(rect[1] for rect in obstacle_rects) - margin
        bottom = max(rect[3] for rect in obstacle_rects) + margin
    else:
        left = min(start[0], end[0]) - margin
        right = max(start[0], end[0]) + margin
        top = min(start[1], end[1]) - margin
        bottom = max(start[1], end[1]) + margin

    candidates = [
        [
            start,
            (left, start[1]),
            (left, top),
            (end[0], top),
            end,
        ],
        [
            start,
            (right, start[1]),
            (right, top),
            (end[0], top),
            end,
        ],
        [
            start,
            (left, start[1]),
            (left, bottom),
            (end[0], bottom),
            end,
        ],
        [
            start,
            (right, start[1]),
            (right, bottom),
            (end[0], bottom),
            end,
        ],
    ]

    valid = [
        simplify_point_tuples(route)
        for route in candidates
        if route_is_clear_tuple(route, obstacle_rects)
    ]

    if valid:
        return min(valid, key=route_length_tuples)

    return simplify_point_tuples([start, (start[0], end[1]), end])


def fallback_route(
    start: QPointF | PointTuple,
    end: QPointF | PointTuple,
    obstacle_rects: Sequence[QRectF | RectTuple],
    config: RoutingConfig,
    lane_distance: float = 0.0,
) -> list[QPointF]:
    """
    Large outside perimeter fallback.

    This should be rare, but it avoids hanging the UI if grid routing fails.
    """
    route = fallback_route_tuples(
        start=_point_tuple(start),
        end=_point_tuple(end),
        obstacle_rects=_normalise_rects(obstacle_rects),
        config=config,
        lane_distance=lane_distance,
    )
    return [_qpoint(point) for point in route]


def route_orthogonal_path_tuples(
    start: QPointF | PointTuple,
    end: QPointF | PointTuple,
    obstacle_rects: Sequence[QRectF | RectTuple],
    config: RoutingConfig | None = None,
    lane_distance: float = 0.0,
) -> list[PointTuple]:
    """
    Worker-safe routing API.

    Given a start point, end point, and obstacle rectangles, return a Manhattan
    route made only of primitive tuples. No Qt value types are created here, so
    this function is safe to call from background routing workers.
    """
    config = config or RoutingConfig()
    start_tuple = _point_tuple(start)
    end_tuple = _point_tuple(end)
    obstacle_tuples = _normalise_rects(obstacle_rects)

    limit = routing_obstacle_limit()
    if limit > 0 and len(obstacle_tuples) > limit:
        return simplify_point_tuples(
            fallback_route_tuples(
                start=start_tuple,
                end=end_tuple,
                obstacle_rects=obstacle_tuples,
                config=config,
                lane_distance=lane_distance,
            )
        )

    route = find_grid_route_tuples(
        start=start_tuple,
        end=end_tuple,
        obstacle_rects=obstacle_tuples,
        config=config,
        lane_distance=lane_distance,
    )

    if route is None:
        route = fallback_route_tuples(
            start=start_tuple,
            end=end_tuple,
            obstacle_rects=obstacle_tuples,
            config=config,
            lane_distance=lane_distance,
        )

    return simplify_point_tuples(route)


def route_orthogonal_path(
    start: QPointF | PointTuple,
    end: QPointF | PointTuple,
    obstacle_rects: Sequence[QRectF | RectTuple],
    config: RoutingConfig | None = None,
    lane_distance: float = 0.0,
) -> list[QPointF]:
    """
    Public GUI routing API.

    Given a start point, end point, and obstacle rectangles, return a Manhattan
    route that avoids obstacle interiors when possible.
    """
    route = route_orthogonal_path_tuples(
        start=start,
        end=end,
        obstacle_rects=obstacle_rects,
        config=config,
        lane_distance=lane_distance,
    )
    return [_qpoint(point) for point in route]