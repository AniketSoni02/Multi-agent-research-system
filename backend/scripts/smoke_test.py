"""Verify the Gemini key works through langchain-google-genai.

The raw REST endpoints are already known to work; this checks the wrapper layer.
Three probes, each covering something a graph node depends on:

  chat        -> researcher, synthesizer, direct_answer
  structured  -> router, planner, verdict
  tools       -> the whole critic tool loop; without tool_calls it cannot run

    python -m backend.scripts.smoke_test
"""

import asyncio
from typing import List

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from backend import config


class Probe(BaseModel):
    subtasks: List[str]


class VerifyClaim(BaseModel):
    """Look a factual claim up with a web search."""

    claim: str = Field(description="The claim to verify.")


async def main() -> None:
    key = config.require_api_key()
    print(f"chat model  : {config.CHAT_MODEL}\n")

    llm = ChatGoogleGenerativeAI(model=config.CHAT_MODEL, google_api_key=key)

    reply = await llm.ainvoke("Reply with exactly: OK")
    print(f"[chat]       {reply.content!r}")

    structured = await llm.with_structured_output(Probe).ainvoke(
        "Split 'the history of coffee' into exactly 2 research subtasks."
    )
    print(f"[structured] {structured.subtasks}")

    tool_reply = await llm.bind_tools([VerifyClaim]).ainvoke(
        "Use the VerifyClaim tool to check this claim: 'Rome was founded in 753 BC'."
    )
    calls = getattr(tool_reply, "tool_calls", []) or []
    if not calls:
        print("[tools]      NO tool_calls emitted -- the critic loop cannot work as designed")
    else:
        print(f"[tools]      {[(c['name'], c['args']) for c in calls]}")

    print("\nAll three paths work. Safe to run the graph.")


if __name__ == "__main__":
    asyncio.run(main())
