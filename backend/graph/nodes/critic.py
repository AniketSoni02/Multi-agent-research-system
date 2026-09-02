"""The Critic's evidence loop: critic -> critic_tools -> tool_results -> verdict -> feedback.

The point of the split is that no single call both gathers the evidence and
renders the judgement. The critic node may only call tools; the verdict node
sees the evidence they returned and produces forced JSON from it. A rejection
therefore has to point at something a tool actually found.
"""

import asyncio
import logging
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel, Field

from backend import config
from backend.graph import prompts
from backend.graph.nodes.common import call, get_llm
from backend.graph.state import ResearchState, ToolEvidence
from backend.tools import critic_tools

logger = logging.getLogger(__name__)


class CriticVerdict(BaseModel):
    approved: bool = Field(
        description="True only if the evidence shows the report is comprehensive and well-supported."
    )
    feedback: str = Field(description="A short review explaining the verdict.")
    missing: List[str] = Field(
        default_factory=list,
        description="Coverage gaps, each a concrete researchable question. Empty when approved.",
    )
    unsupported: List[str] = Field(
        default_factory=list,
        description="Draft claims the evidence did not substantiate. Empty when approved.",
    )


def _subtask_list(state: ResearchState) -> str:
    subtasks = sorted({f["subtask"] for f in state.get("researcher_findings", [])})
    return "\n".join(f"- {s}" for s in subtasks) or "(none)"


# ---------------------------------------------------------------------------- critic


async def critic_node(state: ResearchState) -> dict:
    messages = list(state.get("critic_messages", []))

    if not messages:
        iteration = state.get("iteration", 1)
        max_iterations = state.get("max_iterations", config.MAX_ITERATIONS)
        messages = [
            SystemMessage(
                content=prompts.CRITIC_SYSTEM.format(
                    max_calls=config.MAX_CRITIC_TOOL_CALLS,
                    iteration=iteration,
                    max_iterations=max_iterations,
                )
            ),
            HumanMessage(
                content=prompts.CRITIC_DRAFT.format(
                    topic=state["topic"],
                    subtasks=_subtask_list(state),
                    draft_report=state.get("draft_report", ""),
                )
            ),
        ]

    reply = await call(get_llm().bind_tools(critic_tools.TOOL_SCHEMAS), messages)
    messages.append(reply)

    calls = getattr(reply, "tool_calls", []) or []
    logger.info(
        "critic turn requested %s tool call(s); %s used so far",
        len(calls),
        state.get("critic_tool_calls", 0),
    )
    return {"critic_messages": messages}


def route_after_critic(state: ResearchState) -> str:
    """Keep looping only while the critic wants tools and has calls left."""
    messages = state.get("critic_messages", [])
    if not messages:
        return "tool_results"

    last = messages[-1]
    if not getattr(last, "tool_calls", None):
        return "tool_results"
    if state.get("critic_tool_calls", 0) >= config.MAX_CRITIC_TOOL_CALLS:
        logger.info("critic tool-call cap reached; moving to the verdict")
        return "tool_results"
    return "critic_tools"


# ---------------------------------------------------------------------- critic tools


async def _dispatch(name: str, args: Dict[str, Any], state: ResearchState) -> str:
    if name == "CheckCoverage":
        return await critic_tools.check_coverage(
            args.get("subtask", ""), state.get("draft_report", "")
        )
    if name == "VerifyClaim":
        return await critic_tools.verify_claim(args.get("claim", ""), state["session_id"])
    if name == "CheckGrounding":
        return await critic_tools.check_grounding(
            args.get("statement", ""), state.get("researcher_findings", [])
        )
    return f"Unknown tool {name!r}."


async def critic_tools_node(state: ResearchState) -> dict:
    messages = list(state.get("critic_messages", []))
    used = state.get("critic_tool_calls", 0)
    calls = list(getattr(messages[-1], "tool_calls", []) or [])

    # The cap is a total for the round, so a batch that would cross it is
    # truncated rather than rejected wholesale.
    budget = max(0, config.MAX_CRITIC_TOOL_CALLS - used)
    allowed, refused = calls[:budget], calls[budget:]

    results = await asyncio.gather(
        *(_dispatch(c["name"], c.get("args") or {}, state) for c in allowed),
        return_exceptions=True,
    )

    iteration = state.get("iteration", 1)
    evidence: List[ToolEvidence] = list(state.get("tool_evidence", []))

    for call, result in zip(allowed, results):
        if isinstance(result, Exception):
            logger.warning("critic tool %s failed: %s", call["name"], result)
            text = f"The {call['name']} tool failed: {result}"
        else:
            text = result
        messages.append(ToolMessage(content=text, tool_call_id=call["id"]))
        evidence.append(
            {
                "tool": call["name"],
                "args": call.get("args") or {},
                "result": text,
                "iteration": iteration,
            }
        )

    for call in refused:
        # Answer every pending call: an unanswered tool_call leaves a malformed
        # exchange, and saying why beats the critic re-requesting it in a loop.
        messages.append(
            ToolMessage(
                content=(
                    f"Not run: the {config.MAX_CRITIC_TOOL_CALLS}-call review budget is spent. "
                    "Draw your conclusions from the evidence you already have."
                ),
                tool_call_id=call["id"],
            )
        )

    logger.info("critic tools ran %s call(s), refused %s", len(allowed), len(refused))
    return {
        "critic_messages": messages,
        "critic_tool_calls": used + len(allowed),
        "tool_evidence": evidence,
    }


