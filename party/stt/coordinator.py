"""
STT coordinator.

Connects the STT listener and reaction filter to the main trigger queue.
Enforces STT-specific cooldown separate from chat/hotkey cooldowns.
"""

import asyncio
import time
from party.stt.listener import STTListener
from party.stt.filter import should_react
from party.models import Trigger, TriggerType, TriggerPriority
from party.config import settings
from party.log import get_logger

log = get_logger(__name__)


class STTCoordinator:
    def __init__(self, enqueue_fn, poke_fn=None):
        """
        enqueue_fn: async callable that accepts a Trigger.
        poke_fn: callable that updates activity status.
        """
        self._enqueue = enqueue_fn
        self._poke_fn = poke_fn
        self._last_stt_trigger = 0.0
        self._listener = STTListener(on_utterance=self._handle_utterance)

    async def _handle_utterance(self, text: str):
        """Handle a transcribed utterance from the STT listener."""
        if self._poke_fn:
            self._poke_fn()

        # Check STT cooldown
        now = time.monotonic()
        elapsed = now - self._last_stt_trigger
        if elapsed < settings.stt_cooldown_seconds:
            remaining = settings.stt_cooldown_seconds - elapsed
            log.debug(
                "stt.cooldown_active",
                remaining_seconds=round(remaining, 1),
                utterance=text[:40],
            )
            return

        # Run reaction filter
        react = await should_react(text)
        if not react:
            return

        # Build and enqueue trigger
        self._last_stt_trigger = now
        trigger = Trigger(
            type=TriggerType.STT,
            text=text,
            priority=TriggerPriority.NORMAL,
            cooldown_key="stt",
            game=None,
        )

        log.info(
            "stt.trigger_created",
            trigger_id=trigger.trigger_id,
            text=text[:80],
        )
        await self._enqueue(trigger)

    async def start(self):
        await self._listener.start()

    async def stop(self):
        await self._listener.stop()
