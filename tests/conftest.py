"""Fakes that let the whole graph run without touching the Gemini API.

Only get_llm is replaced. The real ask() and call() still run, so the throttle
chokepoint every node goes through is exercised rather than stubbed out -- with
the interval set to zero so the suite stays fast.
"""

from typing import Any, Dict, List

import pytest
from langchain_core.messages import AIMessage

from backend import config
from backend.graph.nodes import common, critic, research, routing

# The node modules import get_llm by name, so each holds its own reference and
# has to be patched individually.
_LLM_MODULES = (common, routing, research, critic)


def _as_text(payload) -> str:
    """Flatten whatever was handed to the model into something assertable."""
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list):
        return "\n".join(_as_text(p) for p in payload)
    content = getattr(payload, "content", None)
    return content if isinstance(content, str) else str(payload)


class FakeStructured:
    """Stands in for llm.with_structured_output(Schema)."""

    def __init__(self, schema, replies, owner):
        self.schema = schema
        self.replies = replies
        self.owner = owner

    async def ainvoke(self, prompt, **_kwargs):
        self.owner.prompts.append(_as_text(prompt))
        self.owner.calls += 1
        name = self.schema.__name__
        if name not in self.replies:
            raise AssertionError(f"no scripted {name} reply")
        value = self.replies[name]
        if isinstance(value, list):
            return value.pop(0) if len(value) > 1 else value[0]
        return value


class FakeBound:
    """Stands in for llm.bind_tools([...])."""

    def __init__(self, turns, owner):
        self.turns = turns
        self.owner = owner

    async def ainvoke(self, messages, **_kwargs):
        self.owner.bound_calls.append(messages)
        self.owner.calls += 1
        return self.turns.pop(0) if len(self.turns) > 1 else self.turns[0]


class FakeLLM:
    def __init__(self, structured=None, tool_turns=None, text="fake text"):
        self.structured = structured or {}
        self.tool_turns = tool_turns or [AIMessage(content="done reviewing")]
        self.text = text
        self.bound_calls: List[Any] = []
        self.prompts: List[str] = []
        # Every path through the fake increments this, so a test can assert a
        # query cost zero API calls.
        self.calls = 0

    def with_structured_output(self, schema):
        return FakeStructured(schema, self.structured, self)

    def bind_tools(self, _schemas):
        return FakeBound(self.tool_turns, self)

    async def ainvoke(self, messages, **_kwargs):
        self.prompts.append(_as_text(messages))
        self.calls += 1
        return AIMessage(content=self.text)


@pytest.fixture
def fake_llm(monkeypatch):
    """Install a FakeLLM across every node module. Returns a configure callable."""

    holder: Dict[str, Any] = {}

    def install(**kwargs):
        llm = FakeLLM(**kwargs)
        holder["llm"] = llm
        # The throttle is real; a 2s gap per call would make the suite crawl.
        monkeypatch.setattr(config, "LLM_MIN_INTERVAL_SECONDS", 0)
        for module in _LLM_MODULES:
            monkeypatch.setattr(module, "get_llm", lambda: llm, raising=False)
        return llm

    return install


@pytest.fixture
def no_network(monkeypatch):
    """Silence the vector store and web search so nothing leaves the process."""
    from backend.tools import retriever, web_search

    async def no_docs(*_a, **_kw):
        return []

    async def no_results(*_a, **_kw):
        return []

    async def no_write(*_a, **_kw):
        return None

    monkeypatch.setattr(retriever, "retrieve_async", no_docs)
    monkeypatch.setattr(retriever, "add_finding_async", no_write)
    monkeypatch.setattr(web_search, "search_async", no_results)


def tool_call(name: str, args: dict, call_id: str) -> dict:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}
