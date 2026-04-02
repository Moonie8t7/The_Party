import asyncio
from party.models import Scene, CHARACTERS
from party.output import tts
from party.output.obs import notify as obs_notify
from party.config import settings
from party.log import get_logger

log = get_logger(__name__)


class SpeechManager:
    async def play_item(self, response: CharacterResponse) -> None:
        """
        Play a single response immediately. 
        Used for incremental updates to minimize perceived latency.
        """
        character = CHARACTERS.get(response.name)
        vs = character.voice_settings if character else None
        
        audio_bytes = await tts.generate(response.text, response.voice_id, response.name, vs)
        
        log.info("speech.start", character=response.name)
        await obs_notify("speaking_start", response.name, text=response.text, display_name=response.display_name)
        await tts.play(audio_bytes, response.text, response.name)
        await obs_notify("speaking_end", response.name)
        log.info("speech.end", character=response.name)
        
        await asyncio.sleep(settings.inter_character_gap_seconds)

    async def play(self, scene: Scene) -> None:
        """Sequential playback of a full scene (Legacy/Fallback)."""
        for response in scene.responses:
            await self.play_item(response)
        await obs_notify("idle", None)


speech_manager = SpeechManager()
