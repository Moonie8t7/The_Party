import asyncio
import time
from typing import Optional
from party.config import settings
from party.log import get_logger

log = get_logger(__name__)

# Cache for the active scene name
class _SceneCache:
    def __init__(self):
        self.scene: Optional[str] = None
        self.expiry: float = 0
        self.lock = asyncio.Lock()

    def clear(self):
        self.scene = None
        self.expiry = 0

_cache = _SceneCache()

def clear_scene_cache():
    """Resets the scene cache (used primarily for testing)."""
    _cache.clear()

async def get_current_scene() -> str:
    """
    Retrieves the current program scene name from OBS.
    Caches result for 5 seconds to prevent connection spam.
    """
    async with _cache.lock:
        now = time.monotonic()
        if _cache.scene and now < _cache.expiry:
            return _cache.scene

        try:
            loop = asyncio.get_event_loop()
            scene = await asyncio.wait_for(
                loop.run_in_executor(None, _get_scene_sync),
                timeout=2.0
            )
            if scene:
                _cache.scene = scene
                _cache.expiry = now + 5.0  # 5 second TTL
                return scene
            return _cache.scene or "Unknown"
        except Exception as e:
            log.debug("obs.scene_lookup_failed", reason=str(e))
            return _cache.scene or "Unknown"

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
