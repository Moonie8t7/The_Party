import pytest
import json
import os
import tempfile
from party.persistence.transcript import TranscriptWriter
from party.models import Scene, Trigger, TriggerType, TriggerPriority, CharacterResponse
import uuid
from datetime import datetime


def make_scene() -> Scene:
    trigger = Trigger(
        trigger_id=str(uuid.uuid4()),
        received_at=datetime.utcnow(),
        type=TriggerType.HOTKEY,
        text="DM Moonie died.",
        priority=TriggerPriority.NORMAL,
        cooldown_key=None,
        game=None,
    )
    response = CharacterResponse(
        name="grokthar",
        display_name="Grokthar",
        text="Told you so.",
        voice_id="PLACEHOLDER_GROKTHAR",
        provider="grok",
        latency_ms=300,
    )
    return Scene(
        trigger=trigger,
        characters=["grokthar"],
        responses=[response],
        router_method="rule",
        total_latency_ms=300,
    )


@pytest.mark.asyncio
async def test_transcript_writes_valid_jsonl():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
        path = f.name

    try:
        writer = TranscriptWriter(path=path)
        scene = make_scene()
        await writer.write(scene)

        with open(path) as f:
            lines = f.readlines()

        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert "trigger_id" in entry
        assert "text" in entry
        assert "responses" in entry
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_transcript_appends_multiple_entries():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
        path = f.name

    try:
        writer = TranscriptWriter(path=path)
        for _ in range(3):
            await writer.write(make_scene())

        with open(path) as f:
            lines = [l for l in f.readlines() if l.strip()]

        assert len(lines) == 3
        for line in lines:
            json.loads(line)
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_transcript_creates_directory_if_missing():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "subdir", "transcript.jsonl")
        writer = TranscriptWriter(path=path)
        await writer.write(make_scene())
        assert os.path.exists(path)
