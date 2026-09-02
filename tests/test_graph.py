"""End-to-end runs of the compiled graph with the LLM and network faked out.

These are the tests that actually exercise the topology: the Send() fan-out and
its join, the critic's inner tool loop, and the outer review loop back to the
planner. Nothing here touches Gemini or the web.
"""

import pytest
from langchain_core.messages import AIMessage

from backend import config
from backend.graph.build import build_graph
from backend.graph.nodes.critic import CriticVerdict
from backend.graph.nodes.research import PlannerOutput
from backend.graph.nodes.routing import RouteDecision
from backend.graph.state import initial_state
from tests.conftest import tool_call


async def run(graph, topic="a topic", max_iterations=3):
    """Return the node sequence the SSE endpoint would stream, and the end state.

    Both modes are needed: "updates" gives the per-node deltas the frontend sees,
    but merging those by hand would clobber the reducers -- the accumulated state
    only exists in the "values" snapshots.
    """
    state = initial_state("test-session", topic, max_iterations)
    seen = []
    final = {}
    async for mode, chunk in graph.astream(
        state, stream_mode=["updates", "values"], config={"recursion_limit": 50}
    ):
        if mode == "updates":
            seen.extend(chunk.keys())
        else:
            final = chunk
    return seen, final


class TestDirectPath:
    @pytest.mark.asyncio
    async def test_a_simple_question_skips_the_whole_research_pipeline(self, fake_llm, no_network):
        fake_llm(
            structured={"RouteDecision": RouteDecision(mode="direct", reason="one fact")},
            text="# CPU\n\nCentral Processing Unit.",
        )
        seen, final = await run(build_graph(), topic="what does CPU stand for")

        assert seen == ["router", "direct_answer"]
        assert "planner" not in seen and "researcher" not in seen
        assert final["final_report"].startswith("# CPU")
        assert final["approved"] is True


class TestResearchPath:
    @pytest.mark.asyncio
    async def test_fans_out_joins_and_finalizes_on_approval(self, fake_llm, no_network):
        fake_llm(
            structured={
                "RouteDecision": RouteDecision(mode="research", reason="multi-faceted"),
                "PlannerOutput": PlannerOutput(complexity="three angles", subtasks=["a", "b", "c"]),
                "CriticVerdict": CriticVerdict(approved=True, feedback="solid", missing=[], unsupported=[]),
            },
            tool_turns=[AIMessage(content="the draft holds up")],
            text="# Draft",
        )
        seen, final = await run(build_graph())

        # One researcher event per subtask, and the synthesizer runs once after
        # all three -- that single static edge is the join barrier.
        assert seen.count("researcher") == 3
        assert seen.count("synthesizer") == 1
        assert seen.index("synthesizer") > max(
            i for i, n in enumerate(seen) if n == "researcher"
        )
        assert seen[-1] == "finalize"
        assert len(final["researcher_findings"]) == 3
        assert final["approved"] is True
        assert final["final_report"] == "# Draft"

    @pytest.mark.asyncio
    async def test_the_critic_gathers_evidence_before_the_verdict(self, fake_llm, no_network):
        fake_llm(
            structured={
                "RouteDecision": RouteDecision(mode="research", reason="x"),
                "PlannerOutput": PlannerOutput(complexity="x", subtasks=["a"]),
                "CriticVerdict": CriticVerdict(approved=True, feedback="ok", missing=[], unsupported=[]),
            },
            tool_turns=[
                AIMessage(
                    content="",
                    tool_calls=[
                        tool_call("CheckCoverage", {"subtask": "a"}, "1"),
                        tool_call("CheckGrounding", {"statement": "s"}, "2"),
                    ],
                ),
                AIMessage(content="checks came back clean"),
            ],
            text="covered -- section 1",
        )
        seen, final = await run(build_graph())

        assert "critic_tools" in seen
        assert seen.count("critic") == 2  # asked for tools, then wrapped up
        assert [e["tool"] for e in final["tool_evidence"]] == ["CheckCoverage", "CheckGrounding"]
        # The verdict node must run after the evidence is aggregated.
        assert seen.index("tool_results") < seen.index("verdict") < seen.index("critic_feedback")

    @pytest.mark.asyncio
    async def test_the_tool_loop_cannot_run_away(self, fake_llm, no_network):
        # A critic that asks for a tool on every single turn, forever.
        fake_llm(
            structured={
                "RouteDecision": RouteDecision(mode="research", reason="x"),
                "PlannerOutput": PlannerOutput(complexity="x", subtasks=["a"]),
                "CriticVerdict": CriticVerdict(approved=True, feedback="ok", missing=[], unsupported=[]),
            },
            tool_turns=[
                AIMessage(content="", tool_calls=[tool_call("CheckCoverage", {"subtask": "a"}, "1")])
            ],
            text="covered",
        )
        seen, final = await run(build_graph())

        assert final["critic_tool_calls"] == config.MAX_CRITIC_TOOL_CALLS
        assert seen.count("critic_tools") == config.MAX_CRITIC_TOOL_CALLS
        assert seen[-1] == "finalize"


