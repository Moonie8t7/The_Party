import json
import random
import re
from dataclasses import dataclass, field

# ── Conduct patterns ──────────────────────────────────────────────────────────
# TOS_PATTERNS: racial, ethnic, and targeted slurs — hard violations.
# Conservative by design: false positives are acceptable, false negatives are not.

TOS_PATTERNS = [
    r'\bn[i!1][g9][g9][e3]r',
    r'\bn[i!1][g9][g9][a@]',
    r'\bch[i!1]nk',
    r'\bsp[i!1][ck]\b',
    r'\bk[i!1]k[e3]',
    r'\btr[a@]nn',
    r'\bf[a@][g9][g9][o0]t',
    r'\br[e3]t[a@]rd',
    r'\bwh[o0]r[e3]',
    r'\bsl[u]t',
    r'\bc[u]nt',
]

# CONTROVERSY_PATTERNS: topics characters should sidestep rather than engage.
CONTROVERSY_PATTERNS = [
    r'\bpolitics?\b', r'\bpolitical\b',
    r'\belection\b', r'\bvoting\b', r'\bvoter\b',
    r'\brepublican\b', r'\bdemocrat\b', r'\btory\b', r'\blabour party\b',
    r'\btrump\b', r'\bbiden\b', r'\bstarmer\b', r'\bsunak\b',
    r'\bpalestine\b', r'\bisrael\b', r'\bpalestinian\b', r'\bisraeli\b',
    r'\bislam\b', r'\bmuslim\b', r'\bchristianity\b', r'\bjudaism\b',
    r'\batheism\b', r'\bgod exists\b', r'\bdoes god\b',
    r'\babortion\b', r'\bpro.?life\b', r'\bpro.?choice\b',
    r'\bblack lives\b', r'\bblm\b', r'\bwhite supremac\b',
    r'\bimmigration\b', r'\billegal alien\b',
    r'\bgun control\b', r'\bsecond amendment\b',
    r'\bdeath penalty\b', r'\bcapital punishment\b',
    r'\beuthanasia\b',
]


def check_conduct(text: str) -> tuple[str, str] | None:
    """
    Check trigger text for conduct violations.
    Returns (violation_type, reason) or None if clean.
    violation_type is "tos" or "controversy".
    TOS check runs before controversy check.
    """
    lower = text.lower()
    for pattern in TOS_PATTERNS:
        if re.search(pattern, lower):
            return ("tos", f"matched: {pattern}")
    for pattern in CONTROVERSY_PATTERNS:
        if re.search(pattern, lower):
            return ("controversy", f"matched: {pattern}")
    return None
from typing import Optional
from anthropic import AsyncAnthropic
from party.config import settings
from party.models import Trigger, CHARACTERS, DirectAddressResult, TriggerType
from party.log import get_logger
from party.orchestration.modes import ExecutionMode
from party.context.phonetics import (
    CHARACTER_NAMES,
    PHONETIC_ALIASES,
    is_direct_address as detect_phonetic_address,
    PhoneticMatchResult
)

log = get_logger(__name__)


# ── RouterResult — Sprint 11 breaking change ──────────────────────────────────

@dataclass
class RouterResult:
    """
    Structured routing decision returned by route_trigger().

    Invariants:
    - len(primary) == 1 always
    - len(companions) <= 1 for non-SYSTEM triggers; up to 4 for SYSTEM
    - primary[0] not in companions
    """
    primary: list[str]       # always exactly 1 character name
    companions: list[str]    # 0–1 for normal triggers; up to 4 for SYSTEM
    method: str              # "rule" | "llm" | "default" | "direct_address" | "idle" | "system"
    mode: ExecutionMode      # PARALLEL or SEQUENTIAL


# ── ExecutionMode assignment per trigger type (Task 11.6) ─────────────────────

