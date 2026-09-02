"""Ingest uploaded documents into a session's Chroma collection."""

import logging
from pathlib import Path
from typing import List

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.tools.retriever import get_store

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md", ".markdown"}

_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)


class UnsupportedFileType(ValueError):
    pass


def read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise UnsupportedFileType(
            f"{path.suffix or 'this file type'} is not supported. Upload a PDF, .txt or .md file."
        )
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    return path.read_text(encoding="utf-8", errors="replace")


def ingest_file(session_id: str, path: Path, display_name: str) -> int:
    """Chunk, embed and upsert one file. Returns the number of chunks stored."""
    text = read_text(path).strip()
    if not text:
        # A scanned PDF with no text layer lands here; surface it rather than
        # silently storing nothing.
        raise ValueError(
            f"No extractable text found in {display_name}. If it is a scanned PDF, it needs OCR first."
        )

    chunks = _splitter.split_text(text)
    docs: List[Document] = [
        Document(page_content=chunk, metadata={"source": display_name, "chunk": i})
        for i, chunk in enumerate(chunks)
    ]
    get_store(session_id).add_documents(docs)
    logger.info("ingested %s chunks from %s for session %s", len(docs), display_name, session_id)
    return len(docs)
