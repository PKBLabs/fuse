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
"""
Resolve SST component/subcomponent names to icon files.

This module is intentionally heuristic. It should give a good default icon when
the database is populated from sst-info, while still allowing users to override
the chosen icon later in the GUI.

Expected icon directory:
    media/sst_component_icons/

The filenames below match the icon set currently in that directory
"""

from __future__ import annotations
import csv
from pathlib import Path


from fuse.core.resource_paths import (
    FUSE_PACKAGE_ROOT,
    ARCH_COMPONENT_ICON_DIR,
    ARCH_COMPONENT_ICON_RELATIVE_DIR,
)

PROJECT_ROOT = FUSE_PACKAGE_ROOT
PLUGIN_ROOT = Path(__file__).resolve().parent

DEFAULT_ICON_DIR = ARCH_COMPONENT_ICON_DIR
DEFAULT_OVERRIDE_FILE = PLUGIN_ROOT / "config" / "sst_icon_overrides.csv"
RELATIVE_ICON_DIR = ARCH_COMPONENT_ICON_RELATIVE_DIR


# Exact filenames found in your icon set.
ICON_FILES: dict[str, str] = {
    "and_gate": "AND_gate.png",
    "buffer_gate": "buffer_gate.png",
    "cache_memory_tracer": "cache_memory_tracer.png",
    "cpu": "cpu1.png",
    "crossbar": "crossbar.png",
    "cxl_interface": "CXL_iface.png",
    "delay_buffer": "delay_buffer.png",
    "dram": "DRAM.png",
    "elf_binary_loader": "ELF_binary_loader.png",
    "fam_nic": "FAM_NIC.png",
    "fam_pool": "FAM_pool.png",
    "fifo_queue": "FIFO_queue.png",
    "generator": "generator.png",
    "generic_component": "generic_component.png",
    "memory_cache_controller": "memory_cache_controller.png",
    "memory_directory_controller": "memory_directory_controller.png",
    "memory_sieve": "memory_sieve.png",
    "mips_decoder": "MIPS_decoder.png",
    "mips_handler": "MIPS_handler.png",
    "mmu": "mmu.png",
    "nand_gate": "NAND_gate.png",
    "network_bus": "network_bus.png",
    "nic": "NIC.png",
    "noc_bridge": "NoC_bridge.png",
    "noc_router": "NoC_router.png",
    "noc_traffic_generator": "NoC_traffic_generator.png",
    "nor_gate": "NOR_gate.png",
    "not_gate": "NOT_(inverter)_gate.png",
    "or_gate": "OR_gate.png",
    "page_table": "page_table.png",
    "pagefault_handler": "pagefault_handler.png",
    "passthrough_tlb": "passthrough_tlb.png",
    "prefetcher": "prefetcher.png",
    "rdma_nic": "RDMA_NIC.png",
    "register": "register.png",
    "register_file": "register_file.png",
    "riscv_decoder": "RISC-V_decoder.png",
    "riscv_handler": "RISC-V_handler.png",
    "rtl_component": "RTL_component.png",
    "scratchpad_memory": "scratchpad_memory.png",
    "smart_nic": "smart_NIC.png",
    "tlb": "tlb.png",
    "trace_reader": "trace_reader.png",
    "xnor_gate": "XNOR_gate.png",
    "xor_gate": "XOR_gate.png",
}


