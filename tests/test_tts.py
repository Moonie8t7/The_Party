import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from party.output import tts
from party.models import CharacterVoiceSettings, CHARACTERS

@pytest.mark.asyncio
async def test_generate_returns_none_when_no_api_key():
    """With no API key, generate() should return None."""
    with patch("party.output.tts.settings") as mock_settings:
        mock_settings.elevenlabs_api_key = ""
        audio = await tts.generate("Hello world.", "voice_id", "grokthar")
        assert audio is None

@pytest.mark.asyncio
async def test_generate_calls_elevenlabs_when_api_key_set():
    """With an API key, generate() should call _generate_audio executor."""
    with patch("party.output.tts.settings") as mock_settings:
        mock_settings.elevenlabs_api_key = "test_key"
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop_instance = MagicMock()
            mock_loop_instance.run_in_executor = AsyncMock(return_value=b"fake_audio")
            mock_loop.return_value = mock_loop_instance
            
            vs = CharacterVoiceSettings()
            audio = await tts.generate("Hello world.", "test_voice_id", "grokthar", vs)
            
            assert audio == b"fake_audio"
            mock_loop_instance.run_in_executor.assert_called_once()
            args = mock_loop_instance.run_in_executor.call_args[0]
            assert args[1] == tts._generate_audio
            assert args[2] == "Hello world."
            assert args[3] == "test_voice_id"
            assert args[4] == vs

@pytest.mark.asyncio
async def test_generate_failure_returns_none():
    """If ElevenLabs raises, generate() catches it and returns None."""
    with patch("party.output.tts.settings") as mock_settings:
        mock_settings.elevenlabs_api_key = "test_key"
        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop_instance = MagicMock()
            mock_loop_instance.run_in_executor = AsyncMock(side_effect=Exception("API error"))
            mock_loop.return_value = mock_loop_instance
            
            audio = await tts.generate("Hello world.", "test_voice_id", "grokthar")
            assert audio is None

@pytest.mark.asyncio
async def test_play_with_none_calls_placeholder():
    """If play() receives None for audio_bytes, it should call placeholder."""
    with patch("party.output.tts._placeholder_speak", new_callable=AsyncMock) as mock_placeholder:
        await tts.play(None, "Hello world.", "grokthar")
        mock_placeholder.assert_called_once_with("Hello world.", "grokthar")

@pytest.mark.asyncio
async def test_play_with_bytes_runs_executor():
    """If play() receives bytes, it runs _play_audio_bytes in executor."""
    with patch("asyncio.get_event_loop") as mock_loop:
        mock_loop_instance = MagicMock()
        mock_loop_instance.run_in_executor = AsyncMock()
        mock_loop.return_value = mock_loop_instance
        
        await tts.play(b"audio", "Hello world.", "grokthar")
        
        mock_loop_instance.run_in_executor.assert_called_once_with(None, tts._play_audio_bytes, b"audio")

@pytest.mark.asyncio
async def test_placeholder_duration_scales_with_word_count():
    """Placeholder sleep should scale with word count."""
    slept = []
    async def mock_sleep(duration):
        slept.append(duration)

    with patch("asyncio.sleep", side_effect=mock_sleep):
        await tts._placeholder_speak("one two three four five", "grokthar")

    assert len(slept) == 1
    assert slept[0] == pytest.approx(5 * 0.4)

# ============================================================
# Sprint 3b - Voice settings tests
# ============================================================

def test_voice_settings_defaults():
    vs = CharacterVoiceSettings()
    assert vs.speed == 1.00
    assert vs.stability == 0.55
    assert vs.similarity_boost == 0.80
    assert vs.style == 0.00
    assert vs.use_speaker_boost is True

def test_gemaux_voice_settings():
    vs = CHARACTERS["gemaux"].voice_settings
    assert vs.speed == 0.92
    assert vs.stability == 0.60
    assert vs.similarity_boost == 0.95
    assert vs.style == 0.10
    assert vs.use_speaker_boost is False

def test_deepwilla_voice_settings():
    vs = CHARACTERS["deepwilla"].voice_settings
    assert vs.speed == 1.08
    assert vs.stability == 0.48
    assert vs.similarity_boost == 0.95
    assert vs.style == 0.23
    assert vs.use_speaker_boost is False

def test_default_characters_have_speaker_boost():
    for name in ("clauven", "geptima", "grokthar"):
        assert CHARACTERS[name].voice_settings.use_speaker_boost is True, name
