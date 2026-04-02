import pytest
from unittest.mock import AsyncMock, patch
from party.orchestration.router import route_trigger
from party.models import Trigger, TriggerType, TriggerPriority
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


@pytest.mark.asyncio
async def test_router_death_keywords():
    trigger = make_trigger("DM Moonie just died to a zombie horde.")
    result = await route_trigger(trigger)
    assert "grokthar" in result
    assert len(result) >= 2


@pytest.mark.asyncio
async def test_router_lore_keywords():
    trigger = make_trigger("DM Moonie is reading lore about an ancient civilisation.")
    result = await route_trigger(trigger)
    assert "clauven" in result


@pytest.mark.asyncio
async def test_router_combat_keywords():
    trigger = make_trigger("DM Moonie is fighting a massive boss.")
    result = await route_trigger(trigger)
    assert "grokthar" in result


@pytest.mark.asyncio
async def test_router_chat_keywords():
    trigger = make_trigger("A viewer in chat said something spicy.")
    result = await route_trigger(trigger)
    assert "grokthar" in result or "gemaux" in result


@pytest.mark.asyncio
async def test_router_technical_keywords():
    trigger = make_trigger("DM Moonie is trying to decide between two weapon upgrades.")
    result = await route_trigger(trigger)
    assert "deepwilla" in result


@pytest.mark.asyncio
async def test_router_llm_fallback_on_no_match():
    """Ambiguous trigger should use LLM fallback or default cast."""
    trigger = make_trigger("DM Moonie just stared at a wall for two minutes.")
    with patch(
        "party.orchestration.router._llm_route",
        new_callable=AsyncMock,
        return_value=["grokthar", "gemaux"],
    ):
        result = await route_trigger(trigger)
    assert len(result) >= 2
    for name in result:
        assert name in ["clauven", "geptima", "gemaux", "grokthar", "deepwilla"]


@pytest.mark.asyncio
async def test_router_default_cast_on_llm_failure():
    """If LLM fallback fails, return default cast."""
    trigger = make_trigger("Something completely ambiguous with no keywords.")
    with patch(
        "party.orchestration.router._llm_route",
        new_callable=AsyncMock,
        side_effect=Exception("LLM failed"),
    ):
        result = await route_trigger(trigger)
    assert result == ["grokthar", "gemaux"]


@pytest.mark.asyncio
async def test_router_returns_valid_character_names_only():
    """Router must never return a name not in CHARACTERS."""
    from party.models import CHARACTERS
    trigger = make_trigger("DM Moonie died in combat.")
    result = await route_trigger(trigger)
    for name in result:
        assert name in CHARACTERS