_MODE_MAP: dict[TriggerType, ExecutionMode] = {
    TriggerType.SYSTEM:        ExecutionMode.PARALLEL,
    TriggerType.HOTKEY:        ExecutionMode.PARALLEL,
    TriggerType.CHAT_TRIGGER:  ExecutionMode.SEQUENTIAL,
    TriggerType.STT:           ExecutionMode.SEQUENTIAL,
    TriggerType.IDLE:          ExecutionMode.PARALLEL,
    TriggerType.TIMED:         ExecutionMode.SEQUENTIAL,
    TriggerType.VIEWER_EVENT:  ExecutionMode.SEQUENTIAL,
}


# ── Round-robin index for IDLE primary selection ──────────────────────────────

_idle_index = 0


def _get_mode(trigger_type: TriggerType) -> ExecutionMode:
    return _MODE_MAP.get(trigger_type, ExecutionMode.SEQUENTIAL)


def _select_companion(primary: str, trigger_type: TriggerType) -> Optional[str]:
    """
    Probabilistically select one companion for non-direct-address routing.
    STT triggers never get a companion.
    IDLE triggers always get one (banter is the point).
    """
    if trigger_type == TriggerType.STT:
        return None

    candidates = COMPANION_PROBABILITIES[primary]

    if trigger_type == TriggerType.IDLE:
        # Always assign a companion for IDLE
        for companion_name, probability in candidates:
            if random.random() < probability:
                return companion_name
        return candidates[0][0] if candidates else None

    # Standard global chance gate
    if random.random() >= COMPANION_GLOBAL_CHANCE:
        return None

    for companion_name, probability in candidates:
        if random.random() < probability:
            return companion_name

    return None


