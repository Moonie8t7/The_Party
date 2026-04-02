import re
from dataclasses import dataclass, field
from party.providers.base import ProviderError
from party.log import get_logger

log = get_logger(__name__)

SENTENCE_LIMITS = {
    "clauven":   5,
    "geptima":   3,
    "gemaux":    3,
    "grokthar":  3,
    "deepwilla": 4,
}


def count_sentences(text: str) -> int:
    """Rough sentence count — splits on . ! ? followed by space or end."""
    sentences = re.split(r'[.!?]+(?:\s|$)', text.strip())
    return len([s for s in sentences if s.strip()])


@dataclass
class RepairResult:
    text: str
    repaired: bool
    changes: list = field(default_factory=list)
    sentence_count: int = 0
    length_violation: bool = False


def repair_response(
    text: str,
    trigger_id: str = "",
    character_name: str = "unknown",
) -> RepairResult:
    """
    Validates and repairs LLM output.
    Returns RepairResult with .text, .repaired, .sentence_count, .length_violation.
    Raises ProviderError if text is empty after repair.
    """
    original = text
    changes = []

    # 1. Strip leading/trailing whitespace
    text = text.strip()

    # 2. Remove stage directions: *asterisks*
    text_no_stage = re.sub(r'\*[^*]*\*', '', text).strip()
    if text_no_stage != text:
        changes.append("removed_stage_directions")
        text = text_no_stage

    # 3. Replace em dashes and en dashes
    text_no_dash = re.sub(r'—\s*([a-z])', r', \1', text)
    text_no_dash = re.sub(r'—', '.', text_no_dash)
    text_no_dash = re.sub(r'–\s*([a-z])', r', \1', text_no_dash)
    text_no_dash = re.sub(r'–', '.', text_no_dash)
    if text_no_dash != text:
        changes.append("replaced_dashes")
        text = text_no_dash

    # Final strip
    text = text.strip()

    if not text:
        raise ProviderError("repair", character_name or "unknown", "empty after repair")

    was_repaired = text != original
    if changes and trigger_id:
        log.info("output.repair", trigger_id=trigger_id, character=character_name, changes=changes)

    sentence_count = count_sentences(text)
    limit = SENTENCE_LIMITS.get(character_name, 5)
    length_violation = sentence_count > limit

    return RepairResult(
        text=text,
        repaired=was_repaired,
        changes=changes,
        sentence_count=sentence_count,
        length_violation=length_violation,
    )