# Ordered from most-specific to least-specific.
#
# Order matters. For example:
#   - "passthrough TLB" must match before generic "TLB"
#   - "RDMA NIC" and "Smart NIC" must match before generic "NIC"
#   - "XNOR" must match before "NOR" and "OR"
#   - "NAND" must match before "AND"
ICON_KEYWORDS: list[tuple[str, list[str]]] = [
    # Fabric / NIC / memory expansion
    ("rdma_nic", ["rdma nic", "rdma"]),
    ("smart_nic", ["smart nic", "smartnic"]),
    ("fam_nic", [
        "fabric attached memory nic",
        "fabric-attached memory nic",
        "fam nic",
        "fabric memory nic",
    ]),
    ("fam_pool", [
        "fabric attached memory pool",
        "fabric-attached memory pool",
        "fam pool",
        "fabric memory pool",
        "memory pool",
    ]),
    ("cxl_interface", ["cxl interface", "cxl iface", "cxl"]),

    # Translation / virtual memory
    ("passthrough_tlb", [
        "passthrough tlb",
        "pass through tlb",
        "pass-through tlb",
        "bypass tlb",
    ]),
    ("tlb", [
        "tlb",
        "translation lookaside buffer",
        "translation look aside buffer",
        "lookaside buffer",
        "look-aside buffer",
    ]),
    ("pagefault_handler", [
        "pagefault handler",
        "page fault handler",
        "pagefault",
        "page fault",
    ]),
    ("page_table", ["page table", "pagetable"]),
    ("mmu", ["mmu", "memory management unit"]),

    # Memory hierarchy / memory systems
    ("memory_directory_controller", [
        "memory directory controller",
        "directory controller",
        "dir controller",
        "dirctrl",
        "directory",
        "coherence directory",
    ]),
    ("memory_cache_controller", [
        "memory cache controller",
        "cache controller",
        "cachectrl",
        "cache ctrl",
        "l1 controller",
        "l2 controller",
        "l3 controller",
    ]),
    ("cache_memory_tracer", [
        "cache memory tracer",
        "cache tracer",
        "memory tracer",
    ]),
    ("memory_sieve", ["memory sieve", "sieve"]),
    ("scratchpad_memory", [
        "scratchpad memory",
        "scratch pad memory",
        "scratchpad",
        "scratch pad",
        "spm",
    ]),
    ("dram", [
        "dram",
        "ddr",
        "ddr3",
        "ddr4",
        "ddr5",
        "ram",
    ]),

    # Queues / buffers / prefetch
    ("prefetcher", ["prefetcher", "prefetch"]),
    ("delay_buffer", ["delay buffer", "delay"]),
    ("fifo_queue", [
        "fifo transaction queue",
        "fifo queue",
        "transaction queue",
        "tx queue",
        "queue",
        "fifo",
    ]),

    # Network on chip / interconnect
    ("noc_traffic_generator", [
        "network traffic generator",
        "noc traffic generator",
        "traffic generator",
        "network generator",
    ]),
    ("noc_bridge", [
        "network on chip bridge",
        "noc bridge",
        "bridge noc",
        "bridge",
    ]),
    ("noc_router", [
        "network on chip router",
        "noc router",
        "on chip router",
        "on-chip router",
    ]),
    ("crossbar", ["crossbar", "xbar", "cross bar"]),
    ("network_bus", ["network bus", "interconnect bus", "system bus", "bus"]),

    # CPU / ISA / executable loading
    ("riscv_decoder", [
        "risc-v decoder",
        "riscv decoder",
        "risc v decoder",
    ]),
    ("riscv_handler", [
        "risc-v handler",
        "riscv handler",
        "risc v handler",
    ]),
    ("mips_decoder", ["mips decoder"]),
    ("mips_handler", ["mips handler"]),
    ("elf_binary_loader", [
        "elf binary loader",
        "elf loader",
        "binary loader",
        "loader",
    ]),
    ("cpu", [
        "cpu",
        "processor",
        "core",
        "simplecpu",
        "prospero",
        "miranda cpu",
        "ariel",
    ]),

    # RTL / digital logic
    ("rtl_component", [
        "rtl component",
        "rtl",
        "verilog",
        "vhdl",
        "hardware block",
    ]),

    # Logic gates. Keep inverted/specific gates before generic gates.
    ("xnor_gate", ["xnor gate", "xnor"]),
    ("xor_gate", ["xor gate", "xor"]),
    ("nand_gate", ["nand gate", "nand"]),
    ("and_gate", ["and gate"]),
    ("nor_gate", ["nor gate", "nor"]),
    ("or_gate", ["or gate"]),
    ("not_gate", ["not gate", "inverter", "invert"]),
    ("buffer_gate", ["buffer gate", "logic buffer", "buf gate"]),

    # Register structures
    ("register_file", ["register file", "regfile", "reg file"]),
    ("register", ["individual register", "register"]),

    # Generic stimulus / source components
    ("trace_reader", ["trace reader", "trace"]),
    ("generator", [
        "generator",
        "traffic gen",
        "message generator",
        "memory traffic",
        "streaming generator",
        "source",
    ]),

    # Network interface fallback after more-specific NICs.
    ("nic", ["network interface controller", "network interface", "nic"]),
]


