"""Central configuration, loaded once from .env at import time."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")

# The key in .env is quoted, and python-dotenv strips the quotes for us. Whitespace
# around the "=" is also tolerated, so a stray space in .env does not break auth.
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip().strip('"').strip("'")

# Model ID verified working against this key. gemini-2.0/2.5-flash are NOT
# available to it, so do not "modernize" this back.
CHAT_MODEL = os.getenv("CHAT_MODEL", "gemini-3.6-flash")

# Embedding model for the per-session vector store, 3072 dims. Verified against
# this key by backend/scripts/smoke_test.py; text-embedding-004 and
# embedding-001 both 404 here, so do not "modernize" this either.
EMBED_MODEL = os.getenv("EMBED_MODEL", "models/gemini-embedding-001")

# How many planner -> researchers -> synthesizer -> critic rounds are allowed
# before the report is finalized regardless of the critic's verdict.
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "3"))

# The planner judges complexity and asks for between 1 and MAX_SUBTASKS
# researchers, so a narrow topic does not pay for a five-way fan-out.
MAX_SUBTASKS = int(os.getenv("MAX_SUBTASKS", "5"))

WEB_RESULTS_PER_SUBTASK = int(os.getenv("WEB_RESULTS_PER_SUBTASK", "5"))

# Chunks a researcher pulls from the session store before deciding whether it
# still needs the web. Below RAG_MIN_HITS the store is too thin to rely on.
RAG_K = int(os.getenv("RAG_K", "4"))
RAG_MIN_HITS = int(os.getenv("RAG_MIN_HITS", "2"))

# Ceiling on the critic's inner tool loop, per review round.
MAX_CRITIC_TOOL_CALLS = int(os.getenv("MAX_CRITIC_TOOL_CALLS", "5"))

# Minimum gap between two chat calls, enforced across the whole graph. The free
# tier limits requests per minute as well as per day, and a fanned-out round
# would otherwise fire five calls at once. Set to 0 to disable.
LLM_MIN_INTERVAL_SECONDS = float(os.getenv("LLM_MIN_INTERVAL_SECONDS", "2.0"))

CHROMA_DIR = PROJECT_ROOT / "data" / "chroma"

FRONTEND_DIR = PROJECT_ROOT / "frontend"

# Test hook: forces the critic to reject the first draft so the loop-back path
# can be exercised without depending on the model's judgement.
FORCE_CRITIC_REJECT_ONCE = os.getenv("FORCE_CRITIC_REJECT_ONCE") == "1"


def require_api_key() -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Add it to .env at the project root."
        )
    return GEMINI_API_KEY
