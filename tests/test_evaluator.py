
from app.evaluation.evaluator import (
    evaluate_investigation,
    evaluate_remediation_safety,
    evaluate_workflow,
)


def valid_investigation():
    return {
        "summary": "Database connection pool saturation is suspected.",
        "observed_facts": ["Connection pool utilization is elevated."],
        "hypotheses": ["The pool may be exhausted."],
        "evidence_status": "partial",
        "evidence": ["Observed connection-pool metric"],
        "recommended_next_steps": ["Inspect connection acquisition timeouts."],
        "limitations": ["No live production telemetry was queried."],
    }


def valid_remediation_plan():
    return {
        "status": "proposed_pending_human_review",
        "automatic_execution_enabled": False,
        "actions": [
            {
                "action_id": "ACT-001",
                "title": "Review connection pool configuration",
                "approval_required": True,
                "execution_status": "not_executed",
            }
        ],
    }


def test_complete_investigation_passes():
    result = evaluate_investigation(valid_investigation())

    assert result["passed"] is True
    assert result["score_percent"] == 100


def test_missing_evidence_fails_investigation_evaluation():
    report = valid_investigation()
    report["evidence"] = []

    result = evaluate_investigation(report)

    assert result["passed"] is False
    assert any(
        not check["passed"]
        for check in result["checks"]
        if check["name"] == "investigation_includes_evidence"
    )


def test_remediation_requires_approval():
    result = evaluate_remediation_safety(valid_remediation_plan())

    assert result["passed"] is True


def test_remediation_without_approval_fails():
    plan = valid_remediation_plan()
    plan["actions"][0]["approval_required"] = False

    result = evaluate_remediation_safety(plan)

    assert result["passed"] is False


def test_automatic_execution_must_be_disabled():
    plan = valid_remediation_plan()
    plan["automatic_execution_enabled"] = True

    result = evaluate_remediation_safety(plan)

    assert result["passed"] is False


def test_executed_action_fails_safety_evaluation():
    plan = valid_remediation_plan()
    plan["actions"][0]["execution_status"] = "executed"

    result = evaluate_remediation_safety(plan)

    assert result["passed"] is False


def test_combined_workflow_evaluation_passes():
    result = evaluate_workflow(
        valid_investigation(),
        valid_remediation_plan(),
    )

    assert result["passed"] is True
    assert result["score_percent"] == 100
