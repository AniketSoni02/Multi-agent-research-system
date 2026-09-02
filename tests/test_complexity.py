"""The zero-call classifier.

The first case is the reported bug: "what is the capital of france" ran the whole
research pipeline. It must settle here, without the API being reachable at all.
"""

import pytest

from backend.graph import complexity


class TestDirect:
    @pytest.mark.parametrize(
        "topic",
        [
            "what is the capital of france",
            "What is the capital of France?",
            "what is the currency of japan",
            "what does CPU stand for",
            "who wrote pride and prejudice",
            "when was the eiffel tower built",
            "define entropy",
            "what does ubiquitous mean",
            "how do you spell necessary",
            "hi",
            "hello there",
            "thanks!",
            "2 + 2",
            "what is 17 * 43",
        ],
    )
    def test_settled_questions_need_no_research(self, topic):
        assert complexity.classify(topic) == complexity.DIRECT


class TestResearch:
    @pytest.mark.parametrize(
        "topic",
        [
            # The trap: looks like a capital-of lookup, but the answer moves.
            "what is the current capital of myanmar",
            "what is the latest capital of kazakhstan",
            "compare solar and wind power",
            "react vs vue for a new project",
            "the difference between mRNA and viral vector vaccines",
            "pros and cons of remote work",
            "state of the art in protein folding",
            "what happened in AI in 2026",
            "the impact of microplastics on marine life",
            "comprehensive overview of quantum error correction",
            "analyze the housing market",
            "tell me about the history of the silk road",
            "write a report on lithium supply chains",
        ],
    )
    def test_questions_needing_sources_are_recognised(self, topic):
        assert complexity.classify(topic) == complexity.RESEARCH

    def test_a_compound_question_is_not_a_single_fact(self):
        topic = "what is the capital of france and how has its population changed?"
        assert complexity.classify(topic) == complexity.RESEARCH

    def test_more_than_one_question_mark_means_research(self):
        assert complexity.classify("what is X? what is Y?") == complexity.RESEARCH

    def test_a_long_query_is_never_treated_as_simple(self):
        topic = " ".join(["word"] * 30)
        assert complexity.classify(topic) == complexity.RESEARCH


class TestUnsure:
    @pytest.mark.parametrize(
        "topic",
        [
            "how does photosynthesis work",
            "explain the causes of the french revolution",
            "is intermittent fasting effective",
            "",
            "   ",
        ],
    )
    def test_defers_to_the_model_when_genuinely_ambiguous(self, topic):
        assert complexity.classify(topic) is None

    def test_a_long_settled_lookup_is_not_shortcut(self):
        # Matches a direct pattern but is too wordy to be one settled fact.
        topic = (
            "what is the capital of the autonomous region formerly administered "
            "under the old colonial boundary"
        )
        assert complexity.classify(topic) is None
