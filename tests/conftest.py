"""Fakes that let the whole graph run without touching the Gemini API."""

import asyncio
from typing import Any, Dict, List

import pytest
from langchain_core.messages import AIMessage

from backend.graph.nodes import common, critic, research, routing

# The node modules import get_llm and ask by name, so each one holds its own
# reference and has to be patched individually.
_LLM_MODULES = (common, routing, research, critic)
_ASK_MODULES = (common, routing, research)


class FakeStructured:
    """Stands in for llm.with_structured_output(Schema)."""

    def __init__(self, schema, replies):
        self.schema = schema
        self.replies = replies

    async def ainvoke(self, _prompt, **_kwargs):
        name = self.schema.__name__
        if name not in self.replies:
            raise AssertionError(f"no scripted {name} reply")
        value = self.replies[name]
        if isinstance(value, list):
            return value.pop(0) if len(value) > 1 else value[0]
        return value


class FakeBound:
    """Stands in for llm.bind_tools([...])."""

    def __init__(self, turns, calls_seen):
        self.turns = turns
        self.calls_seen = calls_seen

    async def ainvoke(self, messages, **_kwargs):
        self.calls_seen.append(messages)
        return self.turns.pop(0) if len(self.turns) > 1 else self.turns[0]


class FakeLLM:
    def __init__(self, structured=None, tool_turns=None, text="fake text"):
        self.structured = structured or {}
        self.tool_turns = tool_turns or [AIMessage(content="done reviewing")]
        self.text = text
        self.bound_calls: List[Any] = []
        self.prompts: List[Any] = []

    def with_structured_output(self, schema):
        return FakeStructured(schema, self.structured)

    def bind_tools(self, _schemas):
        return FakeBound(self.tool_turns, self.bound_calls)

    async def ainvoke(self, messages, **_kwargs):
        self.prompts.append(messages)
        return AIMessage(content=self.text)


@pytest.fixture
def fake_llm(monkeypatch):
    """Install a FakeLLM across every node module. Returns a configure callable."""

    holder: Dict[str, Any] = {}

    def install(**kwargs):
        llm = FakeLLM(**kwargs)
        holder["llm"] = llm
        for module in _LLM_MODULES:
            monkeypatch.setattr(module, "get_llm", lambda: llm, raising=False)

        async def fake_ask(prompt):
            llm.prompts.append(prompt)
            return llm.text

        for module in _ASK_MODULES:
            monkeypatch.setattr(module, "ask", fake_ask, raising=False)
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
