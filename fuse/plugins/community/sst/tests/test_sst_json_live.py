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

import shutil
import subprocess

import pytest

pytestmark = pytest.mark.sst_live


def test_exported_sst_json_loads_with_real_sst(tmp_path):
    if shutil.which("sst") is None:
        pytest.skip("sst is not installed")

    # TODO:
    # Build a known-good FUSE scene using simpleElementExample components
    # with required valid parameters, export JSON, then run:
    #
    # sst --run-mode=init exported.json
    #
    # This should be added after confirming the exact valid example component
    # parameters for the SST version in CI.

    pytest.skip("Need known-good SST example model fixture")
