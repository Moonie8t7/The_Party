"""
Tests for the key events log reader (Task 10.4).
"""
import os
import tempfile
import pytest
from unittest.mock import patch


def test_read_key_events_returns_empty_when_file_missing():
    from party.context.key_events import read_key_events
    with patch("party.context.key_events.KEY_EVENTS_PATH", "/nonexistent/path.txt"):
        result = read_key_events()
    assert result == []


def test_read_key_events_skips_comments_and_blanks():
    from party.context.key_events import read_key_events
    content = (
        "# This is a comment\n"
        "# Another comment\n"
        "\n"
        "2026-04-01 [BF6] — Moonie survived a wipe.\n"
        "\n"
        "# More comments\n"
        "2026-04-02 [BF6] — Chat named his rifle.\n"
    )
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        tmppath = f.name
    try:
        with patch("party.context.key_events.KEY_EVENTS_PATH", tmppath):
            result = read_key_events()
        assert len(result) == 2
        assert "survived a wipe" in result[0]
        assert "named his rifle" in result[1]
    finally:
        os.unlink(tmppath)


def test_read_key_events_returns_most_recent_entries():
    from party.context.key_events import read_key_events
    lines = [f"2026-04-01 [BF6] — Event {i}.\n" for i in range(20)]
    content = "".join(lines)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        tmppath = f.name
    try:
        with patch("party.context.key_events.KEY_EVENTS_PATH", tmppath):
            result = read_key_events(max_entries=10)
        assert len(result) == 10
        assert "Event 19" in result[-1]
        assert "Event 9" not in result[0]  # Event 0–9 excluded
    finally:
        os.unlink(tmppath)


def test_format_key_events_empty_returns_empty_string():
    from party.context.key_events import format_key_events_for_context
    assert format_key_events_for_context([]) == ""


def test_format_key_events_includes_header_and_entries():
    from party.context.key_events import format_key_events_for_context
    result = format_key_events_for_context(["2026-04-01 [BF6] — Test event."])
    assert "Key moments from previous sessions" in result
    assert "Test event" in result


def test_key_events_in_warm_primary_context():
    """Key events must appear in format_warm_primary() output."""
    from party.orchestration.context import WarmContext, format_warm_primary
    warm = WarmContext(
        timestamp="Friday 04 April 2026, 20:00",
        scene="Gaming",
        session="",
        vision_current="",
        vision_recent=[],
        stream_feats="",
        key_events=["2026-04-02 [BF6] — First stream. Chat was delighted."],
    )
    output = format_warm_primary(warm)
    assert "First stream" in output
    assert "Chat was delighted" in output


def test_key_events_absent_from_warm_companion_context():
    """Key events must NOT appear in format_warm_companion() output."""
    from party.orchestration.context import WarmContext, format_warm_companion
    warm = WarmContext(
        timestamp="Friday 04 April 2026, 20:00",
        scene="Gaming",
        session="",
        vision_current="",
        vision_recent=[],
        stream_feats="",
        key_events=["2026-04-02 [BF6] — First stream. Chat was delighted."],
    )
    output = format_warm_companion(warm)
    assert "First stream" not in output
    assert "Key moments" not in output
