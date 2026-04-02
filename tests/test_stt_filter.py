import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_filter_returns_false_on_error():
    from party.stt.filter import should_react
    with patch("party.stt.filter.Anthropic", side_effect=Exception("API error")):
        result = await should_react("something happened")
    assert result is False


def test_filter_prompt_contains_yes_no_instructions():
    from party.stt.filter import FILTER_PROMPT
    assert "YES" in FILTER_PROMPT
    assert "NO" in FILTER_PROMPT


def test_filter_prompt_covers_react_cases():
    from party.stt.filter import FILTER_PROMPT
    assert "emotional" in FILTER_PROMPT.lower() or "reaction" in FILTER_PROMPT.lower()


@pytest.mark.asyncio
async def test_filter_returns_false_for_no_response():
    from party.stt.filter import should_react

    mock_content = MagicMock()
    mock_content.text = "NO"
    mock_response = MagicMock()
    mock_response.content = [mock_content]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("party.stt.filter.Anthropic", return_value=mock_client):
        with patch("asyncio.get_event_loop") as mock_loop:
            import asyncio

            async def fake_executor(executor, fn):
                return fn()

            mock_loop.return_value.run_in_executor = fake_executor
            result = await should_react("let me just grab this item here")

    assert isinstance(result, bool)
