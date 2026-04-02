import asyncio
import time
from unittest.mock import patch, MagicMock
from party.context.obs_context import get_current_scene

async def test_obs_cache():
    # Mock the internal sync call
    mock_sync = MagicMock()
    mock_sync.return_value = "TestScene"
    
    with patch('party.context.obs_context._get_scene_sync', mock_sync):
        # 1. First call - should connect to OBS
        res1 = await get_current_scene()
        assert res1 == "TestScene"
        assert mock_sync.call_count == 1
        
        # 2. Immediate second call - should use cache
        res2 = await get_current_scene()
        assert res2 == "TestScene"
        assert mock_sync.call_count == 1
        
        print("Cache hits verified!")
        
        # 3. Wait for expiry (simulated via patch time if needed, but we'll just wait 6s for real)
        # Actually, let's just patch time.monotonic for a faster test
        with patch('time.monotonic', return_value=time.monotonic() + 10):
             res3 = await get_current_scene()
             assert res3 == "TestScene"
             assert mock_sync.call_count == 2
             print("Cache expiry and re-fetch verified!")

if __name__ == "__main__":
    asyncio.run(test_obs_cache())
