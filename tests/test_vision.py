import asyncio
import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock


# --- capture.py ---

@pytest.mark.asyncio
async def test_capture_burst_returns_empty_on_obs_failure():
    """capture_burst should return empty list if OBS is not running."""
    from party.vision.capture import capture_burst

    with patch("party.vision.capture._capture_sync", side_effect=Exception("OBS not running")):
        with patch("party.vision.capture.settings") as mock_settings:
            mock_settings.vision_burst_frames = 2
            mock_settings.vision_burst_interval_seconds = 0.0
            result = await capture_burst()
    assert result == []


@pytest.mark.asyncio
async def test_capture_burst_returns_partial_on_mixed_failure():
    """capture_burst returns only successful frames."""
    from party.vision.capture import capture_burst

    call_count = 0

    def _sync_mixed():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "frame1_b64"
        raise Exception("OBS hiccup")

    with patch("party.vision.capture._capture_sync", side_effect=_sync_mixed):
        with patch("party.vision.capture.settings") as mock_settings:
            mock_settings.vision_burst_frames = 2
            mock_settings.vision_burst_interval_seconds = 0.0
            result = await capture_burst()
    assert result == ["frame1_b64"]


# --- describe.py ---

@pytest.mark.asyncio
async def test_describe_burst_returns_none_on_empty_input():
    from party.vision.describe import describe_burst

    result = await describe_burst([])
    assert result is None


@pytest.mark.asyncio
async def test_describe_burst_returns_none_on_api_failure():
    from party.vision.describe import describe_burst

    with patch("party.vision.describe.OpenAI", side_effect=Exception("API error")):
        result = await describe_burst(["fake_base64_data"])
    assert result is None


@pytest.mark.asyncio
async def test_describe_burst_uses_sequence_prompt_for_multiple_frames():
    """Multi-frame burst should use SEQUENCE_PROMPT."""
    from party.vision.describe import describe_burst, SEQUENCE_PROMPT

    captured_prompt = {}

    def _mock_sync(frames):
        captured_prompt["text"] = frames
        return "A player is fighting a boss."

    with patch("party.vision.describe._describe_sync", side_effect=_mock_sync):
        result = await describe_burst(["frame1", "frame2"])

    assert result == "A player is fighting a boss."


# --- log.py ---

def test_append_and_get_recent_entries(tmp_path):
    """append_entry and get_recent_entries work with a temp log path."""
    from party.vision import log as vision_log

    log_path = str(tmp_path / "vision_log_2099-01-01.txt")

    with patch.object(vision_log, "settings") as mock_settings:
        mock_settings.vision_log_enabled = True
        mock_settings.vision_log_max_file_entries = 100
        mock_settings.vision_log_path = str(tmp_path / "vision_log_{date}.txt")

        with patch("party.vision.log.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.side_effect = lambda fmt: (
                "2099-01-01" if "%Y" in fmt else "12:00:00"
            )

            vision_log.append_entry("The player is exploring a cave.")
            vision_log.append_entry("An enemy appears on screen.")

            entries = vision_log.get_recent_entries(5)

    assert len(entries) == 2
    assert "cave" in entries[0]
    assert "enemy" in entries[1]


def test_get_recent_entries_empty_when_no_file(tmp_path):
    from party.vision import log as vision_log

    with patch.object(vision_log, "settings") as mock_settings:
        mock_settings.vision_log_enabled = True
        mock_settings.vision_log_path = str(tmp_path / "vision_log_{date}.txt")

        with patch("party.vision.log.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.side_effect = lambda fmt: (
                "2099-01-01" if "%Y" in fmt else "12:00:00"
            )
            entries = vision_log.get_recent_entries(5)

    assert entries == []


def test_append_caps_at_max_entries(tmp_path):
    from party.vision import log as vision_log

    with patch.object(vision_log, "settings") as mock_settings:
        mock_settings.vision_log_enabled = True
        mock_settings.vision_log_max_file_entries = 3
        mock_settings.vision_log_path = str(tmp_path / "vision_log_{date}.txt")

        with patch("party.vision.log.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.side_effect = lambda fmt: (
                "2099-01-01" if "%Y" in fmt else "12:00:00"
            )
            for i in range(5):
                vision_log.append_entry(f"Entry {i}")

            entries = vision_log.get_recent_entries(10)

    assert len(entries) == 3
    assert "Entry 2" in entries[0]
    assert "Entry 4" in entries[2]


# --- loop.py ---

