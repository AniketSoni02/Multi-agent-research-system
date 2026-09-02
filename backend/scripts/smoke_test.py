"""Verify the Gemini key works through langchain-google-genai.

The raw REST endpoints are already known to work; this checks the wrapper layer.
Four probes, each covering something a graph node depends on:

  chat        -> researcher, synthesizer, direct_answer
  structured  -> router, planner, verdict
  tools       -> the whole critic tool loop; without tool_calls it cannot run
  embeddings  -> the RAG path (retrieval and finding write-back)

The embedding probe walks a candidate list because the model IDs available to
this key are not the documented defaults -- gemini-3.6-flash works here while
gemini-2.0/2.5-flash do not, so the embedding model cannot be assumed either.

    python -m backend.scripts.smoke_test
"""

import asyncio
from typing import List

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from pydantic import BaseModel, Field

from backend import config


class Probe(BaseModel):
    subtasks: List[str]


class VerifyClaim(BaseModel):
    """Look a factual claim up in the session's document store."""

    claim: str = Field(description="The claim to verify.")


EMBED_CANDIDATES = [
    config.EMBED_MODEL,
    "models/text-embedding-004",
    "models/gemini-embedding-001",
    "gemini-embedding-001",
    "models/embedding-001",
]


async def main() -> None:
    key = config.require_api_key()
    print(f"chat model  : {config.CHAT_MODEL}")
    print(f"embed model : {config.EMBED_MODEL}\n")

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

    working = None
    for candidate in dict.fromkeys(EMBED_CANDIDATES):
        try:
            vec = await GoogleGenerativeAIEmbeddings(
                model=candidate, google_api_key=key
            ).aembed_query("test")
            print(f"[embed]      {candidate} -> {len(vec)} dims")
            working = candidate
            break
        except Exception as exc:
            print(f"[embed]      {candidate} failed: {type(exc).__name__}: {str(exc)[:120]}")

    if working and working != config.EMBED_MODEL:
        print(f"\n>>> Set EMBED_MODEL to {working!r} in backend/config.py")
    elif not working:
        print("\n>>> No embedding model resolved. The RAG path cannot run.")


if __name__ == "__main__":
    asyncio.run(main())
