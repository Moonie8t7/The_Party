import pytest
from party.providers.costs import estimate_cost, COST_PER_1K_INPUT, COST_PER_1K_OUTPUT


def test_estimate_cost_anthropic():
    cost = estimate_cost("anthropic", input_tokens=1000, output_tokens=100)
    assert cost > 0
    assert cost == pytest.approx(0.003 + 0.0015, abs=0.0001)


def test_estimate_cost_zero_tokens():
    cost = estimate_cost("anthropic", input_tokens=0, output_tokens=0)
    assert cost == 0.0


def test_estimate_cost_unknown_provider():
    # Unknown provider should not crash — uses fallback rate
    cost = estimate_cost("unknown_provider", input_tokens=1000, output_tokens=100)
    assert cost >= 0


def test_all_providers_have_rates():
    for provider in ["anthropic", "openai", "gemini", "grok", "deepseek"]:
        assert provider in COST_PER_1K_INPUT
        assert provider in COST_PER_1K_OUTPUT


def test_cost_scales_with_tokens():
    cost_small = estimate_cost("anthropic", 100, 10)
    cost_large = estimate_cost("anthropic", 10000, 1000)
    assert cost_large > cost_small
