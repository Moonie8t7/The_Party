"""
Context tier architecture for Sprint 11.

Three tiers per call:
  Cold   — character system prompt (assembled at startup, never rebuilt)
  Warm   — per-trigger: scene, session, vision, feats (same for all chars in scene)
  Hot    — per-character: trigger text + role instruction + optional primary response
"""
import os
from dataclasses import dataclass, field
from datetime import datetime

from typing import Optional
from party.config import settings
from party.models import Trigger, TriggerType
from party.context.session import read_session_context
from party.context.key_events import read_key_events, format_key_events_for_context
from party.context.viewer_memory import get_viewer, format_viewer_context
from party.vision.loop import get_latest_description
from party.vision.log import get_recent_entries
from party.log import get_logger

log = get_logger(__name__)

# ── Closing instructions injected as the final hot-context line ───────────────

COMPANION_SEQUENTIAL_CLOSING = (
    "Now add a brief (1 sentence) unrequested comment to the conversation. "
    "Acknowledge what was just said. Use natural social recall for any past events—"
    "do not recite dates or exact log entries."
)

COMPANION_PARALLEL_CLOSING = (
    "React to this situation as your character. Keep your response to one sentence. "
    "React to what is happening, not to what another character may have said."
)

NORMAL_CLOSING = (
    "Now respond as your character, aware of the current context "
    "and what your party members just said. Use natural social recall for any "
    "past events—do not recite dates or exact log entries."
)

# ── Vision log limits per role ────────────────────────────────────────────────
# Task 11.10 — dynamic vision log injection limits

VISION_CONTEXT_ENTRIES = {
    "primary":   3,
    "companion": 1,
    "system":    5,
}


# ── WarmContext dataclass ─────────────────────────────────────────────────────

@dataclass
class WarmContext:
    timestamp: str
    scene: str
    session: str
    vision_current: str
    vision_recent: list[str] = field(default_factory=list)
    stream_feats: str = ""
    key_events: list[str] = field(default_factory=list)
    viewer_context: str = ""


async def build_warm_context(scene: str = "Unknown", viewer: Optional[str] = None) -> WarmContext:
    """
    Build the warm context for a trigger. Async because session/vision reads
    may involve file I/O. Called once per trigger; shared across all character calls.
    """
    now = datetime.now()
    timestamp = now.strftime("%A %d %B %Y, %H:%M")

    session = read_session_context() or ""
    vision_current = get_latest_description() or ""
    # Read the maximum we might need; callers slice per role
    vision_recent = get_recent_entries(VISION_CONTEXT_ENTRIES["system"]) or []

    stream_feats = ""
    feats_path = os.path.join("session", "stream_feats.txt")
    if os.path.exists(feats_path):
        try:
            with open(feats_path, "r", encoding="utf-8") as f:
                feats = f.read().strip()
                if feats:
                    stream_feats = feats
        except Exception:
            pass

    key_events = read_key_events()

    viewer_context = ""
    if viewer:
        viewer_data = await get_viewer(viewer)
        if viewer_data:
            viewer_context = format_viewer_context(viewer_data, viewer)

    return WarmContext(
        timestamp=timestamp,
        scene=scene,
        session=session,
        vision_current=vision_current,
        vision_recent=vision_recent,
        stream_feats=stream_feats,
        key_events=key_events,
        viewer_context=viewer_context,
    )


# ── Warm context formatters ───────────────────────────────────────────────────

def format_warm_primary(warm: WarmContext) -> str:
    """
    Full warm context string for the session snapshot passed to primary characters.
    Includes session context, vision log (up to 3 entries), scene, and stream feats.
    """
    parts = [
        f"Current date and time: {warm.timestamp}",
        "You are currently in a live stream on Twitch. The streamer/user you are talking to is Moonie.",
    ]
    if warm.session:
        parts.append("Session context:")
        parts.append(warm.session)
    if warm.key_events:
        formatted = format_key_events_for_context(warm.key_events)
        if formatted:
            parts.append(formatted)
    if warm.viewer_context:
        parts.append(f"Viewer context: {warm.viewer_context}")
    if warm.vision_current:
        parts.append(f"Currently on screen: {warm.vision_current}")
    recent = warm.vision_recent[:VISION_CONTEXT_ENTRIES["primary"]]
    if recent:
        parts.append("Recent screen observations:")
        parts.extend(f"  {entry}" for entry in recent)
    parts.append(f"Current OBS Scene: {warm.scene}")
    if warm.stream_feats:
        parts.append("\nStream Feats and Milestones (Historical context):")
        parts.append(warm.stream_feats)
    return "\n".join(parts)


def format_warm_companion(warm: WarmContext) -> str:
    """
    Compressed warm context for companion calls.
    Excludes session context, stream feats, and all but the latest vision line.
    Target: ≤ 40% of primary context size by token estimate.
    """
    parts = [f"Current OBS Scene: {warm.scene}"]
    if warm.vision_current:
        parts.append(f"Currently on screen: {warm.vision_current}")
    return "\n".join(parts)


# ── Message builders (hot context) ───────────────────────────────────────────

def build_primary_message(trigger: Trigger, warm: WarmContext) -> list[dict]:
    """
    Build the user message for a primary character call.
    Returns a single-item messages list.
    """
    if trigger.type == TriggerType.SYSTEM:
        content = f"System event: {trigger.text}"
    elif trigger.type == TriggerType.IDLE:
        content = "Start an idle conversation based on the current scene and context."
    else:
        content = f"Moonie said: {trigger.text}"
    return [{"role": "user", "content": content}]


def build_companion_sequential_message(
    trigger: Trigger,
    warm: WarmContext,
    primary_display_name: str,
    primary_text: str,
) -> list[dict]:
    """
    Build the user message for a sequential companion call.
    The companion receives the primary's full response and reacts to it.
    Task 11.3 — sequential companion context contract.
    """
    if trigger.type == TriggerType.IDLE:
        situation = "Current Situation: Idle chatter"
    else:
        situation = f"Moonie said: {trigger.text}"

    content = "\n".join([
        situation,
        "",
        f"{primary_display_name} said: {primary_text}",
        "",
        COMPANION_SEQUENTIAL_CLOSING,
    ])
    return [{"role": "user", "content": content}]


def build_companion_parallel_message(trigger: Trigger, warm: WarmContext) -> list[dict]:
    """
    Build the user message for a parallel companion call.
    The companion does NOT know what the primary said — fires simultaneously.
    Task 11.3 — parallel companion context contract.
    """
    content = "\n".join([
        trigger.text,
        "",
        COMPANION_PARALLEL_CLOSING,
    ])
    return [{"role": "user", "content": content}]
