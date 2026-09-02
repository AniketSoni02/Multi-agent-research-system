"""The router and the direct-answer shortcut.

Not every question is worth a five-researcher, multi-round research run. The
router spends one structured call deciding, and the direct path spends one more
answering -- versus the minutes and dozens of calls the research path costs.
"""

import logging
from typing import Literal

from pydantic import BaseModel, Field

from backend.graph import prompts
from backend.graph.nodes.common import ask, get_llm
from backend.graph.state import ResearchState

logger = logging.getLogger(__name__)


class RouteDecision(BaseModel):
    mode: Literal["direct", "research"] = Field(
        description="'direct' for a question one answer can settle, 'research' for one needing sources."
    )
    reason: str = Field(description="One sentence explaining the choice.")


async def router_node(state: ResearchState) -> dict:
    try:
        router = get_llm().with_structured_output(RouteDecision)
        decision: RouteDecision = await router.ainvoke(
            prompts.ROUTER.format(topic=state["topic"])
        )
        mode, reason = decision.mode, decision.reason
    except Exception as exc:
        # Falling through to the thorough path is the safe failure: a wasted
        # research run is a cost, a wrongly-shortcut answer is a defect.
        logger.warning("router failed, defaulting to research: %s", exc)
        mode, reason = "research", "Router unavailable; defaulted to the full research pipeline."

    logger.info("router chose %s: %s", mode, reason)
    return {"mode": mode, "route_reason": reason}


def route_after_router(state: ResearchState) -> str:
    return "direct_answer" if state.get("mode") == "direct" else "planner"


async def direct_answer_node(state: ResearchState) -> dict:
    answer = await ask(prompts.DIRECT_ANSWER.format(topic=state["topic"]))
    logger.info("direct answer produced a %s-char response", len(answer))
    # Writing final_report means the report pane, copy, download and history all
    # work on this path with no separate wiring.
    return {"final_report": answer, "approved": True}
