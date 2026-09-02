"""Per-session Chroma vector store, running embedded (no server, no Docker).

The store is written by the researchers themselves: each briefing is fed back in
as a document, so a second round -- and the critic's verify_claim tool -- can
retrieve what round one established instead of re-searching the web for it.
"""

import asyncio
import logging
from typing import List, Optional, Tuple

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from backend import config

logger = logging.getLogger(__name__)

COLLECTION = "docs"

_embeddings: Optional[GoogleGenerativeAIEmbeddings] = None

# Up to MAX_SUBTASKS researcher branches finish at once and all write back to the
# same collection. Chroma's persistent backend is sqlite, which raises "database
# is locked" under concurrent writers, so writes are serialized. They are short
# and off the critical path, so the queueing costs nothing.
_write_lock = asyncio.Lock()


def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = GoogleGenerativeAIEmbeddings(
            model=config.EMBED_MODEL,
            google_api_key=config.require_api_key(),
        )
    return _embeddings


def _session_dir(session_id: str) -> str:
    path = config.CHROMA_DIR / session_id
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def get_store(session_id: str) -> Chroma:
    return Chroma(
        collection_name=COLLECTION,
        embedding_function=get_embeddings(),
        persist_directory=_session_dir(session_id),
    )


def has_documents(session_id: str) -> bool:
    """True only if this session has a non-empty collection."""
    path = config.CHROMA_DIR / session_id
    if not path.exists():
        return False
    try:
        return get_store(session_id)._collection.count() > 0
    except Exception as exc:
        logger.warning("could not inspect chroma collection for %s: %s", session_id, exc)
        return False


def retrieve(session_id: str, query: str, k: int) -> List[Document]:
    """Retrieve chunks for a query, degrading to [] when the store is empty.

    An empty store is the normal case, not an error: round one always starts
    with nothing, and the researchers simply fall back to web search.
    """
    if not has_documents(session_id):
        return []
    try:
        return get_store(session_id).similarity_search(query, k=k)
    except Exception as exc:
        logger.warning("rag retrieval failed for %s: %s", session_id, exc)
        return []


async def retrieve_async(session_id: str, query: str, k: int) -> List[Document]:
    return await asyncio.to_thread(retrieve, session_id, query, k)


def _add_finding(session_id: str, subtask: str, content: str, sources: List[str], iteration: int) -> None:
    doc = Document(
        page_content=f"Research question: {subtask}\n\n{content}",
        metadata={
            "source": f"finding: {subtask}",
            "kind": "finding",
            "iteration": iteration,
            # Chroma metadata values must be scalars, so the source list is
            # flattened rather than stored as a list.
            "urls": ", ".join(sources),
        },
    )
    get_store(session_id).add_documents([doc])


async def add_finding_async(
    session_id: str, subtask: str, content: str, sources: List[str], iteration: int
) -> None:
    """Write one researcher briefing back into the session store.

    A briefing is 200-400 words, so it goes in whole rather than chunked -- the
    unit a later retrieval wants back is the whole answer to a subtask.
    """
    async with _write_lock:
        await asyncio.to_thread(_add_finding, session_id, subtask, content, sources, iteration)


def format_documents(docs: List[Document], start_index: int = 1) -> Tuple[str, List[str]]:
    """Render chunks as a numbered block, plus the source names for citation."""
    if not docs:
        return "(nothing in the session knowledge base yet)", []
    lines: List[str] = []
    sources: List[str] = []
    for i, doc in enumerate(docs, start=start_index):
        name = doc.metadata.get("source", "session document")
        sources.append(name)
        lines.append(f"[{i}] {name}\n    {doc.page_content.strip()}")
    return "\n".join(lines), sources
