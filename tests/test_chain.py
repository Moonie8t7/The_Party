import pytest
from unittest.mock import AsyncMock, patch
from party.orchestration.chain import run_chain
from party.models import Trigger, TriggerType, TriggerPriority, CharacterResponse
from party.providers.base import ProviderError
import uuid
from datetime import datetime


def make_trigger(text: str) -> Trigger:
    return Trigger(
        trigger_id=str(uuid.uuid4()),
        received_at=datetime.utcnow(),
        type=TriggerType.HOTKEY,
        text=text,
        priority=TriggerPriority.NORMAL,
        cooldown_key=None,
        game=None,
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
    characters = ["grokthar", "geptima"]

    with patch("party.orchestration.chain.call_character") as mock_call:
        mock_call.side_effect = [
            mock_response("grokthar", "Grokthar", "Told you so."),
            mock_response("geptima", "Geptima", "Right, so accidents happen."),
        ]
        responses = await run_chain(trigger, characters)

    assert len(responses) == 2
    assert responses[0].name == "grokthar"
    assert responses[1].name == "geptima"


@pytest.mark.asyncio
async def test_chain_skips_failed_provider():
    """If one provider fails, the chain continues with remaining characters."""
    trigger = make_trigger("DM Moonie died.")
    characters = ["grokthar", "geptima", "deepwilla"]

    with patch("party.orchestration.chain.call_character") as mock_call:
        mock_call.side_effect = [
            mock_response("grokthar", "Grokthar", "Told you so."),
            ProviderError("openai", "geptima", "timeout"),
            mock_response("deepwilla", "Deepwilla", "Fascinating failure mode."),
        ]
        responses = await run_chain(trigger, characters)

    assert len(responses) == 2
    names = [r.name for r in responses]
    assert "grokthar" in names
    assert "deepwilla" in names
    assert "geptima" not in names


@pytest.mark.asyncio
async def test_chain_returns_empty_if_all_providers_fail():
    """If every provider fails, return empty list with no crash."""
    trigger = make_trigger("DM Moonie died.")
    characters = ["grokthar", "geptima"]

    with patch("party.orchestration.chain.call_character") as mock_call:
        mock_call.side_effect = [
            ProviderError("grok", "grokthar", "timeout"),
            ProviderError("openai", "geptima", "timeout"),
        ]
        responses = await run_chain(trigger, characters)

    assert responses == []


@pytest.mark.asyncio
async def test_chain_passes_context_to_subsequent_characters():
    """Second character's call should include first character's response."""
    trigger = make_trigger("DM Moonie died.")
    characters = ["grokthar", "geptima"]
    calls = []

    async def capture_call(character, messages):
        calls.append((character.name, messages))
        if character.name == "grokthar":
            return mock_response("grokthar", "Grokthar", "Told you so.")
        return mock_response("geptima", "Geptima", "Right, accidents happen.")

    with patch("party.orchestration.chain.call_character", side_effect=capture_call):
        await run_chain(trigger, characters)

    second_call_messages = calls[1][1]
    assert any("Grokthar" in str(m) for m in second_call_messages)


@pytest.mark.asyncio
async def test_chain_applies_companion_closing_to_companion_character():
    """Companion character should receive COMPANION_CLOSING, not NORMAL_CLOSING."""
    from party.orchestration.chain import COMPANION_CLOSING, NORMAL_CLOSING

    trigger = make_trigger("Grokthar: how many times has Moonie died now?")
    characters = ["grokthar", "geptima"]
    calls = []

    async def capture_call(character, messages):
        calls.append((character.name, messages))
        if character.name == "grokthar":
            return mock_response("grokthar", "Grokthar", "At least seven times.")
        return mock_response("geptima", "Geptima", "Statistically speaking...")

    with patch("party.orchestration.chain.call_character", side_effect=capture_call):
        await run_chain(trigger, characters, companion_characters={"geptima"})

    # Grokthar's call uses the initial context (no closing instruction)
    grokthar_content = calls[0][1][0]["content"]
    assert "brief unrequested side comment" not in grokthar_content

    # Geptima's call should use COMPANION_CLOSING
    geptima_content = calls[1][1][0]["content"]
    assert "brief unrequested side comment" in geptima_content
    assert "Now respond as your character" not in geptima_content


@pytest.mark.asyncio
async def test_chain_applies_normal_closing_when_no_companion_set():
    """Without companion_characters, all characters get NORMAL_CLOSING."""
    trigger = make_trigger("DM Moonie died.")
    characters = ["grokthar", "geptima"]
    calls = []

    async def capture_call(character, messages):
        calls.append((character.name, messages))
        if character.name == "grokthar":
            return mock_response("grokthar", "Grokthar", "Told you so.")
        return mock_response("geptima", "Geptima", "Right, accidents happen.")

    with patch("party.orchestration.chain.call_character", side_effect=capture_call):
        await run_chain(trigger, characters, companion_characters=None)

    geptima_content = calls[1][1][0]["content"]
    assert "Now respond as your character" in geptima_content
    assert "brief unrequested side comment" not in geptima_content
