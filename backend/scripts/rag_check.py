"""Round-trip the session vector store against the real embedding API.

Writes two findings the way a researcher would, then retrieves them the way a
later round and the critic's verify_claim tool would. This exercises the one
part of the RAG path the offline tests fake out: that the embedding model
resolves and that similarity search actually ranks the right finding first.

    python -m backend.scripts.rag_check
"""

import asyncio
import shutil

from backend import config
from backend.tools import retriever

SESSION = "ragcheck"

FINDINGS = [
    (
        "How much electricity do data centres use?",
        "Data centres consumed about 415 TWh in 2024, roughly 1.5% of global electricity demand.",
        ["https://iea.org/reports/energy-and-ai"],
    ),
    (
        "What is the water footprint of data centre cooling?",
        "Evaporative cooling can consume 1.8 litres of water per kWh of IT load in hot climates.",
        ["https://example.org/cooling"],
    ),
]


async def main() -> None:
    path = config.CHROMA_DIR / SESSION
    if path.exists():
        shutil.rmtree(path)

    print(f"embed model : {config.EMBED_MODEL}")
    print(f"store       : {path}\n")

    assert retriever.retrieve(SESSION, "anything", k=4) == [], "empty store should return []"
    print("[empty]      retrieve on a fresh session returns [] (the round-one case)")

    # Concurrent, the way the Send() fan-out finishes: this is what the write
    # lock exists to survive.
    await asyncio.gather(
        *(retriever.add_finding_async(SESSION, q, a, s, 1) for q, a, s in FINDINGS)
    )
    print(f"[write]      {len(FINDINGS)} findings written back concurrently")

    docs = await retriever.retrieve_async(SESSION, "data centre power consumption", k=2)
    print(f"[retrieve]   {len(docs)} hits for a power query")
    top = docs[0].page_content if docs else ""
    print(f"[top hit]    {top[:90]}...")
    assert "415 TWh" in top, "similarity search ranked the wrong finding first"

    block, sources = retriever.format_documents(docs)
    print(f"[format]     sources: {sources}")
    assert block.startswith("[1] "), "citation numbering should start at [1]"

    shutil.rmtree(path, ignore_errors=True)
    print("\nRAG path works end to end.")


if __name__ == "__main__":
    asyncio.run(main())
