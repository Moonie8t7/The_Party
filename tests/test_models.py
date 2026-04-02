import pytest
from pydantic import ValidationError
from party.models import IncomingTrigger, TriggerType, Trigger, TriggerPriority, CharacterResponse
import uuid
from datetime import datetime


def test_incoming_trigger_valid():
    t = IncomingTrigger(type="hotkey", text="DM Moonie died.")
    assert t.type == TriggerType.HOTKEY
    assert t.text == "DM Moonie died."


def test_incoming_trigger_rejects_empty_text():
    with pytest.raises(ValidationError):
        IncomingTrigger(type="hotkey", text="")


def test_incoming_trigger_rejects_oversized_text():
    with pytest.raises(ValidationError):
        IncomingTrigger(type="hotkey", text="A" * 1001)


def test_incoming_trigger_rejects_invalid_type():
    with pytest.raises(ValidationError):
        IncomingTrigger(type="invalid_type", text="Something happened.")


def test_incoming_trigger_rejects_missing_fields():
    with pytest.raises(ValidationError):
        IncomingTrigger(text="Something happened.")  # missing type


def test_character_response_has_required_fields():
    r = CharacterResponse(
        name="grokthar",
        display_name="Grokthar",
        text="Told you so.",
        voice_id="PLACEHOLDER_GROKTHAR",
        provider="grok",
        latency_ms=300,
    )
    assert r.repaired is False


def test_trigger_assigns_id_automatically():
    t = Trigger(
        type=TriggerType.HOTKEY,
        text="Something happened.",
        priority=TriggerPriority.NORMAL,
        cooldown_key=None,
        game=None,
    )
    assert len(t.trigger_id) > 0
    assert t.received_at is not None


def test_characters_dict_has_five_entries():
    from party.models import CHARACTERS
    assert len(CHARACTERS) == 5
    for name in ["clauven", "geptima", "gemaux", "grokthar", "deepwilla"]:
        assert name in CHARACTERS
        assert CHARACTERS[name].provider_type in [
            "anthropic", "openai", "gemini", "grok", "deepseek"
        ]


def test_context_supplement_contains_party_overview():
    """All characters should have party overview in their context."""
    from party.models import CHARACTERS
    for name, character in CHARACTERS.items():
        assert "THE PARTY" in character.context_supplement or \
               character.context_supplement == "", \
               f"{name} missing party overview in context_supplement"


def test_context_supplement_contains_moonie_context():
    """All characters should have Moonie context."""
    from party.models import CHARACTERS
    for name, character in CHARACTERS.items():
        assert "WatchMoonie" in character.context_supplement or \
               character.context_supplement == "", \
               f"{name} missing moonie context in context_supplement"