ROUTING_RULES = [

    # ── Death / failure ──────────────────────────────────────────
    {
        "keywords": [
            "died", "death", "killed", "game over", "failed",
            "wiped", "lost", "respawn", "you died", "defeated",
        ],
        "characters": ["grokthar", "geptima", "deepwilla"],
    },

    # ── Victory / achievement ────────────────────────────────────
    {
        "keywords": [
            "won", "beat", "completed", "finished", "victory",
            "achievement", "unlocked", "level up", "leveled up",
            "trophy", "cleared", "first clear", "platinum",
        ],
        "characters": ["gemaux", "geptima", "grokthar"],
    },

    # ── Close call / near death ──────────────────────────────────
    {
        "keywords": [
            "barely", "almost died", "low health", "close call",
            "survived", "nearly", "one shot", "clutch", "last second",
        ],
        "characters": ["grokthar", "deepwilla", "geptima"],
    },

    # ── Combat / action ──────────────────────────────────────────
    {
        "keywords": [
            "fight", "combat", "battle", "attack", "enemy",
            "boss", "horde", "ambush", "pvp", "killed an enemy",
            "slayed", "eliminated",
        ],
        "characters": ["grokthar", "deepwilla", "geptima"],
    },

    # ── Skill / impressive play ──────────────────────────────────
    {
        "keywords": [
            "incredible", "insane play", "perfect", "flawless",
            "no damage", "speedrun", "skill", "clutch play",
            "outplayed", "montage",
        ],
        "characters": ["grokthar", "gemaux", "deepwilla"],
    },

    # ── Mistake / blunder ────────────────────────────────────────
    {
        "keywords": [
            "mistake", "blunder", "misplay", "accident", "oops",
            "fell off", "walked into", "accidentally", "forgot",
            "sold the wrong", "wasted",
        ],
        "characters": ["grokthar", "geptima", "deepwilla"],
    },

    # ── Lore / knowledge / who is ────────────────────────────────
    {
        "keywords": [
            "lore", "history", "why", "how does", "explain",
            "what is", "who is", "who are", "tell me about",
            "what was", "backstory", "origin",
        ],
        "characters": ["clauven", "gemaux", "geptima"],
    },

    # ── Technical / game mechanics ───────────────────────────────
    {
        "keywords": [
            "build", "craft", "upgrade", "mechanics", "system",
            "stats", "damage", "loadout", "gear", "min max",
            "optimise", "optimize", "meta", "tier list",
        ],
        "characters": ["deepwilla", "clauven"],
    },

    # ── Strategy / planning ──────────────────────────────────────
    {
        "keywords": [
            "plan", "strategy", "approach", "should moonie",
            "what should", "next step", "how to", "best way",
            "decision", "choose", "pick", "which one",
        ],
        "characters": ["clauven", "deepwilla", "geptima"],
    },

    # ── Discovery / exploration ──────────────────────────────────
    {
        "keywords": [
            "found", "discovered", "secret", "hidden",
            "exploring", "new area", "dungeon", "treasure",
            "easter egg", "rare", "collectible",
        ],
        "characters": ["clauven", "deepwilla", "gemaux"],
    },

    # ── Loot / inventory / purchases ─────────────────────────────
    {
        "keywords": [
            "loot", "inventory", "item", "weapon", "armour", "armor",
            "bought", "purchased", "dropped", "reward", "chest",
            "legendary", "rare drop",
        ],
        "characters": ["deepwilla", "clauven", "grokthar"],
    },

    # ── Frustration / stuck ──────────────────────────────────────
    {
        "keywords": [
            "stuck", "frustrated", "impossible", "keeps dying",
            "annoying", "rage", "unfair", "broken", "cheating",
            "wall", "can't figure", "no idea",
        ],
        "characters": ["geptima", "grokthar", "deepwilla"],
    },

    # ── Horror / jump scare / tension ────────────────────────────
    {
        "keywords": [
            "scared", "terrifying", "jump scare", "horror",
            "creepy", "spooked", "dark", "tense", "jumpscared",
        ],
        "characters": ["gemaux", "grokthar", "geptima"],
    },

    # ── Funny / absurd moment ────────────────────────────────────
    {
        "keywords": [
            "hilarious", "cursed", "what just happened",
            "absurd", "ridiculous", "glitch", "bug",
            "that was weird", "chaotic",
        ],
        "characters": ["gemaux", "grokthar", "deepwilla"],
    },

    # ── Emotional / touching moment ──────────────────────────────
    {
        "keywords": [
            "sad", "emotional", "touching", "beautiful", "moving",
            "heartbreaking", "wholesome", "lovely", "sweet",
            "meaningful",
        ],
        "characters": ["geptima", "gemaux", "clauven"],
    },

    # ── Grinding / farming / slow moment ────────────────────────
    {
        "keywords": [
            "grinding", "farming", "farming for", "repeating",
            "doing the same", "slow", "boring section",
            "fetch quest", "side quest",
        ],
        "characters": ["deepwilla", "grokthar", "gemaux"],
    },

    # ── NPC / story moment ───────────────────────────────────────
    {
        "keywords": [
            "npc", "character said", "cutscene", "dialogue",
            "plot twist", "betrayal", "reveal", "ending",
            "narrative moment", "story beat",
        ],
        "characters": ["gemaux", "clauven", "geptima"],
    },

    # ── First time / new game ────────────────────────────────────
    {
        "keywords": [
            "first time", "never played", "new game", "just started",
            "beginning", "tutorial", "first impression",
        ],
        "characters": ["clauven", "gemaux", "deepwilla"],
    },

    # ── Technical issues ─────────────────────────────────────────
    {
        "keywords": [
            "crashed", "lag", "frame drop", "disconnected",
            "bug", "glitch", "loading", "frozen", "error",
        ],
        "characters": ["deepwilla", "grokthar", "geptima"],
    },

    # ── About Moonie / the stream / FAQ ──────────────────────────
    {
        "keywords": [
            "who is moonie", "how long", "how many", "when did",
            "what does moonie", "dungeon arcade", "watchmoonie",
            "your setup", "your specs", "your mic",
        ],
        "characters": ["clauven", "geptima", "gemaux"],
    },

    # ── Introduction / welcome ───────────────────────────────────
    {
        "keywords": [
            "welcome", "hello", "hi everyone", "hey chat",
            "good evening", "good morning", "starting stream",
            "going live", "stream is starting",
        ],
        "characters": ["geptima", "gemaux", "clauven"],
    },

    # ── Community moments ─────────────────────────────────────────
    {
        "keywords": [
            "raided", "subscribed", "followed", "donation",
            "gifted", "bits", "hype train", "new follower",
            "thank you for", "thanks for",
        ],
        "characters": ["geptima", "gemaux", "grokthar"],
    },

    # ── Chat chaos / direct chat reference ───────────────────────
    {
        "keywords": [
            "someone said", "in chat", "the chat", "chat is saying",
            "chat thinks", "chat wants",
        ],
        "characters": ["grokthar", "gemaux"],
    },

    # ── Creative / narrative / roleplay ──────────────────────────
    {
        "keywords": [
            "narrative", "roleplay", "imagine", "what if",
            "backstory", "universe", "world building",
        ],
        "characters": ["gemaux", "clauven", "deepwilla"],
    },

    # ── STT - Moonie thinking out loud ────────────────────────────
    # Catches uncertainty and self-directed questions
    {
        "keywords": ["i think", "maybe i should", "not sure", "i wonder", "what if i"],
        "characters": ["clauven", "geptima"],
    },

]


