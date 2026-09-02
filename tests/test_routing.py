"""Routing decisions: the pure functions that steer the graph."""

import pytest
from langchain_core.messages import AIMessage

from backend import config
from backend.graph.build import continue_to_researchers
from backend.graph.nodes.critic import route_after_critic, route_after_critic_feedback
from backend.graph.nodes.routing import RouteDecision, route_after_router, router_node
from tests.conftest import tool_call


class TestRouteAfterRouter:
    def test_direct_goes_to_direct_answer(self):
        assert route_after_router({"mode": "direct"}) == "direct_answer"

    def test_research_goes_to_planner(self):
        assert route_after_router({"mode": "research"}) == "planner"

    def test_unset_mode_takes_the_research_path(self):
        assert route_after_router({}) == "planner"


class TestRouterNode:
    @pytest.mark.asyncio
    async def test_uses_the_models_decision(self, fake_llm):
        fake_llm(structured={"RouteDecision": RouteDecision(mode="direct", reason="trivial")})
        result = await router_node({"topic": "what is 2+2"})
        assert result["mode"] == "direct"
        assert result["route_reason"] == "trivial"

    @pytest.mark.asyncio
    async def test_falls_back_to_research_when_the_router_fails(self, fake_llm, monkeypatch):
        fake_llm()  # no scripted RouteDecision, so with_structured_output raises
        result = await router_node({"topic": "anything"})
        assert result["mode"] == "research"


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
