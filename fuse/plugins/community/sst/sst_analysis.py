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
import hashlib
import json
import pandas as pd

from fuse.plugins.community.sst.initialize_db import get_connection
from fuse.plugins.community.sst.get_sstinfo import parse_sstinfo_output


def read_sql_df(query: str, params=()):
    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)


def get_components_df():
    return read_sql_df("""
        SELECT
            e.id AS element_id,
            e.name AS element,
            c.id AS component_id,
            c.name AS component,
            c.is_subcomp,
            c.category,
            c.iface,
            c.description,
            c.functionality,
            c.checkpointable
        FROM components c
        JOIN elements e ON c.parent_id = e.id
        ORDER BY e.name, c.is_subcomp, c.name
    """)


def elements_with_most_components():
    df = get_components_df()

    return (
        df.groupby("element")
          .size()
          .reset_index(name="component_count")
          .sort_values("component_count", ascending=False)
    )


def subcomponents_implementing_interface(interface_text: str):
    df = get_components_df()

    return df[
        (df["is_subcomp"] == 1)
        & df["iface"].str.contains(interface_text, case=False, na=False)
    ].sort_values(["element", "component"])


def required_parameters():
    return read_sql_df("""
        SELECT
            e.name AS element,
            c.name AS component,
            c.is_subcomp,
            p.name AS parameter,
            p.description,
            p.default_val,
            p.required
        FROM parameters p
        JOIN components c
            ON p.parent_type = 'components'
           AND p.parent_id = c.id
        JOIN elements e
            ON c.parent_id = e.id
        WHERE p.required = 1
        ORDER BY e.name, c.name, p.name
    """)


def component_parameter_summary():
    return read_sql_df("""
        SELECT
            e.name AS element,
            c.name AS component,
            c.is_subcomp,
            COUNT(p.id) AS parameter_count,
            SUM(CASE WHEN p.required = 1 THEN 1 ELSE 0 END) AS required_parameter_count
        FROM components c
        JOIN elements e ON c.parent_id = e.id
        LEFT JOIN parameters p
            ON p.parent_type = 'components'
           AND p.parent_id = c.id
        GROUP BY c.id
        ORDER BY required_parameter_count DESC, parameter_count DESC
    """)

def get_latest_sst_info_runs(limit=2):
    return read_sql_df(
        """
        SELECT id, stdout, stderr, created_at
        FROM sst_info_runs
        WHERE return_code = 0
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )


def component_signature(component):
    """
    Make a stable fingerprint for one parsed component/subcomponent.
    If any meaningful metadata changes, this hash changes.
    """
    payload = {
        "element_name": component.element_name,
        "name": component.name,
        "is_subcomp": component.is_subcomp,
        "description": component.description,
        "iface": component.iface,
        "category": component.category,
        "functionality": component.functionality,
        "checkpointable": component.checkpointable,
        "parameters": sorted(
            [
                {
                    "name": p.name,
                    "description": p.description,
                    "default_val": p.default_val,
                    "required": p.required,
                }
                for p in component.parameters
            ],
            key=lambda x: x["name"],
        ),
        "ports": sorted(
            [
                {
                    "name": p.name,
                    "description": p.description,
                    "iface": p.iface,
                }
                for p in component.ports
            ],
            key=lambda x: x["name"],
        ),
        "subcomp_slots": sorted(
            [
                {
                    "name": s.name,
                    "description": s.description,
                    "iface": s.iface,
                }
                for s in component.subcomp_slots
            ],
            key=lambda x: x["name"],
        ),
        "statistics": sorted(
            [
                {
                    "name": s.name,
                    "description": s.description,
                    "units": s.units,
                    "iface": s.iface,
                }
                for s in component.statistics
            ],
            key=lambda x: x["name"],
        ),
    }

    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parsed_components_to_df(stdout: str):
    _elements, components = parse_sstinfo_output(stdout)

    records = []

    for component in components:
        kind = "subcomponent" if component.is_subcomp else "component"

        records.append(
            {
                "key": f"{component.element_name}|{kind}|{component.name}",
                "element": component.element_name,
                "component": component.name,
                "kind": kind,
                "iface": component.iface,
                "category": component.category,
                "checkpointable": component.checkpointable,
                "parameter_count": len(component.parameters),
                "port_count": len(component.ports),
                "subcomp_slot_count": len(component.subcomp_slots),
                "statistic_count": len(component.statistics),
                "signature": component_signature(component),
            }
        )

    return pd.DataFrame(records)


def compare_latest_two_sstinfo_runs():
    runs = get_latest_sst_info_runs(limit=2)

    if len(runs) < 2:
        raise RuntimeError("Need at least two successful sst-info runs to compare.")

    latest = runs.iloc[0]
    previous = runs.iloc[1]

    latest_df = parsed_components_to_df(latest["stdout"])
    previous_df = parsed_components_to_df(previous["stdout"])

    comparison = previous_df.merge(
        latest_df,
        on="key",
        how="outer",
        suffixes=("_previous", "_latest"),
        indicator=True,
    )

    added = comparison[comparison["_merge"] == "right_only"]
    removed = comparison[comparison["_merge"] == "left_only"]

    changed = comparison[
        (comparison["_merge"] == "both")
        & (comparison["signature_previous"] != comparison["signature_latest"])
    ]

    return {
        "previous_run_id": int(previous["id"]),
        "latest_run_id": int(latest["id"]),
        "added": added,
        "removed": removed,
        "changed": changed,
    }