# COMPANION_PROBABILITIES[primary] = [(companion, probability), ...]
# Listed in priority order - first to pass speaks
COMPANION_PROBABILITIES: dict[str, list[tuple[str, float]]] = {
    "clauven": [
        ("grokthar",  0.45),
        ("deepwilla", 0.35),
        ("gemaux",    0.30),
        ("geptima",   0.15),
    ],
    "geptima": [
        ("grokthar",  0.30),
        ("gemaux",    0.25),
        ("deepwilla", 0.20),
        ("clauven",   0.10),
    ],
    "gemaux": [
        ("grokthar",  0.40),
        ("deepwilla", 0.30),
        ("geptima",   0.20),
        ("clauven",   0.15),
    ],
    "grokthar": [
        ("geptima",   0.35),
        ("gemaux",    0.25),
        ("deepwilla", 0.20),
        ("clauven",   0.10),
    ],
    "deepwilla": [
        ("clauven",   0.30),
        ("gemaux",    0.35),
        ("geptima",   0.25),
        ("grokthar",  0.20),
    ],
}

COMPANION_GLOBAL_CHANCE = 0.50

# ── d20 personality-weighted character selection (Sprint 14b) ─────────────────

# Weights reflect personality fit for each roll type.
# Nat1: Grokthar (blunt mockery), Deepwilla (finds the failure mode interesting),
#        Geptima (practical sympathy), Gemaux (dramatic despair), Clauven (measured disappointment)
# Nat20: Gemaux (fortune is theatrical), Geptima (practical celebration),
#         Grokthar (grudging respect), Clauven (analytical note), Deepwilla (probability angle)
_D20_CHARACTER_WEIGHTS: dict[str, list[tuple[str, float]]] = {
    "nat1": [
        ("grokthar",  0.40),
        ("deepwilla", 0.25),
        ("geptima",   0.18),
        ("gemaux",    0.12),
        ("clauven",   0.05),
    ],
    "nat20": [
        ("gemaux",    0.38),
        ("geptima",   0.25),
        ("grokthar",  0.20),
        ("clauven",   0.10),
        ("deepwilla", 0.07),
    ],
}


def _select_d20_character(roll_type: str) -> str:
    """
    Select a single character to react to a nat1 or nat20 roll.
    Uses personality-weighted random selection.
    Falls back to grokthar for nat1, gemaux for nat20 if roll_type unrecognised.
    """
    weights = _D20_CHARACTER_WEIGHTS.get(roll_type)
    if not weights:
        return "grokthar" if roll_type == "nat1" else "gemaux"

    names = [name for name, _ in weights]
    probs = [prob for _, prob in weights]
    # Normalise to sum to 1.0 in case of float drift
    total = sum(probs)
    normalised = [p / total for p in probs]

    return random.choices(names, weights=normalised, k=1)[0]


def detect_direct_address(text: str) -> DirectAddressResult:
    """
    Check if the trigger text is directly addressing a specific character or the whole party.
    Uses centralized phonetic engine for robust detection.
    """
    res = detect_phonetic_address(text)
    if not res["matched"]:
        return DirectAddressResult(detected=False, primary=None, companion_candidates=[])
    
    if res["is_group"]:
        # Group addressed - pick a primary but allow others to join with high probability
        primary = random.choice(CHARACTER_NAMES)
        other_chars = [c for c in CHARACTER_NAMES if c != primary]
        return DirectAddressResult(
            detected=True,
            primary=primary,
            companion_candidates=[(c, 0.90) for c in other_chars],
        )
    else:
        # Specific character addressed
        name = res["target"]
        return DirectAddressResult(
            detected=True,
            primary=name,
            companion_candidates=COMPANION_PROBABILITIES[name],
        )


