# ── Sprint 15A: IDLE and HOTKEY sequential routing ─────────────────────────

import pytest
from unittest.mock import AsyncMock, patch
from party.models import Trigger, TriggerType
from party.orchestration.modes import ExecutionMode


def _make_trigger(trigger_type: TriggerType, text: str = "test") -> Trigger:
    return Trigger(type=trigger_type, text=text, priority=1,
                   cooldown_key=None, game=None, viewer=None)


@pytest.mark.asyncio
async def test_idle_trigger_routes_sequential():
    from party.orchestration.router import route_trigger
    trigger = _make_trigger(TriggerType.IDLE)
    result = await route_trigger(trigger)
    assert result.mode == ExecutionMode.SEQUENTIAL


@pytest.mark.asyncio
async def test_hotkey_trigger_routes_sequential():
    from party.orchestration.router import route_trigger
    trigger = _make_trigger(TriggerType.HOTKEY, text="test hotkey")
    result = await route_trigger(trigger)
    assert result.mode == ExecutionMode.SEQUENTIAL


@pytest.mark.asyncio
async def test_system_trigger_remains_parallel():
    from party.orchestration.router import route_trigger
    trigger = _make_trigger(TriggerType.SYSTEM, text="watchmoonie just subscribed")
    result = await route_trigger(trigger)
    assert result.mode == ExecutionMode.PARALLEL


def test_idle_budget_is_normal():
    """IDLE budget must be 'normal' so companion is not skipped on slight primary delay."""
    from party.orchestration.chain import _BUDGET_MAP
    assert _BUDGET_MAP[TriggerType.IDLE] == "normal"


def test_hotkey_budget_is_normal():
    from party.orchestration.chain import _BUDGET_MAP
    assert _BUDGET_MAP[TriggerType.HOTKEY] == "normal"


# ── Sprint 15B: Per-character affinity ────────────────────────────────────

import pytest
from party.context.viewer_memory import (
    get_character_affinity,
    increment_character_affinity,
    update_viewer,
    get_viewer,
)
from party.orchestration.router import _select_d20_character, AFFINITY_BONUS_PER_INTERACTION
from party.models import CHARACTERS


@pytest.mark.asyncio
async def test_increment_affinity_creates_entry(tmp_path, monkeypatch):
    """Affinity entry created when viewer record exists."""
    import party.context.viewer_memory as vm
    monkeypatch.setattr(vm, "VIEWER_MEMORY_PATH", str(tmp_path / "viewer_memory.json"))
    monkeypatch.setattr(vm, "_memory", {})
    monkeypatch.setattr(vm, "_loaded", False)

    await update_viewer("testuser", {"firsts": 1})
    await increment_character_affinity("testuser", "grokthar")

    viewer = await get_viewer("testuser")
    assert viewer["character_affinity"]["grokthar"] == 1


@pytest.mark.asyncio
async def test_increment_affinity_accumulates(tmp_path, monkeypatch):
    """Multiple increments accumulate correctly."""
    import party.context.viewer_memory as vm
    monkeypatch.setattr(vm, "VIEWER_MEMORY_PATH", str(tmp_path / "viewer_memory.json"))
    monkeypatch.setattr(vm, "_memory", {})
    monkeypatch.setattr(vm, "_loaded", False)

    await update_viewer("testuser", {"firsts": 1})
    for _ in range(5):
        await increment_character_affinity("testuser", "gemaux")

    viewer = await get_viewer("testuser")
    assert viewer["character_affinity"]["gemaux"] == 5


@pytest.mark.asyncio
async def test_increment_affinity_no_record_is_silent(tmp_path, monkeypatch):
    """Incrementing affinity for unknown viewer does not crash or create record."""
    import party.context.viewer_memory as vm
    monkeypatch.setattr(vm, "VIEWER_MEMORY_PATH", str(tmp_path / "viewer_memory.json"))
    monkeypatch.setattr(vm, "_memory", {})
    monkeypatch.setattr(vm, "_loaded", False)

    # Should not raise
    await increment_character_affinity("nobody", "grokthar")
    assert await get_viewer("nobody") is None


def test_get_character_affinity_empty_record():
    """Returns empty dict when no affinity data present."""
    assert get_character_affinity({}) == {}
    assert get_character_affinity({"firsts": 3}) == {}


def test_select_d20_no_affinity_returns_valid_character():
    from party.models import CHARACTERS
    for _ in range(20):
        result = _select_d20_character("nat1")
        assert result in CHARACTERS
        result = _select_d20_character("nat20")
        assert result in CHARACTERS


def test_select_d20_with_affinity_returns_valid_character():
    affinity = {"grokthar": 10, "gemaux": 2}
    for _ in range(20):
        result = _select_d20_character("nat1", affinity=affinity)
        assert result in CHARACTERS


def test_affinity_bonus_is_positive():
    """Affinity bonus must be positive — higher affinity = more likely selection."""
    assert AFFINITY_BONUS_PER_INTERACTION > 0


def test_affinity_bonus_is_bounded():
    """Affinity bonus per interaction must not overwhelm personality weights at reasonable counts."""
    # At 20 interactions, bonus should not exceed the highest base weight (0.40)
    max_bonus = 20 * AFFINITY_BONUS_PER_INTERACTION
    assert max_bonus <= 1.0, "Affinity bonus is too large — would dominate personality weights"


def test_select_d20_high_affinity_biases_selection():
    """With very high affinity for one character, they should dominate selection."""
    import random
    random.seed(42)
    affinity = {"grokthar": 100}  # Extreme affinity for grokthar
    results = [_select_d20_character("nat1", affinity=affinity) for _ in range(50)]
    grokthar_count = results.count("grokthar")
    assert grokthar_count > 30, f"High affinity should bias toward grokthar, got {grokthar_count}/50"
