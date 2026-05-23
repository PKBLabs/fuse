# Application Startup

The application entry point is:

```text
fuse/app/main.py
```

It imports:

```python
from fuse.app.app import main
```

and calls `main()`.

## Startup sequence

The main startup function in `fuse/app/app.py` performs these steps:

1. Creates `QApplication`.
2. Sets application and organization names from `fuse.core.app_info`.
3. Starts a splash timer.
4. Creates and shows the splash screen from `fuse.app.splash`.
5. Constructs `MainWindow`.
6. Shows the main window after the splash delay.
7. Starts the Qt event loop.

## MainWindow initialization

`MainWindow.__init__()` creates:

- `ComponentPalette`
- `ModelScene`
- `ModelView`
- `PropertiesPanel`

It then calls:

- `setup_menu_bar()`
- `setup_layout()`
- `setup_properties_panel()`
- `setup_status_bar()`
- `ensure_database_ready()`
- `self.palette.load_components()`

## Splash screen

The splash screen is implemented in:

```text
fuse/app/splash.py
```

It displays:

- FUSE logo.
- Edition.
- Version.
- Full product name.
- Copyright.
- Current startup message.

Relevant environment variable:

```text
FUSE_SPLASH_MS
```

Tests can set it to `0`.

## Test auto-close

The application supports test-mode auto-close via:

```text
FUSE_TEST_AUTOCLOSE_MS
```

This allows launch/shutdown tests to run in CI without hanging.

## Running directly

From the parent directory of the FUSE package:

```bash
python -m fuse.app.main
```

From the FUSE package root:

```bash
PYTHONPATH="$(pwd)/.." .venv/bin/python -m fuse.app.main
```
