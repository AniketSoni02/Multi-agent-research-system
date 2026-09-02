"""The router and the direct-answer shortcut.

The router runs before the planner and decides how much machinery the query
deserves. A question the heuristic recognises is settled costs no API call to
route at all, so answering it costs exactly one call in total; anything else is
judged once, on a 0-5 scale, and that number is handed to the planner rather
than re-derived there.
"""

import logging
from typing import Optional

from pydantic import BaseModel, Field

from backend import config
from backend.graph import complexity, prompts
from backend.graph.nodes.common import ask, call, get_llm
from backend.graph.state import ResearchState

logger = logging.getLogger(__name__)


class ComplexityAssessment(BaseModel):
    complexity: int = Field(
        ge=0,
        le=5,
        description="0 if one direct answer settles it; otherwise how many research subtasks it needs.",
    )
    reason: str = Field(description="One sentence explaining the score.")


def _decision(mode: str, score: Optional[int], reason: str) -> dict:
    logger.info("router chose %s (complexity=%s): %s", mode, score, reason)
    return {"mode": mode, "complexity": score, "route_reason": reason}


async def router_node(state: ResearchState) -> dict:
    topic = state["topic"]

    # Free path first. This is what keeps "what is the capital of france" from
    # ever reaching the API to be routed -- and what keeps it working when the
    # daily quota is spent.
    verdict = complexity.classify(topic)
    if verdict == complexity.DIRECT:
        return _decision("direct", 0, "Recognised as a settled, single-fact question.")
    if verdict == complexity.RESEARCH:
        # No score: the planner judges scope itself, which it has to do anyway.
        return _decision("research", None, "Recognised as needing gathered sources.")

    try:
        assessment: ComplexityAssessment = await call(
            get_llm().with_structured_output(ComplexityAssessment),
            prompts.ROUTER.format(topic=topic, hi=config.MAX_SUBTASKS),
        )
    except Exception as exc:
        # The heuristic had no opinion and the model is unreachable. Research is
        # the safe guess: an over-researched answer is a cost, an
        # under-researched one is a defect.
        logger.warning("router call failed, defaulting to research: %s", exc)
        return _decision(
            "research", None, "Router unavailable; defaulted to the full research pipeline."
        )

    score = max(0, min(assessment.complexity, config.MAX_SUBTASKS))
    mode = "direct" if score == 0 else "research"
    return _decision(mode, score, assessment.reason)


def route_after_router(state: ResearchState) -> str:
    return "direct_answer" if state.get("mode") == "direct" else "planner"


async def direct_answer_node(state: ResearchState) -> dict:
    answer = await ask(prompts.DIRECT_ANSWER.format(topic=state["topic"]))
    logger.info("direct answer produced a %s-char response", len(answer))
    # Writing final_report means the report pane, copy, download and history all
    # work on this path with no separate wiring.
    return {"final_report": answer, "approved": True}
