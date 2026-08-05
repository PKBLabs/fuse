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
"""Crash diagnostics and breadcrumb logging for FUSE.

Qt/PySide crashes can terminate the process in native code before a Python
exception exists. This module keeps enough information on disk during normal UI
operations that an exit code such as 139 still leaves a useful trail:

* a rotating application log with Python, Qt, and FUSE breadcrumbs;
* faulthandler output for fatal native signals where Python can dump stacks;
* uncaught exception hooks for main-thread and worker-thread Python failures;
* a rolling breadcrumb/context JSON file describing recent UI actions.
"""
from __future__ import annotations

import atexit
import contextlib
import faulthandler
import json
import logging
import os
import platform
import signal
import sys
import threading
import time
import traceback
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import Any, Callable

_LOGGER_NAME = "fuse.diagnostics"
_MAX_BREADCRUMBS = int(os.environ.get("FUSE_DIAGNOSTIC_BREADCRUMBS", "800"))
_MAX_QT_MESSAGES = int(os.environ.get("FUSE_DIAGNOSTIC_QT_MESSAGES", "300"))

_breadcrumbs: deque[dict[str, Any]] = deque(maxlen=_MAX_BREADCRUMBS)
_qt_messages: deque[dict[str, Any]] = deque(maxlen=_MAX_QT_MESSAGES)
_context_providers: list[Callable[[], dict[str, Any]]] = []
_operation_stack: list[dict[str, Any]] = []
_logger: logging.Logger | None = None
_log_dir: Path | None = None
_fault_file_handle = None
_installed = False
_previous_sys_excepthook = None
_previous_threading_excepthook = None
_previous_qt_message_handler = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _state_log_dir(app_name: str = "fuse") -> Path:
    explicit = os.environ.get("FUSE_CRASH_LOG_DIR") or os.environ.get("FUSE_LOG_DIR")
    if explicit:
        return Path(explicit).expanduser()

    xdg_state_home = os.environ.get("XDG_STATE_HOME")
    if xdg_state_home:
        return Path(xdg_state_home).expanduser() / "fuse" / "logs"

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / app_name / "logs"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / app_name

    return Path.home() / ".local" / "state" / "fuse" / "logs"


def diagnostics_log_dir() -> Path:
    global _log_dir
    if _log_dir is None:
        _log_dir = _state_log_dir()
    _log_dir.mkdir(parents=True, exist_ok=True)
    return _log_dir


def _safe_json_value(value: Any, *, _depth: int = 0) -> Any:
    if _depth > 4:
        return repr(value)

    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, (list, tuple, set)):
        result = []
        for item in list(value)[:80]:
            result.append(_safe_json_value(item, _depth=_depth + 1))
        if len(value) > 80:
            result.append(f"... {len(value) - 80} more")
        return result

    if isinstance(value, dict):
        result = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 120:
                result["..."] = f"{len(value) - 120} more"
                break
            result[str(key)] = _safe_json_value(item, _depth=_depth + 1)
        return result

    for attr in ("name", "objectName", "instance_name", "node_id", "link_id", "attachment_id"):
        try:
            candidate = getattr(value, attr)
            if callable(candidate):
                candidate = candidate()
            if candidate not in (None, ""):
                return {type(value).__name__: _safe_json_value(candidate, _depth=_depth + 1)}
        except Exception:
            pass

    return repr(value)


def _selected_environment() -> dict[str, str]:
    prefixes = ("FUSE_", "SST_", "QT_", "PYTHON", "LD_LIBRARY_PATH", "PATH")
    selected: dict[str, str] = {}
    for key, value in os.environ.items():
        if key.startswith(prefixes) or key in prefixes:
            selected[key] = value
    return selected


def _process_metadata() -> dict[str, Any]:
    return {
        "timestamp_utc": _utc_now(),
        "pid": os.getpid(),
        "ppid": getattr(os, "getppid", lambda: None)(),
        "argv": list(sys.argv),
        "executable": sys.executable,
        "cwd": os.getcwd(),
        "platform": platform.platform(),
        "python": sys.version,
        "thread": threading.current_thread().name,
        "log_dir": str(diagnostics_log_dir()),
        "environment": _selected_environment(),
    }


def _thread_stacks() -> dict[str, list[str]]:
    stacks: dict[str, list[str]] = {}
    current_frames = sys._current_frames()
    threads_by_id = {thread.ident: thread.name for thread in threading.enumerate()}
    for thread_id, frame in current_frames.items():
        name = threads_by_id.get(thread_id, str(thread_id))
        stacks[name] = traceback.format_stack(frame)
    return stacks


