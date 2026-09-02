"""The research spine: planner clamping, RAG fallback, citation numbering, finalize."""

import pytest
from langchain_core.documents import Document

from backend import config
from backend.graph.nodes.research import (
    PlannerOutput,
    finalize_node,
    format_findings,
    planner_node,
    researcher_node,
)


def _doc(text, source):
    return Document(page_content=text, metadata={"source": source})


class TestPlannerNode:
    @pytest.mark.asyncio
    async def test_honours_a_small_subtask_count(self, fake_llm):
        fake_llm(structured={"PlannerOutput": PlannerOutput(complexity="narrow", subtasks=["one"])})
        result = await planner_node({"topic": "t", "iteration": 0})
        assert result["subtasks"] == ["one"]
        assert result["complexity"] == "narrow"
        assert result["iteration"] == 1

    @pytest.mark.asyncio
    async def test_clamps_an_overlong_plan(self, fake_llm):
        too_many = [f"s{i}" for i in range(9)]
        fake_llm(structured={"PlannerOutput": PlannerOutput(complexity="broad", subtasks=too_many)})
        result = await planner_node({"topic": "t", "iteration": 0})
        assert len(result["subtasks"]) == config.MAX_SUBTASKS

    @pytest.mark.asyncio
    async def test_never_fans_out_to_zero_researchers(self, fake_llm):
        fake_llm(structured={"PlannerOutput": PlannerOutput(complexity="x", subtasks=["", "   "])})
        result = await planner_node({"topic": "the topic", "iteration": 0})
        assert result["subtasks"] == ["the topic"]

    @pytest.mark.asyncio
    async def test_gap_round_prompt_carries_both_problem_lists(self, fake_llm):
        llm = fake_llm(structured={"PlannerOutput": PlannerOutput(complexity="x", subtasks=["new"])})
        captured = {}

        class Capturing:
            def __init__(self, schema):
                self.schema = schema

            async def ainvoke(self, prompt, **_kw):
                captured["prompt"] = prompt
                return PlannerOutput(complexity="x", subtasks=["new"])

        llm.with_structured_output = Capturing
        await planner_node(
            {
                "topic": "t",
                "iteration": 1,
                "researcher_findings": [
                    {"subtask": "old", "content": "c", "sources": [], "iteration": 1}
                ],
                "critic_feedback": "thin",
                "missing": ["what about cost"],
                "unsupported": ["X causes Y"],
            }
        )
        assert "what about cost" in captured["prompt"]
        assert "X causes Y" in captured["prompt"]
        assert "old" in captured["prompt"]


class TestResearcherNode:
    @pytest.mark.asyncio
    async def test_empty_store_falls_back_to_web_search(self, fake_llm, monkeypatch):
        fake_llm(text="briefing")
        from backend.tools import retriever, web_search

        searched = []

        async def no_docs(*_a, **_kw):
            return []

        async def search(query, n):
            searched.append(query)
            return [{"title": "T", "url": "https://e.com", "snippet": "s"}]

        async def noop_write(*_a, **_kw):
            return None

        monkeypatch.setattr(retriever, "retrieve_async", no_docs)
        monkeypatch.setattr(retriever, "add_finding_async", noop_write)
        monkeypatch.setattr(web_search, "search_async", search)

        result = await researcher_node(
            {"session_id": "s", "topic": "t", "subtask": "sub", "iteration": 1}
        )
        assert searched == ["sub"]
        assert result["researcher_findings"][0]["sources"] == ["https://e.com"]

    @pytest.mark.asyncio
    async def test_a_well_stocked_store_skips_the_web(self, fake_llm, monkeypatch):
        fake_llm(text="briefing")
        from backend.tools import retriever, web_search

        searched = []

        async def docs(*_a, **_kw):
            return [_doc("a", "finding: x"), _doc("b", "finding: y")]

        async def search(query, n):
            searched.append(query)
            return []

        async def noop_write(*_a, **_kw):
            return None

        monkeypatch.setattr(retriever, "retrieve_async", docs)
        monkeypatch.setattr(retriever, "add_finding_async", noop_write)
        monkeypatch.setattr(web_search, "search_async", search)

        result = await researcher_node(
            {"session_id": "s", "topic": "t", "subtask": "sub", "iteration": 2}
        )
        assert searched == []  # RAG_MIN_HITS satisfied, so the web is not consulted
        assert result["researcher_findings"][0]["sources"] == ["finding: x", "finding: y"]

    @pytest.mark.asyncio
    async def test_citation_numbering_runs_continuously_across_both_blocks(
        self, fake_llm, monkeypatch
    ):
        llm = fake_llm(text="briefing")
        from backend.tools import retriever, web_search

        async def one_doc(*_a, **_kw):
            return [_doc("chunk text", "finding: earlier")]

        async def search(*_a, **_kw):
            return [{"title": "T", "url": "https://e.com", "snippet": "s"}]

        async def noop_write(*_a, **_kw):
            return None

        monkeypatch.setattr(retriever, "retrieve_async", one_doc)
        monkeypatch.setattr(retriever, "add_finding_async", noop_write)
        monkeypatch.setattr(web_search, "search_async", search)

        await researcher_node({"session_id": "s", "topic": "t", "subtask": "sub", "iteration": 1})
        prompt = llm.prompts[0]
        # The one retrieved chunk takes [1], so the first web result must be [2]
        # or the briefing's inline citations point at the wrong source.
        assert "[1] finding: earlier" in prompt
        assert "[2] T" in prompt

    @pytest.mark.asyncio
    async def test_a_failed_write_back_does_not_lose_the_finding(self, fake_llm, monkeypatch):
        fake_llm(text="briefing")
        from backend.tools import retriever, web_search

        async def no_docs(*_a, **_kw):
            return []

        async def no_results(*_a, **_kw):
            return []

        async def boom(*_a, **_kw):
            raise RuntimeError("database is locked")

        monkeypatch.setattr(retriever, "retrieve_async", no_docs)
        monkeypatch.setattr(web_search, "search_async", no_results)
        monkeypatch.setattr(retriever, "add_finding_async", boom)

        result = await researcher_node(
            {"session_id": "s", "topic": "t", "subtask": "sub", "iteration": 1}
        )
        assert result["researcher_findings"][0]["content"] == "briefing"


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
