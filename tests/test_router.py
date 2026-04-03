import pytest
from unittest.mock import AsyncMock, patch
from party.orchestration.router import route_trigger, RouterResult
from party.orchestration.modes import ExecutionMode
from party.models import Trigger, TriggerType, TriggerPriority
import uuid
from datetime import datetime


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


@pytest.mark.asyncio
async def test_router_death_keywords():
    trigger = make_trigger("DM Moonie just died to a zombie horde.")
    result = await route_trigger(trigger)
    assert isinstance(result, RouterResult)
    assert "grokthar" in result.primary + result.companions
    assert len(result.primary) == 1


@pytest.mark.asyncio
async def test_router_lore_keywords():
    trigger = make_trigger("DM Moonie is reading lore about an ancient civilisation.")
    result = await route_trigger(trigger)
    assert isinstance(result, RouterResult)
    assert "clauven" in result.primary + result.companions


@pytest.mark.asyncio
async def test_router_combat_keywords():
    trigger = make_trigger("DM Moonie is fighting a massive boss.")
    result = await route_trigger(trigger)
    assert isinstance(result, RouterResult)
    assert "grokthar" in result.primary + result.companions


@pytest.mark.asyncio
async def test_router_chat_keywords():
    trigger = make_trigger("A viewer in chat said something spicy.")
    result = await route_trigger(trigger)
    all_chars = result.primary + result.companions
    assert "grokthar" in all_chars or "gemaux" in all_chars


@pytest.mark.asyncio
async def test_router_technical_keywords():
    trigger = make_trigger("DM Moonie is trying to decide between two weapon upgrades.")
    result = await route_trigger(trigger)
    assert "deepwilla" in result.primary + result.companions


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
    assert isinstance(result, RouterResult)
    assert len(result.primary) == 1
    for name in result.primary + result.companions:
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
    assert result.primary == ["grokthar"]
    assert result.companions == ["gemaux"]
    assert result.method == "default"


@pytest.mark.asyncio
async def test_router_returns_valid_character_names_only():
    """Router must never return a name not in CHARACTERS."""
    from party.models import CHARACTERS
    trigger = make_trigger("DM Moonie died in combat.")
    result = await route_trigger(trigger)
    for name in result.primary + result.companions:
        assert name in CHARACTERS


@pytest.mark.asyncio
async def test_router_result_has_exactly_one_primary():
    """RouterResult.primary must always have exactly one character."""
    for ttype in [TriggerType.HOTKEY, TriggerType.CHAT_TRIGGER, TriggerType.STT]:
        trigger = make_trigger("DM Moonie died in combat.", ttype=ttype)
        result = await route_trigger(trigger)
        assert len(result.primary) == 1, f"Expected 1 primary for {ttype}, got {result.primary}"


@pytest.mark.asyncio
async def test_router_result_primary_not_in_companions():
    """Primary character must never also be in companions."""
    trigger = make_trigger("DM Moonie died in combat.")
    result = await route_trigger(trigger)
    assert result.primary[0] not in result.companions


@pytest.mark.asyncio
async def test_router_execution_mode_hotkey_is_parallel():
    trigger = make_trigger("DM Moonie died.", ttype=TriggerType.HOTKEY)
    result = await route_trigger(trigger)
    assert result.mode == ExecutionMode.PARALLEL


@pytest.mark.asyncio
async def test_router_execution_mode_chat_is_sequential():
    trigger = make_trigger("DM Moonie died.", ttype=TriggerType.CHAT_TRIGGER)
    result = await route_trigger(trigger)
    assert result.mode == ExecutionMode.SEQUENTIAL


@pytest.mark.asyncio
async def test_router_execution_mode_stt_is_sequential():
    trigger = make_trigger("DM Moonie died.", ttype=TriggerType.STT)
    result = await route_trigger(trigger)
    assert result.mode == ExecutionMode.SEQUENTIAL


@pytest.mark.asyncio
async def test_router_stt_has_no_companion():
    """STT triggers must never get a companion."""
    # Run several times to overcome randomness
    for _ in range(10):
        trigger = make_trigger("DM Moonie died in combat.", ttype=TriggerType.STT)
        result = await route_trigger(trigger)
        assert result.companions == [], f"STT trigger got companion: {result.companions}"


@pytest.mark.asyncio
async def test_router_system_has_all_five_speakers():
    """SYSTEM triggers should include all five characters."""
    trigger = make_trigger("Stream is going live!", ttype=TriggerType.SYSTEM)
    result = await route_trigger(trigger)
    all_chars = result.primary + result.companions
    assert len(all_chars) == 5
    assert result.mode == ExecutionMode.PARALLEL
