
from __future__ import annotations

from typing import Any

from google.adk.agents import Agent

from app.investigation.investigator import investigate_incident
from app.knowledge.retriever import search_knowledge
from app.remediation.planner import plan_remediation
from app.simulator.incident_simulator import simulate_incident


def search_runbooks(query: str, limit: int = 3) -> dict[str, Any]:
    """Search AegisFlow's local runbooks and historical incident records."""
    results = search_knowledge(query=query, limit=limit)
    return {
        "query": query,
        "result_count": len(results),
        "results": results,
    }


def investigate_scenario(scenario: str) -> dict[str, Any]:
    """Simulate an incident and investigate it using existing evidence."""
    incident = simulate_incident(scenario)

    if hasattr(incident, "model_dump"):
        incident = incident.model_dump(mode="json")

    report = investigate_incident(incident)
    return report


def propose_remediation(scenario: str) -> dict[str, Any]:
    """Create an investigation report and a safe remediation proposal.

    This tool does not execute remediation or modify infrastructure.
    """
    report = investigate_scenario(scenario)
    plan = plan_remediation(report)

    return {
        "investigation": report,
        "remediation_plan": plan,
        "execution_performed": False,
        "human_approval_required": True,
    }


root_agent = Agent(
    name="aegisflow_incident_agent",
    model="gemini-flash-latest",
    description=(
        "An evidence-based incident investigation and safe remediation "
        "planning agent."
    ),
    instruction="""
You are AegisFlow, an AI assistant for incident investigation.

Your responsibilities:
1. Help investigate database saturation, authentication failures,
   and payment-provider timeouts.
2. Use the supplied tools to inspect local runbooks, historical
   incidents, and investigation reports.
3. Distinguish observed facts from hypotheses.
4. Explain which evidence supports each recommendation.
5. Suggest safe, reversible remediation steps where appropriate.
6. Clearly state uncertainties and missing evidence.
7. Never claim that a proposed fix was executed or that an incident
   was resolved unless verified evidence explicitly establishes that.

Safety rules:
- You are an advisory agent, not an autonomous production operator.
- Never execute shell commands or modify infrastructure.
- Never bypass human approval.
- Remediation plans are proposals only.
- Do not invent metrics, logs, evidence, or root causes.
- If evidence is insufficient, explain what additional evidence is
  needed instead of presenting a hypothesis as a confirmed cause.

Available scenarios:
- database_saturation
- auth_failure
- payment_timeout

When the user requests an investigation, use investigate_scenario.
When the user asks for remediation recommendations, use
propose_remediation.
When the user asks about runbooks or past incidents, use search_runbooks.

Present findings in clear sections: Observations, Hypotheses,
Supporting Evidence, Recommended Next Steps, and Safety Notes.
""",
    tools=[
        search_runbooks,
        investigate_scenario,
        propose_remediation,
    ],
)
