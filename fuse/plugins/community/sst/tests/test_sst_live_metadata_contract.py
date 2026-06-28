# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

from __future__ import annotations

import subprocess

import pytest

from fuse.plugins.community.sst.tests.sst_version_support import require_sst_info


pytestmark = [pytest.mark.sst, pytest.mark.sst_live, pytest.mark.slow]


def test_live_sst_info_output_contains_parseable_component_metadata_contract():
    """Smoke-test the real local sst-info contract without assuming optional elements.

    This is intentionally broad: it verifies that FUSE can run and parse the
    local SST metadata stream. More specific live tests cover memHierarchy when
    that library is present in the local install.
    """

    sst_info = require_sst_info()

    completed = subprocess.run(
        [sst_info],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
        check=False,
    )
    output = (completed.stdout + "\n" + completed.stderr).strip()

    assert completed.returncode == 0, output

    from fuse.plugins.community.sst.get_sstinfo import parse_sstinfo_output

    elements, components = parse_sstinfo_output(completed.stdout)

    assert elements, "live sst-info output did not expose any element libraries"
    assert components, "live sst-info output did not expose any components/subcomponents"
    assert any(component.name for component in components)
