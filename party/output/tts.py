import asyncio
import io
import time
from party.config import settings
from party.log import get_logger
from party.models import CharacterVoiceSettings

log = get_logger(__name__)

_DEFAULT_VOICE_SETTINGS = CharacterVoiceSettings()


async def speak(
    text: str,
    voice_id: str,
    character_name: str,
    voice_settings: CharacterVoiceSettings | None = None,
) -> None:
    """
    Speaks text using ElevenLabs if API key is set, otherwise uses placeholder.
    Always awaitable. Never raises — logs errors and falls back silently.
    """
    vs = voice_settings if voice_settings is not None else _DEFAULT_VOICE_SETTINGS

    if not settings.elevenlabs_api_key:
        await _placeholder_speak(text, character_name)
        return

    try:
        await _elevenlabs_speak(text, voice_id, character_name, vs)
    except Exception as e:
        log.warning(
            "tts.elevenlabs_failed",
            character=character_name,
            reason=str(e),
        )
        await _placeholder_speak(text, character_name)


async def _elevenlabs_speak(
    text: str, voice_id: str, character_name: str, vs: CharacterVoiceSettings
) -> None:
    """Real ElevenLabs TTS call + audio playback."""
    from elevenlabs.client import ElevenLabs  # noqa: import inside to keep module loadable without key

    t_start = time.monotonic()
    log.info("tts.elevenlabs_start", character=character_name, chars=len(text))

    loop = asyncio.get_event_loop()

    # Synchronous API call runs in thread pool — never blocks asyncio
    audio_bytes = await loop.run_in_executor(
        None,
        _generate_audio,
        text,
        voice_id,
        vs,
    )

    t_generated = time.monotonic()

    # Playback also blocks — run in thread pool so asyncio stays free
    await loop.run_in_executor(None, _play_audio_bytes, audio_bytes)

    t_complete = time.monotonic()

    log.info(
        "tts.timing",
        character=character_name,
        generation_ms=int((t_generated - t_start) * 1000),
        playback_ms=int((t_complete - t_generated) * 1000),
        total_ms=int((t_complete - t_start) * 1000),
    )
    log.info("tts.elevenlabs_complete", character=character_name)


def _generate_audio(text: str, voice_id: str, vs: CharacterVoiceSettings) -> bytes:
    """Synchronous ElevenLabs audio generation. Run in thread pool."""
    from elevenlabs.client import ElevenLabs
    from elevenlabs import VoiceSettings

    client = ElevenLabs(api_key=settings.elevenlabs_api_key)

    audio_generator = client.text_to_speech.convert(
        voice_id=voice_id,
        text=text,
        model_id=settings.elevenlabs_model_id,
        voice_settings=VoiceSettings(
            stability=vs.stability,
            similarity_boost=vs.similarity_boost,
            style=vs.style,
            use_speaker_boost=vs.use_speaker_boost,
            speed=vs.speed,
        ),
        output_format="mp3_44100_128",
    )

    return b"".join(audio_generator)


def _play_audio_bytes(audio_bytes: bytes) -> None:
    """Synchronous audio playback via sounddevice. Blocks until complete."""
    import sounddevice as sd
    import soundfile as sf

    audio_buffer = io.BytesIO(audio_bytes)
    data, samplerate = sf.read(audio_buffer, dtype="float32")
    sd.play(data, samplerate)
    sd.wait()


async def _placeholder_speak(text: str, character_name: str) -> None:
    """Simulated TTS — sleeps to simulate speaking duration at 0.4s/word."""
    word_count = len(text.split())
    duration = word_count * 0.4
    log.debug(
        "tts.placeholder",
        character=character_name,
        words=word_count,
        simulated_duration=duration,
    )
    await asyncio.sleep(duration)