def resolve_companions(result: DirectAddressResult, scene: str = "Unknown") -> list[str]:
    """
    Given a DirectAddressResult, probabilistically select companions.
    """
    if not result.detected:
        return []

    # If it's a group address (determined by high probabilities in candidates),
    # we skip the global gate or use a much higher one.
    is_group = any(p > 0.8 for _, p in result.companion_candidates)
    
    # If in Gaming scene, we are MUCH less likely to have companions
    is_gaming = (scene == "Gaming")
    global_chance = 0.15 if is_gaming else COMPANION_GLOBAL_CHANCE

    if not is_group and random.random() >= global_chance:
        return []

    companions = []
    for companion_name, probability in result.companion_candidates:
        # Scale individual probabilities down in gaming scene
        effective_prob = probability * 0.4 if is_gaming else probability
        if random.random() < effective_prob:
            companions.append(companion_name)

    return companions


async def _llm_route(trigger_id: str, trigger_text: str) -> list[str]:
    """LLM fallback routing. Returns list of character names (primary first)."""
    import asyncio
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    router_prompt = f"""You are routing a message to the correct party members in a D&D-themed Twitch stream.

The party members are:
- clauven (High Elf Wizard): analysis, patterns, lore, careful reasoning
- geptima (Human Cleric): support, empathy, practical guidance, broadly helpful
- gemaux (Changeling Bard): narrative, creativity, unexpected angles, entertainment
- grokthar (Half-Orc Ranger): blunt reactions, calling things out, instinct, chaos
- deepwilla (Rock Gnome Artificer): technical observations, wild ideas, enthusiasm, science

The trigger to route: "{trigger_text}"

Return ONLY a JSON array of 2 or 3 character names in the order they should speak.
The first character should be most relevant to the trigger.
Example: ["grokthar", "clauven"]"""

    response = await asyncio.wait_for(
        client.messages.create(
            model=settings.router_model,
            max_tokens=100,
            messages=[{"role": "user", "content": router_prompt}],
        ),
        timeout=settings.provider_timeout_normal_seconds,
    )

    raw = response.content[0].text.strip()
    match = re.search(r"\[.*?\]", raw)
    if match:
        result_chars = json.loads(match.group())
        result_chars = [c for c in result_chars if c in CHARACTERS]
        if result_chars:
            return result_chars

    raise ValueError("LLM returned no valid character names")


async def route_trigger(trigger: Trigger) -> RouterResult:
    """
    Public router interface. Returns RouterResult.
    This is the Sprint 11 breaking change — previously returned list[str].
    """
    return await _route_with_method(trigger)


