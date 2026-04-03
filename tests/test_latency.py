"""
Sprint 11 — Latency budget system tests (Task 11.19).
"""
import asyncio
import time
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from party.orchestration.chain import run_chain, _get_budget
from party.orchestration.router import RouterResult
from party.orchestration.modes import ExecutionMode
from party.models import Trigger, TriggerType, TriggerPriority, CharacterResponse
from party.providers.base import ProviderError
import uuid
from datetime import datetime


@pytest.fixture(autouse=True)
def mock_scene(monkeypatch):
    """Prevent OBS WebSocket connection attempts in latency tests."""
    async def _fast_scene():
        return "Gaming"
    monkeypatch.setattr("party.context.obs_context.get_current_scene", _fast_scene)


def make_trigger(text: str = "DM Moonie died.", ttype: TriggerType = TriggerType.HOTKEY) -> Trigger:
    return Trigger(
        trigger_id=str(uuid.uuid4()),
        received_at=datetime.utcnow(),
        type=ttype,
        text=text,
        priority=TriggerPriority.NORMAL,
        cooldown_key=None,
        game=None,
    )


def mock_response(name: str, text: str = "Response.") -> CharacterResponse:
    return CharacterResponse(
        name=name,
        display_name=name.capitalize(),
        text=text,
        voice_id=f"PLACEHOLDER_{name.upper()}",
        provider="mock",
        latency_ms=100,
    )


@pytest.mark.asyncio
async def test_primary_always_delivered():
    """Scene must always contain at least the primary's response."""
    trigger = make_trigger()
    router_result = RouterResult(primary=["grokthar"], companions=[], method="rule", mode=ExecutionMode.SEQUENTIAL)

    with patch("party.orchestration.chain.call_character") as mock_call:
        mock_call.return_value = mock_response("grokthar")
        responses = [r async for r in run_chain(trigger, router_result)]

    assert len(responses) >= 1
    assert responses[0].name == "grokthar"


@pytest.mark.asyncio
async def test_companion_skipped_when_budget_exceeded():
    """If primary call exceeds the latency budget, companion is skipped."""
    trigger = make_trigger(ttype=TriggerType.CHAT_TRIGGER)
    budget_ms = _get_budget(TriggerType.CHAT_TRIGGER)
    router_result = RouterResult(primary=["grokthar"], companions=["geptima"],
                                 method="rule", mode=ExecutionMode.SEQUENTIAL)

    async def slow_primary(character, snapshot, messages, **kwargs):
        # Simulate primary taking longer than budget
        await asyncio.sleep((budget_ms + 200) / 1000)
        return mock_response(character.name)

    with patch("party.orchestration.chain.call_character", side_effect=slow_primary):
        responses = [r async for r in run_chain(trigger, router_result)]

    # Only primary should have responded
    assert len(responses) == 1
    assert responses[0].name == "grokthar"


@pytest.mark.asyncio
async def test_parallel_companion_timeout_handled_gracefully():
    """Parallel companion that times out should not raise; primary still delivered."""
    trigger = make_trigger(ttype=TriggerType.HOTKEY)
    budget_ms = _get_budget(TriggerType.HOTKEY)
    router_result = RouterResult(primary=["grokthar"], companions=["geptima"],
                                 method="rule", mode=ExecutionMode.PARALLEL)

    async def slow_for_companion(character, snapshot, messages, **kwargs):
        if character.name == "geptima":
            # Delay well beyond the remaining budget
            await asyncio.sleep((budget_ms + 1000) / 1000)
        return mock_response(character.name)

    with patch("party.orchestration.chain.call_character", side_effect=slow_for_companion):
        responses = [r async for r in run_chain(trigger, router_result)]

    # Primary should still come through
    assert any(r.name == "grokthar" for r in responses)


@pytest.mark.asyncio
async def test_parallel_fires_both_calls_simultaneously():
    """Parallel mode: total time should be close to the slower task, not their sum."""
    trigger = make_trigger(ttype=TriggerType.HOTKEY)
    router_result = RouterResult(primary=["grokthar"], companions=["geptima"],
                                 method="rule", mode=ExecutionMode.PARALLEL)
    delay = 0.25  # 250ms each

    async def delayed(character, snapshot, messages, **kwargs):
        await asyncio.sleep(delay)
        return mock_response(character.name)

    with patch("party.orchestration.chain.call_character", side_effect=delayed):
        start = time.perf_counter()
        responses = [r async for r in run_chain(trigger, router_result)]
        elapsed = time.perf_counter() - start

    # Sequential would take ~0.5s; parallel should be ~0.25s + overhead
    assert elapsed < delay * 1.8, f"Expected ~{delay}s parallel, got {elapsed:.2f}s"
    assert len(responses) == 2


@pytest.mark.asyncio
async def test_sequential_companion_receives_primary_response():
    """In sequential mode, companion context must contain primary's response text."""
    trigger = make_trigger(ttype=TriggerType.CHAT_TRIGGER)
    router_result = RouterResult(primary=["grokthar"], companions=["geptima"],
                                 method="rule", mode=ExecutionMode.SEQUENTIAL)
    calls = []

    async def capture(character, snapshot, messages, **kwargs):
        calls.append((character.name, messages))
        if character.name == "grokthar":
            return mock_response("grokthar", "Death is just a setback.")
        return mock_response("geptima", "Indeed.")

    with patch("party.orchestration.chain.call_character", side_effect=capture):
        responses = [r async for r in run_chain(trigger, router_result)]

    assert len(responses) == 2
    companion_content = calls[1][1][0]["content"]
    assert "Death is just a setback" in companion_content
