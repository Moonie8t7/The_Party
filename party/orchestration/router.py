import json
import random
import re
from anthropic import Anthropic
from party.config import settings
from party.models import Trigger, CHARACTERS, DirectAddressResult, TriggerType
from party.log import get_logger
from party.context.phonetics import (
    CHARACTER_NAMES,
    PHONETIC_ALIASES,
    is_direct_address as detect_phonetic_address,
    PhoneticMatchResult
)

log = get_logger(__name__)

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


def resolve_companions(result: DirectAddressResult) -> list[str]:
    """
    Given a DirectAddressResult, probabilistically select companions.
    """
    if not result.detected:
        return []

    # If it's a group address (determined by high probabilities in candidates),
    # we skip the global gate or use a much higher one.
    is_group = any(p > 0.8 for _, p in result.companion_candidates)

    if not is_group and random.random() >= COMPANION_GLOBAL_CHANCE:
        return []

    companions = []
    for companion_name, probability in result.companion_candidates:
        if random.random() < probability:
            companions.append(companion_name)

    return companions


async def _llm_route(trigger_id: str, trigger_text: str) -> list[str]:
    """LLM fallback routing."""
    import asyncio
    loop = asyncio.get_event_loop()
    client = Anthropic(api_key=settings.anthropic_api_key)

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
        loop.run_in_executor(
            None,
            lambda: client.messages.create(
                model=settings.router_model,
                max_tokens=100,
                messages=[{"role": "user", "content": router_prompt}],
            ),
        ),
        timeout=settings.provider_timeout_seconds,
    )

    raw = response.content[0].text.strip()
    match = re.search(r"\[.*?\]", raw)
    if match:
        result_chars = json.loads(match.group())
        result_chars = [c for c in result_chars if c in CHARACTERS]
        if result_chars:
            return result_chars

    raise ValueError("LLM returned no valid character names")


async def route_trigger(trigger: Trigger) -> list[str]:
    """Public router interface."""
    characters, _, _ = await _route_with_method(trigger)
    return characters


async def _route_with_method(trigger: Trigger) -> tuple[list[str], str, set[str]]:
    """Internal router logic."""
    if trigger.type == TriggerType.IDLE:
        all_chars = list(CHARACTERS.keys())
        random.shuffle(all_chars)
        count = random.randint(2, 3)
        characters = all_chars[:count]
        log.info("router.idle_select", trigger_id=trigger.trigger_id, characters=characters)
        return characters, "idle", set()

    # ── Direct address check ──────────
    direct = detect_direct_address(trigger.text)
    if direct.detected:
        companions = resolve_companions(direct)
        characters = [direct.primary] + companions
        companion_set = set(companions)

        log.info(
            "router.direct_address",
            trigger_id=trigger.trigger_id,
            primary=direct.primary,
            companions=companions,
        )
        return characters, "direct_address", companion_set

    # ── Rule-based routing ──────────
    text_lower = trigger.text.lower()
    for idx, rule in enumerate(ROUTING_RULES):
        if any(kw in text_lower for kw in rule["keywords"]):
            characters = rule["characters"]
            log.info(
                "router.rule_match",
                trigger_id=trigger.trigger_id,
                characters=characters,
                rule_index=idx,
            )
            return characters, "rule", set()

    # ── LLM fallback ──────────
    log.info("router.llm_fallback_attempt", trigger_id=trigger.trigger_id)
    try:
        characters = await _llm_route(trigger.trigger_id, trigger.text)
        log.info(
            "router.llm_fallback", trigger_id=trigger.trigger_id, characters=characters
        )
        return characters, "llm", set()
    except Exception as e:
        log.warning(
            "router.llm_fallback_failed", trigger_id=trigger.trigger_id, reason=str(e)
        )

    # Final fallback
    default = ["grokthar", "gemaux"]
    log.info("router.default", trigger_id=trigger.trigger_id, reason="no_rule_no_llm")
    return default, "default", set()
