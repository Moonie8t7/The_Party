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


# ── Renown system ─────────────────────────────────────────────────────────────

def calculate_renown(viewer_data: dict) -> int:
    """
    Calculate a viewer's Renown score from their memory record.

    Renown is a single integer reflecting presence, support, fate, and level.
    It is deterministic — same input always yields the same score.
    Called automatically on every update_viewer() call.

    Scoring breakdown:
      Presence (chatter history):
        - First chatter ×10 per occurrence
        - Second chatter ×6 per occurrence
        - Third chatter ×3 per occurrence

      Support (financial generosity):
        - Subscriber: 20 base + 3 per cumulative month
        - Gift bomber: 2 per gift in last bomb (capped at 50)
        - Gifted sub recipient: 5

      Raiding:
        - 1 point per 5 viewers in last raid (capped at 30)

      Fate (dice):
        - Nat 20: 5 points each (fortune is renowned)
        - Nat 1: 2 points each (infamy is memorable)

      Adventurer level:
        - 2 points per level above 1 (Level 20 = +38)
    """
    score = 0

    # Presence
    score += viewer_data.get("firsts", 0) * 10
    score += viewer_data.get("seconds", 0) * 6
    score += viewer_data.get("thirds", 0) * 3

    # Support
    if viewer_data.get("subscriber"):
        sub_months = viewer_data.get("sub_months", 0)
        score += 20 + (sub_months * 3)

    if viewer_data.get("gift_bomber"):
        bomb_count = viewer_data.get("last_bomb_count", 0)
        score += min(bomb_count * 2, 50)

    if viewer_data.get("gifted_sub"):
        score += 5

    # Raiding
    if viewer_data.get("raider"):
        raid_viewers = viewer_data.get("last_raid_viewers", 0)
        score += min(raid_viewers // 5, 30)

    # Fate
    score += viewer_data.get("d20_nat20s", 0) * 5
    score += viewer_data.get("d20_nat1s", 0) * 2

    # Level
    level = viewer_data.get("level", 1)
    score += max(0, (level - 1) * 2)

    return score


def get_renown_tier(score: int) -> str:
    """
    Map a Renown score to a narrative tier label.

    The label is used inside format_viewer_context as a natural
    description of the viewer's standing. It must read naturally
    in a sentence: "{username} is {label}."

    Tiers:
      0–9:   a newcomer to the Dungeon Arcade
      10–24: a familiar face in the Dungeon Arcade
      25–49: a known adventurer of the Dungeon Arcade
      50–99: a seasoned regular of the Dungeon Arcade
      100+:  a legend of the Dungeon Arcade
    """
    if score >= 100:
        return "a legend of the Dungeon Arcade"
    if score >= 50:
        return "a seasoned regular of the Dungeon Arcade"
    if score >= 25:
        return "a known adventurer of the Dungeon Arcade"
    if score >= 10:
        return "a familiar face in the Dungeon Arcade"
    return "a newcomer to the Dungeon Arcade"


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
    Always sets last_seen to today's date and recalculates Renown.
    """
    if not username:
        return
    async with _lock:
        _ensure_loaded()
        key = username.lower()
        existing = _memory.get(key, {})
        existing.update(data)
        existing["last_seen"] = date.today().isoformat()
        existing["renown"] = calculate_renown(existing)
        _memory[key] = existing
        _write_to_disk()
        log.debug("viewer_memory.updated", viewer=username)


async def increment_character_affinity(username: str, character_name: str) -> None:
    """
    Increment the affinity counter for a specific character and viewer.
    Creates the affinity dict and character entry if not present.
    Silent on failure — affinity is enhancement, not core.
    """
    if not username or not character_name:
        return
    async with _lock:
        _ensure_loaded()
        key = username.lower()
        if key not in _memory:
            return  # Don't create a record just for affinity
        record = _memory[key]
        affinity = record.setdefault("character_affinity", {})
        affinity[character_name] = affinity.get(character_name, 0) + 1
        _write_to_disk()
        log.debug("viewer_memory.affinity_incremented",
                  viewer=username, character=character_name,
                  count=affinity[character_name])


def get_character_affinity(viewer_data: dict) -> dict[str, int]:
    """
    Return per-character affinity counts from a viewer record.
    Returns empty dict if no affinity data present.
    """
    return viewer_data.get("character_affinity", {})


def format_viewer_context(viewer_data: dict, username: str) -> str:
    """
    Convert a viewer's memory record into natural language for warm primary context.

    Uses Renown tier as the opening description. Adds subscriber, raider,
    first chatter, d20 history, and level detail as available.

    Never produces a stat dump — two or three sentences maximum,
    written as a memory, not a readout.
    """
    if not viewer_data or not username:
        return ""

    firsts = viewer_data.get("firsts", 0)
    seconds = viewer_data.get("seconds", 0)
    thirds = viewer_data.get("thirds", 0)
    level = viewer_data.get("level", 1)
    total_chatter = firsts + seconds + thirds

    is_raider = viewer_data.get("raider", False)
    last_raid_viewers = viewer_data.get("last_raid_viewers")

    is_subscriber = viewer_data.get("subscriber", False)
    sub_months = viewer_data.get("sub_months")
    sub_tier = viewer_data.get("sub_tier")

    is_gifted = viewer_data.get("gifted_sub", False)

    nat20s = viewer_data.get("d20_nat20s", 0)
    nat1s = viewer_data.get("d20_nat1s", 0)

    renown = viewer_data.get("renown", 0)

    # Nothing meaningful to surface for a complete unknown
    if (total_chatter == 0 and level <= 1 and not is_raider
            and not is_subscriber and not is_gifted
            and nat20s == 0 and nat1s == 0):
        return ""

    parts = []

    # Opening — Renown tier defines standing
    tier = get_renown_tier(renown)
    parts.append(f"{username} is {tier}.")

    # Support detail — subscriber loyalty or gifted status
    if is_subscriber and sub_months:
        tier_note = f" ({sub_tier})" if sub_tier and sub_tier not in ("tier 1", "prime") else ""
        parts.append(
            f"They have been a subscriber for "
            f"{sub_months} month{'s' if sub_months != 1 else ''}{tier_note}."
        )
    elif is_gifted and not is_subscriber:
        parts.append("They were gifted a subscription by the community.")

    # Raider history
    if is_raider and last_raid_viewers:
        parts.append(f"They have raided the Dungeon Arcade before, bringing {last_raid_viewers} viewers.")
    elif is_raider:
        parts.append("They have raided the Dungeon Arcade before.")

    # Chatter history — only mention if notable
    if total_chatter > 0 and not is_raider:
        if firsts >= 5:
            parts.append(f"They are a frequent early arrival — first chatter {firsts} times.")
        elif firsts > 0:
            parts.append(f"They have claimed first chatter {firsts} time{'s' if firsts != 1 else ''}.")

    # Dice fate — mention if they have notable history
    if nat20s >= 3 and nat1s >= 3:
        parts.append(
            f"The dice both favour and curse them — {nat20s} natural 20s and {nat1s} fumbles."
        )
    elif nat20s >= 2:
        parts.append(f"Fortune has smiled on them — {nat20s} natural 20s to their name.")
    elif nat1s >= 2:
        parts.append(f"The dice have not been kind — {nat1s} fumbles recorded.")
    elif nat20s == 1:
        parts.append("They have rolled a natural 20 in the Dungeon Arcade.")
    elif nat1s == 1:
        parts.append("They have rolled a natural 1 in the Dungeon Arcade.")

    # Level — only mention if meaningful
    if level >= 5:
        parts.append(f"As an adventurer, they are Level {level}.")

    # Cap at 3 sentences to avoid context bloat
    return " ".join(parts[:3])
