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
from __future__ import annotations

from fuse.core.model.project_settings import PluginProjectSettings, ToolchainSettings
from fuse.core.persistence.database import get_connection, rows_to_dicts
from fuse.core.toolchains.providers import provider_from_toolchain
from fuse.plugin_api.interfaces import FrameworkTarget, ItemDetails, PaletteItem


DEFAULT_GEM5_VERSION = "25.1.0.1"
PREVIOUS_GEM5_VERSION = "24.1.0.3"
DEFAULT_GEM5_ISA = "X86"


class Gem5Plugin:
    plugin_id = "gem5"
    name = "gem5"

    def initialize_database(self, conn) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gem5_framework_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                source_kind TEXT NOT NULL DEFAULT 'built-in',
                source_path TEXT NOT NULL DEFAULT '',
                gem5_root TEXT NOT NULL DEFAULT '',
                gem5_binary_path TEXT NOT NULL DEFAULT '',
                build_isa TEXT NOT NULL DEFAULT 'X86',
                is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,

                UNIQUE(version, source_kind, source_path, build_isa)
            )
        """)

        conn.execute("""
            INSERT OR IGNORE INTO gem5_framework_versions (
                version,
                label,
                source_kind,
                source_path,
                gem5_root,
                gem5_binary_path,
                build_isa,
                is_default
            )
            VALUES
                (?, ?, 'built-in', '', '', '', ?, 1),
                (?, ?, 'built-in', '', '', '', ?, 0)
        """, (
            DEFAULT_GEM5_VERSION,
            f"gem5 {DEFAULT_GEM5_VERSION}",
            DEFAULT_GEM5_ISA,
            PREVIOUS_GEM5_VERSION,
            f"gem5 {PREVIOUS_GEM5_VERSION}",
            DEFAULT_GEM5_ISA,
        ))

    def bootstrap_database(self) -> None:
        return

    def list_targets(self) -> list[FrameworkTarget]:
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT id, version, label, is_default
                FROM gem5_framework_versions
                ORDER BY is_default DESC, version DESC, id DESC
            """).fetchall()

        targets: list[FrameworkTarget] = []

        for row in rows_to_dicts(rows):
            targets.append(
                FrameworkTarget(
                    plugin_id=self.plugin_id,
                    target_id=str(row["id"]),
                    display_name=row["label"] or f"gem5 {row['version']}",
                    framework_name="gem5",
                    framework_version=row["version"],
                    is_default=bool(row["is_default"]),
                )
            )

        return targets

    def load_palette_items(self, target_id: str | None = None) -> list[PaletteItem]:
        # Placeholder for future gem5 SimObject/model-template palette support.
        # Returning an empty list is valid: it makes the gem5 target selectable
        # in Project Settings without yet exposing gem5 components in the palette.
        return []

    def load_item_details(
        self,
        item_id: str,
        target_id: str | None = None,
    ) -> ItemDetails:
        raise KeyError(f"gem5 item details are not implemented yet: {item_id}")

    def validate_toolchain(
        self,
        plugin_settings: PluginProjectSettings,
    ) -> tuple[bool, str]:
        ok, message, _ = validate_gem5_toolchain(
            toolchain=plugin_settings.toolchain,
            expected_version=plugin_settings.framework_version,
            timeout_seconds=60,
        )
        return ok, message

    def import_metadata_for_toolchain(self, plugin_settings: PluginProjectSettings) -> None:
        # gem5 does not yet have a metadata importer equivalent to SST's sst-info.
        # Future work can query SimObjects/config schemas here.
        return


def gem5_command_from_toolchain(toolchain: ToolchainSettings) -> list[str]:
    binary = (
        toolchain.tool_paths.get("gem5Binary")
        or toolchain.tool_paths.get("remoteGem5Binary")
        or "gem5"
    )
    return [binary]


def validate_gem5_toolchain(
    toolchain: ToolchainSettings,
    expected_version: str = "",
    timeout_seconds: int = 60,
) -> tuple[bool, str, str]:
    """Validate that the configured local/SSH gem5 binary is reachable.

    Returns:
        (ok, user_message, detected_output)
    """
    provider = provider_from_toolchain(toolchain)
    command = [*gem5_command_from_toolchain(toolchain), "--version"]
    result = provider.run(command, timeout_seconds=timeout_seconds)
    output = (result.stdout + result.stderr).strip()

    if result.return_code != 0:
        return (
            False,
            (
                "gem5 validation failed.\n\n"
                f"Backend: {result.backend}\n"
                f"Host: {result.host or 'local'}\n"
                f"Command: {' '.join(command)}\n"
                f"Return code: {result.return_code}\n\n"
                f"STDERR/STDOUT:\n{output}"
            ),
            output,
        )

    if "gem5" not in output.lower():
        return (
            False,
            (
                "The configured command ran successfully, but its version output "
                "does not look like gem5.\n\n"
                f"Command: {' '.join(command)}\n\nOutput:\n{output}"
            ),
            output,
        )

    if expected_version and expected_version not in output:
        return (
            False,
            (
                f"The project target is gem5 {expected_version}, but the configured "
                "gem5 binary reported a different version.\n\n"
                f"Command: {' '.join(command)}\n\nOutput:\n{output}"
            ),
            output,
        )

    version_text = f"gem5 {expected_version}" if expected_version else "gem5"
    return (
        True,
        (
            f"Validated {version_text} toolchain.\n\n"
            f"Backend: {result.backend}\n"
            f"Host: {result.host or 'local'}\n"
            f"Command: {' '.join(command)}\n\n"
            f"Output:\n{output}"
        ),
        output,
    )


def register_plugin():
    return Gem5Plugin()
