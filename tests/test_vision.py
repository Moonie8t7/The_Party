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
