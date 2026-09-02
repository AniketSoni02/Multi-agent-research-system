"""Shared graph state and the per-branch payload used by the Send() fan-out."""

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage


class Finding(TypedDict):
    """One researcher's answer to one subtask."""

    subtask: str
    content: str
    sources: List[str]
    iteration: int


class ToolEvidence(TypedDict):
    """One critic tool call and what it returned.

    This is what makes a rejection accountable: every entry in `missing` and
    `unsupported` is supposed to trace back to one of these rows rather than to
    an unaided opinion about the draft.
    """

    tool: str
    args: Dict[str, Any]
    result: str
    iteration: int


class ResearchState(TypedDict, total=False):
    session_id: str
    topic: str

    # Set by the router. "direct" skips the whole research pipeline for a
    # question one LLM call can answer.
    mode: str
    route_reason: str

    # Rewritten by the planner on every round. On a loop-back these are the
    # gap-focused follow-ups, not a repeat of the first round's subtasks.
    subtasks: List[str]
    complexity: str

    iteration: int
    max_iterations: int

    # operator.add is append-only, so findings accumulate across every round and
    # each one carries the iteration it came from. The synthesizer re-reads the
    # whole set on a revision pass, which means later rounds never lose earlier
    # research.
    researcher_findings: Annotated[List[Finding], operator.add]

    draft_report: str

    # The critic's scratchpad for one review round. Deliberately reducer-free:
    # every critic node returns the whole list, and the synthesizer zeroes all
    # three fields at the top of each round so evidence from round 1 is not
    # re-judged in round 2.
    critic_messages: List[BaseMessage]
    critic_tool_calls: int
    tool_evidence: List[ToolEvidence]
    evidence_summary: str

    # The verdict, split the way the critic reports it: coverage gaps are
    # something to go research, unsupported claims are something to cut or
    # qualify, and they lead the planner in different directions.
    critic_approved: bool
    critic_feedback: str
    missing: List[str]
    unsupported: List[str]

    final_report: Optional[str]

    # Whether the report shipped with the critic's sign-off. Set explicitly so
    # the UI does not have to infer it from the report's text.
    approved: bool


class ResearcherInput(TypedDict):
    """Payload handed to each parallel researcher branch via Send()."""

    session_id: str
    topic: str
    subtask: str
    iteration: int


def initial_state(session_id: str, topic: str, max_iterations: int) -> ResearchState:
    return {
        "session_id": session_id,
        "topic": topic,
        "mode": "",
        "route_reason": "",
        "subtasks": [],
        "complexity": "",
        "iteration": 0,
        "max_iterations": max_iterations,
        "researcher_findings": [],
        "draft_report": "",
        "critic_messages": [],
        "critic_tool_calls": 0,
        "tool_evidence": [],
        "evidence_summary": "",
        "critic_approved": False,
        "critic_feedback": "",
        "missing": [],
        "unsupported": [],
        "final_report": None,
        "approved": False,
    }
