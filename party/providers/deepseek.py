# PROVIDER AUDIT (Sprint 11)
# SDK: openai (OpenAI-compatible endpoint via base_url)
# Async client available: YES — openai.AsyncOpenAI with base_url override
# Current implementation: sync OpenAI client in run_in_executor
# Action: migrated to AsyncOpenAI with base_url in Task 11.16

import time
from openai import AsyncOpenAI
from party.models import Character, CharacterResponse
from party.config import settings
from party.providers.base import BaseProvider, ProviderError
from party.providers.costs import estimate_cost


class DeepSeekProvider(BaseProvider):
    def __init__(self):
        super().__init__()
        self.client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url="https://api.deepseek.com",
        )

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
            full_messages = [{"role": "system", "content": full_prompt}] + messages
            response = await self.client.chat.completions.create(
                model=character.model_id,
                max_tokens=300,
                messages=full_messages,
            )
            text = response.choices[0].message.content.strip()
            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0
            return text, input_tokens, output_tokens

        try:
            text, input_tokens, output_tokens = await self._with_timeout_and_retry(
                _call, timeout=timeout, max_retries=max_retries
            )
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError("deepseek", character.name, str(e))

        latency_ms = int((time.monotonic() - start) * 1000)
        return CharacterResponse(
            name=character.name,
            display_name=character.display_name,
            text=text,
            voice_id=character.voice_id,
            provider="deepseek",
            latency_ms=latency_ms,
            tokens_input=input_tokens,
            tokens_output=output_tokens,
            estimated_cost_usd=estimate_cost("deepseek", input_tokens, output_tokens),
        )