def _collect_provider_context() -> list[dict[str, Any]]:
    contexts = []
    for provider in list(_context_providers):
        try:
            contexts.append(_safe_json_value(provider()))
        except Exception as exc:
            contexts.append(
                {
                    "provider": repr(provider),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return contexts


def current_context() -> dict[str, Any]:
    return {
        "process": _process_metadata(),
        "active_operations": list(_operation_stack),
        "breadcrumbs": list(_breadcrumbs),
        "qt_messages": list(_qt_messages),
        "providers": _collect_provider_context(),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(_safe_json_value(payload), file, indent=2, sort_keys=True)
        file.write("\n")
    os.replace(temporary, path)


def write_diagnostics_report(
    reason: str,
    *,
    exc_type: type[BaseException] | None = None,
    exc_value: BaseException | None = None,
    exc_traceback: TracebackType | None = None,
    include_thread_stacks: bool = True,
) -> Path | None:
    """Write a point-in-time diagnostics JSON report and return its path."""

    try:
        payload = current_context()
        payload["reason"] = reason
        if exc_type is not None:
            payload["exception"] = {
                "type": getattr(exc_type, "__name__", repr(exc_type)),
                "message": str(exc_value),
                "traceback": traceback.format_exception(exc_type, exc_value, exc_traceback),
            }
        if include_thread_stacks:
            payload["thread_stacks"] = _thread_stacks()

        log_dir = diagnostics_log_dir()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        report_path = log_dir / f"fuse_diagnostics_{timestamp}_{os.getpid()}_{reason}.json"
        latest_path = log_dir / "fuse_diagnostics_latest.json"
        _write_json(report_path, payload)
        _write_json(latest_path, payload)
        logger = get_logger()
        logger.info("wrote diagnostics report: %s", report_path)
        _flush_handlers(logger)
        return report_path
    except Exception:
        return None


def _flush_handlers(logger: logging.Logger | None = None) -> None:
    logger = logger or _logger
    if logger is None:
        return
    for handler in logger.handlers:
        try:
            handler.flush()
        except Exception:
            pass
    try:
        if _fault_file_handle is not None:
            _fault_file_handle.flush()
    except Exception:
        pass


def get_logger() -> logging.Logger:
    global _logger
    if _logger is None:
        _logger = logging.getLogger(_LOGGER_NAME)
        _logger.setLevel(logging.DEBUG)
        _logger.propagate = False
    return _logger


def _rotate_current_logs(log_dir: Path) -> None:
    current = log_dir / "fuse_current.log"
    previous = log_dir / "fuse_previous.log"
    if current.exists():
        try:
            if previous.exists():
                previous.unlink()
            current.replace(previous)
        except Exception:
            pass

    fault = log_dir / "fuse_current_fault.log"
    previous_fault = log_dir / "fuse_previous_fault.log"
    if fault.exists():
        try:
            if previous_fault.exists():
                previous_fault.unlink()
            fault.replace(previous_fault)
        except Exception:
            pass


def _configure_logging(log_dir: Path) -> logging.Logger:
    logger = get_logger()
    logger.handlers.clear()

    current_log = log_dir / "fuse_current.log"
    session_log = log_dir / f"fuse_{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}_{os.getpid()}.log"

    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03dZ %(levelname)s [%(threadName)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    formatter.converter = time.gmtime

    for path in (current_log, session_log):
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    stderr_enabled = os.environ.get("FUSE_DIAGNOSTICS_STDERR", "").lower() in {"1", "true", "yes"}
    if stderr_enabled:
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(formatter)
        logger.addHandler(console)

    return logger


def _install_faulthandler(log_dir: Path) -> None:
    global _fault_file_handle

    fault_path = log_dir / "fuse_current_fault.log"
    _fault_file_handle = fault_path.open("a", encoding="utf-8")
    _fault_file_handle.write(f"FUSE faulthandler log started {_utc_now()} pid={os.getpid()}\n")
    _fault_file_handle.flush()

    try:
        faulthandler.enable(file=_fault_file_handle, all_threads=True)
    except Exception:
        pass

    for signal_name in ("SIGUSR1", "SIGUSR2"):
        sig = getattr(signal, signal_name, None)
        if sig is None:
            continue
        try:
            faulthandler.register(sig, file=_fault_file_handle, all_threads=True, chain=True)
        except Exception:
            pass


def _handle_uncaught_exception(exc_type, exc_value, exc_traceback) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        if _previous_sys_excepthook is not None:
            _previous_sys_excepthook(exc_type, exc_value, exc_traceback)
        return

    logger = get_logger()
    logger.critical(
        "uncaught Python exception",
        exc_info=(exc_type, exc_value, exc_traceback),
    )
    write_diagnostics_report(
        "uncaught_exception",
        exc_type=exc_type,
        exc_value=exc_value,
        exc_traceback=exc_traceback,
    )
    _flush_handlers(logger)

    if _previous_sys_excepthook is not None and _previous_sys_excepthook is not _handle_uncaught_exception:
        _previous_sys_excepthook(exc_type, exc_value, exc_traceback)


def _handle_thread_exception(args) -> None:
    logger = get_logger()
    logger.critical(
        "uncaught thread exception in %s",
        getattr(args.thread, "name", "<unknown>"),
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )
    write_diagnostics_report(
        "uncaught_thread_exception",
        exc_type=args.exc_type,
        exc_value=args.exc_value,
        exc_traceback=args.exc_traceback,
    )
    _flush_handlers(logger)

    if _previous_threading_excepthook is not None and _previous_threading_excepthook is not _handle_thread_exception:
        _previous_threading_excepthook(args)


def install_qt_message_handler() -> None:
    """Capture Qt warnings/errors/fatal messages in the diagnostics log."""

    global _previous_qt_message_handler

    try:
        from PySide6 import QtCore
    except Exception:
        return

    def _qt_message_handler(mode, context, message):
        try:
            mode_name = getattr(mode, "name", str(mode))
        except Exception:
            mode_name = str(mode)

        payload = {
            "timestamp_utc": _utc_now(),
            "mode": mode_name,
            "message": str(message),
            "category": getattr(context, "category", "") if context is not None else "",
            "file": getattr(context, "file", "") if context is not None else "",
            "function": getattr(context, "function", "") if context is not None else "",
            "line": getattr(context, "line", 0) if context is not None else 0,
        }
        _qt_messages.append(payload)

        logger = get_logger()
        level = logging.ERROR if "Fatal" in mode_name or "Critical" in mode_name else logging.WARNING
        logger.log(
            level,
            "Qt %s: %s (%s:%s %s)",
            payload["mode"],
            payload["message"],
            payload["file"],
            payload["line"],
            payload["function"],
        )
        _flush_handlers(logger)

        if _previous_qt_message_handler is not None:
            try:
                _previous_qt_message_handler(mode, context, message)
            except Exception:
                pass

    try:
        _previous_qt_message_handler = QtCore.qInstallMessageHandler(_qt_message_handler)
    except Exception:
        pass


def install_crash_diagnostics(app_name: str = "fuse", org_name: str = "") -> Path:
    """Install crash diagnostics hooks and return the active log directory."""

    global _installed, _previous_sys_excepthook, _previous_threading_excepthook

    log_dir = diagnostics_log_dir()
    if _installed:
        return log_dir

    log_dir.mkdir(parents=True, exist_ok=True)
    _rotate_current_logs(log_dir)
    logger = _configure_logging(log_dir)
    _install_faulthandler(log_dir)

    _previous_sys_excepthook = sys.excepthook
    sys.excepthook = _handle_uncaught_exception

    if hasattr(threading, "excepthook"):
        _previous_threading_excepthook = threading.excepthook
        threading.excepthook = _handle_thread_exception

    install_qt_message_handler()

    _installed = True
    breadcrumb(
        "diagnostics.installed",
        app_name=app_name,
        org_name=org_name,
        log_dir=str(log_dir),
        pid=os.getpid(),
        python=sys.version.split()[0],
        platform=platform.platform(),
    )
    atexit.register(_on_process_exit)
    return log_dir


def _on_process_exit() -> None:
    try:
        breadcrumb("process.exit", active_operations=len(_operation_stack))
        write_diagnostics_report("normal_exit", include_thread_stacks=False)
    except Exception:
        pass
    finally:
        try:
            _flush_handlers()
        except Exception:
            pass
        try:
            if _fault_file_handle is not None:
                _fault_file_handle.close()
        except Exception:
            pass


def register_context_provider(provider: Callable[[], dict[str, Any]]) -> None:
    if provider not in _context_providers:
        _context_providers.append(provider)


def breadcrumb(event: str, **fields: Any) -> None:
    """Record a durable UI breadcrumb.

    Breadcrumbs are intentionally cheap, serializable, and flushed immediately so
    native crashes leave the most recent action on disk.
    """

    try:
        payload = {
            "timestamp_utc": _utc_now(),
            "event": str(event),
            "thread": threading.current_thread().name,
            **{str(key): _safe_json_value(value) for key, value in fields.items()},
        }
        _breadcrumbs.append(payload)

        logger = get_logger()
        details = json.dumps(payload, sort_keys=True, default=str)
        logger.info("breadcrumb %s", details)
        _flush_handlers(logger)
    except Exception:
        pass


@contextlib.contextmanager
def active_operation(name: str, **fields: Any):
    """Context manager that breadcrumbs start/end/error for risky UI actions."""

    operation = {
        "name": str(name),
        "started_utc": _utc_now(),
        "thread": threading.current_thread().name,
        **{str(key): _safe_json_value(value) for key, value in fields.items()},
    }
    _operation_stack.append(operation)
    breadcrumb(f"{name}.start", **fields)
    try:
        yield
    except BaseException as exc:
        breadcrumb(
            f"{name}.error",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        write_diagnostics_report(
            f"{name}_error",
            exc_type=type(exc),
            exc_value=exc,
            exc_traceback=exc.__traceback__,
        )
        raise
    finally:
        try:
            if operation in _operation_stack:
                _operation_stack.remove(operation)
        except Exception:
            pass
        breadcrumb(f"{name}.end", **fields)
