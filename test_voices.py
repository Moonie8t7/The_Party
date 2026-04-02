"""
Voice preview test — run this manually to verify each character's voice.
Usage: python test_voices.py
Requires ELEVENLABS_API_KEY and VOICE_* vars set in .env
"""

import asyncio
from party.output.tts import speak
from party.models import CHARACTERS
from party.config import settings

TEST_LINES = {
    "clauven": "That is an interesting position, however I would need to consider it further before committing to a view.",
    "geptima": "Right, so accidents happen. The important thing is what we do next.",
    "gemaux": "Ah, but that is the very essence of true theatre. The moment before everything changes.",
    "grokthar": "Told Moonie this would happen. Should have scouted the perimeter first.",
    "deepwilla": "Right, yes, obviously, but what if the failure mode is actually the more interesting result?",
}


async def main():
    if not settings.elevenlabs_api_key:
        print("ELEVENLABS_API_KEY not set. Set it in .env and retry.")
        return

    for name, line in TEST_LINES.items():
        character = CHARACTERS[name]
        print(f"\n[{character.display_name}] Speaking...")
        print(f"  Voice ID: {character.voice_id}")
        print(f"  Text: {line[:60]}...")
        await speak(line, character.voice_id, name)
        await asyncio.sleep(0.5)

    print("\nAll voices tested.")


if __name__ == "__main__":
    asyncio.run(main())
