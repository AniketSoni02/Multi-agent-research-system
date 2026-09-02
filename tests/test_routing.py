"""Routing decisions: the pure functions that steer the graph."""

import pytest
from langchain_core.messages import AIMessage

from backend import config
from backend.graph.build import continue_to_researchers
from backend.graph.nodes.critic import route_after_critic, route_after_critic_feedback
from backend.graph.nodes.routing import (
    ComplexityAssessment,
    route_after_router,
    router_node,
)
from tests.conftest import tool_call


class TestRouteAfterRouter:
    def test_direct_goes_to_direct_answer(self):
        assert route_after_router({"mode": "direct"}) == "direct_answer"

    def test_research_goes_to_planner(self):
        assert route_after_router({"mode": "research"}) == "planner"

    def test_unset_mode_takes_the_research_path(self):
        assert route_after_router({}) == "planner"


class TestRouterNode:
    """The reported bug: a simple question ran the whole research pipeline."""

    @pytest.mark.asyncio
    async def test_a_settled_question_is_routed_direct_without_any_api_call(self, fake_llm):
        llm = fake_llm()  # nothing scripted: any API call would raise
        result = await router_node({"topic": "what is the capital of france"})

        assert result["mode"] == "direct"
        assert result["complexity"] == 0
        # This is the regression guard. Routing must not depend on the API being
        # reachable, or an exhausted quota sends simple questions to research.
        assert llm.calls == 0

    @pytest.mark.asyncio
    async def test_an_obvious_research_topic_also_skips_the_routing_call(self, fake_llm):
        llm = fake_llm()
        result = await router_node({"topic": "compare solar and wind power"})

        assert result["mode"] == "research"
        # No score: the planner judges scope itself, as it would anyway.
        assert result["complexity"] is None
        assert llm.calls == 0

    @pytest.mark.asyncio
    async def test_an_ambiguous_query_is_scored_by_the_model(self, fake_llm):
        llm = fake_llm(
            structured={"ComplexityAssessment": ComplexityAssessment(complexity=3, reason="broad")}
        )
        result = await router_node({"topic": "how does photosynthesis work"})

        assert result["mode"] == "research"
        assert result["complexity"] == 3
        assert result["route_reason"] == "broad"
        assert llm.calls == 1

    @pytest.mark.asyncio
    async def test_a_zero_score_from_the_model_takes_the_direct_path(self, fake_llm):
        fake_llm(
            structured={"ComplexityAssessment": ComplexityAssessment(complexity=0, reason="simple")}
        )
        result = await router_node({"topic": "is intermittent fasting effective"})
        assert result["mode"] == "direct"
        assert result["complexity"] == 0

    @pytest.mark.asyncio
    async def test_an_over_range_score_is_clamped(self, fake_llm):
        fake_llm(
            structured={"ComplexityAssessment": ComplexityAssessment(complexity=5, reason="huge")}
        )
        result = await router_node({"topic": "how does photosynthesis work"})
        assert result["complexity"] <= config.MAX_SUBTASKS

    @pytest.mark.asyncio
    async def test_falls_back_to_research_when_the_model_is_unreachable(self, fake_llm):
        fake_llm()  # nothing scripted, so the structured call raises
        result = await router_node({"topic": "how does photosynthesis work"})
        assert result["mode"] == "research"
        assert result["complexity"] is None


class TestRouteAfterCritic:
    def test_no_messages_means_no_evidence_to_gather(self):
        assert route_after_critic({"critic_messages": []}) == "tool_results"

    def test_a_reply_without_tool_calls_ends_the_loop(self):
        state = {"critic_messages": [AIMessage(content="I am satisfied")], "critic_tool_calls": 0}
        assert route_after_critic(state) == "tool_results"

    def test_pending_tool_calls_within_budget_keep_looping(self):
        reply = AIMessage(content="", tool_calls=[tool_call("VerifyClaim", {"claim": "x"}, "1")])
        state = {"critic_messages": [reply], "critic_tool_calls": 0}
        assert route_after_critic(state) == "critic_tools"

    def test_the_cap_ends_the_loop_even_with_calls_pending(self):
        reply = AIMessage(content="", tool_calls=[tool_call("VerifyClaim", {"claim": "x"}, "1")])
        state = {"critic_messages": [reply], "critic_tool_calls": config.MAX_CRITIC_TOOL_CALLS}
        assert route_after_critic(state) == "tool_results"


class TestRouteAfterCriticFeedback:
    def test_approval_finalizes(self):
        assert route_after_critic_feedback(
            {"critic_approved": True, "iteration": 1, "max_iterations": 3}
        ) == "finalize"

    def test_rejection_with_rounds_left_loops_back(self):
        assert route_after_critic_feedback(
            {"critic_approved": False, "iteration": 1, "max_iterations": 3}
        ) == "planner"

    def test_the_iteration_cap_finalizes_without_approval(self):
        assert route_after_critic_feedback(
            {"critic_approved": False, "iteration": 3, "max_iterations": 3}
        ) == "finalize"


class TestContinueToResearchers:
    def test_one_send_per_subtask_each_carrying_the_session(self):
        sends = continue_to_researchers(
            {"session_id": "s1", "topic": "t", "subtasks": ["a", "b", "c"], "iteration": 1}
        )
        assert [s.node for s in sends] == ["researcher"] * 3
        assert [s.arg["subtask"] for s in sends] == ["a", "b", "c"]
        # Without session_id the branch cannot read or write the vector store.
        assert all(s.arg["session_id"] == "s1" for s in sends)
        assert all(s.arg["iteration"] == 1 for s in sends)

    def test_a_single_subtask_still_fans_out(self):
        sends = continue_to_researchers(
            {"session_id": "s1", "topic": "t", "subtasks": ["only"], "iteration": 1}
        )
        assert len(sends) == 1
