"""
Provider cost estimation.
Rates are approximate mid-2025 values per 1K tokens.
"""

COST_PER_1K_INPUT = {
    "anthropic":  0.003,    # claude-sonnet-4-6 input
    "openai":     0.0025,   # gpt-4o input
    "gemini":     0.00015,  # gemini-2.5-flash input
    "grok":       0.003,    # grok-3 input
    "deepseek":   0.00027,  # deepseek-chat input
}

COST_PER_1K_OUTPUT = {
    "anthropic":  0.015,
    "openai":     0.010,
    "gemini":     0.0006,
    "grok":       0.015,
    "deepseek":   0.0011,
}


def estimate_cost(provider: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD for a provider call."""
    input_cost = (input_tokens / 1000) * COST_PER_1K_INPUT.get(provider, 0.003)
    output_cost = (output_tokens / 1000) * COST_PER_1K_OUTPUT.get(provider, 0.015)
    return round(input_cost + output_cost, 6)
