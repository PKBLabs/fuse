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
from PySide6.QtCore import QPointF, QRectF


def test_simplify_points_removes_collinear_middle_point():
    from fuse.core.routing.routing import simplify_points

    points = [
        QPointF(0, 0),
        QPointF(10, 0),
        QPointF(20, 0),
    ]

    simplified = simplify_points(points)

    assert len(simplified) == 2
    assert simplified[0] == QPointF(0, 0)
    assert simplified[1] == QPointF(20, 0)


def test_segment_intersects_rect_detects_crossing():
    from fuse.core.routing.routing import segment_intersects_rect

    rect = QRectF(40, 40, 20, 20)

    assert segment_intersects_rect(QPointF(0, 50), QPointF(100, 50), rect)
    assert not segment_intersects_rect(QPointF(0, 10), QPointF(100, 10), rect)


def test_route_length_is_positive_for_nonempty_route():
    from fuse.core.routing.routing import route_length

    points = [
        QPointF(0, 0),
        QPointF(10, 0),
        QPointF(10, 10),
    ]

    assert route_length(points) > 0