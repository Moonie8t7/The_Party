import asyncio
import os
import sys
from datetime import datetime

# Add current dir to sys.path to ensure 'party' package is findable
sys.path.append(os.getcwd())

from party.models import Trigger, Scene, CharacterResponse, TriggerType, TriggerPriority
from party.persistence.transcript import write_transcript

async def test_writer():
    trigger = Trigger(
        type=TriggerType.HOTKEY,
        text="Diagnostic test",
        priority=TriggerPriority.NORMAL,
        cooldown_key=None,
        game=None
    )
    
    scene = Scene(
        trigger=trigger,
        characters=["clauven"],
        responses=[
            CharacterResponse(
                name="clauven",
                display_name="Clauven",
                text="Diagnostic response",
                voice_id="mock_voice",
                provider="mock",
                latency_ms=100,
                estimated_cost_usd=0.001
            )
        ],
        router_method="test",
        total_latency_ms=150
    )
    
    print("Writing diagnostic entry...")
    try:
        await write_transcript(scene)
        print("Write complete. Checking file...")
    except Exception as e:
        print(f"FAILED TO WRITE: {e}")
        import traceback
        traceback.print_exc()
        return
    
    path = "logs/transcript.jsonl"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            print(f"File has {len(lines)} lines.")
            print(f"Last line: {lines[-1][:200]}...")
    else:
        print(f"File does NOT exist at {os.path.abspath(path)}!")

if __name__ == "__main__":
    asyncio.run(test_writer())