# ---------------------------------------------------------------------- tool results


def _format_evidence(evidence: List[ToolEvidence]) -> str:
    if not evidence:
        return "(the critic called no tools, so there is no evidence for or against the draft)"
    blocks = []
    for i, row in enumerate(evidence, start=1):
        args = ", ".join(f"{k}={v!r}" for k, v in row["args"].items())
        blocks.append(f"[{i}] {row['tool']}({args})\n{row['result']}")
    return "\n\n".join(blocks)


def tool_results_node(state: ResearchState) -> dict:
    """Fold the tool calls into one evidence block. Deterministic, no LLM."""
    evidence = state.get("tool_evidence", [])
    summary = _format_evidence(evidence)
    logger.info("aggregated %s piece(s) of tool evidence", len(evidence))

    # The transcript has served its purpose once the evidence is extracted, and
    # keeping it would carry this round's tool exchange into the next one.
    return {"evidence_summary": summary, "critic_messages": []}


# --------------------------------------------------------------------------- verdict


async def verdict_node(state: ResearchState) -> dict:
    iteration = state.get("iteration", 1)
    verdict_llm = get_llm().with_structured_output(CriticVerdict)

    try:
        result: CriticVerdict = await call(
            verdict_llm,
            prompts.VERDICT.format(
                topic=state["topic"],
                subtasks=_subtask_list(state),
                draft_report=state.get("draft_report", ""),
                evidence=state.get("evidence_summary", "") or "(none)",
                iteration=iteration,
                max_iterations=state.get("max_iterations", config.MAX_ITERATIONS),
            ),
        )
    except Exception as exc:
        # Approving on a failed verdict call would ship an unreviewed report;
        # rejecting would burn a round on nothing. Approve, and say why.
        logger.warning("verdict call failed, approving without review: %s", exc)
        return {
            "critic_approved": True,
            "critic_feedback": f"The verdict step failed ({exc}); the draft was not reviewed.",
            "missing": [],
            "unsupported": [],
        }

    return {
        "critic_approved": result.approved,
        "critic_feedback": result.feedback,
        "missing": result.missing,
        "unsupported": result.unsupported,
    }


# -------------------------------------------------------------------- critic feedback


def _dedupe(items: List[str]) -> List[str]:
    return list(dict.fromkeys(i.strip() for i in items if i and i.strip()))


def critic_feedback_node(state: ResearchState) -> dict:
    """Normalize the verdict into the fields the planner and the UI consume."""
    iteration = state.get("iteration", 1)

    if config.FORCE_CRITIC_REJECT_ONCE and iteration == 1:
        # Test hook, so the loop-back path can be exercised deterministically.
        logger.info("FORCE_CRITIC_REJECT_ONCE active: rejecting round 1 draft")
        return {
            "critic_approved": False,
            "critic_feedback": "Forced rejection (FORCE_CRITIC_REJECT_ONCE) to exercise the loop-back path.",
            "missing": [f"What are the main criticisms or counterarguments regarding {state['topic']}?"],
            "unsupported": [f"That the consensus view of {state['topic']} is settled."],
        }

    approved = bool(state.get("critic_approved"))
    missing = _dedupe(state.get("missing", []))
    unsupported = _dedupe(state.get("unsupported", []))

    if approved and (missing or unsupported):
        # The model sometimes approves while still listing problems. The lists
        # are the substantive answer, so they win over the boolean.
        logger.info("critic approved while listing problems; treating as not approved")
        approved = False

    logger.info(
        "critic verdict on round %s: approved=%s, %s missing, %s unsupported",
        iteration,
        approved,
        len(missing),
        len(unsupported),
    )
    return {
        "critic_approved": approved,
        "missing": [] if approved else missing,
        "unsupported": [] if approved else unsupported,
    }


def route_after_critic_feedback(state: ResearchState) -> str:
    if state.get("critic_approved"):
        return "finalize"
    if state.get("iteration", 0) >= state.get("max_iterations", config.MAX_ITERATIONS):
        logger.info("iteration cap reached; finalizing without critic approval")
        return "finalize"
    return "planner"
