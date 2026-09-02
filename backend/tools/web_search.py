"""DuckDuckGo web search via ddgs.

ddgs is synchronous and blocking, so callers inside the graph must go through
`search_async`, otherwise one researcher branch would stall the event loop and the
Send() fan-out would degrade to sequential execution.
"""

import asyncio
import logging
import time
from typing import List, TypedDict

from ddgs import DDGS

logger = logging.getLogger(__name__)


class SearchResult(TypedDict):
    title: str
    url: str
    snippet: str


def search(query: str, max_results: int = 5, attempts: int = 3) -> List[SearchResult]:
    """Return web results, or an empty list if DuckDuckGo will not cooperate.

    Search failures must never abort a research run: a report built from fewer
    sources beats no report at all.
    """
    delay = 1.0
    for attempt in range(1, attempts + 1):
        try:
            with DDGS() as ddgs:
                raw = list(ddgs.text(query, max_results=max_results))
            return [
                {
                    "title": r.get("title", "") or "",
                    "url": r.get("href", "") or r.get("url", "") or "",
                    "snippet": r.get("body", "") or "",
                }
                for r in raw
            ]
        except Exception as exc:  # rate limits, transient network, parser drift
            logger.warning("web search attempt %s/%s failed for %r: %s", attempt, attempts, query, exc)
            if attempt == attempts:
                return []
            time.sleep(delay)
            delay *= 2
    return []


async def search_async(query: str, max_results: int = 5) -> List[SearchResult]:
    return await asyncio.to_thread(search, query, max_results)


def format_results(results: List[SearchResult], start_index: int = 1) -> str:
    """Render results as a numbered block the researcher prompt can cite as [n]."""
    if not results:
        return "(no web results available for this subtask)"
    lines = []
    for i, r in enumerate(results, start=start_index):
        lines.append(f"[{i}] {r['title']}\n    {r['url']}\n    {r['snippet']}")
    return "\n".join(lines)
