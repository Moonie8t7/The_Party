# PROVIDER AUDIT (Sprint 11)
# SDK: anthropic
# Async client available: YES — anthropic.AsyncAnthropic
# Current implementation: sync client in run_in_executor
# Action: migrated to AsyncAnthropic in Task 11.16

import time
from anthropic import AsyncAnthropic
from party.models import Character, CharacterResponse
from party.config import settings
from party.providers.base import BaseProvider, ProviderError
from party.providers.costs import estimate_cost


class AnthropicProvider(BaseProvider):
    def __init__(self):
        super().__init__()
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def call(
        self,
        character: Character,
        system_prompt: str,
        messages: list[dict],
        timeout: float = 10.0,
        max_retries: int = 1,
    ) -> CharacterResponse:
        start = time.monotonic()
        full_prompt = self._build_system_prompt(character, system_prompt)

        async def _call():
            response = await self.client.messages.create(
                model=character.model_id,
                max_tokens=600,
                system=full_prompt,
                messages=messages,
            )
            text = response.content[0].text.strip()
            input_tokens = response.usage.input_tokens if response.usage else 0
            output_tokens = response.usage.output_tokens if response.usage else 0
            return text, input_tokens, output_tokens

        try:
            text, input_tokens, output_tokens = await self._with_timeout_and_retry(
                _call, timeout=timeout, max_retries=max_retries
            )
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError("anthropic", character.name, str(e))

        latency_ms = int((time.monotonic() - start) * 1000)
        return CharacterResponse(
            name=character.name,
            display_name=character.display_name,
            text=text,
            voice_id=character.voice_id,
            provider="anthropic",
            latency_ms=latency_ms,
            tokens_input=input_tokens,
            tokens_output=output_tokens,
            estimated_cost_usd=estimate_cost("anthropic", input_tokens, output_tokens),
        )
