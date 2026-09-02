"""Per-session Chroma vector store, running embedded (no server, no Docker)."""

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
    """True only if this session has an ingested, non-empty collection."""
    path = config.CHROMA_DIR / session_id
    if not path.exists():
        return False
    try:
        return get_store(session_id)._collection.count() > 0
    except Exception as exc:
        logger.warning("could not inspect chroma collection for %s: %s", session_id, exc)
        return False


def retrieve(session_id: str, query: str, k: int) -> List[Document]:
    """Retrieve chunks for a query, degrading to [] when nothing was uploaded.

    A research run with no uploaded documents is a normal case, not an error --
    the researchers simply fall back to web search only.
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


def format_documents(docs: List[Document], start_index: int = 1) -> Tuple[str, List[str]]:
    """Render chunks as a numbered block, plus the source names for citation."""
    if not docs:
        return "(no local documents uploaded for this session)", []
    lines: List[str] = []
    sources: List[str] = []
    for i, doc in enumerate(docs, start=start_index):
        name = doc.metadata.get("source", "uploaded document")
        sources.append(name)
        lines.append(f"[{i}] {name}\n    {doc.page_content.strip()}")
    return "\n".join(lines), sources
