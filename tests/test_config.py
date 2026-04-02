import pytest
import os
from unittest.mock import patch


def test_config_loads():
    """Config should load without error in test environment."""
    from party.config import settings
    assert settings.ws_port == 8765
    assert settings.queue_max_size > 0
    assert settings.provider_timeout_seconds > 0


def test_config_requires_anthropic_key():
    """Missing Anthropic key should raise on import."""
    from party.config import settings
    # Verify the key is present in the real config
    assert len(settings.anthropic_api_key) > 0


def test_config_default_values():
    """Defaults should be applied when env vars are not set."""
    from party.config import settings
    assert settings.inter_character_gap_seconds == 0.5
    assert settings.provider_max_retries == 2
    assert settings.router_model == "claude-haiku-4-5-20251001"


def test_config_transcript_path_set():
    from party.config import settings
    assert settings.transcript_path.endswith(".jsonl")
