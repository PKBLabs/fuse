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

from fuse.plugins.community.sst.initialize_db import initialize_sst_schema


@dataclass
class SSTPlugin:
    plugin_id: str = "com.pkbresearchlabs.fuse.sst"
    name: str = "FUSE SST Plugin"

    def initialize_database(self, conn) -> None:
        initialize_sst_schema(conn)


def register_plugin():
    return SSTPlugin()