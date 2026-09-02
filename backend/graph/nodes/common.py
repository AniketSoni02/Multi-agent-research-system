"""The shared LLM client and the text handling every node needs.

Every node is async and every Gemini call is awaited. That matters for the
researcher: the Send() fan-out only runs branches concurrently if their bodies
yield control, so a blocking call would quietly serialize the whole round.
"""

import logging
from typing import Optional

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from backend import config

logger = logging.getLogger(__name__)

_llm: Optional[ChatGoogleGenerativeAI] = None


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


async def ask(prompt: str) -> str:
    response = await get_llm().ainvoke([HumanMessage(content=prompt)])
    return text_of(response.content)
