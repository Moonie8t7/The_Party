"""
Session context manager.

Handles:
- Auto-population of date, time, game, IGDB summary at startup
- Hot-reload on every trigger (reads file fresh each call)
- Writing auto-populated fields without clobbering manual notes
"""

import os
from datetime import datetime
from pathlib import Path
from party.config import settings
from party.log import get_logger

log = get_logger(__name__)

_SESSION_PATH = Path(settings.session_context_path)


def ensure_session_file():
    """Create session directory and file if they don't exist."""
    _SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _SESSION_PATH.exists():
        _SESSION_PATH.write_text(
            "# Session Context — The Party\n"
            "# Edit anytime mid-stream. Changes take effect on the next trigger.\n\n"
            "DATE: [auto]\n"
            "TIME: [auto]\n"
            "STREAM_TITLE: [auto]\n"
            "GAME: [auto]\n"
            "GAME_SUMMARY: [auto]\n\n"
            "# ── Add your session notes below ──\n\n"
            "CURRENT_OBJECTIVE: \n"
            "NOTABLE_MOMENTS: \n"
            "NPC_NOTES: \n"
            "PARTY_NOTES: \n",
            encoding="utf-8",
        )


def update_auto_fields(
    game: str = "",
    game_summary: str = "",
    stream_title: str = "",
):
    """
    Overwrite auto-populated fields in session_context.txt.
    Preserves all manual notes below the auto section.
    """
    ensure_session_file()

    now = datetime.now()
    auto_fields = {
        "DATE": now.strftime("%A %d %B %Y"),
        "TIME": now.strftime("%H:%M"),
        "STREAM_TITLE": stream_title or "[not set]",
        "GAME": game or "[not set]",
        "GAME_SUMMARY": game_summary or "[not available]",
    }

    content = _SESSION_PATH.read_text(encoding="utf-8")
    lines = content.splitlines()
    new_lines = []

    for line in lines:
        updated = False
        for key, value in auto_fields.items():
            if line.startswith(f"{key}:"):
                new_lines.append(f"{key}: {value}")
                updated = True
                break
        if not updated:
            new_lines.append(line)

    _SESSION_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    log.info(
        "session.context_updated",
        game=auto_fields["GAME"],
        date=auto_fields["DATE"],
        time=auto_fields["TIME"],
    )


def read_session_context() -> str:
    """
    Read and return the current session context as a formatted string.
    Called on every trigger — always fresh.
    Strips comment lines.
    """
    ensure_session_file()
    try:
        content = _SESSION_PATH.read_text(encoding="utf-8")
        lines = [
            line for line in content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        return "\n".join(lines)
    except Exception as e:
        log.warning("session.read_failed", reason=str(e))
        return ""
