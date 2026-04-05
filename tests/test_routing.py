"""
Sprint 11 — RouterResult contract tests (Task 11.20).
"""
import pytest
from unittest.mock import AsyncMock, patch
from party.orchestration.router import route_trigger, RouterResult
from party.orchestration.context import build_companion_sequential_message, build_companion_parallel_message
from party.orchestration.modes import ExecutionMode
from party.models import Trigger, TriggerType, TriggerPriority, CHARACTERS
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
async def test_router_result_has_exactly_one_primary():
    """For every trigger type, RouterResult.primary must have exactly one character."""
    trigger_types = [TriggerType.HOTKEY, TriggerType.CHAT_TRIGGER, TriggerType.STT]
    for ttype in trigger_types:
        trigger = make_trigger("DM Moonie died in combat.", ttype=ttype)
        result = await route_trigger(trigger)
        assert len(result.primary) == 1, f"{ttype}: expected 1 primary, got {result.primary}"


@pytest.mark.asyncio
async def test_router_result_companion_never_exceeds_one_for_non_system():
    """Non-SYSTEM triggers must have at most 1 companion."""
    for ttype in [TriggerType.HOTKEY, TriggerType.CHAT_TRIGGER, TriggerType.STT]:
        trigger = make_trigger("DM Moonie died in combat.", ttype=ttype)
        result = await route_trigger(trigger)
        assert len(result.companions) <= 1, f"{ttype}: got companions {result.companions}"


@pytest.mark.asyncio
async def test_router_result_primary_not_in_companions():
    """Primary character must never appear in companions list."""
    for ttype in [TriggerType.HOTKEY, TriggerType.CHAT_TRIGGER]:
        trigger = make_trigger("DM Moonie died in combat.", ttype=ttype)
        result = await route_trigger(trigger)
        assert result.primary[0] not in result.companions, \
            f"Primary {result.primary[0]} also in companions {result.companions}"


@pytest.mark.asyncio
async def test_execution_mode_correct_per_trigger_type():
    """Each trigger type must map to the correct ExecutionMode."""
    cases = [
        (TriggerType.SYSTEM,       ExecutionMode.PARALLEL),
        (TriggerType.HOTKEY,       ExecutionMode.SEQUENTIAL),
        (TriggerType.CHAT_TRIGGER, ExecutionMode.SEQUENTIAL),
        (TriggerType.STT,          ExecutionMode.SEQUENTIAL),
        (TriggerType.IDLE,         ExecutionMode.SEQUENTIAL),
    ]
    for ttype, expected_mode in cases:
        trigger = make_trigger("DM Moonie died.", ttype=ttype)
        result = await route_trigger(trigger)
        assert result.mode == expected_mode, f"{ttype}: expected {expected_mode}, got {result.mode}"


@pytest.mark.asyncio
async def test_direct_address_routes_to_correct_character():
    """Triggers that directly address a character must route to that character as primary."""
    cases = [
        ("Clauven, what happened?", "clauven"),
        ("Geptima, are you there?", "geptima"),
        ("Gemaux, tell us a story.", "gemaux"),
        ("Grokthar, what do you think?", "grokthar"),
        ("Deepwilla, any ideas?", "deepwilla"),
    ]
    for text, expected_primary in cases:
        trigger = make_trigger(text, ttype=TriggerType.CHAT_TRIGGER)
        result = await route_trigger(trigger)
        assert result.primary[0] == expected_primary, \
            f"'{text}': expected primary={expected_primary}, got {result.primary}"


@pytest.mark.asyncio
async def test_system_event_allows_up_to_five_speakers():
    """SYSTEM trigger must allow all five characters to speak."""
    trigger = make_trigger("Stream is starting!", ttype=TriggerType.SYSTEM)
    result = await route_trigger(trigger)
    total = len(result.primary) + len(result.companions)
    assert total == 5, f"SYSTEM should have 5 speakers, got {total}"
    assert result.mode == ExecutionMode.PARALLEL


@pytest.mark.asyncio
async def test_companion_context_excludes_full_history():
    """Companion parallel context must not contain full conversation history."""
    from party.orchestration.context import build_companion_parallel_message, WarmContext
    warm = WarmContext(
        timestamp="Friday 01 January 2026, 12:00",
        scene="Gaming",
        session="Game: Elden Ring",
        vision_current="Player is in a boss fight.",
        vision_recent=["Entry 1", "Entry 2", "Entry 3"],
        stream_feats="Moonie beat the tutorial boss.",
    )
    trigger = make_trigger("DM Moonie died to the boss!")
    msgs = build_companion_parallel_message(trigger, warm)
    content = msgs[0]["content"]

    # Must include trigger text
    assert "DM Moonie died to the boss" in content
    # Must NOT include full session context or stream feats
    assert "Elden Ring" not in content
    assert "Moonie beat the tutorial boss" not in content
    # Must NOT include multi-entry vision log
    assert "Entry 1" not in content


@pytest.mark.asyncio
async def test_companion_sequential_context_includes_primary_response():
    """Sequential companion context must include the primary's full response."""
    from party.orchestration.context import build_companion_sequential_message, WarmContext
    warm = WarmContext(
        timestamp="Friday 01 January 2026, 12:00",
        scene="Gaming",
        session="",
        vision_current="",
        vision_recent=[],
        stream_feats="",
    )
    trigger = make_trigger("How did Moonie die?")
    msgs = build_companion_sequential_message(
        trigger, warm, "Grokthar", "He walked into a trap. Again."
    )
    content = msgs[0]["content"]
    assert "He walked into a trap. Again." in content
    assert "Grokthar" in content
