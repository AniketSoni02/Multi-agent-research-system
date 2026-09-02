# Research Agent

A multi-agent research and report system built on LangGraph, FastAPI and Gemini.

Give it a topic. A **Planner** splits it into subtasks, several **Researchers** work those
subtasks in parallel against live web search, a **Synthesizer** merges the findings into one
report, and a **Critic** decides whether the report ships or goes back to the Planner for
another round.

```
              ┌──────────────┐
              │ Topic input  │
              └──────┬───────┘
                     ▼
              ┌──────────────┐  ◄──────────── gaps found ─────────────┐
              │   Planner    │                                        │
              └──────┬───────┘                                        │
        Send() fan-out — runs in parallel                             │
        ┌────────────┼────────────┐                                   │
        ▼            ▼            ▼                                   │
   ┌─────────┐  ┌─────────┐  ┌─────────┐                              │
   │Researcher│ │Researcher│ │Researcher│                             │
   │   web    │ │   web    │ │   web    │                             │
   └────┬─────┘ └────┬────┘  └────┬────┘                              │
        └────────────┼────────────┘                                   │
                     ▼                                                │
              ┌──────────────┐                                        │
              │ Synthesizer  │                                        │
              └──────┬───────┘                                        │
                     ▼                                                │
              ┌──────────────┐ ─────────────────────────────────────► ┘
              │    Critic    │
              └──────┬───────┘
                approved
                     ▼
              ┌──────────────┐
              │ Final report │
              └──────────────┘
```

## Setup

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

`.env` at the project root needs one key:

```
GEMINI_API_KEY = "your-key-here"
```

Verify the key works through LangChain before running the app:

```bash
.venv/Scripts/python.exe -m backend.scripts.smoke_test
```

That checks chat and structured output (the Planner and Critic depend on it).

## Run

```bash
.venv/Scripts/python.exe -m uvicorn backend.main:app --reload --port 8000
```

Open <http://localhost:8000>. The backend serves the frontend itself, so the page is
same-origin with the API — no CORS setup, and `EventSource` works.

## How it works

**Backend** (`backend/`)

| File | Role |
| --- | --- |
| `graph/state.py` | Shared `ResearchState`; `researcher_findings` uses an `operator.add` reducer so parallel branches and later rounds all append into one list. |
| `graph/build.py` | Topology. `Send()` fans out one researcher per subtask; the single `researcher → synthesizer` edge is the join barrier. |
| `graph/nodes.py` | The five nodes. All async — `Send()` branches only run concurrently if their bodies await. |
| `graph/prompts.py` | One prompt per node, with separate first-round and gap-round variants for the Planner and Synthesizer. |
| `tools/web_search.py` | DuckDuckGo via `ddgs`, with retry/backoff. Returns `[]` rather than failing a run. |
| `main.py` | SSE research stream and static frontend mount. |

**Frontend** (`frontend/`) is plain HTML + Tailwind (CDN) + vanilla JS, styled to the
`design.md` "Liquid Blue Glass" token system. `pipeline.js` drives the live stepper,
`sse-client.js` consumes the event stream, `history.js` is the navbar session history,
and `app.js` handles the form and the report.

### Session history

The **History** button in the navbar lists past sessions newest-first, searchable by topic.
A row shows its age at rest and swaps it for rename and delete buttons on hover. Clicking a
row restores that session's topic and saved report; the live stepper is not replayed.

A session is recorded when a run starts (so an interrupted run is still listed) and updated
when its report arrives. Storage is the browser's `localStorage` (newest 50 sessions) —
per-browser, never sent to the server, and it only holds runs made after this feature
existed.

### The loop-back

`operator.add` is append-only, so findings accumulate rather than reset between rounds.
On a loop-back the Planner writes **new, gap-focused** subtasks (it is shown the previous
ones and told not to repeat them), the new researchers append, and the Synthesizer revises
its previous draft using the full accumulated set. Earlier research is never discarded.

`MAX_ITERATIONS` (default 3) caps the rounds. If the cap is hit without approval, the
report still ships, with a note at the top listing the Critic's outstanding concerns.

## Configuration

All optional, via `.env`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `CHAT_MODEL` | `gemini-3.6-flash` | Chat model for all four agents. |
| `MAX_ITERATIONS` | `3` | Critic rounds before forced finalization. |
| `WEB_RESULTS_PER_SUBTASK` | `5` | Web results per researcher. |
| `FORCE_CRITIC_REJECT_ONCE` | unset | Set to `1` to force a round-1 rejection and exercise the loop-back path. |

Note the model ID is not arbitrary: `gemini-2.0-flash` and `gemini-2.5-flash` both return
404 for this API key. Check `/api/health` if in doubt.

## API

| Route | Purpose |
| --- | --- |
| `GET /api/health` | Configured model and whether the API key is present. |
| `GET /api/research/stream?session_id=&topic=` | SSE stream, one event per completed node. |

The stream emits `{"node": …, "output": …}` per node, bracketed by `{"event": "start"}`
and `{"event": "done"}`, with `{"event": "error", "message": …}` on failure. Sessions are
just a client-generated UUID labelling a run — no auth, no database.
