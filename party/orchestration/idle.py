import asyncio
import random
from datetime import datetime
from party.models import Trigger, TriggerType, TriggerPriority
from party.context.obs_context import get_current_scene
from party.log import get_logger

log = get_logger(__name__)

IDLE_SCENES = {"Startup", "BRB", "Post Game"}
IDLE_THRESHOLD_SECONDS = 60.0

class IdleCoordinator:
    def __init__(self, scheduler):
        self.scheduler = scheduler
        self._running = False
        self._task = None

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        log.info("idle.coordinator_started", scenes=list(IDLE_SCENES), threshold=IDLE_THRESHOLD_SECONDS)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("idle.coordinator_stopped")

    async def _loop(self):
        while self._running:
            await asyncio.sleep(10.0)  # Check every 10 seconds
            
            # Check scene
            try:
                scene = await get_current_scene()
            except Exception:
                scene = "Unknown"
                
            if scene not in IDLE_SCENES:
                continue
                
            # Check last activity
            last_activity = self.scheduler.get_last_activity_time()
            elapsed = (datetime.utcnow() - last_activity).total_seconds()
            
            if elapsed >= IDLE_THRESHOLD_SECONDS:
                log.info("idle.triggering_chatter", scene=scene, elapsed_seconds=int(elapsed))
                trigger = Trigger(
                    type=TriggerType.IDLE,
                    text=(
                        f"[System: The party is idling on the '{scene}' scene. Start a natural, deeply in-character conversation. "
                        "Ask each other personal questions or recall past 'Stream Feats' together. "
                        "IMPORTANT: Do not recite dates or exact log entries like a computer. Weave the history into conversation naturally "
                        "(e.g., 'Remember when we took down that first boss?' or 'I'm still thinking about that follower goal'). "
                        "Show real emotion and personality. Only Clauven should even consider being precise about dates/metrics.]"
                    ),
                    priority=TriggerPriority.NORMAL,
                    cooldown_key="idle_chatter",
                    game=None
                )
                await self.scheduler.enqueue(trigger)
