"""FastAPI app: SSE research stream and the static frontend.

Single-user local tool -- no auth, no database. Sessions are just a
client-generated UUID that labels a run.
"""

import json
import logging
import re

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from backend import config
from backend.graph.build import get_graph
from backend.graph.state import initial_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Research Agent")

_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _safe_session_id(session_id: str) -> str:
    """Reject anything that is not a plain, log-safe identifier."""
    if not _SESSION_RE.match(session_id):
        raise HTTPException(status_code=400, detail="Invalid session id.")
    return session_id


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "chat_model": config.CHAT_MODEL,
        "max_iterations": config.MAX_ITERATIONS,
        "max_critic_tool_calls": config.MAX_CRITIC_TOOL_CALLS,
        "api_key_configured": bool(config.GEMINI_API_KEY),
    }


# The critic's scratchpad holds LangChain message objects, which json.dumps
# cannot encode -- left in, it would kill the stream mid-run. It is also of no
# use to the browser: the UI reads the tool calls from tool_evidence.
_UNSERIALIZABLE_KEYS = {"critic_messages"}


def _serializable(node_output):
    if not isinstance(node_output, dict):
        return node_output
    return {k: v for k, v in node_output.items() if k not in _UNSERIALIZABLE_KEYS}


@app.get("/api/research/stream")
async def research_stream(session_id: str, topic: str):
    """Run the graph, streaming one SSE event per completed node.

    This is a GET because EventSource cannot issue a POST.
    """
    session_id = _safe_session_id(session_id)
    topic = (topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required.")
    if not config.GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not configured.")

    async def event_generator():
        graph = get_graph()
        state = initial_state(session_id, topic, config.MAX_ITERATIONS)

        yield {
            "data": json.dumps(
                {
                    "event": "start",
                    "topic": topic,
                    "max_iterations": config.MAX_ITERATIONS,
                    "max_critic_tool_calls": config.MAX_CRITIC_TOOL_CALLS,
                }
            )
        }

        try:
            # stream_mode="updates" emits {node_name: partial_state_update} as each
            # node finishes, so every fanned-out researcher surfaces on its own.
            async for update in graph.astream(
                state, stream_mode="updates", config={"recursion_limit": 50}
            ):
                for node_name, node_output in update.items():
                    yield {
                        "data": json.dumps(
                            {"node": node_name, "output": _serializable(node_output)},
                            default=str,
                        )
                    }
        except Exception as exc:
            logger.exception("research run failed")
            yield {"data": json.dumps({"event": "error", "message": str(exc)})}
            return

        yield {"data": json.dumps({"event": "done"})}

    return EventSourceResponse(event_generator())


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


class RevalidatingStaticFiles(StaticFiles):
    """Serve the frontend with no-cache so the browser always revalidates.

    StaticFiles sends an ETag but no Cache-Control, which lets browsers apply
    heuristic caching and serve a stale bundle without asking. That is how a
    frontend change can silently not appear -- an old sse-client.js has no
    handler for a newly added node and drops its events on the floor. The ETag
    still makes revalidation cheap: unchanged files come back as a 304.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


# Mounted last so it cannot shadow the /api routes above. On Vercel, public/ is
# served by the CDN and is not bundled into the function, so there is nothing
# to mount -- StaticFiles would refuse a missing directory at import time.
if config.FRONTEND_DIR.is_dir():
    app.mount(
        "/", RevalidatingStaticFiles(directory=str(config.FRONTEND_DIR), html=True), name="frontend"
    )
