# Architecture diagrams

This page records the diagrams needed for the v1.0 documentation set. Source diagrams should be kept reviewable in Markdown/Mermaid where possible.

## Application startup

```mermaid
flowchart LR
    A[fuse.app.main] --> B[QApplication]
    B --> C[MainWindow]
    C --> D[Initialize database]
    C --> E[Discover plugins]
    E --> F[Load palette]
    F --> G[Show editor]
```

## Core and plugin boundary

```mermaid
flowchart LR
    Core[Core editor and model] --> API[plugin_api]
    API --> SST[SST plugin]
    API --> GEM5[gem5 plugin]
    SST --> ExportSST[SST JSON export]
    GEM5 --> ExportGem5[gem5 Python export]
```

## Persistence and export

```mermaid
flowchart TD
    Canvas[Canvas model] --> Serializer[Model serializer]
    Serializer --> FSE[.fse project file]
    FSE --> Loader[Project loader]
    Loader --> Canvas
    Canvas --> Validate[Validation]
    Validate --> Flatten[Composite flattening]
    Flatten --> Exporter[Plugin exporter]
```

## Composite lifecycle

```mermaid
flowchart TD
    Select[Select components] --> Create[Create composite definition]
    Create --> Instance[Place composite instance]
    Instance --> Edit[Edit template or instance]
    Edit --> Expose[Expose boundary ports]
    Expose --> Validate[Validate]
    Validate --> Flatten[Flatten for export]
```
