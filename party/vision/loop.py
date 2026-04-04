"""
Vision background loop.

Runs on a configurable timer. Captures a burst of OBS screenshots,
describes them with GPT-4o Vision, appends to the vision log,
and stores the latest description. The description is read by
chain.py on every trigger.
"""

import asyncio
import time
from typing import Optional
from party.config import settings
from party.vision.capture import capture_burst
from party.vision.describe import describe_burst
from party.vision import log as vision_log
from party.context.obs_context import get_current_scene
from party.log import get_logger

log = get_logger(__name__)

# Scenes in which vision capture is active.
# Capture is skipped silently on all other scenes (BRB, Startup, Chat, Post Game).
VISION_CAPTURE_SCENES = {"Gaming"}

# Module-level storage for latest description
_latest_description: Optional[str] = None
_loop_task: Optional[asyncio.Task] = None


def get_latest_description() -> Optional[str]:
    """
    Return the most recent vision description.
    Called by chain.py on every trigger.
    Returns None if vision is disabled or no description yet.
    """
    return _latest_description


async def start_vision_loop():
    """Start the background vision loop."""
    global _loop_task

    if not settings.vision_enabled:
        log.info("vision.disabled")
        return

    if settings.vision_interval_seconds < 30:
        log.warning(
            "vision.interval_too_short",
            configured=settings.vision_interval_seconds,
            minimum=30,
        )

    _loop_task = asyncio.create_task(_run_loop())
    log.info(
        "vision.loop_started",
        interval_seconds=settings.vision_interval_seconds,
        burst_frames=settings.vision_burst_frames,
    )


async def stop_vision_loop():
    """Stop the background vision loop."""
    global _loop_task
    if _loop_task and not _loop_task.done():
        _loop_task.cancel()
        try:
            await _loop_task
        except asyncio.CancelledError:
            pass
    log.info("vision.loop_stopped")


async def _run_loop():
    """Main vision loop. Runs until cancelled."""
    global _latest_description

    # Initial delay - let OBS settle before first capture
    await asyncio.sleep(5.0)

    while True:
        burst_start = time.monotonic()

        try:
            # Scene gate — only capture during active gameplay.
            # BRB, Startup, Chat, Post Game skipped silently.
            scene = await get_current_scene()
            if scene not in VISION_CAPTURE_SCENES:
                log.debug("vision.skipped_non_gaming_scene", scene=scene)
            else:
                frames = await capture_burst()

                if frames:
                    description = await describe_burst(frames)

                    if description:
                        _latest_description = description
                        vision_log.append_entry(description)
                        log.info(
                            "vision.description_updated",
                            description=description[:80],
                            frames_used=len(frames),
                        )
                    else:
                        log.debug("vision.description_empty")
                else:
                    log.debug("vision.burst_failed_silently")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("vision.loop_error", reason=str(e))
            burst_start = time.monotonic()

        # Account for time spent so the interval stays consistent
        burst_duration = time.monotonic() - burst_start
        wait_time = max(settings.vision_interval_seconds - burst_duration, 10.0)
        await asyncio.sleep(wait_time)
