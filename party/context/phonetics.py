"""
Phonetic dictionary and direct address detection for The Party.
Centralized location for "sounds like" and name mappings.
"""

import re
import difflib
from typing import TypedDict, Optional, Dict, List

# --- Constants ---
CHARACTER_NAMES = ["clauven", "geptima", "gemaux", "grokthar", "deepwilla"]

PHONETIC_ALIASES = {
    "clauven": [
        "clorvin", "clovin", "clovan", "cloven", "clover",
        "clauvin", "clavin", "clayven", "clo ven", "clo vin", "clay ven"
    ],
    "deepwilla": [
        "deepwiller", "deepvilla", "deepwillow", "deep villa",
        "deep willa", "deep willer", "deep willow",
        "deepwila", "deepwilah", "deep will ah", "deepwella", "deepweller"
    ],
    "geptima": [
        "septima", "geptema", "geptimma", "geptimah",
        "gep tima", "gep tema", "jeptima", "jeptema",
        "gepima", "getima", "kep tima", "keptima"
    ],
    "gemaux": [
        "gemmo", "gem-o", "gemauto", "gemo",
        "gem oh", "gem o", "gem mow",
        "gemma", "gemer", "gemoe", "jemo", "gem ow", "gem au"
    ],
    "grokthar": [
        "grok-thar", "grokthor", "grockthar",
        "grock thor", "grok thar", "grok tar", "grok dar",
        "grock thar", "grock dar", "grokther", "groktharh"
    ],
}

# Strict group aliases: Specific to the system, low collision risk
GROUP_ALIASES_STRICT = [
    "party", "the party", "partee", "pardy", "barty", "pawty", "potty", "the potty"
]

# Broad group aliases: Natural language, high collision risk (only front-of-sentence or wake-word)
GROUP_ALIASES_BROAD = [
    "everyone", "everybody", "every body", "all of you", "all of ya", "you all", "yall", "guys"
]

WAKE_WORDS = {"hey", "yo", "ask", "oi"}

FUZZY_THRESHOLD_CHAR = 0.84
FUZZY_THRESHOLD_GROUP_STRICT = 0.85

# --- Structured Return Type ---

class PhoneticMatchResult(TypedDict):
    matched: bool
    target: Optional[str]      # "clauven", "group", None
    match_type: Optional[str]  # "exact", "alias", "fuzzy", None
    is_group: bool
    score: float               # 1.0 for exact/alias, 0.0-1.0 for fuzzy
    matched_text: Optional[str]

# --- Internal Utilities ---

def normalize_for_match(text: str) -> str:
    """Lowercase, strip punctuation, collapse all spaces."""
    clean = re.sub(r"[^\w\s]", "", text.lower())
    return "".join(clean.split())

def _dedupe(items: List[str]) -> List[str]:
    return list(dict.fromkeys(items))

def _build_alias_to_canonical() -> Dict[str, str]:
    """Builds a map of NORMALIZED aliases to their canonical character names."""
    mapping = {}
    for name in CHARACTER_NAMES:
        mapping[normalize_for_match(name)] = name
        for alias in PHONETIC_ALIASES.get(name, []):
            mapping[normalize_for_match(alias)] = name
    return mapping

ALIAS_TO_CANONICAL = _build_alias_to_canonical()

def _compile_patterns(names_or_aliases: List[str]) -> List[re.Pattern[str]]:
    patterns = []
    for item in names_or_aliases:
        escaped = re.escape(item)
        # 1. Start of line with optional leading noise/punctuation
        patterns.append(re.compile(rf"^({escaped})(?:\b|[,:!\-\s])", re.I))
        # 2. Wake word + name (Captures the name in group 1)
        patterns.append(re.compile(rf"\b(?:hey|ask|yo|oi)\s+({escaped})\b", re.I))
        # 3. Mention style (@name)
        patterns.append(re.compile(rf"(?:^|\s)@({escaped})\b", re.I))
        # 4. Name followed by attention punctuation anywhere
        patterns.append(re.compile(rf"\b({escaped})[,:]", re.I))
    return patterns

# Precompiled Patterns
CHAR_PATTERNS = {name: _compile_patterns(_dedupe([name] + PHONETIC_ALIASES.get(name, []))) for name in CHARACTER_NAMES}
STRICT_GROUP_PATTERNS = _compile_patterns(_dedupe(GROUP_ALIASES_STRICT))

# Broad group patterns are restricted to Start of line or explicit wake words
# We ensure the group word is captured as group 1 for consistency
BROAD_GROUP_PATTERNS = []
for group in _dedupe(GROUP_ALIASES_BROAD):
    escaped = re.escape(group)
    BROAD_GROUP_PATTERNS.append(re.compile(rf"^(?:hey\s+|yo\s+|ask\s+|oi\s+)?({escaped})(?:\b|[,:!\-\s])", re.I))
    BROAD_GROUP_PATTERNS.append(re.compile(rf"\b(?:hey|yo|ask|oi)\s+({escaped})\b", re.I))

