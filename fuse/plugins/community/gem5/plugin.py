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
from dataclasses import dataclass


@dataclass
class Gem5Plugin:
    plugin_id: str = "gem5"
    name: str = "FUSE gem5 Plugin"

    def initialize_database(self, conn) -> None:
        """
        Placeholder for future gem5-specific tables.

        The plugin is recognized by core, but it does not add tables yet.
        """
        return None


def register_plugin():
    return Gem5Plugin()