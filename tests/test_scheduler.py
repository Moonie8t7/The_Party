import pytest
import asyncio
from unittest.mock import AsyncMock
from party.queue.scheduler import Scheduler
from party.models import Trigger, TriggerType, TriggerPriority
import uuid
from datetime import datetime


def make_trigger(
    text: str,
    priority: TriggerPriority = TriggerPriority.NORMAL,
    cooldown_key: str | None = None,
) -> Trigger:
    return Trigger(
        trigger_id=str(uuid.uuid4()),
        received_at=datetime.utcnow(),
        type=TriggerType.HOTKEY,
        text=text,
        priority=priority,
        cooldown_key=cooldown_key,
        game=None,
    )


@pytest.mark.asyncio
async def test_scheduler_processes_trigger():
    """A queued trigger should be processed by the consumer."""
    processed = []

    async def mock_handler(trigger: Trigger):
        processed.append(trigger.trigger_id)

    scheduler = Scheduler(handler=mock_handler, max_size=10)
    trigger = make_trigger("DM Moonie died.")
    await scheduler.enqueue(trigger)
    await asyncio.sleep(0.1)
    assert len(processed) == 1


@pytest.mark.asyncio
async def test_scheduler_deduplicates_identical_text():
    """Same text within dedup window should only process once."""
    processed = []

    async def mock_handler(trigger: Trigger):
        processed.append(trigger.trigger_id)

    scheduler = Scheduler(handler=mock_handler, max_size=10)
    text = "DM Moonie died again."
    for _ in range(5):
        await scheduler.enqueue(make_trigger(text))

    await asyncio.sleep(0.5)
    assert len(processed) == 1


@pytest.mark.asyncio
async def test_scheduler_respects_cooldown_key():
    """Triggers with the same cooldown_key should be throttled."""
    processed = []

    async def mock_handler(trigger: Trigger):
        processed.append(trigger.trigger_id)

    scheduler = Scheduler(handler=mock_handler, max_size=10)
    for _ in range(3):
        await scheduler.enqueue(
            make_trigger("Different text each time.", cooldown_key="hotkey_death")
        )

    await asyncio.sleep(0.5)
    assert len(processed) == 1


@pytest.mark.asyncio
async def test_scheduler_high_priority_jumps_queue():
    """HIGH priority trigger should be processed before NORMAL."""
    order = []

    async def mock_handler(trigger: Trigger):
        order.append(trigger.text)
        await asyncio.sleep(0.05)

    scheduler = Scheduler(handler=mock_handler, max_size=10)

    for i in range(3):
        await scheduler.enqueue(
            make_trigger(f"Normal trigger {i}", priority=TriggerPriority.NORMAL)
        )

    await scheduler.enqueue(
        make_trigger("High priority trigger", priority=TriggerPriority.HIGH)
    )

    await asyncio.sleep(1.0)
    assert order.index("High priority trigger") < 3


@pytest.mark.asyncio
async def test_scheduler_drops_when_full():
    """When queue is full, lowest priority should be dropped."""
    processed = []

    async def slow_handler(trigger: Trigger):
        processed.append(trigger.trigger_id)
        await asyncio.sleep(0.2)

    scheduler = Scheduler(handler=slow_handler, max_size=3)

    for i in range(10):
        await scheduler.enqueue(
            make_trigger(f"Trigger {i}", priority=TriggerPriority.LOW)
        )

    await asyncio.sleep(2.0)
    assert len(processed) <= 4


@pytest.mark.asyncio
async def test_scheduler_processes_sequentially():
    """Consumer should process one trigger at a time - no parallel execution."""
    concurrent_count = []
    current = [0]

    async def mock_handler(trigger: Trigger):
        current[0] += 1
        concurrent_count.append(current[0])
        await asyncio.sleep(0.05)
        current[0] -= 1

    scheduler = Scheduler(handler=mock_handler, max_size=10)
    for i in range(5):
        await scheduler.enqueue(make_trigger(f"Trigger {i}"))

    await asyncio.sleep(1.0)
    assert max(concurrent_count) == 1
