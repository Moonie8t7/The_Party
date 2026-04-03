import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from party.orchestration.chain import run_chain, COMPANION_CLOSING, NORMAL_CLOSING
from party.orchestration.router import RouterResult
from party.orchestration.modes import ExecutionMode
from party.models import Trigger, TriggerType, TriggerPriority, CharacterResponse
from party.providers.base import ProviderError
import uuid
from datetime import datetime


@pytest.fixture(autouse=True)
def mock_scene(monkeypatch):
    """Prevent OBS WebSocket connection attempts in chain tests."""
    async def _fast_scene():
        return "Gaming"
    monkeypatch.setattr("party.context.obs_context.get_current_scene", _fast_scene)


def make_trigger(text: str, ttype: TriggerType = TriggerType.HOTKEY) -> Trigger:
    return Trigger(
        trigger_id=str(uuid.uuid4()),
        received_at=datetime.utcnow(),
        type=ttype,
        text=text,
        priority=TriggerPriority.NORMAL,
        cooldown_key=None,
        game=None,
    )


def make_result(
    primary: str,
    companions: list[str] = None,
    mode: ExecutionMode = ExecutionMode.SEQUENTIAL,
    method: str = "rule",
) -> RouterResult:
    return RouterResult(
        primary=[primary],
        companions=companions or [],
        method=method,
        mode=mode,
    )


def mock_response(name: str, display_name: str, text: str) -> CharacterResponse:
    return CharacterResponse(
        name=name,
        display_name=display_name,
        text=text,
        voice_id=f"PLACEHOLDER_{name.upper()}",
        provider="mock",
        latency_ms=100,
    )


@pytest.mark.asyncio
async def test_chain_returns_responses_for_all_characters():
    trigger = make_trigger("DM Moonie died.")
    router_result = make_result("grokthar", companions=["geptima"])

    with patch("party.orchestration.chain.call_character") as mock_call:
        mock_call.side_effect = [
            mock_response("grokthar", "Grokthar", "Told you so."),
            mock_response("geptima", "Geptima", "Right, so accidents happen."),
        ]
        responses = [r async for r in run_chain(trigger, router_result)]

    assert len(responses) == 2
    assert responses[0].name == "grokthar"
    assert responses[1].name == "geptima"


@pytest.mark.asyncio
async def test_chain_skips_failed_provider():
    """If primary provider fails, chain stops (no companion)."""
    trigger = make_trigger("DM Moonie died.")
    router_result = make_result("grokthar", companions=["geptima"])

    with patch("party.orchestration.chain.call_character") as mock_call:
        mock_call.side_effect = ProviderError("grok", "grokthar", "timeout")
        responses = [r async for r in run_chain(trigger, router_result)]

    assert responses == []


@pytest.mark.asyncio
async def test_chain_parallel_execution_for_system_trigger():
    """SYSTEM triggers run in parallel: total time should be ~max(task times), not sum."""
    trigger = make_trigger("Death", ttype=TriggerType.SYSTEM)
    router_result = RouterResult(
        primary=["grokthar"],
        companions=["geptima"],
        method="system",
        mode=ExecutionMode.PARALLEL,
    )

    async def side_effect_fn(character, snapshot, messages, **kwargs):
        if character.name == "geptima":
            await asyncio.sleep(0.2)
            return mock_response("geptima", "Geptima", "Oh no.")
        return mock_response("grokthar", "Grokthar", "DEAD.")

    with patch("party.orchestration.chain.call_character", side_effect=side_effect_fn):
        import time as _time
        start = _time.monotonic()
        responses = [r async for r in run_chain(trigger, router_result)]
        elapsed = _time.monotonic() - start

    assert elapsed < 0.5, f"Parallel should be ~0.2s, got {elapsed:.2f}s"
    assert len(responses) == 2


@pytest.mark.asyncio
async def test_chain_sequential_passes_primary_response_to_companion():
    """Sequential companion receives the primary's response text in its context."""
    trigger = make_trigger("DM Moonie died.", ttype=TriggerType.CHAT_TRIGGER)
    router_result = make_result("grokthar", companions=["geptima"], mode=ExecutionMode.SEQUENTIAL)
    calls = []

    async def capture_call(character, session_snapshot, messages, **kwargs):
        calls.append((character.name, messages))
        if character.name == "grokthar":
            return mock_response("grokthar", "Grokthar", "Told you so.")
        return mock_response("geptima", "Geptima", "Right, accidents happen.")

    with patch("party.orchestration.chain.call_character", side_effect=capture_call):
        responses = [r async for r in run_chain(trigger, router_result)]

    assert len(responses) == 2
    companion_content = calls[1][1][0]["content"]
    assert "Grokthar" in companion_content


@pytest.mark.asyncio
async def test_chain_applies_companion_closing_to_sequential_companion():
    """Sequential companion should receive COMPANION_CLOSING instruction."""
    trigger = make_trigger("How many times has Moonie died?", ttype=TriggerType.CHAT_TRIGGER)
    router_result = make_result("grokthar", companions=["geptima"], mode=ExecutionMode.SEQUENTIAL)
    calls = []

    async def capture_call(character, session_snapshot, messages, **kwargs):
        calls.append((character.name, messages))
        if character.name == "grokthar":
            return mock_response("grokthar", "Grokthar", "At least seven times.")
        return mock_response("geptima", "Geptima", "Statistically speaking...")

    with patch("party.orchestration.chain.call_character", side_effect=capture_call):
        responses = [r async for r in run_chain(trigger, router_result)]

    geptima_content = calls[1][1][0]["content"]
    assert "Now add a brief" in geptima_content


@pytest.mark.asyncio
async def test_chain_parallel_companion_does_not_receive_primary_response():
    """Parallel companion context must NOT include primary's response."""
    trigger = make_trigger("DM Moonie died.", ttype=TriggerType.HOTKEY)
    router_result = make_result("grokthar", companions=["geptima"], mode=ExecutionMode.PARALLEL)
    calls = []

    async def capture_call(character, session_snapshot, messages, **kwargs):
        calls.append((character.name, messages))
        if character.name == "grokthar":
            return mock_response("grokthar", "Grokthar", "Told you so.")
        return mock_response("geptima", "Geptima", "Ouch.")

    with patch("party.orchestration.chain.call_character", side_effect=capture_call):
        responses = [r async for r in run_chain(trigger, router_result)]

    companion_content = calls[1][1][0]["content"]
    assert "Grokthar" not in companion_content
    assert "Told you so" not in companion_content


@pytest.mark.asyncio
async def test_chain_returns_empty_if_all_providers_fail():
    """If the primary provider fails, the generator yields nothing."""
    trigger = make_trigger("DM Moonie died.")
    router_result = make_result("grokthar")

    with patch("party.orchestration.chain.call_character") as mock_call:
        mock_call.side_effect = ProviderError("grok", "grokthar", "timeout")
        responses = [r async for r in run_chain(trigger, router_result)]

    assert responses == []


@pytest.mark.asyncio
async def test_chain_no_companion_yields_only_primary():
    """With no companions in RouterResult, only primary speaks."""
    trigger = make_trigger("DM Moonie died.")
    router_result = make_result("grokthar", companions=[])

    with patch("party.orchestration.chain.call_character") as mock_call:
        mock_call.return_value = mock_response("grokthar", "Grokthar", "Told you so.")
        responses = [r async for r in run_chain(trigger, router_result)]

    assert len(responses) == 1
    assert responses[0].name == "grokthar"
