"""
Tests for viewer_event intake handling (Sprint 12).
"""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_viewer_event_passes_viewer_field_to_trigger():
    """viewer field from payload must appear on the enqueued Trigger."""
    from party.intake.server import handle_message

    enqueued = []
    async def mock_enqueue(trigger):
        enqueued.append(trigger)

    payload = '{"type": "viewer_event", "text": "First chatter!", "viewer": "MoonFan"}'
    with patch("party.context.viewer_memory.update_viewer", new=AsyncMock()):
        await handle_message(payload, mock_enqueue)

    assert len(enqueued) == 1
    assert enqueued[0].viewer == "MoonFan"


@pytest.mark.asyncio
async def test_viewer_memory_updated_on_viewer_event():
    """update_viewer must be called when a viewer_event is received."""
    from party.intake.server import handle_message

    async def mock_enqueue(trigger): pass

    payload = '''{
        "type": "viewer_event",
        "text": "First chatter!",
        "viewer": "MoonFan",
        "viewer_id": "12345",
        "rank": 1,
        "history": {"firsts": 3, "seconds": 1, "thirds": 0},
        "level": 7,
        "xp": 42000,
        "roll": {"value": 15, "type": "normal"}
    }'''

    with patch("party.context.viewer_memory.update_viewer", new=AsyncMock()) as mock_update:
        await handle_message(payload, mock_enqueue)

    mock_update.assert_called_once()
    call_args = mock_update.call_args
    assert call_args[0][0] == "MoonFan"
    data = call_args[0][1]
    assert data.get("firsts") == 3
    assert data.get("level") == 7


@pytest.mark.asyncio
async def test_non_viewer_event_does_not_update_memory():
    """update_viewer must NOT be called for non-viewer_event triggers."""
    from party.intake.server import handle_message

    async def mock_enqueue(trigger): pass

    payload = '{"type": "hotkey", "text": "Moonie just died."}'
    with patch("party.context.viewer_memory.update_viewer", new=AsyncMock()) as mock_update:
        await handle_message(payload, mock_enqueue)

    mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_viewer_event_without_viewer_field_still_enqueued():
    """A viewer_event with no viewer field must still be enqueued (graceful)."""
    from party.intake.server import handle_message

    enqueued = []
    async def mock_enqueue(trigger):
        enqueued.append(trigger)

    payload = '{"type": "viewer_event", "text": "Something happened."}'
    with patch("party.context.viewer_memory.update_viewer", new=AsyncMock()):
        await handle_message(payload, mock_enqueue)

    assert len(enqueued) == 1
    assert enqueued[0].viewer is None


@pytest.mark.asyncio
async def test_extra_fields_in_payload_do_not_cause_rejection():
    """Unknown extra fields in the payload must be silently ignored."""
    from party.intake.server import handle_message

    enqueued = []
    async def mock_enqueue(trigger):
        enqueued.append(trigger)

    payload = '{"type": "hotkey", "text": "Test.", "unknown_field": "ignored", "another": 42}'
    await handle_message(payload, mock_enqueue)

    assert len(enqueued) == 1


def test_viewer_event_in_trigger_type_enum():
    """VIEWER_EVENT must exist in TriggerType."""
    from party.models import TriggerType
    assert TriggerType.VIEWER_EVENT == "viewer_event"


def test_trigger_has_viewer_field():
    """Trigger model must accept a viewer field."""
    from party.models import Trigger, TriggerType, TriggerPriority
    import uuid
    from datetime import datetime
    t = Trigger(
        trigger_id=str(uuid.uuid4()),
        received_at=datetime.utcnow(),
        type=TriggerType.VIEWER_EVENT,
        text="First chatter!",
        priority=TriggerPriority.NORMAL,
        cooldown_key=None,
        game=None,
        viewer="MoonFan",
    )
    assert t.viewer == "MoonFan"
