from fuse.plugin_api.interfaces import (
    CompatibilityIssue,
    CompatibilityReport,
    LinkCompatibilityResult,
    MigrationPlan,
)


def test_link_compatibility_result_status_helpers_are_severity_based():
    assert LinkCompatibilityResult().is_ok
    assert LinkCompatibilityResult(severity="warning").is_warning
    assert LinkCompatibilityResult(severity="error").is_error


def test_compatibility_issue_status_helpers_are_severity_based():
    warning = CompatibilityIssue(
        severity="warning",
        object_name="node0",
        message="Parameter changed",
        node_id=1,
        parameter_name="clock",
        fix_kind="set_parameter",
        fix_data={"clock": "1GHz"},
    )

    assert warning.is_warning
    assert not warning.is_error
    assert warning.fix_data == {"clock": "1GHz"}


def test_compatibility_report_aggregates_warning_and_error_state():
    report = CompatibilityReport(plugin_id="sst", destination_target_id="2")
    assert report.can_apply

    report.issues.append(CompatibilityIssue("warning", "node", "soft problem"))
    assert report.has_warnings
    assert report.can_apply

    report.issues.append(CompatibilityIssue("error", "node", "hard problem"))
    assert report.has_errors
    assert not report.can_apply


def test_migration_plan_can_apply_tracks_report_errors():
    report = CompatibilityReport(plugin_id="sst")
    plan = MigrationPlan(plugin_id="sst", report=report)

    assert plan.can_apply

    report.issues.append(CompatibilityIssue("error", "node", "missing component"))

    assert not plan.can_apply


def test_migration_plan_without_report_is_applyable_and_stores_updates():
    plan = MigrationPlan(plugin_id="gem5")
    plan.node_updates.append({"node_id": 1, "target_id": "new"})

    assert plan.can_apply
    assert plan.node_updates == [{"node_id": 1, "target_id": "new"}]
