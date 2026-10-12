
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.evaluator import evaluate_workflow
from app.investigation.investigator import investigate_incident
from app.remediation.planner import plan_remediation
from app.simulator.incident_simulator import simulate_incident


SCENARIOS = [
    "database_saturation",
    "auth_failure",
    "payment_timeout",
]


def to_plain_data(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def main() -> int:
    results = []

    for scenario in SCENARIOS:
        print(f"Evaluating scenario: {scenario}")

        incident = to_plain_data(simulate_incident(scenario))
        investigation = to_plain_data(
            investigate_incident(incident)
        )
        plan = to_plain_data(
            plan_remediation(investigation)
        )

        evaluation = evaluate_workflow(investigation, plan)

        results.append(
            {
                "scenario": scenario,
                "evaluation": evaluation,
            }
        )

        print(
            f"  Passed: {evaluation['passed_checks']}/"
            f"{evaluation['total_checks']} checks"
        )
        print(f"  Score: {evaluation['score_percent']}%")
        print(f"  Overall: {'PASS' if evaluation['passed'] else 'FAIL'}")

    report = {
        "project": "AegisFlow",
        "report_type": "local_simulated_incident_evaluation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": (
            "Results are based on simulated incidents and local modules. "
            "They do not establish production incident accuracy."
        ),
        "all_scenarios_passed": all(
            item["evaluation"]["passed"] for item in results
        ),
        "scenarios": results,
    }

    output_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "evaluation_latest.json"
    output_file.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\nReport saved to: {output_file}")

    return 0 if report["all_scenarios_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
