"""Verify the Gemini key works through langchain-google-genai.

The raw REST endpoints are already known to work; this checks the wrapper layer,
including structured output, which is what the planner and critic depend on.

    python -m backend.scripts.smoke_test
"""

import asyncio
from typing import List

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

from backend import config


class Probe(BaseModel):
    subtasks: List[str]


async def main() -> None:
    key = config.require_api_key()
    print(f"chat model : {config.CHAT_MODEL}")

    llm = ChatGoogleGenerativeAI(model=config.CHAT_MODEL, google_api_key=key)
    reply = await llm.ainvoke("Reply with exactly: OK")
    print(f"[chat]       {reply.content!r}")

    structured = await llm.with_structured_output(Probe).ainvoke(
        "Split 'the history of coffee' into exactly 2 research subtasks."
    )
    print(f"[structured] {structured.subtasks}")

    print("\nBoth paths work. Safe to run the graph.")


if __name__ == "__main__":
    asyncio.run(main())
