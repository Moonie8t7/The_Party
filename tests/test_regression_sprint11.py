"""
Sprint 11 — Regression tests (Task 11.21).
Verify Sprint 11 has not broken any Sprint 1–10 behaviour.
"""
import pytest
import os
import json
from unittest.mock import patch, AsyncMock, MagicMock
from party.models import Trigger, TriggerType, TriggerPriority, CharacterResponse, CHARACTERS, Scene
from party.providers.base import ProviderError
import uuid
from datetime import datetime


def make_trigger(text: str = "Test.", ttype: TriggerType = TriggerType.HOTKEY) -> Trigger:
    return Trigger(
        trigger_id=str(uuid.uuid4()),
        received_at=datetime.utcnow(),
        type=ttype,
        text=text,
        priority=TriggerPriority.NORMAL,
        cooldown_key=None,
        game=None,
    )


def test_system_prompts_unchanged():
    """Character system prompts must contain expected personality markers."""
    expected_markers = {
        "clauven":   ["Clauven", "Wizard"],
        "geptima":   ["Geptima", "Cleric"],
        "gemaux":    ["Gemaux", "Bard"],
        "grokthar":  ["Grokthar", "Ranger"],
        "deepwilla": ["Deepwilla", "Artificer"],
    }
    prompts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")
    for character_name, markers in expected_markers.items():
        path = os.path.join(prompts_dir, f"{character_name}.txt")
        assert os.path.exists(path), f"Missing prompt file: {path}"
        content = open(path, encoding="utf-8").read()
        for marker in markers:
            assert marker in content, f"{character_name}.txt missing marker: {marker}"


def test_scene_data_model_intact():
    """Scene, Trigger, CharacterResponse must all serialise correctly."""
    trigger = make_trigger()
    response = CharacterResponse(
        name="grokthar",
        display_name="Grokthar",
        text="Death comes for us all.",
        voice_id="PLACEHOLDER",
        provider="grok",
        latency_ms=500,
    )
    scene = Scene(
        trigger=trigger,
        characters=["grokthar"],
        responses=[response],
        router_method="rule:0",
        total_latency_ms=500,
        error=None,
    )
    # Pydantic serialisation round-trip
    as_dict = scene.model_dump()
    assert as_dict["characters"] == ["grokthar"]
    assert as_dict["responses"][0]["name"] == "grokthar"
    assert as_dict["error"] is None


def test_tts_pipeline_not_touched():
    """TTS module must still contain the ElevenLabs generation and playback functions."""
    import inspect
    import party.output.tts as tts_module
    # These internal functions are the TTS pipeline — they must remain
    assert hasattr(tts_module, "_generate_audio")
    assert hasattr(tts_module, "_play_audio_bytes")
    assert hasattr(tts_module, "_placeholder_speak")


@pytest.mark.asyncio
async def test_overlay_broadcast_format_unchanged():
    """Overlay notify() must broadcast a JSON payload with the required event fields."""
    from party.output.obs import OverlayServer

    server = OverlayServer()
    sent_payloads = []

    async def fake_broadcast(payload):
        sent_payloads.append(json.loads(payload))

    server._broadcast_raw = fake_broadcast
    server._clients = {"fake_client"}
    await server.notify("speaking_start", "grokthar", text="Hello!", display_name="Grokthar")

    assert len(sent_payloads) == 1
    payload = sent_payloads[0]
    assert payload["event"] == "speaking_start"
    assert payload["character"] == "grokthar"
    # Required fields must be present
    assert "event" in payload
    assert "character" in payload


@pytest.mark.asyncio
async def test_router_result_is_router_result_type():
    """route_trigger() must return RouterResult, not list — Sprint 11 contract."""
    from party.orchestration.router import route_trigger, RouterResult
    trigger = make_trigger("DM Moonie died in combat.")
    result = await route_trigger(trigger)
    assert isinstance(result, RouterResult)
    assert hasattr(result, "primary")
    assert hasattr(result, "companions")
    assert hasattr(result, "method")
    assert hasattr(result, "mode")


def test_all_five_characters_present():
    """CHARACTERS dict must still contain all five party members."""
    required = {"clauven", "geptima", "gemaux", "grokthar", "deepwilla"}
    assert required == set(CHARACTERS.keys())


def test_all_providers_instantiate():
    """All five provider classes must instantiate without error."""
    from party.providers.anthropic import AnthropicProvider
    from party.providers.openai import OpenAIProvider
    from party.providers.gemini import GeminiProvider
    from party.providers.grok import GrokProvider
    from party.providers.deepseek import DeepSeekProvider
    # These are already instantiated in chain.py PROVIDERS — just re-instantiate to verify
    for cls in [AnthropicProvider, OpenAIProvider, GeminiProvider, GrokProvider, DeepSeekProvider]:
        instance = cls()
        assert instance is not None


def test_repair_still_works():
    """repair_response() must still strip violations and return RepairResult."""
    from party.orchestration.repair import repair_response
    result = repair_response("This is fine.", trigger_id="test", character_name="grokthar")
    assert result.text == "This is fine."
    assert result.repaired is False
