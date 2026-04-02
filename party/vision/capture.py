"""
OBS burst screenshot capture via WebSocket.

Captures N frames at a configurable interval and returns them
as a list of base64-encoded PNG strings.
"""

import asyncio
from typing import Optional
from party.config import settings
from party.log import get_logger

log = get_logger(__name__)


async def capture_burst() -> list[str]:
    """
    Capture a burst of screenshots from OBS.
    Returns list of base64-encoded PNG strings.
    List may be shorter than VISION_BURST_FRAMES if some captures fail.
    Returns empty list if OBS is not running.
    """
    frames = []
    n = settings.vision_burst_frames
    interval = settings.vision_burst_interval_seconds

    for i in range(n):
        frame = await _capture_single()
        if frame:
            frames.append(frame)
            log.debug("vision.frame_captured", frame=i + 1, total=n)
        else:
            log.warning("vision.frame_failed", frame=i + 1, total=n)

        # Wait between frames (but not after the last one)
        if i < n - 1:
            await asyncio.sleep(interval)

    if frames:
        log.info(
            "vision.burst_captured",
            frames_captured=len(frames),
            frames_requested=n,
        )
    else:
        log.warning("vision.burst_empty")

    return frames


async def _capture_single() -> Optional[str]:
    """Capture a single screenshot. Returns base64 PNG or None."""
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _capture_sync)
    except Exception as e:
        log.warning("vision.capture_failed", reason=str(e))
        return None


def _capture_sync() -> Optional[str]:
    """Synchronous OBS screenshot capture. Run in thread pool."""
    import obsws_python as obs

    client = obs.ReqClient(
        host=settings.vision_obs_host,
        port=settings.vision_obs_port,
        password=settings.vision_obs_password,
        timeout=5,
    )

    try:
        from party.context.obs_context import _get_scene_sync
        scene_name = _get_scene_sync()
        if not scene_name:
            return None

        response = client.get_source_screenshot(
            scene_name,
            "png",
            1280,
            720,
            -1,
        )

        image_data = response.image_data
        if image_data.startswith("data:"):
            image_data = image_data.split(",", 1)[1]
        return image_data

    finally:
        client.disconnect()
