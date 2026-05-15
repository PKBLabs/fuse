from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF


@dataclass(frozen=True)
class RoutingConfig:
    route_clearance: float = 24.0
    exit_margin: float = 12.0
    lane_spacing: float = 12.0
    bend_penalty: float = 18.0
    fallback_margin: float = 240.0


def same_x(a: QPointF, b: QPointF, tolerance: float = 0.001) -> bool:
    return abs(a.x() - b.x()) < tolerance


def same_y(a: QPointF, b: QPointF, tolerance: float = 0.001) -> bool:
    return abs(a.y() - b.y()) < tolerance


def is_orthogonal_segment(a: QPointF, b: QPointF) -> bool:
    return same_x(a, b) or same_y(a, b)


def segment_intersects_rect(a: QPointF, b: QPointF, rect: QRectF) -> bool:
    """
    Return True if an orthogonal segment crosses the interior of rect.

    Touching the boundary is allowed. Crossing through the interior is not.
    Non-orthogonal segments are treated as invalid/intersecting.
    """
    if same_x(a, b):
        x = a.x()
        y1 = min(a.y(), b.y())
        y2 = max(a.y(), b.y())

        return (
            rect.left() < x < rect.right()
            and not (y2 <= rect.top() or y1 >= rect.bottom())
        )

    if same_y(a, b):
        y = a.y()
        x1 = min(a.x(), b.x())
        x2 = max(a.x(), b.x())

        return (
            rect.top() < y < rect.bottom()
            and not (x2 <= rect.left() or x1 >= rect.right())
        )

    return True


def segment_is_clear(a: QPointF, b: QPointF, rects: list[QRectF]) -> bool:
    if not is_orthogonal_segment(a, b):
        return False

    return not any(segment_intersects_rect(a, b, rect) for rect in rects)


def route_is_clear(points: list[QPointF], rects: list[QRectF]) -> bool:
    for a, b in zip(points, points[1:]):
        if not segment_is_clear(a, b, rects):
            return False

    return True


def route_length(points: list[QPointF]) -> float:
    return sum(
        abs(a.x() - b.x()) + abs(a.y() - b.y())
        for a, b in zip(points, points[1:])
    )


def simplify_points(points: list[QPointF]) -> list[QPointF]:
    """
    Remove duplicate points, collinear middle points, and A-B-A spikes.
    """
    if not points:
        return []

    simplified: list[QPointF] = []

    for point in points:
        if not simplified:
            simplified.append(point)
            continue

        previous = simplified[-1]

        if same_x(previous, point) and same_y(previous, point):
            continue

        simplified.append(point)

        while len(simplified) >= 3:
            a = simplified[-3]
            b = simplified[-2]
            c = simplified[-1]

            # A -> B -> A spike.
            if same_x(a, c) and same_y(a, c):
                simplified.pop(-2)
                simplified.pop(-1)
                continue

            # Collinear middle point.
            if same_x(a, b) and same_x(b, c):
                simplified.pop(-2)
                continue

            if same_y(a, b) and same_y(b, c):
                simplified.pop(-2)
                continue

            break

    return simplified


