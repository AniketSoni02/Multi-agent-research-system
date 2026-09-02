"""The research spine: planner, researcher, synthesizer, finalize."""

import logging
from typing import List

from pydantic import BaseModel, Field

from backend import config
from backend.graph import prompts
from backend.graph.nodes.common import ask, call, get_llm
from backend.graph.state import Finding, ResearcherInput, ResearchState
from backend.tools import web_search

logger = logging.getLogger(__name__)


class PlannerOutput(BaseModel):
    subtasks: List[str] = Field(description="The research subtasks, each self-contained.")


# --------------------------------------------------------------------------- planner


async def planner_node(state: ResearchState) -> dict:
    iteration = state.get("iteration", 0)
    seeded = state.get("complexity")

    if iteration == 0 and isinstance(seeded, int) and seeded > 0:
        # The router already judged the scope, so word that many subtasks rather
        # than re-deciding and risking a different answer.
        prompt = prompts.PLANNER_SEEDED.format(
            topic=state["topic"],
            n=seeded,
            s="" if seeded == 1 else "s",
            reason=state.get("route_reason", "") or "(not recorded)",
        )
    elif iteration == 0:
        prompt = prompts.PLANNER_FIRST_ROUND.format(
            topic=state["topic"], hi=config.MAX_SUBTASKS
        )
    else:
        researched = sorted({f["subtask"] for f in state.get("researcher_findings", [])})
        prompt = prompts.PLANNER_GAP_ROUND.format(
            topic=state["topic"],
            prior_subtasks="\n".join(f"- {s}" for s in researched) or "(none)",
            critic_feedback=state.get("critic_feedback", "") or "(none)",
            missing="\n".join(f"- {m}" for m in state.get("missing", [])) or "(none listed)",
            unsupported="\n".join(f"- {u}" for u in state.get("unsupported", [])) or "(none listed)",
        )

    result: PlannerOutput = await call(get_llm().with_structured_output(PlannerOutput), prompt)

    subtasks = [s.strip() for s in result.subtasks if s and s.strip()]
    if not subtasks:
        # Never fan out to zero researchers; the graph would reach the synthesizer
        # with nothing new to work from.
        subtasks = [state["topic"]]
    subtasks = subtasks[: config.MAX_SUBTASKS]

    logger.info("planner round %s produced %s subtasks", iteration + 1, len(subtasks))
    return {"subtasks": subtasks, "iteration": iteration + 1}


# ------------------------------------------------------------------------ researcher


async def researcher_node(state: ResearcherInput) -> dict:
    subtask = state["subtask"]

    web_results = await web_search.search_async(subtask, config.WEB_RESULTS_PER_SUBTASK)
    web_context = web_search.format_results(web_results, start_index=1)

    answer = await ask(
        prompts.RESEARCHER.format(
            topic=state["topic"],
            subtask=subtask,
            web_context=web_context,
        )
    )

    sources = list(dict.fromkeys(r["url"] for r in web_results if r["url"]))
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


def format_findings(findings: List[Finding]) -> str:
    blocks = []
    for f in findings:
        sources = "\n".join(f"  - {s}" for s in f["sources"]) or "  - (none)"
        blocks.append(
            f"### Subtask (round {f['iteration']}): {f['subtask']}\n{f['content']}\n\nSources:\n{sources}"
        )
    return "\n\n".join(blocks)


async def synthesizer_node(state: ResearchState) -> dict:
    findings = state.get("researcher_findings", [])
    formatted = format_findings(findings)

    if state.get("iteration", 1) > 1 and state.get("draft_report"):
        prompt = prompts.SYNTHESIZER_REVISION.format(
            topic=state["topic"],
            draft_report=state["draft_report"],
            critic_feedback=state.get("critic_feedback", "") or "(none)",
            findings=formatted,
        )
    else:
        prompt = prompts.SYNTHESIZER_FIRST.format(topic=state["topic"], findings=formatted)

    draft = await ask(prompt)
    logger.info("synthesizer merged %s findings into a %s-char draft", len(findings), len(draft))

    # The synthesizer opens each review round, so it clears the critic's
    # scratchpad here: evidence gathered against the previous draft must not be
    # carried into the verdict on this one.
    return {
        "draft_report": draft,
        "critic_messages": [],
        "critic_tool_calls": 0,
        "tool_evidence": [],
        "evidence_summary": "",
    }


# -------------------------------------------------------------------------- finalize


async def finalize_node(state: ResearchState) -> dict:
    report = state.get("draft_report", "")
    approved = bool(state.get("critic_approved"))

    if not approved:
        # The report shipped because the iteration cap ran out, not because the
        # critic signed it off. Say so in the report rather than implying approval.
        rounds = state.get("max_iterations", config.MAX_ITERATIONS)
        note = (
            f"> **Note:** finalized after reaching the review limit of {rounds} "
            f"round{'' if rounds == 1 else 's'} without full Critic approval.\n"
        )
        missing = state.get("missing", [])
        unsupported = state.get("unsupported", [])
        if missing:
            note += "> \n> Still missing:\n"
            note += "".join(f"> - {m}\n" for m in missing)
        if unsupported:
            note += "> \n> Claims the evidence did not support:\n"
            note += "".join(f"> - {u}\n" for u in unsupported)
        report = f"{note}\n{report}"

    return {"final_report": report, "approved": approved}
