import pytest
from unittest.mock import AsyncMock, MagicMock
from party.models import (
    Trigger, TriggerType, TriggerPriority,
    CharacterResponse, Scene, CHARACTERS
)
from party.config import settings
import uuid
from datetime import datetime


@pytest.fixture
def sample_trigger() -> Trigger:
    return Trigger(
        trigger_id=str(uuid.uuid4()),
        received_at=datetime.utcnow(),
        type=TriggerType.HOTKEY,
        text="DM Moonie just died to a zombie horde in 7 Days to Die.",
        priority=TriggerPriority.NORMAL,
        cooldown_key=None,
        game=None,
    )


@pytest.fixture
def chat_trigger() -> Trigger:
    return Trigger(
        trigger_id=str(uuid.uuid4()),
        received_at=datetime.utcnow(),
        type=TriggerType.CHAT_TRIGGER,
        text="A viewer in chat just said this game looks boring.",
        priority=TriggerPriority.LOW,
        cooldown_key="chat_boring",
        game=None,
    )


@pytest.fixture
def ambiguous_trigger() -> Trigger:
    return Trigger(
        trigger_id=str(uuid.uuid4()),
        received_at=datetime.utcnow(),
        type=TriggerType.HOTKEY,
        text="DM Moonie just stood completely still for two minutes staring at a wall.",
        priority=TriggerPriority.NORMAL,
        cooldown_key=None,
        game=None,
    )


@pytest.fixture
def mock_character_response() -> CharacterResponse:
    return CharacterResponse(
        name="grokthar",
        display_name="Grokthar",
        text="Told Moonie this would happen. Should've scouted first.",
        voice_id="PLACEHOLDER_GROKTHAR",
        provider="grok",
        latency_ms=450,
        repaired=False,
    )


@pytest.fixture
def mock_scene(sample_trigger, mock_character_response) -> Scene:
    return Scene(
        trigger=sample_trigger,
        characters=["grokthar", "geptima"],
        responses=[mock_character_response],
        router_method="rule",
        total_latency_ms=450,
        error=None,
    )