def build_route_grid(
    start: QPointF,
    end: QPointF,
    obstacle_rects: list[QRectF],
    config: RoutingConfig,
    lane_distance: float = 0.0,
) -> tuple[
    dict[tuple[float, float], QPointF],
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

    xs = {start.x(), end.x()}
    ys = {start.y(), end.y()}

    for rect in obstacle_rects:
        for offset in offsets:
            xs.add(rect.left() - offset)
            xs.add(rect.right() + offset)
            ys.add(rect.top() - offset)
            ys.add(rect.bottom() + offset)

    # Add local channels around the endpoints too.
    xs.update([start.x() - config.lane_spacing, start.x() + config.lane_spacing])
    xs.update([end.x() - config.lane_spacing, end.x() + config.lane_spacing])
    ys.update([start.y() - config.lane_spacing, start.y() + config.lane_spacing])
    ys.update([end.y() - config.lane_spacing, end.y() + config.lane_spacing])

    def key(point: QPointF) -> tuple[float, float]:
        return (round(point.x(), 3), round(point.y(), 3))

    point_by_key: dict[tuple[float, float], QPointF] = {}

    for x in sorted(xs):
        for y in sorted(ys):
            point = QPointF(x, y)

            if not any(rect.contains(point) for rect in obstacle_rects):
                point_by_key[key(point)] = point

    point_by_key[key(start)] = start
    point_by_key[key(end)] = end

    neighbors: dict[tuple[float, float], list[tuple[float, float]]] = {
        item_key: [] for item_key in point_by_key
    }

    row_points: dict[float, list[QPointF]] = {}
    col_points: dict[float, list[QPointF]] = {}

    for point in point_by_key.values():
        row_points.setdefault(round(point.y(), 3), []).append(point)
        col_points.setdefault(round(point.x(), 3), []).append(point)

    for row in row_points.values():
        row.sort(key=lambda point: point.x())

        for a, b in zip(row, row[1:]):
            if segment_is_clear(a, b, obstacle_rects):
                neighbors[key(a)].append(key(b))
                neighbors[key(b)].append(key(a))

    for col in col_points.values():
        col.sort(key=lambda point: point.y())

        for a, b in zip(col, col[1:]):
            if segment_is_clear(a, b, obstacle_rects):
                neighbors[key(a)].append(key(b))
                neighbors[key(b)].append(key(a))

    return point_by_key, neighbors


def find_grid_route(
    start: QPointF,
    end: QPointF,
    obstacle_rects: list[QRectF],
    config: RoutingConfig,
    lane_distance: float = 0.0,
) -> list[QPointF] | None:
    import heapq
    from itertools import count

    def key(point: QPointF) -> tuple[float, float]:
        return (round(point.x(), 3), round(point.y(), 3))

    def manhattan(a: QPointF, b: QPointF) -> float:
        return abs(a.x() - b.x()) + abs(a.y() - b.y())

    point_by_key, neighbors = build_route_grid(
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
            direction = "h" if same_y(current_point, next_point) else "v"

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

    return simplify_points([point_by_key[item] for item in route_keys])


def fallback_route(
    start: QPointF,
    end: QPointF,
    obstacle_rects: list[QRectF],
    config: RoutingConfig,
    lane_distance: float = 0.0,
) -> list[QPointF]:
    """
    Large outside perimeter fallback.

    This should be rare, but it avoids hanging the UI if grid routing fails.
    """
    margin = (
        config.route_clearance
        + config.exit_margin
        + lane_distance
        + config.fallback_margin
    )

    if obstacle_rects:
        left = min(rect.left() for rect in obstacle_rects) - margin
        right = max(rect.right() for rect in obstacle_rects) + margin
        top = min(rect.top() for rect in obstacle_rects) - margin
        bottom = max(rect.bottom() for rect in obstacle_rects) + margin
    else:
        left = min(start.x(), end.x()) - margin
        right = max(start.x(), end.x()) + margin
        top = min(start.y(), end.y()) - margin
        bottom = max(start.y(), end.y()) + margin

    candidates = [
        [
            start,
            QPointF(left, start.y()),
            QPointF(left, top),
            QPointF(end.x(), top),
            end,
        ],
        [
            start,
            QPointF(right, start.y()),
            QPointF(right, top),
            QPointF(end.x(), top),
            end,
        ],
        [
            start,
            QPointF(left, start.y()),
            QPointF(left, bottom),
            QPointF(end.x(), bottom),
            end,
        ],
        [
            start,
            QPointF(right, start.y()),
            QPointF(right, bottom),
            QPointF(end.x(), bottom),
            end,
        ],
    ]

    valid = [
        simplify_points(route)
        for route in candidates
        if route_is_clear(route, obstacle_rects)
    ]

    if valid:
        return min(valid, key=route_length)

    return simplify_points([start, QPointF(start.x(), end.y()), end])


def route_orthogonal_path(
    start: QPointF,
    end: QPointF,
    obstacle_rects: list[QRectF],
    config: RoutingConfig | None = None,
    lane_distance: float = 0.0,
) -> list[QPointF]:
    """
    Public routing API.

    Given a start point, end point, and obstacle rectangles, return a Manhattan
    route that avoids obstacle interiors when possible.
    """
    config = config or RoutingConfig()

    route = find_grid_route(
        start=start,
        end=end,
        obstacle_rects=obstacle_rects,
        config=config,
        lane_distance=lane_distance,
    )

    if route is None:
        route = fallback_route(
            start=start,
            end=end,
            obstacle_rects=obstacle_rects,
            config=config,
            lane_distance=lane_distance,
        )

    return simplify_points(route)