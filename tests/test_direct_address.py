import pytest
from unittest.mock import patch
from party.orchestration.router import (
    detect_direct_address,
    resolve_companion,
    COMPANION_PROBABILITIES,
)
from party.models import DirectAddressResult


def test_detect_direct_address_name_with_comma():
    result = detect_direct_address("Clauven, what is this game about?")
    assert result.detected is True
    assert result.primary == "clauven"


def test_detect_direct_address_name_with_colon():
    result = detect_direct_address("Grokthar: how many times has Moonie died?")
    assert result.detected is True
    assert result.primary == "grokthar"


def test_detect_direct_address_hey_prefix():
    result = detect_direct_address("hey Deepwilla what do you think of this build?")
    assert result.detected is True
    assert result.primary == "deepwilla"


def test_detect_direct_address_at_prefix():
    result = detect_direct_address("@gemaux what is the story here?")
    assert result.detected is True
    assert result.primary == "gemaux"


def test_detect_direct_address_no_match():
    result = detect_direct_address("DM Moonie just died to a zombie horde.")
    assert result.detected is False
    assert result.primary is None


def test_detect_direct_address_case_insensitive():
    result = detect_direct_address("CLAUVEN, explain this lore.")
    assert result.detected is True
    assert result.primary == "clauven"


def test_resolve_companion_returns_none_when_not_detected():
    result = DirectAddressResult(
        detected=False,
        primary=None,
        companion_candidates=[],
    )
    assert resolve_companion(result) is None


def test_resolve_companion_global_gate_can_block():
    """With gate forced to fail, no companion is selected."""
    result = DirectAddressResult(
        detected=True,
        primary="clauven",
        companion_candidates=COMPANION_PROBABILITIES["clauven"],
    )
    with patch("party.orchestration.router.random.random", return_value=0.99):
        # 0.99 >= 0.50 global gate → blocked
        companion = resolve_companion(result)
    assert companion is None


def test_resolve_companion_selects_first_passing_candidate():
    """First candidate to pass their individual roll is selected."""
    result = DirectAddressResult(
        detected=True,
        primary="clauven",
        companion_candidates=[
            ("grokthar", 0.45),
            ("deepwilla", 0.35),
        ],
    )
    # Mock: global gate passes (0.3 < 0.5), grokthar passes (0.3 < 0.45)
    with patch(
        "party.orchestration.router.random.random",
        side_effect=[0.3, 0.3],
    ):
        companion = resolve_companion(result)
    assert companion == "grokthar"


def test_resolve_companion_skips_failing_candidates():
    """Skips candidates whose roll fails, returns first that passes."""
    result = DirectAddressResult(
        detected=True,
        primary="clauven",
        companion_candidates=[
            ("grokthar", 0.45),
            ("deepwilla", 0.35),
        ],
    )
    # Global gate passes (0.3), grokthar fails (0.9 > 0.45), deepwilla passes (0.2 < 0.35)
    with patch(
        "party.orchestration.router.random.random",
        side_effect=[0.3, 0.9, 0.2],
    ):
        companion = resolve_companion(result)
    assert companion == "deepwilla"


def test_resolve_companion_returns_none_if_all_fail():
    """If all candidates fail their rolls, return None."""
    result = DirectAddressResult(
        detected=True,
        primary="clauven",
        companion_candidates=[
            ("grokthar", 0.45),
            ("deepwilla", 0.35),
        ],
    )
    # Global gate passes, both candidates fail
    with patch(
        "party.orchestration.router.random.random",
        side_effect=[0.3, 0.9, 0.9],
    ):
        companion = resolve_companion(result)
    assert companion is None


def test_all_primaries_have_companion_table():
    """Every character has a companion probability entry."""
    for name in ["clauven", "geptima", "gemaux", "grokthar", "deepwilla"]:
        assert name in COMPANION_PROBABILITIES
        candidates = COMPANION_PROBABILITIES[name]
        assert len(candidates) == 4  # 4 companions (not self)
        for companion, prob in candidates:
            assert companion != name
            assert 0.0 <= prob <= 1.0
