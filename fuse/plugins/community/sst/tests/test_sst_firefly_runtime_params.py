# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

from fuse.plugins.community.sst.export_json import (
    exportable_params_for_node,
    normalize_params_for_node,
)
from fuse.plugins.community.sst.tests.scene_test_helpers import make_node


def test_firefly_ctrlmsg_exports_required_msg_timing_modules_for_runtime_helper():
    node = make_node(
        1,
        "ctrlMsg_0",
        "firefly",
        "ctrlMsg",
        is_subcomp=1,
        parameters={
            "nicsPerNode": "1",
            "loopBackPortName": "loop",
        },
    )

    params = exportable_params_for_node(node)

    assert params["txSetupMod"] == "firefly.LatencyMod"
    assert params["rxSetupMod"] == "firefly.LatencyMod"
    assert params["txFiniMod"] == "firefly.LatencyMod"
    assert params["rxFiniMod"] == "firefly.LatencyMod"
    assert params["txSetupModParams.base"] == "0ns"
    assert params["rxSetupModParams.base"] == "0ns"
    assert params["shortMsgLength"] == "4096"
    assert params["sendAckDelay_ns"] == "0"
    assert "txMemcpyMod" not in params
    assert "rxMemcpyMod" not in params


def test_firefly_ctrlmsg_user_msg_timing_modules_override_runtime_defaults():
    node = make_node(
        1,
        "ctrlMsg_0",
        "firefly",
        "ctrlMsg",
        is_subcomp=1,
        parameters={
            "txSetupMod": "firefly.CustomTx",
            "txSetupModParams.base": "5ns",
        },
    )

    params = exportable_params_for_node(node)

    assert params["txSetupMod"] == "firefly.CustomTx"
    assert params["txSetupModParams.base"] == "5ns"
    assert params["rxSetupMod"] == "firefly.LatencyMod"


def test_firefly_ctrlmsgproto_exports_required_memory_latency_modules():
    node = make_node(
        1,
        "CtrlMsgProto_0",
        "firefly",
        "CtrlMsgProto",
        is_subcomp=1,
        parameters={
            "sendStateDelay_ps": "0",
            "recvStateDelay_ps": "0",
        },
    )

    params = exportable_params_for_node(node)

    assert params["txMemcpyMod"] == "firefly.LatencyMod"
    assert params["rxMemcpyMod"] == "firefly.LatencyMod"
    assert params["txMemcpyModParams.base"] == "0ns"
    assert params["rxMemcpyModParams.base"] == "0ns"
    assert "txSetupMod" not in params
    assert "rxSetupMod" not in params


def test_firefly_ctrlmsgproto_user_memory_latency_modules_override_defaults():
    node = make_node(
        1,
        "CtrlMsgProto_0",
        "firefly",
        "CtrlMsgProto",
        is_subcomp=1,
        parameters={
            "txMemcpyMod": "firefly.CustomMemcpy",
            "txMemcpyModParams.base": "7ns",
        },
    )

    params = exportable_params_for_node(node)

    assert params["txMemcpyMod"] == "firefly.CustomMemcpy"
    assert params["txMemcpyModParams.base"] == "7ns"
    assert params["rxMemcpyMod"] == "firefly.LatencyMod"


def test_firefly_hades_omits_numeric_node_perf_and_adds_net_map_name():
    node = make_node(
        1,
        "hades_0",
        "firefly",
        "hades",
        is_subcomp=1,
        parameters={
            "netMapSize": "4",
            "nodePerf": "1",
        },
    )

    params = normalize_params_for_node(node, exportable_params_for_node(node))

    assert "nodePerf" not in params
    assert params["netMapName"] == "Ember0"


def test_firefly_hades_preserves_explicit_node_perf_and_net_map_name():
    node = make_node(
        1,
        "hades_0",
        "firefly",
        "hades",
        is_subcomp=1,
        parameters={
            "netMapSize": "4",
            "netMapName": "CustomMap",
            "nodePerf": "firefly.SimpleNodePerf",
        },
    )

    params = normalize_params_for_node(node, exportable_params_for_node(node))

    assert params["nodePerf"] == "firefly.SimpleNodePerf"
    assert params["netMapName"] == "CustomMap"


def test_ember_engine_exports_required_api_module_default():
    node = make_node(
        1,
        "EmberEngine_0",
        "ember",
        "EmberEngine",
        parameters={"jobId": "0"},
    )

    params = normalize_params_for_node(node, exportable_params_for_node(node))

    assert params["api.0.module"] == "firefly.hadesMP"


def test_ember_engine_user_api_module_overrides_default():
    node = make_node(
        1,
        "EmberEngine_0",
        "ember",
        "EmberEngine",
        parameters={
            "jobId": "0",
            "api.0.module": "custom.Api",
        },
    )

    params = normalize_params_for_node(node, exportable_params_for_node(node))

    assert params["api.0.module"] == "custom.Api"


def test_ember_engine_legacy_motif_type_param_exports_as_name():
    node = make_node(
        1,
        "EmberEngine_0",
        "ember",
        "EmberEngine",
        parameters={
            "jobId": "0",
            "motif_count": "1",
            "motif0": "ember.AllreduceMotif",
            "motif0.arg.count": "8",
        },
    )

    params = normalize_params_for_node(node, exportable_params_for_node(node))

    assert "motif0" not in params
    assert params["motif0.name"] == "ember.AllreduceMotif"
    assert params["motif0.arg.count"] == "8"
