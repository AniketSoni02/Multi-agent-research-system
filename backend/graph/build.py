"""Graph topology.

    START -> planner --Send() fan-out--> researcher(xN) -> synthesizer -> critic
                ^                                                          |
                +------------------ gaps found ----------------------------+
                                                                           |
                                                          approved -> finalize -> END
"""

import logging
from typing import List, Optional

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from backend.graph.nodes import (
    critic_node,
    finalize_node,
    planner_node,
    researcher_node,
    synthesizer_node,
)
from backend.graph.state import ResearchState

logger = logging.getLogger(__name__)


def continue_to_researchers(state: ResearchState) -> List[Send]:
    """Fan out one researcher branch per subtask, running them in parallel."""
    return [
        Send(
            "researcher",
            {
                "topic": state["topic"],
                "subtask": subtask,
                "iteration": state["iteration"],
            },
        )
        for subtask in state["subtasks"]
    ]


def route_after_critic(state: ResearchState) -> str:
    """Approve -> finalize; gaps -> back to the planner, up to the iteration cap.

    The cap is what guarantees termination: without it a critic that never
    approves would loop forever.
    """
    if state.get("critic_approved"):
        return "finalize"
    if state.get("iteration", 0) >= state.get("max_iterations", 3):
        logger.info("iteration cap reached; finalizing without critic approval")
        return "finalize"
    return "planner"


def build_graph():
    builder = StateGraph(ResearchState)

    builder.add_node("planner", planner_node)
    builder.add_node("researcher", researcher_node)
    builder.add_node("synthesizer", synthesizer_node)
    builder.add_node("critic", critic_node)
    builder.add_node("finalize", finalize_node)

    builder.add_edge(START, "planner")
    builder.add_conditional_edges("planner", continue_to_researchers, ["researcher"])
    # This single edge is the join barrier: every Send() branch must finish
    # before the synthesizer runs.
    builder.add_edge("researcher", "synthesizer")
    builder.add_edge("synthesizer", "critic")
    builder.add_conditional_edges(
        "critic", route_after_critic, {"planner": "planner", "finalize": "finalize"}
    )
    builder.add_edge("finalize", END)

    return builder.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
