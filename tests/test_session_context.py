import pytest
import os
import tempfile
from unittest.mock import patch
from pathlib import Path


def test_update_auto_fields_preserves_manual_notes():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(
            "DATE: old\n"
            "TIME: old\n"
            "STREAM_TITLE: old\n"
            "GAME: old\n"
            "GAME_SUMMARY: old\n"
            "CURRENT_OBJECTIVE: Find the dungeon\n"
            "NOTABLE_MOMENTS: Found a secret room\n"
        )
        path = f.name

    try:
        with patch("party.context.session._SESSION_PATH", Path(path)):
            from party.context.session import update_auto_fields
            update_auto_fields(game="7 Days to Die", stream_title="Day 12")
            content = Path(path).read_text(encoding="utf-8")

        assert "Find the dungeon" in content
        assert "Found a secret room" in content
        assert "7 Days to Die" in content
    finally:
        os.unlink(path)


def test_update_auto_fields_overwrites_auto_keys():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(
            "DATE: old\n"
            "TIME: old\n"
            "STREAM_TITLE: old\n"
            "GAME: old\n"
            "GAME_SUMMARY: old\n"
        )
        path = f.name

    try:
        with patch("party.context.session._SESSION_PATH", Path(path)):
            from party.context.session import update_auto_fields
            update_auto_fields(game="Elden Ring", stream_title="Malenia run")
            content = Path(path).read_text(encoding="utf-8")

        assert "Elden Ring" in content
        assert "Malenia run" in content
        assert "GAME: old" not in content
    finally:
        os.unlink(path)


def test_read_session_context_strips_comments():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(
            "# This is a comment\n"
            "GAME: 7 Days to Die\n"
            "# Another comment\n"
            "CURRENT_OBJECTIVE: Survive\n"
        )
        path = f.name

    try:
        with patch("party.context.session._SESSION_PATH", Path(path)):
            from party.context.session import read_session_context
            result = read_session_context()
        assert "#" not in result
        assert "7 Days to Die" in result
        assert "Survive" in result
    finally:
        os.unlink(path)


def test_read_session_context_returns_empty_on_failure():
    with patch("party.context.session._SESSION_PATH") as mock_path:
        mock_path.exists.return_value = True
        mock_path.read_text.side_effect = OSError("disk error")
        mock_path.parent.mkdir.return_value = None

        from party.context.session import read_session_context
        result = read_session_context()
    assert result == ""
