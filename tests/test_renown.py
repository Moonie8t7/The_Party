"""
Tests for the Renown scoring and tier system (Sprint 14).
"""
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def reset_memory():
    import party.context.viewer_memory as vm
    vm._memory = {}
    vm._loaded = False
    yield
    vm._memory = {}
    vm._loaded = False


# ── calculate_renown ──────────────────────────────────────────────────────────

def test_renown_zero_for_empty_record():
    from party.context.viewer_memory import calculate_renown
    assert calculate_renown({}) == 0


def test_renown_zero_for_level_1_no_activity():
    from party.context.viewer_memory import calculate_renown
    assert calculate_renown({"level": 1}) == 0


def test_renown_chatter_scoring():
    from party.context.viewer_memory import calculate_renown
    data = {"firsts": 3, "seconds": 2, "thirds": 1}
    # 3×10 + 2×6 + 1×3 = 30 + 12 + 3 = 45
    assert calculate_renown(data) == 45


def test_renown_subscriber_base_plus_months():
    from party.context.viewer_memory import calculate_renown
    data = {"subscriber": True, "sub_months": 6}
    # 20 base + 6×3 = 38
    assert calculate_renown(data) == 38


def test_renown_gift_bomber_capped_at_50():
    from party.context.viewer_memory import calculate_renown
    # 100 gifts × 2 = 200, but capped at 50
    assert calculate_renown({"gift_bomber": True, "last_bomb_count": 100}) == 50
    # 10 gifts × 2 = 20, under cap
    assert calculate_renown({"gift_bomber": True, "last_bomb_count": 10}) == 20


def test_renown_raider_capped_at_30():
    from party.context.viewer_memory import calculate_renown
    # 500 viewers // 5 = 100, capped at 30
    assert calculate_renown({"raider": True, "last_raid_viewers": 500}) == 30
    # 40 viewers // 5 = 8
    assert calculate_renown({"raider": True, "last_raid_viewers": 40}) == 8


def test_renown_nat20s_weighted_higher_than_nat1s():
    from party.context.viewer_memory import calculate_renown
    data_nat20 = {"d20_nat20s": 1}
    data_nat1 = {"d20_nat1s": 1}
    assert calculate_renown(data_nat20) == 5
    assert calculate_renown(data_nat1) == 2
    assert calculate_renown(data_nat20) > calculate_renown(data_nat1)


def test_renown_level_contributes():
    from party.context.viewer_memory import calculate_renown
    # Level 11: (11-1) × 2 = 20
    assert calculate_renown({"level": 11}) == 20
    # Level 1: (1-1) × 2 = 0
    assert calculate_renown({"level": 1}) == 0


def test_renown_combined_score():
    from party.context.viewer_memory import calculate_renown
    data = {
        "firsts": 2,       # 20
        "subscriber": True,
        "sub_months": 3,   # 20 + 9 = 29
        "level": 5,        # 8
        "d20_nat20s": 1,   # 5
    }
    # 20 + 29 + 8 + 5 = 62
    assert calculate_renown(data) == 62


def test_renown_is_always_non_negative():
    from party.context.viewer_memory import calculate_renown
    assert calculate_renown({}) >= 0
    assert calculate_renown({"level": 0}) >= 0


# ── get_renown_tier ───────────────────────────────────────────────────────────

def test_tier_newcomer():
    from party.context.viewer_memory import get_renown_tier
    assert "newcomer" in get_renown_tier(0)
    assert "newcomer" in get_renown_tier(9)


def test_tier_familiar_face():
    from party.context.viewer_memory import get_renown_tier
    assert "familiar face" in get_renown_tier(10)
    assert "familiar face" in get_renown_tier(24)


def test_tier_known_adventurer():
    from party.context.viewer_memory import get_renown_tier
    assert "known adventurer" in get_renown_tier(25)
    assert "known adventurer" in get_renown_tier(49)


def test_tier_seasoned_regular():
    from party.context.viewer_memory import get_renown_tier
    assert "seasoned regular" in get_renown_tier(50)
    assert "seasoned regular" in get_renown_tier(99)


def test_tier_legend():
    from party.context.viewer_memory import get_renown_tier
    assert "legend" in get_renown_tier(100)
    assert "legend" in get_renown_tier(9999)


# ── update_viewer stores renown ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_viewer_stores_renown(tmp_path):
    from party.context import viewer_memory as vm
    path = str(tmp_path / "viewer_memory.json")
    with patch.object(vm, "VIEWER_MEMORY_PATH", path):
        await vm.update_viewer("TestFan", {"firsts": 2, "level": 8})
        result = await vm.get_viewer("TestFan")
    assert "renown" in result
    assert result["renown"] > 0


@pytest.mark.asyncio
async def test_renown_increases_with_more_data(tmp_path):
    from party.context import viewer_memory as vm
    path = str(tmp_path / "viewer_memory.json")
    with patch.object(vm, "VIEWER_MEMORY_PATH", path):
        await vm.update_viewer("TestFan", {"firsts": 1})
        r1 = (await vm.get_viewer("TestFan"))["renown"]
        await vm.update_viewer("TestFan", {"subscriber": True, "sub_months": 6})
        r2 = (await vm.get_viewer("TestFan"))["renown"]
    assert r2 > r1


# ── format_viewer_context with Renown ────────────────────────────────────────

def test_format_viewer_context_uses_renown_tier():
    from party.context.viewer_memory import format_viewer_context
    data = {"firsts": 5, "level": 8, "renown": 68}
    result = format_viewer_context(data, "RegularFan")
    assert "seasoned regular" in result


def test_format_viewer_context_mentions_nat20s():
    from party.context.viewer_memory import format_viewer_context
    data = {"d20_nat20s": 3, "renown": 15}
    result = format_viewer_context(data, "LuckyRoller")
    assert "LuckyRoller" in result
    assert "20" in result


def test_format_viewer_context_mentions_nat1s():
    from party.context.viewer_memory import format_viewer_context
    data = {"d20_nat1s": 2, "renown": 4}
    result = format_viewer_context(data, "UnluckyRoller")
    assert "UnluckyRoller" in result
    assert len(result) > 0


def test_format_viewer_context_capped_at_three_sentences():
    from party.context.viewer_memory import format_viewer_context
    data = {
        "firsts": 8, "seconds": 3, "thirds": 2,
        "subscriber": True, "sub_months": 18,
        "raider": True, "last_raid_viewers": 50,
        "d20_nat20s": 5, "d20_nat1s": 3,
        "level": 15, "renown": 250,
    }
    result = format_viewer_context(data, "LegendFan")
    sentences = [s for s in result.split(". ") if s]
    assert len(sentences) <= 3
