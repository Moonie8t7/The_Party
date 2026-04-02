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

        next_audio_task = None
        
        for i, response in enumerate(scene.responses):
            character = CHARACTERS.get(response.name)
            vs = character.voice_settings if character else None
            
            # 1. Get the current audio
            if next_audio_task:
                audio_bytes = await next_audio_task
            else:
                audio_bytes = await tts.generate(response.text, response.voice_id, response.name, vs)
                
            # 2. Pipeline the next audio generation
            if i + 1 < len(scene.responses):
                next_resp = scene.responses[i+1]
                next_char = CHARACTERS.get(next_resp.name)
                next_vs = next_char.voice_settings if next_char else None
                next_audio_task = asyncio.create_task(
                    tts.generate(next_resp.text, next_resp.voice_id, next_resp.name, next_vs)
                )

            # 3. Perform synchronized playback and notifications
            log.info("speech.start", trigger_id=trigger_id, character=response.name)
            await obs_notify("speaking_start", response.name, text=response.text, display_name=response.display_name)
            await tts.play(audio_bytes, response.text, response.name)
            await obs_notify("speaking_end", response.name)
            log.info("speech.end", trigger_id=trigger_id, character=response.name)
            
            await asyncio.sleep(settings.inter_character_gap_seconds)

        await obs_notify("idle", None)


speech_manager = SpeechManager()
