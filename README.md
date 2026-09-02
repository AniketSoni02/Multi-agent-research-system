# Research Agent

A multi-agent research and report system built on LangGraph, FastAPI and Gemini.

Give it a question. A **Router** first decides whether it needs research at all — a simple
question gets one direct answer. Otherwise a **Planner** judges the topic's scope and splits
it into 1–5 subtasks, **Researchers** work those in parallel against the session's knowledge
base and live web search, a **Synthesizer** merges the findings into one report, and a
**Critic** gathers evidence with its own tools before deciding whether the report ships or
goes back to the Planner for another round.

```
                        ┌──────────────┐
                        │    Router    │
                        └──┬────────┬──┘
                    direct │        │ research
              ┌────────────┘        ▼
              ▼              ┌──────────────┐ ◄────── not approved ──────┐
     ┌────────────────┐      │   Planner    │                            │
     │ Direct answer  │      │ judges scope │                            │
     │ one LLM call   │      └──────┬───────┘                            │
     └───────┬────────┘   Send() fan-out — one per subtask, in parallel  │
             │            ┌─────────┼─────────┐                          │
             │            ▼         ▼         ▼                          │
             │      ┌──────────┐ ┌──────────┐ ┌──────────┐               │
             │      │Researcher│ │Researcher│ │  … ≤ 5   │               │
             │      │ RAG →web │ │ RAG →web │ │          │               │
             │      └────┬─────┘ └────┬─────┘ └────┬─────┘               │
             │           └────────────┼────────────┘                     │
             │                        ▼  join, any N                     │
             │                 ┌──────────────┐                          │
             │                 │ Synthesizer  │                          │
             │                 └──────┬───────┘                          │
             │                        ▼                                  │
             │                 ┌──────────────┐ ── tool calls ──┐        │
             │                 │    Critic    │                 │        │
             │                 │  ≤ 5 calls   │ ◄─ results ──┐  │        │
             │                 └──────┬───────┘              │  ▼        │
             │                        │        ┌─────────────┴──────────┐│
             │                        │        │ check_coverage         ││
             │                        │        │ verify_claim  (RAG+web)││
             │                        │        │ check_grounding        ││
             │                        │        └────────────────────────┘│
             │                        ▼                                  │
             │                 ┌──────────────┐                          │
             │                 │ tool_results │  aggregates evidence     │
             │                 └──────┬───────┘                          │
             │                        ▼                                  │
             │                 ┌──────────────┐                          │
             │                 │   Verdict    │  forced JSON             │
             │                 └──────┬───────┘                          │
             │                        ▼                                  │
             │                 ┌──────────────────────────────┐          │
             │                 │ approved · missing[] ·        │ ────────┘
             │                 │            unsupported[]      │
             │                 └──────┬───────────────────────┘
             │              approved, or round cap hit
             │                        ▼
             │                 ┌──────────────┐
             └────────────────►│ Final report │
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

That probes all four things the graph depends on: chat, structured output, **tool calling**
(the Critic's loop cannot run without it), and **embeddings** (the RAG path cannot run
without them). It walks a list of candidate embedding model IDs and tells you which one
resolves. To round-trip the vector store against the real embedding API:

```bash
.venv/Scripts/python.exe -m backend.scripts.rag_check
```

## Run

```bash
.venv/Scripts/python.exe -m uvicorn backend.main:app --reload --port 8000
```

Open <http://localhost:8000>. The backend serves the frontend itself, so the page is
same-origin with the API — no CORS setup, and `EventSource` works.

## Tests

```bash
.venv/Scripts/python.exe -m pytest
```

49 tests, no network and no API calls: the LLM is faked out via the `fake_llm` fixture in
`tests/conftest.py`. `tests/test_graph.py` drives the whole compiled graph, which is what
actually covers the topology — the fan-out and its join, the Critic's inner tool loop and
its cap, and the outer review loop back to the Planner.

## How it works

**Backend** (`backend/`)

| File | Role |
| --- | --- |
| `graph/state.py` | Shared `ResearchState`; `researcher_findings` uses an `operator.add` reducer so parallel branches and later rounds all append into one list. |
| `graph/build.py` | Topology. `Send()` fans out one researcher per subtask; the single `researcher → synthesizer` edge is the join barrier. |
| `graph/nodes/routing.py` | Router and direct answer. |
| `graph/nodes/research.py` | Planner, researcher, synthesizer, finalize. |
| `graph/nodes/critic.py` | The critic's five-stage evidence loop. |
| `graph/nodes/common.py` | Shared LLM client. `text_of` flattens Gemini 3.x content blocks — without it the block-list repr lands in the report. |
| `graph/prompts.py` | One prompt per node, with separate first-round and gap-round variants for the Planner and Synthesizer. |
| `tools/retriever.py` | Per-session Chroma store, embedded — no server, no Docker. |
| `tools/critic_tools.py` | The three tools the Critic can call. |
| `tools/web_search.py` | DuckDuckGo via `ddgs`, with retry/backoff. Returns `[]` rather than failing a run. |
| `main.py` | SSE research stream and static frontend mount. |

All nodes are async — `Send()` branches only run concurrently if their bodies await.

**Frontend** (`frontend/`) is plain HTML + Tailwind (CDN) + vanilla JS, styled to the
`design.md` "Liquid Blue Glass" token system. `pipeline.js` drives the live stepper,
`sse-client.js` consumes the event stream, `history.js` is the navbar session history,
and `app.js` handles the form and the report.

### The router

Every query used to pay for the full pipeline — five researchers, up to three review rounds,
several minutes. The Router spends one structured call deciding whether that is warranted.
"What does CPU stand for" gets one answer; "compare the leading approaches to X" gets the
research path. Borderline questions go to research, and if the Router itself fails the graph
defaults to research: an over-researched answer is a cost, an under-researched one is a
defect.

### The researchers and the knowledge base

Each researcher tries the session's vector store first and only falls back to web search when
the store returns fewer than `RAG_MIN_HITS` chunks. It then **writes its own briefing back**
into the store. Round one therefore starts empty and searches the web; by round two the store
holds round one's findings, so follow-up subtasks retrieve what the run already established
instead of re-searching for it. The Critic's `verify_claim` tool reads the same store.

Citations run continuously across both blocks — if two chunks come back from the store, the
first web result is `[3]` — so the inline `[n]` markers in a briefing always resolve.

Writes are serialized behind an `asyncio.Lock`: up to five branches finish at once, and
Chroma's sqlite backend raises "database is locked" under concurrent writers.

### The critic

The Critic does not judge from impression. It is a bounded tool loop — at most
`MAX_CRITIC_TOOL_CALLS` (default 5) calls per review round — over three tools:

- `check_coverage(subtask)` — does the draft actually address a planned subtask?
- `verify_claim(claim)` — look the claim up in the knowledge base, falling back to web
  search. Pure retrieval, no LLM: the verdict weighs raw sources, not a second opinion.
- `check_grounding(statement)` — does a statement in the draft trace back to what the
  researchers actually found, or was it invented in the write-up?

The evidence is then aggregated and handed to a **separate** forced-JSON verdict step, which
is told every entry must trace to a tool result. The split is the point: no single call both
gathers the evidence and renders the judgement, so a rejection has to point at something a
tool actually found.

The verdict is normalized before it reaches the Planner. If the model approves while still
listing problems, the lists win and the report is not approved.

### The loop-back

`operator.add` is append-only, so findings accumulate rather than reset between rounds.
On a loop-back the Planner writes **new** subtasks aimed at the Critic's `missing` and
`unsupported` lists (it is shown the previous subtasks and told not to repeat them), the new
researchers append, and the Synthesizer revises its previous draft using the full accumulated
set. Earlier research is never discarded.

The Critic's scratchpad is the exception: the Synthesizer clears it at the top of each round,
so evidence gathered against the previous draft is never used to judge the current one.

`MAX_ITERATIONS` (default 3) caps the rounds. If the cap is hit without approval, the report
still ships, with a note at the top listing what is still missing and what the evidence did
not support.

## Configuration

All optional, via `.env`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `CHAT_MODEL` | `gemini-3.6-flash` | Chat model for every agent. |
| `EMBED_MODEL` | `models/gemini-embedding-001` | Embeddings for the session vector store. |
| `MAX_ITERATIONS` | `3` | Critic rounds before forced finalization. |
| `MAX_SUBTASKS` | `5` | Ceiling on the Planner's fan-out. |
| `MAX_CRITIC_TOOL_CALLS` | `5` | Ceiling on the Critic's tool loop, per round. |
| `RAG_K` | `4` | Chunks retrieved per subtask. |
| `RAG_MIN_HITS` | `2` | Below this, the researcher falls back to web search. |
| `WEB_RESULTS_PER_SUBTASK` | `5` | Web results per researcher. |
| `FORCE_CRITIC_REJECT_ONCE` | unset | Set to `1` to force a round-1 rejection and exercise the loop-back path. |

Neither model ID is arbitrary. `gemini-2.0-flash` and `gemini-2.5-flash` both 404 for this
API key, and so do `models/text-embedding-004` and `models/embedding-001`. Re-run the smoke
test rather than assuming a newer ID resolves, and check `/api/health` if in doubt.

**Free-tier quota.** `gemini-3.6-flash` allows 20 `generate_content` requests per day on the
free tier. One research run costs roughly 10–25 calls, so a single full run can exhaust the
day's quota. Embeddings are metered separately and are not affected. On exhaustion the run
surfaces a `429 RESOURCE_EXHAUSTED` error event rather than hanging.

## API

| Route | Purpose |
| --- | --- |
| `GET /api/health` | Configured models, limits, and whether the API key is present. |
| `GET /api/research/stream?session_id=&topic=` | SSE stream, one event per completed node. |

The stream emits `{"node": …, "output": …}` per node, bracketed by `{"event": "start"}`
and `{"event": "done"}`, with `{"event": "error", "message": …}` on failure. Node names are
`router`, `direct_answer`, `planner`, `researcher`, `synthesizer`, `critic`, `critic_tools`,
`tool_results`, `verdict`, `critic_feedback`, `finalize`.

The Critic's message transcript is stripped before encoding — it holds LangChain message
objects `json.dumps` cannot serialize, and the UI reads the tool calls from `tool_evidence`
instead.

Sessions are a client-generated UUID labelling a run. They now mean something server-side:
the UUID names the Chroma collection the run reads and writes. There is still no auth and no
database.
