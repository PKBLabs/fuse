# Routing and Canvas Graphics

The model canvas is built on Qt's graphics-view framework.

## Main classes

```text
ModelView       QGraphicsView wrapper, drag/drop handling.
ModelScene      QGraphicsScene, selection, link creation, rerouting.
ComponentNodeItem  Visual component instance.
PortItem        Visual port dot.
ConnectionItem  Visual link path.
```

## Link routing

The route solver is in:

```text
fuse/core/routing/routing.py
```

`ConnectionItem` delegates path computation to routing functions.

## Routing behavior

The routing system attempts to:

- Use orthogonal link paths.
- Avoid component boxes.
- Keep link endpoints connected to port positions.
- Recompute routes when components move.
- Use cheaper preview routes during active dragging.

## Port rules

Current point-to-point link rule:

```text
Each port may participate in at most one point-to-point link.
```

If the user clicks an already-connected port, the scene rejects the link.

## Moving components

During drag:

- Links attached to the moving node use a cheap preview route.
- This keeps the UI responsive.

On release:

- Attached links are rerouted with the full route algorithm.
- Links whose routes intersect the moved node may also be rerouted.

## Reroute all

The Tools menu includes a `Reroute All Links` action. This should be used as an explicit cleanup operation rather than on every mouse move.
