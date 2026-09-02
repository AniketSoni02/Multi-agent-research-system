"""The critic's evidence loop: the call budget, and the verdict normalization."""

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from backend import config
from backend.graph.nodes.critic import (
    _format_evidence,
    critic_feedback_node,
    critic_node,
    critic_tools_node,
    tool_results_node,
)
from tests.conftest import tool_call


def _state_with_calls(calls, used=0, **extra):
    state = {
        "session_id": "s1",
        "topic": "t",
        "draft_report": "a draft",
        "researcher_findings": [],
        "critic_messages": [AIMessage(content="", tool_calls=calls)],
        "critic_tool_calls": used,
        "tool_evidence": [],
        "iteration": 1,
    }
    state.update(extra)
    return state


class TestCriticNode:
    @pytest.mark.asyncio
    async def test_seeds_the_transcript_on_the_first_turn(self, fake_llm):
        llm = fake_llm(tool_turns=[AIMessage(content="looks fine")])
        result = await critic_node(
            {"topic": "t", "draft_report": "d", "researcher_findings": [], "critic_messages": []}
        )
        messages = result["critic_messages"]
        # system prompt + the draft + the model's reply
        assert len(messages) == 3
        assert "at most" in messages[0].content
        assert "d" in messages[1].content

    @pytest.mark.asyncio
    async def test_continues_an_existing_transcript_without_reseeding(self, fake_llm):
        fake_llm(tool_turns=[AIMessage(content="second turn")])
        prior = [AIMessage(content="first turn"), ToolMessage(content="evidence", tool_call_id="1")]
        result = await critic_node({"topic": "t", "critic_messages": prior})
        assert len(result["critic_messages"]) == 3
        assert result["critic_messages"][0].content == "first turn"


class TestCriticToolsNode:
    @pytest.mark.asyncio
    async def test_runs_every_call_and_records_evidence(self, fake_llm, no_network):
        fake_llm(text="covered -- section 2 addresses it")
        calls = [
            tool_call("CheckCoverage", {"subtask": "a"}, "1"),
            tool_call("CheckCoverage", {"subtask": "b"}, "2"),
        ]
        result = await critic_tools_node(_state_with_calls(calls))

        assert result["critic_tool_calls"] == 2
        assert [e["tool"] for e in result["tool_evidence"]] == ["CheckCoverage"] * 2
        assert [e["args"]["subtask"] for e in result["tool_evidence"]] == ["a", "b"]
        tool_messages = [m for m in result["critic_messages"] if isinstance(m, ToolMessage)]
        assert [m.tool_call_id for m in tool_messages] == ["1", "2"]

    @pytest.mark.asyncio
    async def test_truncates_a_batch_that_would_cross_the_cap(self, fake_llm, no_network):
        fake_llm(text="covered")
        used = config.MAX_CRITIC_TOOL_CALLS - 1
        calls = [tool_call("CheckCoverage", {"subtask": str(i)}, str(i)) for i in range(3)]
        result = await critic_tools_node(_state_with_calls(calls, used=used))

        # Only the one remaining call runs...
        assert result["critic_tool_calls"] == config.MAX_CRITIC_TOOL_CALLS
        assert len(result["tool_evidence"]) == 1
        # ...but every pending call still gets an answer, or the exchange is malformed.
        tool_messages = [m for m in result["critic_messages"] if isinstance(m, ToolMessage)]
        assert len(tool_messages) == 3
        assert "budget is spent" in tool_messages[-1].content

    @pytest.mark.asyncio
    async def test_a_failing_tool_becomes_evidence_rather_than_an_exception(self, fake_llm, no_network, monkeypatch):
        fake_llm()
        from backend.tools import critic_tools

        async def boom(*_a, **_kw):
            raise RuntimeError("network down")

        monkeypatch.setattr(critic_tools, "verify_claim", boom)
        calls = [tool_call("VerifyClaim", {"claim": "x"}, "1")]
        result = await critic_tools_node(_state_with_calls(calls))
        assert "network down" in result["tool_evidence"][0]["result"]

    @pytest.mark.asyncio
    async def test_an_unknown_tool_name_does_not_crash_the_round(self, fake_llm, no_network):
        fake_llm()
        calls = [tool_call("MadeUpTool", {}, "1")]
        result = await critic_tools_node(_state_with_calls(calls))
        assert "Unknown tool" in result["tool_evidence"][0]["result"]


class TestToolResultsNode:
    def test_aggregates_evidence_and_clears_the_transcript(self):
        state = {
            "tool_evidence": [
                {"tool": "CheckCoverage", "args": {"subtask": "a"}, "result": "absent", "iteration": 1}
            ],
            "critic_messages": [AIMessage(content="x")],
        }
        result = tool_results_node(state)
        assert "CheckCoverage" in result["evidence_summary"]
        assert "absent" in result["evidence_summary"]
        # The transcript must not carry into the next round's review.
        assert result["critic_messages"] == []

    def test_says_so_when_the_critic_called_nothing(self):
        result = tool_results_node({"tool_evidence": [], "critic_messages": []})
        assert "no evidence" in result["evidence_summary"]


class TestCriticFeedbackNode:
    def test_approval_clears_both_lists(self):
        result = critic_feedback_node(
            {"critic_approved": True, "missing": [], "unsupported": [], "iteration": 1}
        )
        assert result["critic_approved"] is True
        assert result["missing"] == [] and result["unsupported"] == []

    def test_approving_while_listing_problems_is_treated_as_rejection(self):
        result = critic_feedback_node(
            {
                "critic_approved": True,
                "missing": ["What about cost?"],
                "unsupported": [],
                "iteration": 1,
            }
        )
        assert result["critic_approved"] is False
        assert result["missing"] == ["What about cost?"]

    def test_an_unsupported_claim_alone_also_blocks_approval(self):
        result = critic_feedback_node(
            {"critic_approved": True, "missing": [], "unsupported": ["X causes Y"], "iteration": 1}
        )
        assert result["critic_approved"] is False

    def test_deduplicates_and_strips(self):
        result = critic_feedback_node(
            {
                "critic_approved": False,
                "missing": ["  a  ", "a", "b", ""],
                "unsupported": [],
                "iteration": 1,
            }
        )
        assert result["missing"] == ["a", "b"]

    def test_force_reject_hook_populates_both_lists(self, monkeypatch):
        monkeypatch.setattr(config, "FORCE_CRITIC_REJECT_ONCE", True)
        result = critic_feedback_node({"topic": "solar power", "iteration": 1})
        assert result["critic_approved"] is False
        assert result["missing"] and result["unsupported"]

    def test_force_reject_hook_only_fires_on_round_one(self, monkeypatch):
        monkeypatch.setattr(config, "FORCE_CRITIC_REJECT_ONCE", True)
        result = critic_feedback_node(
            {"topic": "t", "iteration": 2, "critic_approved": True, "missing": [], "unsupported": []}
        )
        assert result["critic_approved"] is True


class TestFormatEvidence:
    def test_numbers_each_row_with_its_arguments(self):
        block = _format_evidence(
            [
                {"tool": "VerifyClaim", "args": {"claim": "c"}, "result": "found", "iteration": 1},
                {"tool": "CheckGrounding", "args": {"statement": "s"}, "result": "unsupported", "iteration": 1},
            ]
        )
        assert "[1] VerifyClaim(claim='c')" in block
        assert "[2] CheckGrounding(statement='s')" in block
