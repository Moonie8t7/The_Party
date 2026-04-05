"""
Tests for the viewer memory store (Sprint 12).
"""
import asyncio
import json
import os
import tempfile
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def reset_memory_module():
    """Reset viewer memory module state between tests."""
    import party.context.viewer_memory as vm
    vm._memory = {}
    vm._loaded = False
    yield
    vm._memory = {}
    vm._loaded = False


@pytest.mark.asyncio
async def test_get_viewer_returns_none_when_file_missing():
    from party.context.viewer_memory import get_viewer
    with patch("party.context.viewer_memory.VIEWER_MEMORY_PATH", "/nonexistent/path.json"):
        result = await get_viewer("testuser")
    assert result is None


@pytest.mark.asyncio
async def test_update_and_get_viewer_roundtrip(tmp_path):
    from party.context import viewer_memory as vm
    path = str(tmp_path / "viewer_memory.json")
    with patch.object(vm, "VIEWER_MEMORY_PATH", path):
        await vm.update_viewer("MoonFan", {"firsts": 3, "level": 7})
        result = await vm.get_viewer("MoonFan")
    assert result is not None
    assert result["firsts"] == 3
    assert result["level"] == 7
    assert "last_seen" in result


@pytest.mark.asyncio
async def test_update_viewer_is_case_insensitive(tmp_path):
    from party.context import viewer_memory as vm
    path = str(tmp_path / "viewer_memory.json")
    with patch.object(vm, "VIEWER_MEMORY_PATH", path):
        await vm.update_viewer("MoonFan", {"firsts": 2})
        result = await vm.get_viewer("moonFAN")
    assert result is not None
    assert result["firsts"] == 2


@pytest.mark.asyncio
async def test_update_viewer_merges_not_overwrites(tmp_path):
    from party.context import viewer_memory as vm
    path = str(tmp_path / "viewer_memory.json")
    with patch.object(vm, "VIEWER_MEMORY_PATH", path):
        await vm.update_viewer("MoonFan", {"firsts": 4, "level": 5})
        await vm.update_viewer("MoonFan", {"level": 6})
        result = await vm.get_viewer("MoonFan")
    assert result["firsts"] == 4   # preserved
    assert result["level"] == 6    # updated


@pytest.mark.asyncio
async def test_file_persists_between_calls(tmp_path):
    from party.context import viewer_memory as vm
    path = str(tmp_path / "viewer_memory.json")
    with patch.object(vm, "VIEWER_MEMORY_PATH", path):
        await vm.update_viewer("StreamerA", {"firsts": 1})

    # Reset in-memory state to force re-read from disk
    vm._memory = {}
    vm._loaded = False

    with patch.object(vm, "VIEWER_MEMORY_PATH", path):
        result = await vm.get_viewer("StreamerA")
    assert result is not None
    assert result["firsts"] == 1


def test_format_viewer_context_known_viewer():
    from party.context.viewer_memory import format_viewer_context
    data = {"firsts": 6, "seconds": 2, "thirds": 1, "level": 9}
    result = format_viewer_context(data, "MoonFan")
    assert "MoonFan" in result
    assert len(result) > 0


def test_format_viewer_context_new_viewer():
    from party.context.viewer_memory import format_viewer_context
    result = format_viewer_context({}, "NewViewer")
    assert result == ""


def test_format_viewer_context_no_stat_dump():
    from party.context.viewer_memory import format_viewer_context
    data = {"firsts": 3, "seconds": 1, "thirds": 0, "level": 4}
    result = format_viewer_context(data, "MoonFan")
    # Must not contain raw numbers presented as stats
    assert "firsts:" not in result.lower()
    assert "seconds:" not in result.lower()


@pytest.mark.asyncio
async def test_viewer_context_in_warm_primary(tmp_path):
    """Viewer context must appear in format_warm_primary when viewer is known."""
    from party.context import viewer_memory as vm
    from party.orchestration.context import WarmContext, format_warm_primary
    path = str(tmp_path / "viewer_memory.json")
    with patch.object(vm, "VIEWER_MEMORY_PATH", path):
        await vm.update_viewer("MoonFan", {"firsts": 5, "level": 8})
        viewer_data = await vm.get_viewer("MoonFan")

    viewer_ctx = vm.format_viewer_context(viewer_data, "MoonFan")
    warm = WarmContext(
        timestamp="Saturday 05 April 2026, 20:00",
        scene="Gaming",
        session="",
        vision_current="",
        vision_recent=[],
        stream_feats="",
        key_events=[],
        viewer_context=viewer_ctx,
    )
    output = format_warm_primary(warm)
    assert "MoonFan" in output


def test_viewer_context_absent_from_warm_companion():
    """Viewer context must NOT appear in format_warm_companion."""
    from party.orchestration.context import WarmContext, format_warm_companion
    warm = WarmContext(
        timestamp="Saturday 05 April 2026, 20:00",
        scene="Gaming",
        session="",
        vision_current="",
        vision_recent=[],
        stream_feats="",
        key_events=[],
        viewer_context="MoonFan is a familiar presence in the Dungeon Arcade.",
    )
    output = format_warm_companion(warm)
    assert "MoonFan" not in output
