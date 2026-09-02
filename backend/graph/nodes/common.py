"""The shared LLM client, the call throttle, and the text handling every node needs.

Every node is async and every Gemini call is awaited. That matters for the
researcher: the Send() fan-out only runs branches concurrently if their bodies
yield control, so a blocking call would quietly serialize the whole round.

Every chat call goes through call() so the whole graph shares one rate limit --
nodes must not invoke a runnable directly, or their calls escape the throttle.
"""

import asyncio
import logging
import time
from typing import Optional

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from backend import config

logger = logging.getLogger(__name__)

_llm: Optional[ChatGoogleGenerativeAI] = None

_throttle_lock = asyncio.Lock()
_last_call_at = 0.0


def get_llm() -> ChatGoogleGenerativeAI:
    global _llm
    if _llm is None:
        _llm = ChatGoogleGenerativeAI(
            model=config.CHAT_MODEL,
            google_api_key=config.require_api_key(),
        )
    return _llm


def text_of(content) -> str:
    """Flatten a message's content to plain text.

    Gemini 3.x returns a list of content blocks (text plus a thought signature)
    rather than a string, so stringifying `content` directly would drop the repr
    of the whole block list into the report.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(p for p in parts if p).strip()
    return str(content)


async def _wait_turn() -> None:
    """Block until at least LLM_MIN_INTERVAL_SECONDS has passed since the last call."""
    global _last_call_at
    interval = config.LLM_MIN_INTERVAL_SECONDS
    if interval <= 0:
        return
    async with _throttle_lock:
        gap = interval - (time.monotonic() - _last_call_at)
        if gap > 0:
            await asyncio.sleep(gap)
        _last_call_at = time.monotonic()


async def call(runnable, payload):
    """Invoke a runnable through the shared throttle.

    The lock is released before the model is awaited, so calls are only *started*
    an interval apart -- a fanned-out round still overlaps in flight rather than
    running strictly one at a time.
    """
    await _wait_turn()
    return await runnable.ainvoke(payload)


async def ask(prompt: str) -> str:
    response = await call(get_llm(), [HumanMessage(content=prompt)])
    return text_of(response.content)
