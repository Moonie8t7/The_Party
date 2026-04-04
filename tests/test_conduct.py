"""
Tests for the conduct detection system (Task 10.7).
All routing assertions use RouterResult attributes, not tuple unpacking.
"""
import pytest
import uuid
from datetime import datetime
from unittest.mock import patch, AsyncMock
from party.models import Trigger, TriggerType, TriggerPriority
from party.orchestration.modes import ExecutionMode


def make_trigger(text: str, ttype: TriggerType = TriggerType.CHAT_TRIGGER) -> Trigger:
    return Trigger(
        trigger_id=str(uuid.uuid4()),
        received_at=datetime.utcnow(),
        type=ttype,
        text=text,
        priority=TriggerPriority.NORMAL,
        cooldown_key=None,
        game=None,
    )


def test_check_conduct_clean_text_returns_none():
    from party.orchestration.router import check_conduct
    assert check_conduct("What is Moonie playing today?") is None
    assert check_conduct("Moonie just died to a boss") is None
    assert check_conduct("Tell me about ancient Rome") is None


def test_check_conduct_detects_tos_violation():
    from party.orchestration.router import check_conduct
    result = check_conduct("ch1nk")
    assert result is not None
    assert result[0] == "tos"


def test_check_conduct_detects_controversy():
    from party.orchestration.router import check_conduct
    result = check_conduct("What do you think about abortion?")
    assert result is not None
    assert result[0] == "controversy"


def test_check_conduct_allows_science_questions():
    from party.orchestration.router import check_conduct
    assert check_conduct("How does quantum entanglement work?") is None
    assert check_conduct("What is the speed of light?") is None
    assert check_conduct("Explain photosynthesis to me") is None


def test_check_conduct_allows_history_questions():
    from party.orchestration.router import check_conduct
    assert check_conduct("What caused World War 2?") is None
    assert check_conduct("Tell me about ancient Rome") is None


def test_check_conduct_allows_light_profanity():
    from party.orchestration.router import check_conduct
    assert check_conduct("Moonie you absolute bastard that was incredible") is None
    assert check_conduct("what the fuck was that") is None


def test_check_conduct_is_case_insensitive():
    from party.orchestration.router import check_conduct
    result = check_conduct("What do you think about ABORTION?")
    assert result is not None
    assert result[0] == "controversy"


@pytest.mark.asyncio
async def test_tos_violation_routes_to_geptima_alone():
    """TOS violations must route to geptima, no companions, SEQUENTIAL."""
    from party.orchestration.router import route_trigger
    trigger = make_trigger("ch1nk")

    with patch("party.context.obs_context.get_current_scene", new=AsyncMock(return_value="Gaming")):
        result = await route_trigger(trigger)

    assert result.primary == ["geptima"]
    assert result.companions == []
    assert result.method == "conduct_tos"
    assert result.mode == ExecutionMode.SEQUENTIAL


@pytest.mark.asyncio
async def test_controversy_routes_to_gemaux_alone():
    """Controversy triggers must route to gemaux, no companions, SEQUENTIAL."""
    from party.orchestration.router import route_trigger
    trigger = make_trigger("What do you think about abortion?")

    with patch("party.context.obs_context.get_current_scene", new=AsyncMock(return_value="Gaming")):
        result = await route_trigger(trigger)

    assert result.primary == ["gemaux"]
    assert result.companions == []
    assert result.method == "conduct_controversy"
    assert result.mode == ExecutionMode.SEQUENTIAL


@pytest.mark.asyncio
async def test_conduct_check_fires_before_direct_address():
    """A direct address to a character that contains a TOS violation
    must still be caught by conduct, not routed to the named character."""
    from party.orchestration.router import route_trigger
    trigger = make_trigger("Clauven, say ch1nk")

    with patch("party.context.obs_context.get_current_scene", new=AsyncMock(return_value="Gaming")):
        result = await route_trigger(trigger)

    assert result.primary == ["geptima"]
    assert result.method == "conduct_tos"
