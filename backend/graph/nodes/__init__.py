"""Graph nodes, grouped by the stage of the pipeline they belong to.

Re-exported here so build.py wires the topology from one flat import.
"""

from backend.graph.nodes.common import ask, get_llm, text_of
from backend.graph.nodes.critic import (
    CriticVerdict,
    critic_feedback_node,
    critic_node,
    critic_tools_node,
    route_after_critic,
    route_after_critic_feedback,
    tool_results_node,
    verdict_node,
)
from backend.graph.nodes.research import (
    PlannerOutput,
    finalize_node,
    format_findings,
    planner_node,
    researcher_node,
    synthesizer_node,
)
from backend.graph.nodes.routing import (
    RouteDecision,
    direct_answer_node,
    route_after_router,
    router_node,
)

__all__ = [
    "ask",
    "get_llm",
    "text_of",
    "RouteDecision",
    "router_node",
    "route_after_router",
    "direct_answer_node",
    "PlannerOutput",
    "planner_node",
    "researcher_node",
    "synthesizer_node",
    "finalize_node",
    "format_findings",
    "CriticVerdict",
    "critic_node",
    "critic_tools_node",
    "route_after_critic",
    "tool_results_node",
    "verdict_node",
    "critic_feedback_node",
    "route_after_critic_feedback",
]
