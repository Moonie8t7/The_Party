"""
OBS Scene Awareness.
Provides the current active scene name from OBS via WebSocket.
"""

import asyncio
from typing import Optional
from party.config import settings
from party.log import get_logger

log = get_logger(__name__)

async def get_current_scene() -> str:
    """
    Retrieves the current program scene name from OBS.
    Returns "Unknown" if OBS is disconnected or any error occurs.
    """
    try:
        loop = asyncio.get_event_loop()
        scene = await asyncio.wait_for(
            loop.run_in_executor(None, _get_scene_sync),
            timeout=2.0
        )
        return scene or "Unknown"
    except Exception as e:
        log.debug("obs.scene_lookup_failed", reason=str(e))
        return "Unknown"

def _get_scene_sync() -> Optional[str]:
    """Synchronous OBS call for use in thread pool."""
    import obsws_python as obs
    
    try:
        client = obs.ReqClient(
            host=settings.vision_obs_host,
            port=settings.vision_obs_port,
            password=settings.vision_obs_password,
            timeout=2,
        )
        try:
            response = client.get_current_program_scene()
            return response.current_program_scene_name
        finally:
            client.disconnect()
    except Exception:
        return None
