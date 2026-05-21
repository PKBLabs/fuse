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
from fuse.plugins.community.sst.db_utils import (
    get_all_elements,
    get_all_components_for_element,
    get_component_details,
)

print(get_all_elements()[:5])

opal_components = get_all_components_for_element("Opal")
print(opal_components)

if opal_components:
    component_id = opal_components[0]["id"]
    details = get_component_details(component_id)
    print(details)