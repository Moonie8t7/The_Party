"""
Viewer memory store.

Persists a JSON record of each viewer who has appeared as a first, second,
or third chatter. Updated on every viewer_event trigger. Read on every
trigger where a viewer is named.

The file auto-creates if missing. All failures are silent — a missing or
corrupt memory file must never break a trigger.

Thread safety: all writes are protected by an asyncio lock. The file is
written synchronously inside the lock (run in a thread if needed, but
JSON writes at this scale are fast enough to be acceptable).
"""

import asyncio
import json
import os
from datetime import date
from typing import Optional
from party.log import get_logger

log = get_logger(__name__)

VIEWER_MEMORY_PATH = os.path.join("session", "viewer_memory.json")

_memory: dict = {}
_lock = asyncio.Lock()
_loaded: bool = False


# ── Internal helpers ──────────────────────────────────────────────────────────

def _ensure_loaded() -> None:
    """Load memory from disk on first access. Call inside lock."""
    global _memory, _loaded
    if _loaded:
        return
    try:
        if os.path.exists(VIEWER_MEMORY_PATH):
            with open(VIEWER_MEMORY_PATH, "r", encoding="utf-8") as f:
                _memory = json.load(f)
            log.debug("viewer_memory.loaded", count=len(_memory))
        else:
            _memory = {}
            _write_to_disk()
            log.info("viewer_memory.created", path=VIEWER_MEMORY_PATH)
    except Exception as e:
        log.warning("viewer_memory.load_failed", reason=str(e))
        _memory = {}
    finally:
        _loaded = True


def _write_to_disk() -> None:
    """Write current memory to disk. Call inside lock."""
    try:
        os.makedirs(os.path.dirname(VIEWER_MEMORY_PATH) or ".", exist_ok=True)
        with open(VIEWER_MEMORY_PATH, "w", encoding="utf-8") as f:
            json.dump(_memory, f, indent=2)
    except Exception as e:
        log.warning("viewer_memory.save_failed", reason=str(e))


# ── Public API ────────────────────────────────────────────────────────────────

async def get_viewer(username: str) -> Optional[dict]:
    """
    Return memory record for a viewer, or None if not known.
    Username is normalised to lowercase for lookup.
    """
    if not username:
        return None
    async with _lock:
        _ensure_loaded()
        return _memory.get(username.lower())


async def update_viewer(username: str, data: dict) -> None:
    """
    Merge data into a viewer's memory record and persist to disk.
    Creates the record if it does not exist.
    Always sets last_seen to today's date.
    """
    if not username:
        return
    async with _lock:
        _ensure_loaded()
        key = username.lower()
        existing = _memory.get(key, {})
        existing.update(data)
        existing["last_seen"] = date.today().isoformat()
        _memory[key] = existing
        _write_to_disk()
        log.debug("viewer_memory.updated", viewer=username)


def format_viewer_context(viewer_data: dict, username: str) -> str:
    """
    Convert a viewer's memory record into a natural language context line
    for injection into warm primary context.

    This must never surface raw numbers as a stat dump. One or two sentences,
    written as a memory, not a readout.
    """
    if not viewer_data or not username:
        return ""

    firsts = viewer_data.get("firsts", 0)
    seconds = viewer_data.get("seconds", 0)
    thirds = viewer_data.get("thirds", 0)
    level = viewer_data.get("level", 1)
    total = firsts + seconds + thirds

    if total == 0 and level <= 1:
        return ""

    parts = []

    if total > 0:
        parts.append(f"{username} is a familiar presence in the Dungeon Arcade.")
        if firsts >= 5:
            parts.append(f"They are a frequent early arrival — first chatter {firsts} times.")
        elif firsts > 0:
            parts.append(f"They have been first chatter {firsts} time{'s' if firsts != 1 else ''}.")

    if level > 1:
        parts.append(f"As an adventurer, they are Level {level}.")

    return " ".join(parts)
