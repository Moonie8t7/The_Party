from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from dataclasses import dataclass, field
import uuid
import os
from datetime import datetime


@dataclass
class DirectAddressResult:
    """
    Result of direct address detection.
    If detected is True, primary is the named character.
    companion_candidates is the ordered list of potential companions
    with their individual probabilities.
    """
    detected: bool
    primary: Optional[str]                         # e.g. "clauven"
    companion_candidates: list[tuple[str, float]]  # e.g. [("grokthar", 0.45), ...]


class TriggerType(str, Enum):
    HOTKEY = "hotkey"
    CHAT_TRIGGER = "chat_trigger"
    TIMED = "timed"
    STT = "stt"
    SYSTEM = "system"
    IDLE = "idle"
    VIEWER_EVENT = "viewer_event"


class TriggerPriority(int, Enum):
    HIGH = 0    # death, raid, boss
    NORMAL = 1  # general events
    LOW = 2     # chat banter, timed


class IncomingTrigger(BaseModel):
    """Raw payload from Streamer.bot. Validated at intake."""
    model_config = ConfigDict(extra="ignore")

    type: TriggerType
    text: str = Field(min_length=1, max_length=1000)
    priority: TriggerPriority = TriggerPriority.NORMAL
    cooldown_key: Optional[str] = None
    game: Optional[str] = None

    # Viewer event fields — populated by Streamer.bot for viewer_event triggers.
    # All optional; ignored for all other trigger types.
    viewer: Optional[str] = None          # username
    viewer_id: Optional[str] = None       # Twitch user ID
    rank: Optional[int] = None            # 1, 2, or 3
    history: Optional[dict] = None        # {"firsts": N, "seconds": N, "thirds": N}
    roll: Optional[dict] = None           # {"value": N, "type": "nat1"|"nat20"|"normal"}
    xp: Optional[int] = None             # total XP in XP system
    level: Optional[int] = None          # current level (1–20)

    # Generic event-specific data for memory storage (Sprint 13).
    # Used by raids, subs, gift subs, gift bombs.
    event_data: Optional[dict] = None


class Trigger(BaseModel):
    """Enriched trigger with system-assigned fields."""
    trigger_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    received_at: datetime = Field(default_factory=datetime.utcnow)
    type: TriggerType
    text: str
    priority: TriggerPriority
    cooldown_key: Optional[str]
    game: Optional[str]
    viewer: Optional[str] = None    # username if this is a viewer_event


class CharacterResponse(BaseModel):
    """A single character's response in the chain."""
    name: str
    display_name: str
    text: str
    voice_id: str
    provider: str
    latency_ms: int
    repaired: bool = False
    tokens_input: int = 0
    tokens_output: int = 0
    estimated_cost_usd: float = 0.0
    length_chars: int = 0
    length_sentences: int = 0


class Scene(BaseModel):
    """A complete processed trigger ready for output."""
    trigger: Trigger
    characters: list[str]
    responses: list[CharacterResponse]
    router_method: str           # "rule" | "llm" | "default"
    total_latency_ms: int
    error: Optional[str] = None


class TranscriptEntry(BaseModel):
    """Written to transcript.jsonl after each scene completes."""
    trigger_id: str
    received_at: str
    type: str
    text: str
    characters: list[str]
    router_method: str
    responses: list[dict]
    total_latency_ms: int
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    total_estimated_cost_usd: float = 0.0
    total_repair_events: int = 0
    error: Optional[str] = None


# ============================================================
# CHARACTER CONFIG
# ============================================================

@dataclass
class CharacterVoiceSettings:
    speed: float = 1.00
    stability: float = 0.55
    similarity_boost: float = 0.80
    style: float = 0.00
    use_speaker_boost: bool = True


@dataclass
class Character:
    name: str
    display_name: str
    provider_type: str    # "anthropic" | "openai" | "gemini" | "grok" | "deepseek"
    model_id: str
    voice_id: str         # ElevenLabs voice ID - set via settings.voice_*
    voice_settings: CharacterVoiceSettings = field(default_factory=CharacterVoiceSettings)
    prompt: str = ""               # loaded at startup
    context_supplement: str = ""   # appended to system prompt at call time


_prompts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts")


def _load_prompt(name: str) -> str:
    path = os.path.join(_prompts_dir, f"{name}.txt")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Prompt file missing: {path}")
    with open(path, encoding="utf-8") as f:
        return f.read()


def _load_context_supplements() -> str:
    """Load all context supplement files for characters."""
    supplement_files = [
        os.path.join(_prompts_dir, "moonie_context.txt"),
        os.path.join(_prompts_dir, "party_overview.txt"),
    ]
    parts = []
    for path in supplement_files:
        try:
            parts.append(open(path, encoding="utf-8").read().strip())
        except FileNotFoundError:
            pass
    return "\n\n".join(parts)


def _build_characters() -> dict:
    """Build CHARACTERS dict, pulling voice IDs from settings."""
    from party.config import settings  # local import avoids circular at module level

    context_supplement = _load_context_supplements()

    return {
        "clauven": Character(
            name="clauven",
            display_name="Clauven",
            provider_type="anthropic",
            model_id="claude-sonnet-4-6",
            voice_id=settings.voice_clauven,
            voice_settings=CharacterVoiceSettings(
                speed=1.00, stability=0.55, similarity_boost=0.80,
                style=0.00, use_speaker_boost=True,
            ),
            prompt=_load_prompt("clauven"),
            context_supplement=context_supplement,
        ),
        "geptima": Character(
            name="geptima",
            display_name="Geptima",
            provider_type="openai",
            model_id="gpt-4o",
            voice_id=settings.voice_geptima,
            voice_settings=CharacterVoiceSettings(
                speed=1.00, stability=0.55, similarity_boost=0.80,
                style=0.00, use_speaker_boost=True,
            ),
            prompt=_load_prompt("geptima"),
            context_supplement=context_supplement,
        ),
        "gemaux": Character(
            name="gemaux",
            display_name="Gemaux",
            provider_type="gemini",
            model_id="gemini-2.5-flash",
            voice_id=settings.voice_gemaux,
            voice_settings=CharacterVoiceSettings(
                speed=0.92, stability=0.60, similarity_boost=0.95,
                style=0.10, use_speaker_boost=False,
            ),
            prompt=_load_prompt("gemaux"),
            context_supplement=context_supplement,
        ),
        "grokthar": Character(
            name="grokthar",
            display_name="Grokthar",
            provider_type="grok",
            model_id="grok-3",
            voice_id=settings.voice_grokthar,
            voice_settings=CharacterVoiceSettings(
                speed=1.00, stability=0.55, similarity_boost=0.80,
                style=0.00, use_speaker_boost=True,
            ),
            prompt=_load_prompt("grokthar"),
            context_supplement=context_supplement,
        ),
        "deepwilla": Character(
            name="deepwilla",
            display_name="Deepwilla",
            provider_type="deepseek",
            model_id="deepseek-chat",
            voice_id=settings.voice_deepwilla,
            voice_settings=CharacterVoiceSettings(
                speed=1.08, stability=0.48, similarity_boost=0.95,
                style=0.23, use_speaker_boost=False,
            ),
            prompt=_load_prompt("deepwilla"),
            context_supplement=context_supplement,
        ),
    }


CHARACTERS: dict[str, Character] = _build_characters()
