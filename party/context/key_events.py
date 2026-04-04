"""
Key Events Log reader.

Reads the persistent cross-stream key events log and returns
the most recent N entries for context injection.

The log is read fresh on every call — no caching — so entries
added mid-stream are available on the next trigger without restart.
"""

import os
from party.log import get_logger

log = get_logger(__name__)

KEY_EVENTS_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "session", "key_events.txt"
))
KEY_EVENTS_MAX_ENTRIES = 10


def read_key_events(max_entries: int = KEY_EVENTS_MAX_ENTRIES) -> list[str]:
    """
    Read the key events log and return the most recent N entries.
    Returns empty list if file is missing, empty, or unreadable.
    Skips comment lines (starting with #) and blank lines.
    """
    try:
        if not os.path.exists(KEY_EVENTS_PATH):
            return []

        with open(KEY_EVENTS_PATH, encoding="utf-8") as f:
            lines = f.readlines()

        entries = [
            line.strip()
            for line in lines
            if line.strip() and not line.strip().startswith("#")
        ]

        if not entries:
            return []

        recent = entries[-max_entries:]
        log.debug("key_events.loaded", count=len(recent))
        return recent

    except Exception as e:
        log.warning("key_events.read_failed", reason=str(e))
        return []


def format_key_events_for_context(entries: list[str]) -> str:
    """
    Format key event entries for injection into character context.
    Returns empty string if no entries.
    """
    if not entries:
        return ""
    lines = ["Key moments from previous sessions:"]
    for entry in entries:
        lines.append(f"  {entry}")
    return "\n".join(lines)
