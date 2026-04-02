import asyncio
import time
from abc import ABC, abstractmethod
from party.models import Character, CharacterResponse
from party.config import settings


class ProviderError(Exception):
    def __init__(self, provider: str, character: str, reason: str):
        self.provider = provider
        self.character = character
        self.reason = reason
        super().__init__(f"[{provider}:{character}] {reason}")


class BaseProvider(ABC):
    @abstractmethod
    async def call(
        self,
        character: Character,
        system_prompt: str,
        messages: list[dict],
    ) -> CharacterResponse:
        ...

    @staticmethod
    def _build_system_prompt(character: Character, system_prompt: str) -> str:
        """Append context_supplement to system prompt if present."""
        if character.context_supplement:
            return system_prompt + "\n\n" + character.context_supplement
        return system_prompt

    async def _with_timeout_and_retry(self, coro_fn, *args):
        """Retry wrapper with exponential backoff."""
        last_error = None
        for attempt in range(settings.provider_max_retries + 1):
            try:
                return await asyncio.wait_for(
                    coro_fn(*args),
                    timeout=settings.provider_timeout_seconds,
                )
            except asyncio.TimeoutError:
                last_error = "timeout"
            except Exception as e:
                last_error = str(e)
            if attempt < settings.provider_max_retries:
                await asyncio.sleep(0.5 * (2 ** attempt))
        raise ProviderError(
            self.__class__.__name__,
            "unknown",
            last_error or "unknown error",
        )
