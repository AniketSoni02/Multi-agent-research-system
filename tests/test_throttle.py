"""The shared rate limit every chat call goes through."""

import asyncio
import time

import pytest

from backend import config
from backend.graph.nodes import common


class Recorder:
    """A runnable that records when each invocation actually started."""

    def __init__(self):
        self.started_at = []

    async def ainvoke(self, _payload, **_kwargs):
        self.started_at.append(time.monotonic())
        return "ok"


@pytest.fixture(autouse=True)
def reset_throttle():
    common._last_call_at = 0.0
    yield
    common._last_call_at = 0.0


class TestThrottle:
    @pytest.mark.asyncio
    async def test_sequential_calls_are_spaced_by_the_interval(self, monkeypatch):
        monkeypatch.setattr(config, "LLM_MIN_INTERVAL_SECONDS", 0.15)
        runnable = Recorder()

        await common.call(runnable, "a")
        await common.call(runnable, "b")

        gap = runnable.started_at[1] - runnable.started_at[0]
        assert gap >= 0.15

    @pytest.mark.asyncio
    async def test_a_fanned_out_round_is_staggered_not_simultaneous(self, monkeypatch):
        """Five researchers finishing at once must not fire five calls at once."""
        monkeypatch.setattr(config, "LLM_MIN_INTERVAL_SECONDS", 0.1)
        runnable = Recorder()

        await asyncio.gather(*(common.call(runnable, i) for i in range(5)))

        starts = sorted(runnable.started_at)
        gaps = [b - a for a, b in zip(starts, starts[1:])]
        assert all(g >= 0.09 for g in gaps), gaps
        assert starts[-1] - starts[0] >= 0.35

    @pytest.mark.asyncio
    async def test_a_zero_interval_disables_the_wait(self, monkeypatch):
        monkeypatch.setattr(config, "LLM_MIN_INTERVAL_SECONDS", 0)
        runnable = Recorder()

        began = time.monotonic()
        await asyncio.gather(*(common.call(runnable, i) for i in range(5)))

        assert time.monotonic() - began < 0.1

    @pytest.mark.asyncio
    async def test_the_result_is_passed_through_untouched(self, monkeypatch):
        monkeypatch.setattr(config, "LLM_MIN_INTERVAL_SECONDS", 0)
        assert await common.call(Recorder(), "payload") == "ok"