# These types were discussed, but their matching icon files were not present in
# the uploaded zip. They intentionally fall back to generic_component unless you
# later add files and update ICON_FILES.
MISSING_ICON_TYPES: dict[str, list[str]] = {
    "mux": ["mux", "multiplexer"],
    "demux": ["demux", "demultiplexer"],
    "clock_source": ["clock source", "clock generator", "clock", "oscillator"],
    "half_adder": ["half adder"],
    "full_adder": ["full adder"],
    "multiplier": ["multiplier", "multiply"],
    "divider": ["divider", "division"],
    "alu": ["alu", "arithmetic logic unit"],
    "flip_flop": ["flip flop", "flip-flop", "dff", "d flip flop"],
}


def _override_match_score(
    row: dict,
    *,
    name: str,
    element: str = "",
    object_kind: str = "",
) -> int:
    """
    Higher score means a more specific override match.

    Matching priority:
      element + kind + name
      element + name
      kind + name
      name only
    """
    row_name = normalize(row.get("name", ""))
    row_element = normalize(row.get("element_library", ""))
    row_kind = normalize(row.get("object_kind", ""))

    target_name = normalize(name)
    target_element = normalize(element)
    target_kind = normalize(object_kind)

    if not row_name or row_name != target_name:
        return 0

    score = 1

    if row_element:
        if row_element != target_element:
            return 0
        score += 2

    if row_kind:
        if row_kind != target_kind:
            return 0
        score += 1

    return score


def load_icon_overrides(
    override_file: Path = DEFAULT_OVERRIDE_FILE,
) -> list[dict]:
    if not override_file.exists():
        return []

    with override_file.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [row for row in reader]


def find_icon_override(
    *,
    name: str,
    element: str = "",
    object_kind: str = "",
    override_file: Path = DEFAULT_OVERRIDE_FILE,
) -> dict | None:
    overrides = load_icon_overrides(override_file)

    best_row = None
    best_score = 0

    for row in overrides:
        score = _override_match_score(
            row,
            name=name,
            element=element,
            object_kind=object_kind,
        )

        if score > best_score:
            best_score = score
            best_row = row

    return best_row


def normalize(text: str) -> str:
    """Normalize free text for fuzzy keyword matching."""
    return (
        (text or "")
        .lower()
        .replace("_", " ")
        .replace("-", " ")
        .replace("/", " ")
        .replace(".", " ")
    )


def _relative_icon_path(filename: str) -> str:
    return str(RELATIVE_ICON_DIR / filename)


def _absolute_icon_path(filename: str, icon_dir: Path = DEFAULT_ICON_DIR) -> Path:
    return icon_dir / filename


def available_icon_keys(icon_dir: Path = DEFAULT_ICON_DIR) -> set[str]:
    """Return icon keys whose configured files are present on disk."""
    return {
        key
        for key, filename in ICON_FILES.items()
        if _absolute_icon_path(filename, icon_dir).exists()
    }


def find_icon_file(
    icon_key: str,
    icon_dir: Path = DEFAULT_ICON_DIR,
    *,
    return_absolute: bool = False,
) -> str:
    """
    Return an icon path for an icon key.

    By default this returns a project-relative path like:
        media/sst_component_icons/NIC.png

    Set return_absolute=True if the GUI will be launched from arbitrary working
    directories and you want QPixmap to load by absolute path.
    """
    filename = ICON_FILES.get(icon_key)

    if filename:
        absolute_path = _absolute_icon_path(filename, icon_dir)
        if absolute_path.exists():
            return str(absolute_path) if return_absolute else _relative_icon_path(filename)

    # Flexible fallback for future renamed files.
    if icon_dir.exists():
        normalized_key = normalize(icon_key).replace(" ", "_")

        for path in icon_dir.iterdir():
            if not path.is_file():
                continue

            if path.suffix.lower() not in {".png", ".webp", ".jpg", ".jpeg"}:
                continue

            normalized_stem = normalize(path.stem).replace(" ", "_")
            if normalized_key in normalized_stem:
                return str(path.resolve()) if return_absolute else str(RELATIVE_ICON_DIR / path.name)

    return ""


