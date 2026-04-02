import asyncio
import hashlib
from datetime import datetime
from typing import Optional, Callable, Awaitable
from party.models import Trigger, TriggerPriority
from party.config import settings
from party.log import get_logger
import structlog

log = get_logger(__name__)


class Scheduler:
    def __init__(
        self,
        handler: Optional[Callable[[Trigger], Awaitable]] = None,
        max_size: Optional[int] = None,
    ):
        self._handler = handler
        self._max_size = max_size if max_size is not None else settings.queue_max_size

        self._items: list[Trigger] = []
        self._not_empty = asyncio.Condition()

        # cooldown_key -> last_accepted datetime
        self._cooldowns: dict[str, datetime] = {}
        # text_hash -> last_accepted datetime
        self._seen: dict[str, datetime] = {}

        # Track last activity for IdleCoordinator
        self.last_activity_time = datetime.utcnow()

        # Auto-start consumer if handler provided at construction time
        if handler is not None:
            asyncio.get_event_loop().create_task(self.run_consumer())

    def get_last_activity_time(self) -> datetime:
        return self.last_activity_time

    def set_handler(self, fn: Callable[[Trigger], Awaitable]) -> None:
        self._handler = fn

    def _cooldown_key_for(self, trigger: Trigger) -> str:
        if trigger.cooldown_key:
            return trigger.cooldown_key
        return f"{trigger.type}:{trigger.text[:40]}"

    def _text_hash(self, text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()

    async def enqueue(self, trigger: Trigger) -> None:
        now = datetime.utcnow()

        # Cooldown check
        ck = self._cooldown_key_for(trigger)
        if ck in self._cooldowns:
            elapsed = (now - self._cooldowns[ck]).total_seconds()
            if elapsed < settings.trigger_cooldown_seconds:
                log.info("trigger.dropped", trigger_id=trigger.trigger_id, reason="cooldown")
                return

        # Deduplication check
        th = self._text_hash(trigger.text)
        if th in self._seen:
            elapsed = (now - self._seen[th]).total_seconds()
            if elapsed < settings.dedup_window_seconds:
                log.info("trigger.dropped", trigger_id=trigger.trigger_id, reason="dedup")
                return

        async with self._not_empty:
            # Back-pressure: if full, drop lowest priority item
            if len(self._items) >= self._max_size:
                worst_idx = max(
                    range(len(self._items)),
                    key=lambda i: self._items[i].priority,
                )
                worst = self._items[worst_idx]
                if worst.priority >= trigger.priority:
                    self._items.pop(worst_idx)
                    log.info("trigger.dropped", trigger_id=worst.trigger_id, reason="queue_full")
                else:
                    log.info("trigger.dropped", trigger_id=trigger.trigger_id, reason="queue_full")
                    return

            # Insert maintaining priority order (lower value = higher priority)
            insert_at = len(self._items)
            for i, item in enumerate(self._items):
                if trigger.priority < item.priority:
                    insert_at = i
                    break
            self._items.insert(insert_at, trigger)

            self._cooldowns[ck] = now
            self._seen[th] = now
            self.last_activity_time = now

            log.info(
                "trigger.queued",
                trigger_id=trigger.trigger_id,
                queue_depth=len(self._items),
            )
            self._not_empty.notify()

    async def _get(self) -> Trigger:
        async with self._not_empty:
            while not self._items:
                await self._not_empty.wait()
            return self._items.pop(0)

    async def run_consumer(self) -> None:
        """Single consumer loop. Processes one trigger at a time."""
        log.info("scheduler.consumer_started")
        while True:
            trigger = await self._get()
            structlog.contextvars.bind_contextvars(trigger_id=trigger.trigger_id)
            try:
                await self._handler(trigger)
            except Exception as e:
                log.error(
                    "scheduler.consumer_error",
                    trigger_id=trigger.trigger_id,
                    reason=str(e),
                )
