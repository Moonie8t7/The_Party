# PROVIDER AUDIT (Sprint 11)
# SDK: google-genai
# Async client available: YES — client.aio.models.generate_content()
# Current implementation: sync client in run_in_executor
# Action: migrated to client.aio async interface in Task 11.16

import time
from google import genai
from google.genai import types
from party.models import Character, CharacterResponse
from party.config import settings
from party.providers.base import BaseProvider, ProviderError
from party.providers.costs import estimate_cost


class GeminiProvider(BaseProvider):
    def __init__(self):
        super().__init__()
        self.client = genai.Client(api_key=settings.gemini_api_key)

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
            contents = []
            for msg in messages:
                role = "user" if msg["role"] == "user" else "model"
                contents.append({"role": role, "parts": [{"text": msg["content"]}]})

            response = await self.client.aio.models.generate_content(
                model=character.model_id,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=full_prompt,
                    max_output_tokens=600,
                ),
            )
            text = response.text.strip()
            meta = response.usage_metadata
            input_tokens = meta.prompt_token_count if meta else 0
            output_tokens = meta.candidates_token_count if meta else 0

            try:
                finish_reason = response.candidates[0].finish_reason
                if str(finish_reason) not in ("FinishReason.STOP", "STOP", "1"):
                    from party.log import get_logger
                    get_logger(__name__).warning(
                        "gemini.unexpected_finish",
                        finish_reason=str(finish_reason),
                        text_preview=text[:60],
                    )
            except Exception:
                pass

            return text, input_tokens, output_tokens

        try:
            text, input_tokens, output_tokens = await self._with_timeout_and_retry(
                _call, timeout=timeout, max_retries=max_retries
            )
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError("gemini", character.name, str(e))

        latency_ms = int((time.monotonic() - start) * 1000)
        return CharacterResponse(
            name=character.name,
            display_name=character.display_name,
            text=text,
            voice_id=character.voice_id,
            provider="gemini",
            latency_ms=latency_ms,
            tokens_input=input_tokens,
            tokens_output=output_tokens,
            estimated_cost_usd=estimate_cost("gemini", input_tokens, output_tokens),
        )
