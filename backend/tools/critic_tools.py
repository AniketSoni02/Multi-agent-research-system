"""The three tools the Critic can call while reviewing a draft.

The argument schemas are declared as bare Pydantic models and dispatched by name
in critic_tools_node rather than being wired through a prebuilt ToolNode. Two
reasons: each tool also needs graph state (the draft, the findings, the session
id) that the model must not get to choose, and the five-call ceiling has to be
enforced at dispatch time, where the pending calls are actually known.
"""

import logging
from typing import List

from pydantic import BaseModel, Field

from backend import config
from backend.graph import prompts
from backend.graph.state import Finding
from backend.tools import retriever, web_search

logger = logging.getLogger(__name__)


class CheckCoverage(BaseModel):
    """Check whether the draft report actually addresses one of the planned subtasks."""

    subtask: str = Field(description="The planned research subtask to check the draft against.")


class VerifyClaim(BaseModel):
    """Look a factual claim up in the session's knowledge base, falling back to web search."""

    claim: str = Field(description="The specific factual claim to look up, stated in full.")


class CheckGrounding(BaseModel):
    """Check whether one statement in the draft is supported by the researchers' findings."""

    statement: str = Field(description="The statement from the draft to trace back to the findings.")


TOOL_SCHEMAS = [CheckCoverage, VerifyClaim, CheckGrounding]


async def check_coverage(subtask: str, draft_report: str) -> str:
    from backend.graph.nodes.common import ask

    if not draft_report.strip():
        return "absent -- there is no draft to check."
    return await ask(
        prompts.CHECK_COVERAGE.format(subtask=subtask, draft_report=draft_report)
    )


async def verify_claim(claim: str, session_id: str) -> str:
    """Retrieval only, deliberately: no LLM sits between the sources and the verdict.

    The knowledge base holds the researchers' own briefings, so this checks a
    claim against what the run actually established before spending a web search
    on it.
    """
    docs = await retriever.retrieve_async(session_id, claim, k=config.RAG_K)
    if docs:
        block, _ = retriever.format_documents(docs)
        return f"Knowledge base evidence for {claim!r}:\n{block}"

    results = await web_search.search_async(claim, config.WEB_RESULTS_PER_SUBTASK)
    if not results:
        return (
            f"No evidence found for {claim!r}: the knowledge base has nothing on it and "
            "web search returned no results."
        )
    return f"Web evidence for {claim!r} (knowledge base had nothing):\n{web_search.format_results(results)}"


async def check_grounding(statement: str, findings: List[Finding]) -> str:
    from backend.graph.nodes.common import ask
    from backend.graph.nodes.research import format_findings

    if not findings:
        return "unsupported -- there are no researcher findings to trace the statement back to."
    return await ask(
        prompts.CHECK_GROUNDING.format(statement=statement, findings=format_findings(findings))
    )
