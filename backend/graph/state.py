"""Shared graph state and the per-branch payload used by the Send() fan-out."""

import operator
from typing import Annotated, List, Optional, TypedDict


class Finding(TypedDict):
    """One researcher's answer to one subtask."""

    subtask: str
    content: str
    sources: List[str]
    iteration: int


class ResearchState(TypedDict, total=False):
    session_id: str
    topic: str

    # Rewritten by the planner on every round. On a loop-back these are the
    # gap-focused follow-ups, not a repeat of the first round's subtasks.
    subtasks: List[str]

    iteration: int
    max_iterations: int

    # operator.add is append-only, so findings accumulate across every round and
    # each one carries the iteration it came from. The synthesizer re-reads the
    # whole set on a revision pass, which means later rounds never lose earlier
    # research.
    researcher_findings: Annotated[List[Finding], operator.add]

    draft_report: str
    critic_feedback: str
    critic_approved: bool
    gaps: List[str]
    final_report: Optional[str]


class ResearcherInput(TypedDict):
    """Payload handed to each parallel researcher branch via Send()."""

    topic: str
    subtask: str
    iteration: int


def initial_state(session_id: str, topic: str, max_iterations: int) -> ResearchState:
    return {
        "session_id": session_id,
        "topic": topic,
        "subtasks": [],
        "iteration": 0,
        "max_iterations": max_iterations,
        "researcher_findings": [],
        "draft_report": "",
        "critic_feedback": "",
        "critic_approved": False,
        "gaps": [],
        "final_report": None,
    }
