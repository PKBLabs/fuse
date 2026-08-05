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
"""Crash diagnostics helpers for the FUSE desktop application."""

from .crash_reporter import (
    active_operation,
    breadcrumb,
    install_crash_diagnostics,
    register_context_provider,
    write_diagnostics_report,
)

__all__ = [
    "active_operation",
    "breadcrumb",
    "install_crash_diagnostics",
    "register_context_provider",
    "write_diagnostics_report",
]
