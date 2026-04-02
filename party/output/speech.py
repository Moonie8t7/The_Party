import asyncio
from party.models import Scene, CHARACTERS
from party.output import tts
from party.output.obs import notify as obs_notify
from party.config import settings
from party.log import get_logger

log = get_logger(__name__)


class SpeechManager:
    async def play(self, scene: Scene) -> None:
        trigger_id = scene.trigger.trigger_id

        for response in scene.responses:
            log.info("speech.start", trigger_id=trigger_id, character=response.name)
            await obs_notify("speaking_start", response.name, text=response.text, display_name=response.display_name)
            character = CHARACTERS.get(response.name)
            vs = character.voice_settings if character else None
            await tts.speak(response.text, response.voice_id, response.name, vs)
            await obs_notify("speaking_end", response.name)
            log.info("speech.end", trigger_id=trigger_id, character=response.name)
            await asyncio.sleep(settings.inter_character_gap_seconds)

        await obs_notify("idle", None)


speech_manager = SpeechManager()
