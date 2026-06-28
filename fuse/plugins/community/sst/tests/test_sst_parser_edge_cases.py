def test_parse_parameter_default_with_nested_brackets():
    from fuse.plugins.community.sst.get_sstinfo import parse_parameter_line

    parameter = parse_parameter_line(
        "range: Description with bracketed list [[1, 2, 3]]"
    )

    assert parameter.name == "range"
    assert parameter.default_val == "[1, 2, 3]"


def test_parse_parameter_description_containing_colon():
    from fuse.plugins.community.sst.get_sstinfo import parse_parameter_line

    parameter = parse_parameter_line(
        "path: Description with colon: still description [/tmp/file]"
    )

    assert parameter.name == "path"
    assert "colon: still description" in parameter.description
    assert parameter.default_val == "/tmp/file"


def test_parse_statistic_without_units():
    from fuse.plugins.community.sst.get_sstinfo import parse_statistic_line

    statistic = parse_statistic_line("requests: Number of requests")

    assert statistic.name == "requests"
    assert statistic.units == ""


def test_parser_ignores_unknown_sections_without_dropping_component():
    from fuse.plugins.community.sst.get_sstinfo import parse_sstinfo_output

    stdout = """
ELEMENT LIBRARY 0 = weirdElement (test)
Components (1 total)
Component 0: WeirdComponent
Description: Test component
Attributes (1 total)
foo
Parameters (1 total)
clock: Clock [1GHz]
"""

    _, components = parse_sstinfo_output(stdout)

    assert len(components) == 1
    assert components[0].name == "WeirdComponent"
    assert components[0].parameters[0].name == "clock"
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
