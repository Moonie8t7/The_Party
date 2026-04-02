import pytest
import json
from party.intake.server import handle_message
from party.models import Trigger


@pytest.mark.asyncio
async def test_intake_accepts_valid_hotkey():
    enqueued = []

    async def mock_enqueue(trigger: Trigger):
        enqueued.append(trigger)

    payload = json.dumps({"type": "hotkey", "text": "DM Moonie died."})
    await handle_message(payload, enqueue_fn=mock_enqueue)
    assert len(enqueued) == 1
    assert enqueued[0].text == "DM Moonie died."


@pytest.mark.asyncio
async def test_intake_accepts_valid_chat_trigger():
    enqueued = []

    async def mock_enqueue(trigger: Trigger):
        enqueued.append(trigger)

    payload = json.dumps({"type": "chat_trigger", "text": "A viewer said something."})
    await handle_message(payload, enqueue_fn=mock_enqueue)
    assert len(enqueued) == 1


@pytest.mark.asyncio
async def test_intake_rejects_invalid_json():
    enqueued = []

    async def mock_enqueue(trigger: Trigger):
        enqueued.append(trigger)

    await handle_message("not valid json {{", enqueue_fn=mock_enqueue)
    assert len(enqueued) == 0


@pytest.mark.asyncio
async def test_intake_rejects_missing_type():
    enqueued = []

    async def mock_enqueue(trigger: Trigger):
        enqueued.append(trigger)

    payload = json.dumps({"text": "Something happened."})
    await handle_message(payload, enqueue_fn=mock_enqueue)
    assert len(enqueued) == 0


@pytest.mark.asyncio
async def test_intake_rejects_empty_text():
    enqueued = []

    async def mock_enqueue(trigger: Trigger):
        enqueued.append(trigger)

    payload = json.dumps({"type": "hotkey", "text": ""})
    await handle_message(payload, enqueue_fn=mock_enqueue)
    assert len(enqueued) == 0


@pytest.mark.asyncio
async def test_intake_rejects_oversized_text():
    enqueued = []

    async def mock_enqueue(trigger: Trigger):
        enqueued.append(trigger)

    payload = json.dumps({"type": "hotkey", "text": "A" * 1001})
    await handle_message(payload, enqueue_fn=mock_enqueue)
    assert len(enqueued) == 0


@pytest.mark.asyncio
async def test_intake_assigns_trigger_id():
    enqueued = []

    async def mock_enqueue(trigger: Trigger):
        enqueued.append(trigger)

    payload = json.dumps({"type": "hotkey", "text": "Something happened."})
    await handle_message(payload, enqueue_fn=mock_enqueue)
    assert len(enqueued[0].trigger_id) > 0
