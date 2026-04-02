import pytest
from unittest.mock import patch, MagicMock
from party.context import obs_context

@pytest.mark.asyncio
async def test_get_current_scene_success():
    """Verify get_current_scene returns the correct name on success."""
    mock_response = MagicMock()
    mock_response.current_program_scene_name = "Gaming"
    
    with patch("obsws_python.ReqClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.get_current_program_scene.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        scene = await obs_context.get_current_scene()
        assert scene == "Gaming"
        mock_client_class.assert_called_once()

@pytest.mark.asyncio
async def test_get_current_scene_failure_returns_unknown():
    """Verify get_current_scene returns 'Unknown' on connection failure."""
    with patch("obsws_python.ReqClient", side_effect=Exception("Connection refused")):
        scene = await obs_context.get_current_scene()
        assert scene == "Unknown"

def test_get_scene_sync_helper():
    """Verify the sync helper works correctly."""
    mock_response = MagicMock()
    mock_response.current_program_scene_name = "Startup"
    
    with patch("obsws_python.ReqClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.get_current_program_scene.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        scene = obs_context._get_scene_sync()
        assert scene == "Startup"
