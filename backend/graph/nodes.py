"""The five graph nodes: planner, researcher, synthesizer, critic, finalize.

Every node is async and every Gemini call is awaited. That matters for the
researcher: the Send() fan-out only runs branches concurrently if their bodies
yield control, so a blocking call here would quietly serialize the whole round.
"""

import logging
from typing import List, Optional

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from backend import config
from backend.graph import prompts
from backend.graph.state import Finding, ResearcherInput, ResearchState
from backend.tools import web_search

logger = logging.getLogger(__name__)

_llm: Optional[ChatGoogleGenerativeAI] = None


def get_llm() -> ChatGoogleGenerativeAI:
    global _llm
    if _llm is None:
        _llm = ChatGoogleGenerativeAI(
            model=config.CHAT_MODEL,
            google_api_key=config.require_api_key(),
        )
    return _llm


class PlannerOutput(BaseModel):
    subtasks: List[str] = Field(description="The research subtasks, each self-contained.")


class CriticOutput(BaseModel):
    approved: bool = Field(description="True only if the report is comprehensive and well-supported.")
    feedback: str = Field(description="A short review explaining the verdict.")
    gaps: List[str] = Field(
        default_factory=list,
        description="Concrete researchable questions for what is missing. Empty when approved.",
    )


def _text_of(content) -> str:
    """Flatten a message's content to plain text.

    Gemini 3.x returns a list of content blocks (text plus a thought signature)
    rather than a string, so stringifying `content` directly would drop the repr
    of the whole block list into the report.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(p for p in parts if p).strip()
    return str(content)


async def _ask(prompt: str) -> str:
    response = await get_llm().ainvoke([HumanMessage(content=prompt)])
    return _text_of(response.content)


# --------------------------------------------------------------------------- planner


async def planner_node(state: ResearchState) -> dict:
    iteration = state.get("iteration", 0)

    if iteration == 0:
        prompt = prompts.PLANNER_FIRST_ROUND.format(topic=state["topic"], lo=3, hi=5)
    else:
        researched = sorted({f["subtask"] for f in state.get("researcher_findings", [])})
        prompt = prompts.PLANNER_GAP_ROUND.format(
            topic=state["topic"],
            prior_subtasks="\n".join(f"- {s}" for s in researched) or "(none)",
            critic_feedback=state.get("critic_feedback", "") or "(none)",
            gaps="\n".join(f"- {g}" for g in state.get("gaps", [])) or "(none listed)",
        )

    planner = get_llm().with_structured_output(PlannerOutput)
    result: PlannerOutput = await planner.ainvoke(prompt)

    subtasks = [s.strip() for s in result.subtasks if s and s.strip()]
    if not subtasks:
        # Never fan out to zero researchers; the graph would reach the synthesizer
        # with nothing new to work from.
        subtasks = [state["topic"]]

    logger.info("planner round %s produced %s subtasks", iteration + 1, len(subtasks))
    return {"subtasks": subtasks, "iteration": iteration + 1}


# ------------------------------------------------------------------------ researcher


async def researcher_node(state: ResearcherInput) -> dict:
    subtask = state["subtask"]

    results = await web_search.search_async(subtask, config.WEB_RESULTS_PER_SUBTASK)
    web_context = web_search.format_results(results, start_index=1)

    answer = await _ask(
        prompts.RESEARCHER.format(
            topic=state["topic"],
            subtask=subtask,
            web_context=web_context,
        )
    )

    sources = list(dict.fromkeys(r["url"] for r in results if r["url"]))
    finding: Finding = {
        "subtask": subtask,
        "content": answer,
        "sources": sources,
        "iteration": state["iteration"],
    }
    # A one-item list: operator.add on the state field appends it alongside the
    # findings from every sibling branch and every earlier round.
    return {"researcher_findings": [finding]}


# ----------------------------------------------------------------------- synthesizer


def _format_findings(findings: List[Finding]) -> str:
    blocks = []
    for f in findings:
        sources = "\n".join(f"  - {s}" for s in f["sources"]) or "  - (none)"
        blocks.append(
            f"### Subtask (round {f['iteration']}): {f['subtask']}\n{f['content']}\n\nSources:\n{sources}"
        )
    return "\n\n".join(blocks)


async def synthesizer_node(state: ResearchState) -> dict:
    findings = state.get("researcher_findings", [])
    formatted = _format_findings(findings)

    if state.get("iteration", 1) > 1 and state.get("draft_report"):
        prompt = prompts.SYNTHESIZER_REVISION.format(
            topic=state["topic"],
            draft_report=state["draft_report"],
            critic_feedback=state.get("critic_feedback", "") or "(none)",
            findings=formatted,
        )
    else:
        prompt = prompts.SYNTHESIZER_FIRST.format(topic=state["topic"], findings=formatted)

    draft = await _ask(prompt)
    logger.info("synthesizer merged %s findings into a %s-char draft", len(findings), len(draft))
    return {"draft_report": draft}


# ---------------------------------------------------------------------------- critic


async def critic_node(state: ResearchState) -> dict:
    iteration = state.get("iteration", 1)

    if config.FORCE_CRITIC_REJECT_ONCE and iteration == 1:
        # Test hook, so the loop-back path can be exercised deterministically.
        logger.info("FORCE_CRITIC_REJECT_ONCE active: rejecting round 1 draft")
        return {
            "critic_approved": False,
            "critic_feedback": "Forced rejection (FORCE_CRITIC_REJECT_ONCE) to exercise the loop-back path.",
            "gaps": [
                f"What are the main criticisms or counterarguments regarding {state['topic']}?",
                f"What concrete real-world examples illustrate {state['topic']}?",
            ],
        }

    subtasks = sorted({f["subtask"] for f in state.get("researcher_findings", [])})
    critic = get_llm().with_structured_output(CriticOutput)
    result: CriticOutput = await critic.ainvoke(
        prompts.CRITIC.format(
            topic=state["topic"],
            subtasks="\n".join(f"- {s}" for s in subtasks) or "(none)",
            draft_report=state.get("draft_report", ""),
            iteration=iteration,
            max_iterations=state.get("max_iterations", config.MAX_ITERATIONS),
        )
    )

    logger.info("critic verdict on round %s: approved=%s", iteration, result.approved)
    return {
        "critic_approved": result.approved,
        "critic_feedback": result.feedback,
        "gaps": [] if result.approved else result.gaps,
    }


# -------------------------------------------------------------------------- finalize


async def finalize_node(state: ResearchState) -> dict:
    report = state.get("draft_report", "")

    if not state.get("critic_approved"):
        # The report shipped because the iteration cap ran out, not because the
        # critic signed it off. Say so in the report rather than implying approval.
        rounds = state.get("max_iterations", config.MAX_ITERATIONS)
        note = (
            f"> **Note:** finalized after reaching the review limit of {rounds} "
            f"round{'' if rounds == 1 else 's'} without full Critic approval. "
            "Remaining concerns:\n"
        )
        for gap in state.get("gaps", []):
            note += f"> - {gap}\n"
        report = f"{note}\n{report}"

    return {"final_report": report}
