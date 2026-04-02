"""
Vision log - append-only dated file of vision descriptions.
One entry per line: "HH:MM:SS - {description}"
Capped at vision_log_max_file_entries lines.
"""

import os
from datetime import datetime
from party.config import settings
from party.log import get_logger

log = get_logger(__name__)


def _get_log_path() -> str:
    date_str = datetime.now().strftime("%Y-%m-%d")
    return settings.vision_log_path.format(date=date_str)


def append_entry(description: str) -> None:
    """Append a timestamped description to today's vision log file."""
    if not settings.vision_log_enabled:
        return

    path = _get_log_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)

    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = f"{timestamp} - {description}\n"

    # Read existing lines
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    else:
        lines = []

    lines.append(entry)

    # Cap at max entries
    max_entries = settings.vision_log_max_file_entries
    if len(lines) > max_entries:
        lines = lines[-max_entries:]

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    log.debug("vision.log_appended", path=path, entries=len(lines))


def get_recent_entries(n: int) -> list[str]:
    """Return the last N entries from today's vision log (stripped, no newline)."""
    if not settings.vision_log_enabled:
        return []

    path = _get_log_path()
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    return [line.rstrip("\n") for line in lines[-n:] if line.strip()]