def fuzzy_ratio(candidate: str, target: str) -> float:
    """Returns similarity ratio (0.0 - 1.0) after normalization."""
    norm_c = normalize_for_match(candidate)
    norm_t = normalize_for_match(target)
    if not norm_c or not norm_t:
        return 0.0
    if norm_c == norm_t:
        return 1.0
    return difflib.SequenceMatcher(None, norm_c, norm_t).ratio()

def strip_leading_wake_words(text: str) -> str:
    """Removes common leading wake words for better fuzzy matching."""
    tokens = text.lower().strip().split()
    while tokens and tokens[0] in WAKE_WORDS:
        tokens.pop(0)
    return " ".join(tokens)

# --- Public Interface ---

def is_direct_address(text: str) -> PhoneticMatchResult:
    """
    Highly robust direct address detection.
    Combines precompiled regex patterns (strict) with fuzzy fallback on aliases.
    """
    text_clean = text.strip()
    if not text_clean:
        return {"matched": False, "target": None, "match_type": None, "is_group": False, "score": 0.0, "matched_text": None}

    # 1. Strict Character Matches (Regex)
    for name, patterns in CHAR_PATTERNS.items():
        for pattern in patterns:
            match = pattern.search(text_clean)
            if match:
                matched_text = match.group(1)
                # Compare NORMALIZED forms to decide if it's "exact" (canonical) or "alias"
                match_type = "exact" if normalize_for_match(matched_text) == normalize_for_match(name) else "alias"
                return {
                    "matched": True, "target": name, "match_type": match_type,
                    "is_group": False, "score": 1.0, "matched_text": matched_text
                }

    # 2. Strict Group Matches (Regex)
    # 2a. Strict Group aliases (always allowed if patterns match)
    for pattern in STRICT_GROUP_PATTERNS:
        match = pattern.search(text_clean)
        if match:
            matched_text = match.group(1)
            return {
                "matched": True, "target": "group", "match_type": "alias",
                "is_group": True, "score": 1.0, "matched_text": matched_text
            }
    
    # 2b. Broad Group aliases (Only if start of line or wake word)
    for pattern in BROAD_GROUP_PATTERNS:
        match = pattern.search(text_clean)
        if match:
            matched_text = match.group(1)
            return {
                "matched": True, "target": "group", "match_type": "alias",
                "is_group": True, "score": 1.0, "matched_text": matched_text
            }

    # 3. Fuzzy Fallback on Opening Phrase
    # We check fuzzy match against ALL aliases (mapped back to canonical)
    stripped = strip_leading_wake_words(text_clean)
    tokens = stripped.split()
    prefixes = []
    if len(tokens) >= 1: prefixes.append(tokens[0])
    if len(tokens) >= 2: prefixes.append(" ".join(tokens[:2]))

    best_char_target = None
    best_char_score = 0.0
    best_char_prefix = None

    for prefix in prefixes:
        norm_prefix = normalize_for_match(prefix)
        if not norm_prefix: continue
        
        # Check against everything in the alias map (ALREADY NORMALISED)
        for cand_norm, canonical in ALIAS_TO_CANONICAL.items():
            if norm_prefix == cand_norm:
                score = 1.0
            else:
                score = difflib.SequenceMatcher(None, norm_prefix, cand_norm).ratio()
            
            if score >= FUZZY_THRESHOLD_CHAR and score > best_char_score:
                best_char_score = score
                best_char_target = canonical
                best_char_prefix = prefix

    if best_char_target:
        # If it was a perfect match with a precomputed alias, we can treat it as "alias" 
        # (Though regex usually catches those first). If it's pure fuzzy, we mark as "fuzzy".
        match_type = "alias" if best_char_score == 1.0 else "fuzzy"
        return {
            "matched": True, "target": best_char_target, "match_type": match_type,
            "is_group": False, "score": best_char_score, "matched_text": best_char_prefix
        }

    # 4. Fuzzy Fallback for Group
    # Only for "Strict" group words (party, potty, etc.)
    # Broad terms like "everyone", "guys" are regex-only to reduce false positives.
    if tokens:
        prefix = tokens[0]
        # Only fuzzy-match the core system summon "party" and its close phonetic variants
        for group_word in ["party", "partee", "pardy", "potty"]:
            score = fuzzy_ratio(prefix, group_word)
            if score >= FUZZY_THRESHOLD_GROUP_STRICT:
                return {
                    "matched": True, "target": "group", "match_type": "fuzzy",
                    "is_group": True, "score": score, "matched_text": prefix
                }

    return {"matched": False, "target": None, "match_type": None, "is_group": False, "score": 0.0, "matched_text": None}
