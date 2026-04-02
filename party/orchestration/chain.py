import re
import time
from datetime import datetime
from typing import Optional
from party.models import Trigger, Scene, Character, CharacterResponse, CHARACTERS
from party.providers.base import ProviderError
from party.providers.anthropic import AnthropicProvider
from party.providers.openai import OpenAIProvider
from party.providers.gemini import GeminiProvider
from party.providers.grok import GrokProvider
from party.providers.deepseek import DeepSeekProvider
from party.orchestration.router import _route_with_method
from party.orchestration.repair import repair_response, SENTENCE_LIMITS
from party.context.session import read_session_context
from party.vision.loop import get_latest_description
from party.vision.log import get_recent_entries
from party.config import settings
from party.log import get_logger

log = get_logger(__name__)


def _build_context_preamble() -> str:
    """
    Build the context preamble injected into every character call.
    Reads session_context.txt fresh on every call.
    """
    parts = []

    now = datetime.now()
    parts.append(f"Current date and time: {now.strftime('%A %d %B %Y, %H:%M')}")

    session = read_session_context()
    if session:
        parts.append("Session context:")
        parts.append(session)

    # Vision context (from background loop)
    vision = get_latest_description()
    if vision:
        parts.append(f"Currently on screen: {vision}")

    # Recent vision log entries
    recent = get_recent_entries(settings.vision_log_max_context_entries)
    if recent:
        parts.append("Recent screen observations:")
        parts.extend(f"  {entry}" for entry in recent)

    return "\n".join(parts)


COMPANION_CLOSING = (
    "You are making a brief unrequested side comment - 1 sentence maximum. "
    "You were not directly asked. React naturally and instinctively to what "
    "{primary} just said. Do not repeat, summarise, or agree with them. "
    "Just your honest gut reaction. One sentence. Then stop."
)

NORMAL_CLOSING = (
    "Now respond as your character, aware of the current context "
    "and what your party members just said."
)


def _count_sentences(text: str) -> int:
    """Rough sentence count - splits on . ! ? followed by space or end."""
    sentences = re.split(r'[.!?]+(?:\s|$)', text.strip())
    return len([s for s in sentences if s.strip()])


PROVIDERS = {
    "anthropic": AnthropicProvider(),
    "openai": OpenAIProvider(),
    "gemini": GeminiProvider(),
    "grok": GrokProvider(),
    "deepseek": DeepSeekProvider(),
}


async def call_character(character: Character, session_snapshot: str, messages: list[dict]) -> CharacterResponse:
    """Call a single character's provider. Exposed for testing/mocking."""
    full_system_prompt = f"{character.prompt}\n\n[SESSION SNAPSHOT]\n{session_snapshot}"
    return await PROVIDERS[character.provider_type].call(
        character,
        full_system_prompt,
        messages,
    )


async def run_chain(
    trigger: Trigger,
    character_names: list[str],
    companion_characters: Optional[set[str]] = None,
) -> list[CharacterResponse]:
    """
    Calls each character in order, passing prior responses as context.
    Returns list of CharacterResponse objects (skips failed providers).
    companion_characters: names that receive the brief companion instruction.
    """
    results = []
    session_snapshot = _build_context_preamble()
    context_messages = [{"role": "user", "content": f"The situation: {trigger.text}"}]

    for i, name in enumerate(character_names):
        character = CHARACTERS[name]
        log.info(
            "provider.call_start",
            trigger_id=trigger.trigger_id,
            character=name,
            provider=character.provider_type,
        )

        try:
            response = await call_character(character, session_snapshot, context_messages)

            # Repair output
            repair = repair_response(response.text, trigger_id=trigger.trigger_id, character_name=name)
            if repair.length_violation:
                log.warning(
                    "repair.length_violation",
                    trigger_id=trigger.trigger_id,
                    character=name,
                    sentence_count=repair.sentence_count,
                    limit=SENTENCE_LIMITS.get(name, 5),
                )
            response = response.model_copy(
                update={
                    "text": repair.text,
                    "repaired": repair.repaired,
                    "length_chars": len(repair.text),
                    "length_sentences": repair.sentence_count,
                }
            )

            log.info(
                "provider.call_end",
                trigger_id=trigger.trigger_id,
                character=name,
                provider=character.provider_type,
                latency_ms=response.latency_ms,
            )
            log.debug(
                "chain.response_text",
                character=name,
                text=response.text,
                length_chars=response.length_chars,
                length_sentences=response.length_sentences,
            )
            results.append(response)

        except ProviderError as e:
            log.error(
                "provider.error",
                trigger_id=trigger.trigger_id,
                character=name,
                provider=e.provider,
                reason=e.reason,
            )
            log.warning("provider.skip", trigger_id=trigger.trigger_id, character=name)
            continue

        # Build context for next character - check if the *next* character is a companion
        next_name = character_names[i + 1] if i + 1 < len(character_names) else None
        is_companion = (
            companion_characters is not None
            and next_name is not None
            and next_name in companion_characters
        )
        summary_lines = [
            f"The situation: {trigger.text}",
            "",
        ]
        for r in results:
            summary_lines.append(f"{r.display_name} just said: {r.text}")
        if results:
            summary_lines.append("")

        if is_companion:
            primary_display = results[0].display_name if results else "the previous speaker"
            closing = COMPANION_CLOSING.format(primary=primary_display)
            log.debug(
                "chain.companion_closing_applied",
                companion=next_name,
                primary=primary_display,
            )
        else:
            closing = NORMAL_CLOSING

        summary_lines.append(closing)
        context_messages = [{"role": "user", "content": "\n".join(summary_lines)}]

    return results


async def orchestrate(trigger: Trigger) -> Scene:
    """Full orchestration pipeline: route → chain → return Scene."""
    start = time.monotonic()

    character_names, router_method, companion_set = await _route_with_method(trigger)
    results = await run_chain(trigger, character_names, companion_characters=companion_set)

    total_latency_ms = int((time.monotonic() - start) * 1000)

    error = None
    if not results:
        error = "all_providers_failed"
        log.error("scene.error", trigger_id=trigger.trigger_id, reason=error)
    else:
        spoken = [r.name for r in results]
        log.info(
            "scene.complete",
            trigger_id=trigger.trigger_id,
            characters_spoken=spoken,
            total_latency_ms=total_latency_ms,
        )

    return Scene(
        trigger=trigger,
        characters=character_names,
        responses=results,
        router_method=router_method,
        total_latency_ms=total_latency_ms,
        error=error,
    )