def fallback_icon_path(
    icon_dir: Path = DEFAULT_ICON_DIR,
    *,
    return_absolute: bool = False,
) -> str:
    """Return the generic component icon path if available."""
    return find_icon_file(
        "generic_component",
        icon_dir=icon_dir,
        return_absolute=return_absolute,
    )


def guess_component_icon_key(
    name: str,
    description: str = "",
    category: str = "",
    iface: str = "",
    element: str = "",
    object_kind: str = "",
    override_file: Path = DEFAULT_OVERRIDE_FILE,
) -> str:
    """
    Guess the best icon key from SST component metadata.

    Returns an icon key such as "rdma_nic" or "tlb". If nothing matches, returns
    "generic_component".
    """
    override = find_icon_override(
        name=name,
        element=element,
        object_kind=object_kind,
        override_file=override_file,
    )

    if override:
        icon_key = (override.get("icon_key") or "").strip()
        if icon_key:
            return icon_key

    haystack = normalize(" ".join([name, description, category, iface, element]))

    for icon_key, keywords in ICON_KEYWORDS:
        for keyword in keywords:
            if normalize(keyword) in haystack:
                return icon_key

    # Recognize types whose icons were discussed but are not currently in the zip.
    # They can be upgraded later simply by adding the files and ICON_FILES entries.
    for missing_key, keywords in MISSING_ICON_TYPES.items():
        for keyword in keywords:
            if normalize(keyword) in haystack:
                return missing_key

    return "generic_component"


def guess_component_icon_path(
    name: str,
    description: str = "",
    category: str = "",
    iface: str = "",
    element: str = "",
    object_kind: str = "",
    icon_dir: Path = DEFAULT_ICON_DIR,
    override_file: Path = DEFAULT_OVERRIDE_FILE,
    *,
    return_absolute: bool = False,
) -> str:
    """
    Guess the icon path for a component/subcomponent from its metadata.

    If the guessed type does not have a corresponding file in the current icon
    set, this falls back to generic_component.png.
    """
    override = find_icon_override(
        name=name,
        element=element,
        object_kind=object_kind,
        override_file=override_file,
    )

    if override:
        explicit_path = (override.get("icon_path") or "").strip()
        if explicit_path:
            resolved = resolve_icon_path(explicit_path, icon_dir=icon_dir)
            if resolved.exists():
                return str(resolved) if return_absolute else explicit_path

        icon_key = (override.get("icon_key") or "").strip()
        if icon_key:
            icon_path = find_icon_file(
                icon_key,
                icon_dir=icon_dir,
                return_absolute=return_absolute,
            )
            if icon_path:
                return icon_path

    icon_key = guess_component_icon_key(
        name=name,
        description=description,
        category=category,
        iface=iface,
        element=element,
        object_kind=object_kind,
        override_file=override_file,
    )

    icon_path = find_icon_file(
        icon_key,
        icon_dir=icon_dir,
        return_absolute=return_absolute,
    )

    if icon_path:
        return icon_path

    return fallback_icon_path(
        icon_dir=icon_dir,
        return_absolute=return_absolute,
    )


def resolve_icon_path(icon_path: str, icon_dir: Path = DEFAULT_ICON_DIR) -> Path:
    """
    Convert a stored icon path into an absolute Path usable by QPixmap.

    Handles:
      - absolute paths
      - project-relative paths like media/sst_component_icons/NIC.png
      - bare filenames like NIC.png
    """
    if not icon_path:
        return Path()

    path = Path(icon_path)

    if path.is_absolute():
        return path

    # Project-relative path, e.g. media/sst_component_icons/NIC.png
    project_relative = PROJECT_ROOT / path
    if project_relative.exists():
        return project_relative

    # Bare filename or relative filename.
    icon_dir_relative = icon_dir / path.name
    if icon_dir_relative.exists():
        return icon_dir_relative

    return project_relative


if __name__ == "__main__":
    # Simple manual sanity check.
    examples = [
        "rdma nic",
        "smart nic",
        "passthrough tlb",
        "risc-v decoder",
        "cache tracer",
        "noc router",
        "crossbar",
        "fifo queue",
        "unknown custom component",
    ]

    for example in examples:
        print(f"{example:30s} -> {guess_component_icon_path(example)}")
