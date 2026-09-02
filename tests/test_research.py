"""The research spine: planner clamping, RAG fallback, citation numbering, finalize."""

import pytest

from backend import config
from backend.graph.nodes.research import (
    PlannerOutput,
    finalize_node,
    format_findings,
    planner_node,
    researcher_node,
)


class TestPlannerNode:
    @pytest.mark.asyncio
    async def test_honours_a_small_subtask_count(self, fake_llm):
        fake_llm(structured={"PlannerOutput": PlannerOutput(subtasks=["one"])})
        result = await planner_node({"topic": "t", "iteration": 0})
        assert result["subtasks"] == ["one"]
        assert result["iteration"] == 1

    @pytest.mark.asyncio
    async def test_clamps_an_overlong_plan(self, fake_llm):
        too_many = [f"s{i}" for i in range(9)]
        fake_llm(structured={"PlannerOutput": PlannerOutput(subtasks=too_many)})
        result = await planner_node({"topic": "t", "iteration": 0})
        assert len(result["subtasks"]) == config.MAX_SUBTASKS

    @pytest.mark.asyncio
    async def test_never_fans_out_to_zero_researchers(self, fake_llm):
        fake_llm(structured={"PlannerOutput": PlannerOutput(subtasks=["", "   "])})
        result = await planner_node({"topic": "the topic", "iteration": 0})
        assert result["subtasks"] == ["the topic"]

    @pytest.mark.asyncio
    async def test_a_seeded_score_asks_for_exactly_that_many_subtasks(self, fake_llm):
        llm = fake_llm(structured={"PlannerOutput": PlannerOutput(subtasks=["a", "b"])})
        await planner_node(
            {"topic": "t", "iteration": 0, "complexity": 2, "route_reason": "two angles"}
        )
        prompt = llm.prompts[0]
        assert "exactly 2 subtasks" in prompt
        assert "two angles" in prompt

    @pytest.mark.asyncio
    async def test_an_unseeded_round_judges_scope_itself(self, fake_llm):
        llm = fake_llm(structured={"PlannerOutput": PlannerOutput(subtasks=["a"])})
        await planner_node({"topic": "t", "iteration": 0, "complexity": None})
        prompt = llm.prompts[0]
        assert "First judge how much this topic actually demands" in prompt

    @pytest.mark.asyncio
    async def test_a_seeded_count_of_one_reads_naturally(self, fake_llm):
        llm = fake_llm(structured={"PlannerOutput": PlannerOutput(subtasks=["a"])})
        await planner_node({"topic": "t", "iteration": 0, "complexity": 1})
        assert "exactly 1 subtask" in llm.prompts[0]

    @pytest.mark.asyncio
    async def test_gap_round_prompt_carries_both_problem_lists(self, fake_llm):
        llm = fake_llm(structured={"PlannerOutput": PlannerOutput(subtasks=["new"])})
        # A loop-back must not be seeded with round one's score.
        await planner_node(
            {
                "topic": "t",
                "iteration": 1,
                "complexity": 3,
                "researcher_findings": [
                    {"subtask": "old", "content": "c", "sources": [], "iteration": 1}
                ],
                "critic_feedback": "thin",
                "missing": ["what about cost"],
                "unsupported": ["X causes Y"],
            }
        )
        prompt = llm.prompts[0]
        assert "what about cost" in prompt
        assert "X causes Y" in prompt
        assert "old" in prompt
        assert "exactly 3" not in prompt


class TestResearcherNode:
    @pytest.mark.asyncio
    async def test_searches_the_web_for_its_subtask(self, fake_llm, monkeypatch):
        fake_llm(text="briefing")
        from backend.tools import web_search

        searched = []

        async def search(query, n):
            searched.append(query)
            return [{"title": "T", "url": "https://e.com", "snippet": "s"}]

        monkeypatch.setattr(web_search, "search_async", search)

        result = await researcher_node(
            {"session_id": "s", "topic": "t", "subtask": "sub", "iteration": 1}
        )
        assert searched == ["sub"]
        assert result["researcher_findings"][0]["sources"] == ["https://e.com"]
        assert result["researcher_findings"][0]["iteration"] == 1

    @pytest.mark.asyncio
    async def test_citations_are_numbered_from_one(self, fake_llm, monkeypatch):
        llm = fake_llm(text="briefing")
        from backend.tools import web_search

        async def search(*_a, **_kw):
            return [
                {"title": "First", "url": "https://a.com", "snippet": "s"},
                {"title": "Second", "url": "https://b.com", "snippet": "s"},
            ]

        monkeypatch.setattr(web_search, "search_async", search)

        await researcher_node({"session_id": "s", "topic": "t", "subtask": "sub", "iteration": 1})
        prompt = llm.prompts[0]
        assert "[1] First" in prompt
        assert "[2] Second" in prompt

    @pytest.mark.asyncio
    async def test_duplicate_urls_are_cited_once(self, fake_llm, monkeypatch):
        fake_llm(text="briefing")
        from backend.tools import web_search

        async def search(*_a, **_kw):
            return [
                {"title": "A", "url": "https://a.com", "snippet": "s"},
                {"title": "A again", "url": "https://a.com", "snippet": "s"},
                {"title": "B", "url": "", "snippet": "s"},
            ]

        monkeypatch.setattr(web_search, "search_async", search)

        result = await researcher_node(
            {"session_id": "s", "topic": "t", "subtask": "sub", "iteration": 1}
        )
        assert result["researcher_findings"][0]["sources"] == ["https://a.com"]

    @pytest.mark.asyncio
    async def test_a_search_that_returns_nothing_still_produces_a_finding(
        self, fake_llm, no_network
    ):
        """Search failure degrades the briefing; it must not fail the round."""
        fake_llm(text="briefing")
        result = await researcher_node(
            {"session_id": "s", "topic": "t", "subtask": "sub", "iteration": 1}
        )
        assert result["researcher_findings"][0]["content"] == "briefing"
        assert result["researcher_findings"][0]["sources"] == []


class TestFinalizeNode:
    @pytest.mark.asyncio
    async def test_an_approved_report_ships_unchanged(self):
        result = await finalize_node({"draft_report": "# Report", "critic_approved": True})
        assert result["final_report"] == "# Report"
        assert result["approved"] is True

    @pytest.mark.asyncio
    async def test_an_unapproved_report_is_prefixed_with_what_is_outstanding(self):
        result = await finalize_node(
            {
                "draft_report": "# Report",
                "critic_approved": False,
                "max_iterations": 3,
                "missing": ["what about cost"],
                "unsupported": ["X causes Y"],
            }
        )
        assert result["approved"] is False
        assert result["final_report"].startswith("> **Note:**")
        assert "what about cost" in result["final_report"]
        assert "X causes Y" in result["final_report"]
        assert "# Report" in result["final_report"]


class TestFormatFindings:
    def test_labels_each_finding_with_its_round_and_sources(self):
        block = format_findings(
            [{"subtask": "s1", "content": "c1", "sources": ["u1"], "iteration": 2}]
        )
        assert "### Subtask (round 2): s1" in block
        assert "- u1" in block

    def test_says_none_when_a_finding_cited_nothing(self):
        block = format_findings([{"subtask": "s1", "content": "c1", "sources": [], "iteration": 1}])
        assert "(none)" in block
