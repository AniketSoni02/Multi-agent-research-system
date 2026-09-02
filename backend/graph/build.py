"""Graph topology.

    START -> router
    router          --direct--> direct_answer -> END
    router          --research--> planner
    planner         --Send() one per subtask--> researcher x N
    researcher      -> synthesizer                    (the join barrier)
    synthesizer     -> critic
    critic          --wants tools, budget left--> critic_tools -> critic
    critic          --done, or budget spent--> tool_results
    tool_results    -> verdict -> critic_feedback
    critic_feedback --rejected, rounds left--> planner
    critic_feedback --approved, or cap hit--> finalize -> END

Two bounded cycles: the outer review loop, capped by MAX_ITERATIONS, and the
critic's inner tool loop, capped by MAX_CRITIC_TOOL_CALLS.
"""

import logging
from typing import List

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from backend.graph.nodes import (
    critic_feedback_node,
    critic_node,
    critic_tools_node,
    direct_answer_node,
    finalize_node,
    planner_node,
    researcher_node,
    route_after_critic,
    route_after_critic_feedback,
    route_after_router,
    router_node,
    synthesizer_node,
    tool_results_node,
    verdict_node,
)
from backend.graph.state import ResearchState

logger = logging.getLogger(__name__)


def continue_to_researchers(state: ResearchState) -> List[Send]:
    """Fan out one researcher branch per subtask, running them in parallel."""
    return [
        Send(
            "researcher",
            {
                # The branch needs this to read from and write back to the
                # session's vector store.
                "session_id": state["session_id"],
                "topic": state["topic"],
                "subtask": subtask,
                "iteration": state["iteration"],
            },
        )
        for subtask in state["subtasks"]
    ]


def build_graph():
    builder = StateGraph(ResearchState)

    builder.add_node("router", router_node)
    builder.add_node("direct_answer", direct_answer_node)
    builder.add_node("planner", planner_node)
    builder.add_node("researcher", researcher_node)
    builder.add_node("synthesizer", synthesizer_node)
    builder.add_node("critic", critic_node)
    builder.add_node("critic_tools", critic_tools_node)
    builder.add_node("tool_results", tool_results_node)
    builder.add_node("verdict", verdict_node)
    builder.add_node("critic_feedback", critic_feedback_node)
    builder.add_node("finalize", finalize_node)

    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router", route_after_router, {"direct_answer": "direct_answer", "planner": "planner"}
    )
    builder.add_edge("direct_answer", END)

    builder.add_conditional_edges("planner", continue_to_researchers, ["researcher"])
    # This single edge is the join barrier: every Send() branch must finish
    # before the synthesizer runs.
    builder.add_edge("researcher", "synthesizer")
    builder.add_edge("synthesizer", "critic")

    builder.add_conditional_edges(
        "critic", route_after_critic, {"critic_tools": "critic_tools", "tool_results": "tool_results"}
    )
    builder.add_edge("critic_tools", "critic")

    builder.add_edge("tool_results", "verdict")
    builder.add_edge("verdict", "critic_feedback")
    builder.add_conditional_edges(
        "critic_feedback",
        route_after_critic_feedback,
        {"planner": "planner", "finalize": "finalize"},
    )

    builder.add_edge("finalize", END)
    return builder.compile()


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
        logger.info("research graph compiled")
    return _graph
