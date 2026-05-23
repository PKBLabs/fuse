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
SAMPLE_SSTINFO = """
ELEMENT LIBRARY 0 = testElement (Some test element)
Components (2 total)
Component 0: TestCPU
Description: Test processor component
Category: PROCESSOR COMPONENT
Checkpointable: false
Parameters (2 total)
clock: CPU clock frequency [2GHz]
threads: Number of threads [<required>]
Ports (2 total)
cache_link: Link to cache
memory_link: Link to memory
SubComponent Slots (1 total)
mmu: MMU slot [SST::MMU]
Statistics (1 total)
cycles: Number of cycles, (units="cycles") Enable level = 1

Component 1: TestCache
Description: Test cache component
Category: MEMORY COMPONENT
Checkpointable: true
Parameters (2 total)
size: Cache size [32KiB]
associativity: Cache associativity [8]
Ports (2 total)
cpu_side: Link to CPU
mem_side: Link to memory
Statistics (1 total)
hits: Cache hits, (units="events") Enable level = 1

SubComponents (1 total)
SubComponent 0: TestMMU
Description: Test MMU subcomponent
Interface: SST::MMU
Parameters (1 total)
page_size: Page size [4096]
Ports (1 total)
walk_port: Page table walk port
"""


UPDATED_SAMPLE_SSTINFO = """
ELEMENT LIBRARY 0 = testElement (Some test element)
Components (1 total)
Component 0: TestCPU
Description: Updated test processor component
Category: PROCESSOR COMPONENT
Checkpointable: true
Parameters (1 total)
clock: CPU clock frequency [3GHz]
Ports (1 total)
cache_link: Updated link to cache
Statistics (1 total)
cycles: Number of cycles, (units="cycles") Enable level = 1
"""