async def _route_with_method(trigger: Trigger) -> RouterResult:
    """Internal router logic. Returns RouterResult."""
    mode = _get_mode(trigger.type)

    # ── Conduct check — always first ──────────────────────────────────────────
    conduct = check_conduct(trigger.text)
    if conduct:
        violation_type, reason = conduct
        log.info(
            "router.conduct_flag",
            trigger_id=trigger.trigger_id,
            violation_type=violation_type,
            reason=reason,
        )
        if violation_type == "tos":
            return RouterResult(
                primary=["geptima"],
                companions=[],
                method="conduct_tos",
                mode=ExecutionMode.SEQUENTIAL,
            )
        else:
            return RouterResult(
                primary=["gemaux"],
                companions=[],
                method="conduct_controversy",
                mode=ExecutionMode.SEQUENTIAL,
            )

    # ── Redundancy check ──────────────────────────────────────────────────────
    if trigger.type == TriggerType.TIMED and "observe and comment" in trigger.text:
        log.info("router.ignore_redundant_timed", trigger_id=trigger.trigger_id)
        return RouterResult(primary=["grokthar"], companions=[], method="ignored_redundant", mode=mode)

    # ── SYSTEM: all characters, primary from routing ──────────────────────────
    if trigger.type == TriggerType.SYSTEM:
        text_lower = trigger.text.lower()

        # ── d20 fast-path: nat1/nat20 → single character, no companion ────────
        if "natural 1" in text_lower or "natural 20" in text_lower:
            roll_type = "nat1" if "natural 1" in text_lower else "nat20"
            primary = _select_d20_character(roll_type)
            log.info(
                "router.d20_select",
                trigger_id=trigger.trigger_id,
                roll_type=roll_type,
                primary=primary,
            )
            return RouterResult(
                primary=[primary],
                companions=[],
                method=f"d20:{roll_type}",
                mode=ExecutionMode.PARALLEL,
            )

        # Standard SYSTEM: all characters respond
        all_chars = list(CHARACTERS.keys())
        primary = "gemaux"  # default primary for SYSTEM
        for rule in ROUTING_RULES:
            if any(kw in text_lower for kw in rule["keywords"]):
                primary = rule["characters"][0]
                break
        companions = [c for c in all_chars if c != primary]
        log.info("router.system_all", trigger_id=trigger.trigger_id, primary=primary)
        return RouterResult(primary=[primary], companions=companions, method="system", mode=mode)

    # ── IDLE: round-robin primary, always one companion ───────────────────────
    if trigger.type == TriggerType.IDLE:
        global _idle_index
        all_chars = list(CHARACTERS.keys())
        primary = all_chars[_idle_index % len(all_chars)]
        _idle_index += 1
        companion = _select_companion(primary, trigger.type)
        companions = [companion] if companion else []
        log.info("router.idle_select", trigger_id=trigger.trigger_id, primary=primary, companions=companions)
        return RouterResult(primary=[primary], companions=companions, method="idle", mode=mode)

    # ── Direct address check ──────────────────────────────────────────────────
    direct = detect_direct_address(trigger.text)
    if direct.detected:
        try:
            from party.context.obs_context import get_current_scene
            scene = await get_current_scene()
        except Exception:
            scene = "Unknown"

        all_companions = resolve_companions(direct, scene=scene)
        # Cap to 1 companion for non-SYSTEM triggers
        companions = all_companions[:1]

        log.info(
            "router.direct_address",
            trigger_id=trigger.trigger_id,
            primary=direct.primary,
            companions=companions,
        )
        return RouterResult(primary=[direct.primary], companions=companions, method="direct_address", mode=mode)

    # ── Rule-based routing ────────────────────────────────────────────────────
    text_lower = trigger.text.lower()
    for idx, rule in enumerate(ROUTING_RULES):
        if any(kw in text_lower for kw in rule["keywords"]):
            primary = rule["characters"][0]
            companion = _select_companion(primary, trigger.type)
            companions = [companion] if companion else []
            log.info(
                "router.rule_match",
                trigger_id=trigger.trigger_id,
                primary=primary,
                companions=companions,
                rule_index=idx,
            )
            return RouterResult(primary=[primary], companions=companions, method=f"rule:{idx}", mode=mode)

    # ── LLM fallback ──────────────────────────────────────────────────────────
    log.info("router.llm_fallback_attempt", trigger_id=trigger.trigger_id)
    try:
        chars = await _llm_route(trigger.trigger_id, trigger.text)
        primary = chars[0]
        companion = _select_companion(primary, trigger.type)
        companions = [companion] if companion else []
        log.info("router.llm_fallback", trigger_id=trigger.trigger_id, primary=primary)
        return RouterResult(primary=[primary], companions=companions, method="llm", mode=mode)
    except Exception as e:
        log.warning("router.llm_fallback_failed", trigger_id=trigger.trigger_id, reason=str(e))

    # ── Final fallback ────────────────────────────────────────────────────────
    log.info("router.default", trigger_id=trigger.trigger_id, reason="no_rule_no_llm")
    return RouterResult(primary=["grokthar"], companions=["gemaux"], method="default", mode=mode)