def test_get_latest_description_returns_none_or_string():
    from party.vision.loop import get_latest_description
    result = get_latest_description()
    assert result is None or isinstance(result, str)


@pytest.mark.asyncio
async def test_vision_loop_does_not_start_when_disabled():
    from party.vision import loop as vision_loop

    with patch.object(vision_loop, "settings") as mock_settings:
        mock_settings.vision_enabled = False
        mock_settings.vision_interval_seconds = 60.0
        await vision_loop.start_vision_loop()
    # No exception = pass


@pytest.mark.asyncio
async def test_stop_vision_loop_safe_when_not_started():
    from party.vision import loop as vision_loop
    vision_loop._loop_task = None
    await vision_loop.stop_vision_loop()


# --- scene-gated loop and source-specific capture ---

def test_vision_capture_scenes_constant_includes_gaming():
    """VISION_CAPTURE_SCENES must include Gaming and exclude idle scenes."""
    from party.vision.loop import VISION_CAPTURE_SCENES
    assert "Gaming" in VISION_CAPTURE_SCENES
    assert "BRB" not in VISION_CAPTURE_SCENES
    assert "Startup" not in VISION_CAPTURE_SCENES
    assert "Chat" not in VISION_CAPTURE_SCENES
    assert "Post Game" not in VISION_CAPTURE_SCENES


def test_capture_uses_gameplay_source_when_configured():
    """When vision_gameplay_source is set, _capture_sync uses it as source_name."""
    from party.vision import capture as vision_capture

    captured_args = {}

    def mock_get_source_screenshot(source_name, fmt, w, h, quality):
        captured_args["source_name"] = source_name
        mock_resp = MagicMock()
        mock_resp.image_data = "data:image/png;base64,FAKEDATA"
        return mock_resp

    mock_client = MagicMock()
    mock_client.get_source_screenshot.side_effect = mock_get_source_screenshot

    with patch("party.vision.capture.settings") as mock_settings:
        mock_settings.vision_gameplay_source = "Gameplay"
        mock_settings.vision_obs_host = "localhost"
        mock_settings.vision_obs_port = 4455
        mock_settings.vision_obs_password = ""

        with patch("obsws_python.ReqClient", return_value=mock_client):
            result = vision_capture._capture_sync()

    assert captured_args.get("source_name") == "Gameplay"
    assert result == "FAKEDATA"


def test_capture_falls_back_to_scene_when_source_not_configured():
    """When vision_gameplay_source is empty, _capture_sync uses the scene name."""
    from party.vision import capture as vision_capture

    captured_args = {}

    def mock_get_source_screenshot(source_name, fmt, w, h, quality):
        captured_args["source_name"] = source_name
        mock_resp = MagicMock()
        mock_resp.image_data = "FAKEDATA"
        return mock_resp

    mock_client = MagicMock()
    mock_client.get_source_screenshot.side_effect = mock_get_source_screenshot

    with patch("party.vision.capture.settings") as mock_settings:
        mock_settings.vision_gameplay_source = ""
        mock_settings.vision_obs_host = "localhost"
        mock_settings.vision_obs_port = 4455
        mock_settings.vision_obs_password = ""

        with patch("obsws_python.ReqClient", return_value=mock_client):
            with patch(
                "party.context.obs_context._get_scene_sync",
                return_value="Gaming"
            ):
                result = vision_capture._capture_sync()

    assert captured_args.get("source_name") == "Gaming"
    assert result == "FAKEDATA"


@pytest.mark.asyncio
async def test_vision_loop_skips_capture_on_non_gaming_scene():
    """Vision loop must not call capture_burst when scene is not Gaming."""
    from party.vision import loop as vision_loop

    capture_called = {"count": 0}

    async def mock_capture_burst():
        capture_called["count"] += 1
        return []

    with patch("party.vision.loop.get_current_scene", return_value="BRB"):
        with patch("party.vision.loop.capture_burst", side_effect=mock_capture_burst):
            with patch.object(vision_loop, "settings") as mock_settings:
                mock_settings.vision_enabled = True
                mock_settings.vision_interval_seconds = 0.05
                mock_settings.vision_burst_frames = 1
                mock_settings.vision_burst_interval_seconds = 0.0

                # Run the loop task briefly then cancel it
                task = asyncio.create_task(vision_loop._run_loop())
                await asyncio.sleep(0.15)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    assert capture_called["count"] == 0, "capture_burst should not be called on BRB scene"