class TestReviewLoop:
    @pytest.mark.asyncio
    async def test_a_rejection_loops_back_to_the_planner_and_accumulates_findings(
        self, fake_llm, no_network
    ):
        fake_llm(
            structured={
                "RouteDecision": RouteDecision(mode="research", reason="x"),
                "PlannerOutput": [
                    PlannerOutput(complexity="round 1", subtasks=["a", "b"]),
                    PlannerOutput(complexity="round 2", subtasks=["c"]),
                ],
                "CriticVerdict": [
                    CriticVerdict(
                        approved=False, feedback="thin", missing=["what about cost"], unsupported=[]
                    ),
                    CriticVerdict(approved=True, feedback="better now", missing=[], unsupported=[]),
                ],
            },
            tool_turns=[AIMessage(content="reviewed")],
            text="# Draft",
        )
        seen, final = await run(build_graph())

        assert seen.count("planner") == 2
        # operator.add is append-only: round 2's single finding joins round 1's two.
        assert len(final["researcher_findings"]) == 3
        assert {f["iteration"] for f in final["researcher_findings"]} == {1, 2}
        assert final["approved"] is True

    @pytest.mark.asyncio
    async def test_the_iteration_cap_ships_the_report_with_the_gaps_noted(
        self, fake_llm, no_network
    ):
        fake_llm(
            structured={
                "RouteDecision": RouteDecision(mode="research", reason="x"),
                "PlannerOutput": PlannerOutput(complexity="x", subtasks=["a"]),
                "CriticVerdict": CriticVerdict(
                    approved=False,
                    feedback="still thin",
                    missing=["what about cost"],
                    unsupported=["X causes Y"],
                ),
            },
            tool_turns=[AIMessage(content="reviewed")],
            text="# Draft",
        )
        seen, final = await run(build_graph(), max_iterations=2)

        assert seen.count("planner") == 2  # capped, not looping forever
        assert final["approved"] is False
        assert final["final_report"].startswith("> **Note:**")
        assert "what about cost" in final["final_report"]
        assert "X causes Y" in final["final_report"]

    @pytest.mark.asyncio
    async def test_each_round_judges_only_its_own_evidence(self, fake_llm, no_network):
        fake_llm(
            structured={
                "RouteDecision": RouteDecision(mode="research", reason="x"),
                "PlannerOutput": PlannerOutput(complexity="x", subtasks=["a"]),
                "CriticVerdict": [
                    CriticVerdict(approved=False, feedback="thin", missing=["gap"], unsupported=[]),
                    CriticVerdict(approved=True, feedback="ok", missing=[], unsupported=[]),
                ],
            },
            tool_turns=[
                AIMessage(content="", tool_calls=[tool_call("CheckCoverage", {"subtask": "a"}, "1")]),
                AIMessage(content="done"),
            ],
            text="covered",
        )
        _, final = await run(build_graph())

        # The synthesizer zeroes the scratchpad each round, so the evidence left
        # at the end belongs to the final review, not to both of them.
        assert len(final["tool_evidence"]) <= config.MAX_CRITIC_TOOL_CALLS


class TestStreamSerialization:
    @pytest.mark.asyncio
    async def test_every_streamed_update_survives_json_encoding(self, fake_llm, no_network):
        """The critic's transcript holds message objects json.dumps cannot encode."""
        import json

        from backend.main import _serializable

        fake_llm(
            structured={
                "RouteDecision": RouteDecision(mode="research", reason="x"),
                "PlannerOutput": PlannerOutput(complexity="x", subtasks=["a"]),
                "CriticVerdict": CriticVerdict(approved=True, feedback="ok", missing=[], unsupported=[]),
            },
            tool_turns=[
                AIMessage(content="", tool_calls=[tool_call("CheckCoverage", {"subtask": "a"}, "1")]),
                AIMessage(content="done"),
            ],
            text="covered",
        )
        graph = build_graph()
        state = initial_state("test-session", "a topic", 3)

        async for update in graph.astream(
            state, stream_mode="updates", config={"recursion_limit": 50}
        ):
            for node_name, node_output in update.items():
                payload = json.dumps(
                    {"node": node_name, "output": _serializable(node_output)}, default=str
                )
                assert "AIMessage" not in payload
