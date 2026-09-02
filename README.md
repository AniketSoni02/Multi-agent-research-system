# Research Agent

A multi-agent research and report system built on LangGraph, FastAPI and Gemini.

Give it a question. A **Router** first decides whether it needs research at all — a simple
question gets one direct answer. Otherwise a **Planner** judges the topic's scope and splits
it into 1–5 subtasks, **Researchers** work those in parallel against live web search, a
**Synthesizer** merges the findings into one report, and a
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
             │      │   web    │ │   web    │ │          │               │
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
             │                        │        │ verify_claim  (web)    ││
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

That probes all three things the graph depends on: chat, structured output, **tool calling**
(the Critic's loop cannot run without it).

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

99 tests, no network and no API calls: only `get_llm` is faked, via the `fake_llm` fixture in
`tests/conftest.py`, so the real `ask()`/`call()` chokepoint is exercised rather than stubbed.
`tests/test_graph.py` drives the whole compiled graph, which is what actually covers the
topology — the fan-out and its join, the Critic's inner tool loop and its cap, and the outer
review loop back to the Planner. It also asserts that "what is the capital of france" costs
exactly **one** LLM call end to end.

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
| `tools/critic_tools.py` | The three tools the Critic can call. |
| `tools/web_search.py` | DuckDuckGo via `ddgs`, with retry/backoff. Returns `[]` rather than failing a run. |
| `main.py` | SSE research stream and static frontend mount. |

All nodes are async — `Send()` branches only run concurrently if their bodies await.

**Frontend** (`frontend/`) is plain HTML + Tailwind (CDN) + vanilla JS, styled to the
`design.md` "Liquid Blue Glass" token system. `pipeline.js` drives the live stepper,
`sse-client.js` consumes the event stream, `history.js` is the navbar session history,
and `app.js` handles the form and the report.

The stepper is deliberately minimal: each card is a node's name, and the dot and border
carry its state (idle, active, complete, skipped, error). No per-node detail and no activity
log — the substance of a run is the report itself.

### The router

Every query used to pay for the full pipeline — five researchers, up to three review rounds,
several minutes. The Router runs first and scores how much work the query deserves, on a
0–5 scale: **0 answers it directly**, and 1–5 is how many researchers the Planner should fan
out to.

Most queries never reach the API to be routed. `backend/graph/complexity.py` settles the
unambiguous ones for free — "what is the capital of france" is `direct`, "compare solar and
wind power" is `research` — so a simple question costs exactly **one** LLM call in total, the
answer itself. Only genuinely ambiguous queries spend a call on the score.

The ordering inside the classifier is the safety property: research markers are checked
first, so "what is the *current* capital of X" hits the recency rule and never reaches the
capital-of pattern. Two interrogatives means two questions, and a compound query goes to
research even when its first half looks settled. The direct list stays deliberately narrow —
an over-researched answer is a cost, an under-researched one is a defect — and anything the
heuristic cannot place is handed to the model, falling back to research if that call fails.

This matters more than it looks: routing used to depend on an API call, so when the daily
quota ran out the Router failed, defaulted to research, and sent every simple question
through the whole pipeline. Now the decision costs nothing and holds regardless.

### The researchers

Each researcher runs one web search for its own subtask and writes a briefing from the
results, citing them inline as `[1]`, `[2]`, … Branches are independent: they share nothing
but the topic, and their findings are merged only at the Synthesizer.

Search failure degrades rather than aborts. `tools/web_search.py` retries three times with
exponential backoff and then returns `[]`; the researcher still writes a briefing, and the
prompt tells it to say plainly what the sources did not answer rather than inventing it.

### The critic

The Critic does not judge from impression. It is a bounded tool loop — at most
`MAX_CRITIC_TOOL_CALLS` (default 5) calls per review round — over three tools:

- `check_coverage(subtask)` — does the draft actually address a planned subtask?
- `verify_claim(claim)` — look the claim up with a fresh web search. Pure retrieval, no LLM:
  the verdict weighs raw sources, not a second opinion. It is also the Critic's only source
  of outside evidence — the other two judge the draft against material the run produced
  itself, so without this the loop would never look beyond its own output.
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
| `CHAT_MODEL` | `gemini-3.5-flash-lite` | Chat model for every agent. |
| `MAX_ITERATIONS` | `3` | Critic rounds before forced finalization. |
| `MAX_SUBTASKS` | `5` | Ceiling on the Planner's fan-out. |
| `MAX_CRITIC_TOOL_CALLS` | `5` | Ceiling on the Critic's tool loop, per round. |
| `LLM_MIN_INTERVAL_SECONDS` | `2.0` | Minimum gap between two chat calls, graph-wide. `0` disables it. |
| `WEB_RESULTS_PER_SUBTASK` | `5` | Web results per researcher. |
| `FORCE_CRITIC_REJECT_ONCE` | unset | Set to `1` to force a round-1 rejection and exercise the loop-back path. |

Do not assume a model ID resolves just because it is documented — not every advertised
model is reachable on a given key. Ask the key what it offers, then verify the three paths
the graph actually needs:

```python
from google import genai
for m in genai.Client(api_key=KEY).models.list():
    print(m.name)
```

`smoke_test.py` then checks chat, structured output and **tool calling** against whatever
`CHAT_MODEL` is set to. Tool calling is the one to watch: the Critic's evidence loop is dead
without it, and that failure is quiet — the critic simply returns no tool calls and the
verdict judges an empty evidence set.

**Free-tier quota.** Quota is metered **per model**, so switching `CHAT_MODEL` gets a fresh
budget. The limit is not uniform: `gemini-3.6-flash` allowed only 20 `generate_content`
requests per day, which one research run (roughly 10–25 calls) could exhaust on its own — a
simple question, by contrast, costs one. On exhaustion the run surfaces a
`429 RESOURCE_EXHAUSTED` error event rather than hanging.

Every chat call in the graph is spaced at least `LLM_MIN_INTERVAL_SECONDS` apart by a shared
throttle in `graph/nodes/common.py`, which also covers the per-minute rate limit: a five-way
researcher fan-out is staggered rather than firing at once. The cost is latency proportional
to call count — roughly 30s added to a 15-call research run — and the direct path, being one
call, is unaffected. Nodes must invoke the model through `common.call()`; a direct
`runnable.ainvoke()` escapes the throttle.

## API

| Route | Purpose |
| --- | --- |
| `GET /api/health` | Configured model, limits, and whether the API key is present. |
| `GET /api/research/stream?session_id=&topic=` | SSE stream, one event per completed node. |

The stream emits `{"node": …, "output": …}` per node, bracketed by `{"event": "start"}`
and `{"event": "done"}`, with `{"event": "error", "message": …}` on failure. Node names are
`router`, `direct_answer`, `planner`, `researcher`, `synthesizer`, `critic`, `critic_tools`,
`tool_results`, `verdict`, `critic_feedback`, `finalize`.

The Critic's message transcript is stripped before encoding — it holds LangChain message
objects `json.dumps` cannot serialize, and the UI reads the tool calls from `tool_evidence`
instead.

Sessions are a client-generated UUID labelling a run — no auth, no database, and nothing
persisted server-side. History lives in the browser's `localStorage`.
