"""
Sprint 13 tests — housekeeping fixes and event expansion.
"""
import pytest
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_trigger(ttype, text="Test", viewer=None):
    from party.models import Trigger, TriggerType, TriggerPriority
    return Trigger(
        trigger_id=str(uuid.uuid4()),
        received_at=datetime.utcnow(),
        type=ttype,
        text=text,
        priority=TriggerPriority.NORMAL,
        cooldown_key=None,
        game=None,
        viewer=viewer,
    )


def make_warm():
    from party.orchestration.context import WarmContext
    return WarmContext(
        timestamp="", scene="Gaming", session="",
        vision_current="", vision_recent=[], stream_feats="",
        key_events=[], viewer_context="",
    )


# ── Task 13.1 — build_primary_message VIEWER_EVENT framing ───────────────────

def test_build_primary_message_viewer_event_uses_stream_event_framing():
    """VIEWER_EVENT triggers must use 'Stream event:' not 'Moonie said:'."""
    from party.orchestration.context import build_primary_message
    from party.models import TriggerType
    trigger = make_trigger(TriggerType.VIEWER_EVENT, "First chatter! Welcome MoonFan.")
    messages = build_primary_message(trigger, make_warm())
    content = messages[0]["content"]
    assert content.startswith("Stream event:")
    assert "Moonie said" not in content


def test_build_primary_message_system_uses_system_event_framing():
    """SYSTEM triggers must still use 'System event:' framing."""
    from party.orchestration.context import build_primary_message
    from party.models import TriggerType
    trigger = make_trigger(TriggerType.SYSTEM, "Moonie just died.")
    messages = build_primary_message(trigger, make_warm())
    assert messages[0]["content"].startswith("System event:")


def test_build_primary_message_hotkey_uses_moonie_said():
    """Non-system, non-viewer triggers must still use 'Moonie said:'."""
    from party.orchestration.context import build_primary_message
    from party.models import TriggerType
    trigger = make_trigger(TriggerType.HOTKEY, "Moonie just got a kill.")
    messages = build_primary_message(trigger, make_warm())
    assert messages[0]["content"].startswith("Moonie said:")


# ── Companion framing fix (extension of 13.1) ────────────────────────────────

def test_build_companion_sequential_message_viewer_event_uses_stream_event_framing():
    """VIEWER_EVENT companion must also use 'Stream event:' not 'Moonie said:'."""
    from party.orchestration.context import build_companion_sequential_message
    from party.models import TriggerType
    trigger = make_trigger(TriggerType.VIEWER_EVENT, "First chatter! Welcome MoonFan.")
    messages = build_companion_sequential_message(trigger, make_warm(), "Clauven", "Welcome!")
    content = messages[0]["content"]
    assert "Stream event:" in content
    assert "Moonie said" not in content


# ── Task 13.2 — Gemaux token limit ───────────────────────────────────────────

def test_gemaux_max_output_tokens_matches_anthropic_and_openai():
    """Gemaux must use max_output_tokens=600, matching Anthropic and OpenAI."""
    import inspect
    import party.providers.gemini as gemini_mod
    source = inspect.getsource(gemini_mod)
    assert "max_output_tokens=1024" not in source
    assert "max_output_tokens=600" in source


# ── Task 13.3 — event_data on IncomingTrigger ────────────────────────────────

def test_incoming_trigger_accepts_event_data():
    """IncomingTrigger must accept an event_data dict."""
    from party.models import IncomingTrigger
    payload = {
        "type": "system",
        "text": "Raid incoming.",
        "viewer": "RaiderXYZ",
        "event_data": {"raider": True, "last_raid_viewers": 42},
    }
    trigger = IncomingTrigger.model_validate(payload)
    assert trigger.event_data == {"raider": True, "last_raid_viewers": 42}


def test_incoming_trigger_event_data_defaults_none():
    from party.models import IncomingTrigger
    t = IncomingTrigger.model_validate({"type": "hotkey", "text": "Test."})
    assert t.event_data is None


# ── Task 13.4 — intake updates memory for system triggers with viewer ─────────

@pytest.mark.asyncio
async def test_system_trigger_with_viewer_updates_memory():
    """A system trigger carrying a viewer field must update viewer memory."""
    from party.intake.server import handle_message

    async def mock_enqueue(trigger): pass

    payload = '''{
        "type": "system",
        "text": "Raider has arrived.",
        "viewer": "RaiderXYZ",
        "viewer_id": "99999",
        "event_data": {"raider": true, "last_raid_viewers": 42}
    }'''

    with patch("party.context.viewer_memory.update_viewer", new=AsyncMock()) as mock_update:
        await handle_message(payload, mock_enqueue)

    mock_update.assert_called_once()
    args = mock_update.call_args[0]
    assert args[0] == "RaiderXYZ"
    assert args[1].get("raider") is True
    assert args[1].get("last_raid_viewers") == 42


@pytest.mark.asyncio
async def test_system_trigger_without_viewer_does_not_update_memory():
    """A system trigger with no viewer field must not update viewer memory."""
    from party.intake.server import handle_message

    async def mock_enqueue(trigger): pass

    payload = '{"type": "system", "text": "Something happened."}'

    with patch("party.context.viewer_memory.update_viewer", new=AsyncMock()) as mock_update:
        await handle_message(payload, mock_enqueue)

    mock_update.assert_not_called()


# ── Task 13.5 — expanded format_viewer_context ───────────────────────────────

def test_format_viewer_context_raider():
    from party.context.viewer_memory import format_viewer_context
    data = {"raider": True, "last_raid_viewers": 47}
    result = format_viewer_context(data, "RaiderXYZ")
    assert "RaiderXYZ" in result
    assert "raided" in result.lower()


def test_format_viewer_context_subscriber():
    from party.context.viewer_memory import format_viewer_context
    data = {"subscriber": True, "sub_tier": "tier 1", "sub_months": 14}
    result = format_viewer_context(data, "LoyalFan")
    assert "LoyalFan" in result
    assert "14" in result
    assert "subscri" in result.lower()


def test_format_viewer_context_gifted_sub():
    from party.context.viewer_memory import format_viewer_context
    data = {"gifted_sub": True, "gifted_tier": "tier 1"}
    result = format_viewer_context(data, "LuckyViewer")
    assert "LuckyViewer" in result
    assert "gift" in result.lower()


def test_format_viewer_context_empty_returns_empty():
    from party.context.viewer_memory import format_viewer_context
    result = format_viewer_context({}, "NoOneKnows")
    assert result == ""


def test_format_viewer_context_combined_raider_and_chatter():
    from party.context.viewer_memory import format_viewer_context
    data = {"raider": True, "last_raid_viewers": 20, "firsts": 3, "level": 8}
    result = format_viewer_context(data, "FriendlyStreamer")
    assert "FriendlyStreamer" in result
    assert "raided" in result.lower()
