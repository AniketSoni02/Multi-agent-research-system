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

# How many planner -> researchers -> synthesizer -> critic rounds are allowed
# before the report is finalized regardless of the critic's verdict.
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "3"))

WEB_RESULTS_PER_SUBTASK = int(os.getenv("WEB_RESULTS_PER_SUBTASK", "5"))

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
