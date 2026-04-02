import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from party.output import tts
from party.models import CharacterVoiceSettings, CHARACTERS


@pytest.mark.asyncio
async def test_placeholder_speak_when_no_api_key():
    """With no API key, speak() should use placeholder."""
    with patch("party.output.tts.settings") as mock_settings:
        mock_settings.elevenlabs_api_key = ""
        with patch("party.output.tts._placeholder_speak", new_callable=AsyncMock) as mock_placeholder:
            await tts.speak("Hello world.", "PLACEHOLDER_VOICE", "grokthar")
            mock_placeholder.assert_called_once_with("Hello world.", "grokthar")


@pytest.mark.asyncio
async def test_elevenlabs_called_when_api_key_set():
    """With an API key, speak() should call ElevenLabs path."""
    with patch("party.output.tts.settings") as mock_settings:
        mock_settings.elevenlabs_api_key = "test_key"
        mock_settings.elevenlabs_model_id = "eleven_turbo_v2_5"
        mock_settings.elevenlabs_stability = 0.5
        mock_settings.elevenlabs_similarity_boost = 0.75
        with patch("party.output.tts._elevenlabs_speak", new_callable=AsyncMock) as mock_el:
            vs = CharacterVoiceSettings()
            await tts.speak("Hello world.", "test_voice_id", "grokthar", vs)
            mock_el.assert_called_once_with("Hello world.", "test_voice_id", "grokthar", vs)


@pytest.mark.asyncio
async def test_elevenlabs_failure_falls_back_to_placeholder():
    """If ElevenLabs raises, fall back to placeholder without crashing."""
    with patch("party.output.tts.settings") as mock_settings:
        mock_settings.elevenlabs_api_key = "test_key"
        with patch(
            "party.output.tts._elevenlabs_speak",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ):
            with patch("party.output.tts._placeholder_speak", new_callable=AsyncMock) as mock_placeholder:
                await tts.speak("Hello world.", "test_voice_id", "grokthar")
                mock_placeholder.assert_called_once()


@pytest.mark.asyncio
async def test_placeholder_duration_scales_with_word_count():
    """Placeholder sleep should scale with word count."""
    slept = []

    async def mock_sleep(duration):
        slept.append(duration)

    with patch("asyncio.sleep", side_effect=mock_sleep):
        with patch("party.output.tts.settings") as mock_settings:
            mock_settings.elevenlabs_api_key = ""
            await tts._placeholder_speak("one two three four five", "grokthar")

    assert len(slept) == 1
    assert slept[0] == pytest.approx(5 * 0.4)


@pytest.mark.asyncio
async def test_speak_never_raises():
    """speak() must never raise regardless of what happens inside."""
    with patch("party.output.tts.settings") as mock_settings:
        mock_settings.elevenlabs_api_key = "test_key"
        with patch(
            "party.output.tts._elevenlabs_speak",
            new_callable=AsyncMock,
            side_effect=RuntimeError("catastrophic failure"),
        ):
            with patch("party.output.tts._placeholder_speak", new_callable=AsyncMock):
                await tts.speak("Test.", "voice_id", "clauven")


# ============================================================
# Sprint 3b - Voice settings tests
# ============================================================

def test_voice_settings_defaults():
    """Default CharacterVoiceSettings has correct values."""
    vs = CharacterVoiceSettings()
    assert vs.speed == 1.00
    assert vs.stability == 0.55
    assert vs.similarity_boost == 0.80
    assert vs.style == 0.00
    assert vs.use_speaker_boost is True


def test_gemaux_voice_settings():
    """Gemaux has her custom voice settings."""
    vs = CHARACTERS["gemaux"].voice_settings
    assert vs.speed == 0.92
    assert vs.stability == 0.60
    assert vs.similarity_boost == 0.95
    assert vs.style == 0.10
    assert vs.use_speaker_boost is False


def test_deepwilla_voice_settings():
    """Deepwilla has her custom voice settings."""
    vs = CHARACTERS["deepwilla"].voice_settings
    assert vs.speed == 1.08
    assert vs.stability == 0.48
    assert vs.similarity_boost == 0.95
    assert vs.style == 0.23
    assert vs.use_speaker_boost is False


def test_default_characters_have_speaker_boost():
    """Clauven, Geptima, and Grokthar all have use_speaker_boost=True."""
    for name in ("clauven", "geptima", "grokthar"):
        assert CHARACTERS[name].voice_settings.use_speaker_boost is True, name


@pytest.mark.asyncio
async def test_speak_passes_voice_settings_to_elevenlabs():
    """voice_settings passed to speak() are forwarded to _elevenlabs_speak."""
    with patch("party.output.tts.settings") as mock_settings:
        mock_settings.elevenlabs_api_key = "test_key"
        with patch("party.output.tts._elevenlabs_speak", new_callable=AsyncMock) as mock_el:
            vs = CharacterVoiceSettings(speed=0.92, stability=0.60)
            await tts.speak("Hello.", "voice_id", "gemaux", vs)
            mock_el.assert_called_once_with("Hello.", "voice_id", "gemaux", vs)
