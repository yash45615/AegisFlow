
from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.genai import types
from google.genai.errors import ServerError

from app.aegisflow_agent.agent import root_agent
from app.investigation.investigator import investigate_incident
from app.knowledge.retriever import search_knowledge
from app.remediation.planner import plan_remediation
from app.simulator.incident_simulator import simulate_incident


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(
    PROJECT_ROOT / "app" / "aegisflow_agent" / ".env"
)

logger = logging.getLogger(__name__)

adk_app = App(
    name="aegisflow",
    root_agent=root_agent,
)

runner = InMemoryRunner(app=adk_app)


def _detect_scenario(prompt: str) -> str | None:
    """Map common incident wording to supported local scenarios."""
    text = prompt.lower()

    if any(term in text for term in (
        "database", "db saturation", "connection pool",
        "connection-pool", "database saturation",
    )):
        return "database_saturation"

    if any(term in text for term in (
        "authentication", "auth failure", "auth_failure",
        "login failure", "login issue",
    )):
        return "auth_failure"

    if any(term in text for term in (
        "payment", "payment provider", "payment-provider",
    )):
        return "payment_timeout"

    return None


def _local_fallback(prompt: str) -> dict[str, object]:
    """Produce evidence-based local results without calling Gemini."""
    scenario = _detect_scenario(prompt)

    if scenario:
        incident = simulate_incident(scenario)

        if hasattr(incident, "model_dump"):
            incident = incident.model_dump(mode="json")

        investigation = investigate_incident(incident)
        remediation = plan_remediation(investigation)

        response = {
            "mode": "local_fallback",
            "notice": (
                "Gemini was unavailable. This report was generated "
                "by AegisFlow's local investigation and planning modules; "
                "it is not an AI-generated response."
            ),
            "scenario": scenario,
            "investigation": investigation,
            "remediation_plan": remediation,
        }
    else:
        results = search_knowledge(prompt, limit=3)

        response = {
            "mode": "local_fallback",
            "notice": (
                "Gemini was unavailable. These are local knowledge "
                "retrieval results, not an AI-generated answer."
            ),
            "query": prompt,
            "knowledge_results": results,
            "message": (
                "Ask about database saturation, authentication failures, "
                "or payment-provider timeouts for a local incident report."
            ),
        }

    return {
        "agent": root_agent.name,
        "session_id": str(uuid4()),
        "response": json.dumps(response, indent=2, ensure_ascii=False),
        "execution_performed": False,
        "human_approval_required": True,
        "fallback_used": True,
    }


async def ask_aegisflow(prompt: str) -> dict[str, object]:
    """Run the ADK agent, falling back locally during Gemini 503 errors."""
    user_id = "aegisflow_api_user"
    session_id = str(uuid4())

    await runner.session_service.create_session(
        app_name=adk_app.name,
        user_id=user_id,
        session_id=session_id,
    )

    message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=prompt)],
    )

    response_parts: list[str] = []

    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=message,
        ):
            if event.author != root_agent.name:
                continue

            if not event.content or not event.content.parts:
                continue

            for part in event.content.parts:
                if part.text:
                    response_parts.append(part.text)

    except ServerError as exc:
        status_code = (
            getattr(exc, "code", None)
            or getattr(exc, "status_code", None)
        )

        if status_code != 503:
            raise

        logger.warning(
            "Gemini returned HTTP 503; using local fallback."
        )
        return _local_fallback(prompt)

    response_text = "\n".join(response_parts).strip()

    if not response_text:
        raise RuntimeError(
            "The ADK agent completed without returning a text response."
        )

    return {
        "agent": root_agent.name,
        "session_id": session_id,
        "response": response_text,
        "execution_performed": False,
        "human_approval_required": True,
        "fallback_used": False,
    }
