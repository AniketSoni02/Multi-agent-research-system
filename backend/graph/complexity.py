"""Decide a query's complexity without spending an API call.

The router used to ask the model whether a question needed research, which cost a
call before any work began -- and on a 20-requests-per-day free tier, that call
failing is what sent "what is the capital of france" down the full research
pipeline. Most queries are unambiguous enough to settle here, for free.

Research markers are checked first. That ordering is the safety property: "what
is the current capital of X" hits the recency marker and never reaches the
capital-of pattern, so a question that looks settled but is not cannot slip
through. The direct list is deliberately narrow for the same reason -- a
wrongly-shortcut answer is a defect, a wrongly-researched one is only a cost.
"""

import re
from typing import List, Optional, Pattern

DIRECT = "direct"
RESEARCH = "research"

# Beyond this a question is doing too much to be one settled fact.
MAX_DIRECT_WORDS = 12
MAX_SIMPLE_WORDS = 25

# Two interrogatives means two questions -- "what is the capital of France and
# how has its population changed" is not one settled fact, even though its first
# half matches a direct pattern exactly.
_INTERROGATIVE = re.compile(r"\b(what|how|why|when|where|who|which)\b", re.IGNORECASE)


def _compile(patterns: List[str]) -> List[Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


# Anything here forces the research path, whatever else the query looks like.
_RESEARCH_MARKERS = _compile(
    [
        # More than one thing being weighed against another.
        r"\b(compare|comparison|versus|vs\.?|difference between|differences between)\b",
        r"\b(pros and cons|trade-?offs?|advantages and disadvantages|better than)\b",
        # The answer moves, so the model's own knowledge is not enough.
        r"\b(latest|current|currently|recent|recently|today|nowadays|so far)\b",
        r"\b(state of the art|cutting.edge|news|upcoming|emerging|trend|trends)\b",
        r"\b20[2-9]\d\b",
        # Asking for a body of work rather than a fact.
        r"\b(comprehensive|overview|deep dive|report on|write a report|survey of)\b",
        r"\b(analy[sz]e|analysis of|evaluate|assessment of|investigate|research)\b",
        r"\b(impact of|implications|consequences of|effects? of|landscape)\b",
        r"\b(everything about|all about|tell me about|explain in detail)\b",
        r"\b(why (is|are|does|do|did)|how (does|do|did) .{20,})\b",
    ]
)

# Only questions whose answer is settled, stable and short.
_DIRECT_MARKERS = _compile(
    [
        r"^\s*(hi|hello|hey|yo|thanks|thank you|good (morning|afternoon|evening))\b",
        r"^\s*[\d\s+\-*/().^%]+\s*[?.]?\s*$",
        r"^\s*what\s+is\s+[\d\s+\-*/().^%]+\s*\??\s*$",
        r"\bwhat\s+(is|are)\s+the\s+(capital|currency|population|official language|"
        r"time zone|area|flag)\s+of\b",
        r"\bwhat\s+does\s+.{1,40}\s+stand\s+for\b",
        r"\bwho\s+(wrote|invented|painted|composed|discovered|founded|directed)\b",
        r"\bwhen\s+(was|were|did)\s+.{1,40}\s+"
        r"(born|die|died|founded|invented|published|built|created|established|released|written)\b",
        r"^\s*define\b",
        r"\bwhat\s+does\s+.{1,40}\s+mean\b",
        r"\bhow\s+do\s+you\s+spell\b",
        r"\bhow\s+many\s+(days|weeks|months|hours|minutes|seconds|letters)\s+(in|are in)\b",
    ]
)


def classify(topic: str) -> Optional[str]:
    """Return "direct", "research", or None when only the model can tell."""
    text = (topic or "").strip()
    if not text:
        return None

    words = text.split()

    if any(p.search(text) for p in _RESEARCH_MARKERS):
        return RESEARCH

    # Several questions at once, or a paragraph, is not one settled fact.
    if text.count("?") > 1 or len(words) > MAX_SIMPLE_WORDS:
        return RESEARCH
    if len(_INTERROGATIVE.findall(text)) > 1:
        return RESEARCH

    if len(words) <= MAX_DIRECT_WORDS and any(p.search(text) for p in _DIRECT_MARKERS):
        return DIRECT

    return None
