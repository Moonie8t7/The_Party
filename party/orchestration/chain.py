import re
import time
import os
import asyncio
from datetime import datetime
from typing import Optional, AsyncGenerator, Any
from party.models import Trigger, Scene, Character, CharacterResponse, CHARACTERS, TriggerType
from party.providers.base import ProviderError
from party.providers.anthropic import AnthropicProvider
from party.providers.openai import OpenAIProvider
from party.providers.gemini import GeminiProvider
from party.providers.grok import GrokProvider
from party.providers.deepseek import DeepSeekProvider
from party.orchestration.router import _route_with_method
from party.orchestration.repair import repair_response, SENTENCE_LIMITS
from party.context.session import read_session_context
from party.context.obs_context import get_current_scene
from party.vision.loop import get_latest_description
from party.vision.log import get_recent_entries
from party.config import settings
from party.log import get_logger

log = get_logger(__name__)


async def _build_context_preamble() -> str:
    """
    Build the context preamble injected into every character call.
    Reads session_context.txt fresh on every call.
    """
    parts = []

    now = datetime.now()
    parts.append(f"Current date and time: {now.strftime('%A %d %B %Y, %H:%M')}")
    parts.append("You are currently in a live stream on Twitch. The streamer/user you are talking to is Moonie.")

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

    # OBS Scene Awareness
    scene = await get_current_scene()
    parts.append(f"Current OBS Scene: {scene}")

    # Stream Feats (Manual log)
    feats_path = os.path.join("session", "stream_feats.txt")
    if os.path.exists(feats_path):
        try:
            with open(feats_path, "r", encoding="utf-8") as f:
                feats = f.read().strip()
                if feats:
                    parts.append("\nStream Feats and Milestones (Historical context):")
                    parts.append(feats)
        except Exception:
            pass

    return "\n".join(parts)


COMPANION_CLOSING = (
    "Now add a brief (1 sentence) unrequested comment to the conversation. "
    "Acknowledge what was just said. Use natural social recall for any past events."
)

NORMAL_CLOSING = (
    "Now respond as your character, aware of the current context "
    "and what your party members just said. Use natural social recall for any "
    "past events—do not recite dates or exact log entries."
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
) -> AsyncGenerator[CharacterResponse, None]:
    """
    Calls characters. If TriggerType is SYSTEM, calls in parallel.
    Otherwise, calls sequentially to allow building on context.
    Yields CharacterResponse objects as they are ready.
    """
    session_snapshot = await _build_context_preamble()
    
    # Parallel execution for SYSTEM events to minimize actual latency
    if trigger.type == TriggerType.SYSTEM:
        log.info("chain.parallel_execution", trigger_id=trigger.trigger_id, count=len(character_names))
        
        context_messages = [{"role": "user", "content": f"System event: {trigger.text}"}]
        tasks = []
        for name in character_names:
            tasks.append(call_character(CHARACTERS[name], session_snapshot, context_messages))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, res in enumerate(results):
            name = character_names[i]
            if isinstance(res, Exception):
                log.error("provider.error", trigger_id=trigger.trigger_id, character=name, reason=str(res))
                continue
            
            # Repair and yield
            repair = repair_response(res.text, trigger_id=trigger.trigger_id, character_name=name)
            response = res.model_copy(update={
                "text": repair.text,
                "repaired": repair.repaired,
                "length_chars": len(repair.text),
                "length_sentences": repair.sentence_count,
            })
            yield response
        return

    # Sequential execution for conversation/idle
    results = []
    if trigger.type == TriggerType.IDLE:
        context_messages = [{"role": "user", "content": "Start an idle conversation based on the current scene and context."}]
    else:
        context_messages = [{"role": "user", "content": f"Moonie said: {trigger.text}"}]

    for i, name in enumerate(character_names):
        character = CHARACTERS[name]
        log.info("provider.call_start", trigger_id=trigger.trigger_id, character=name, provider=character.provider_type)

        try:
            response = await call_character(character, session_snapshot, context_messages)

            # Repair output
            repair = repair_response(response.text, trigger_id=trigger.trigger_id, character_name=name)
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
            results.append(response)
            yield response  # Yield immediately for incremental delivery!

        except ProviderError as e:
            log.error("provider.error", trigger_id=trigger.trigger_id, character=name, provider=e.provider, reason=e.reason)
            continue

        # Build context for next character
        next_name = character_names[i + 1] if i + 1 < len(character_names) else None
        is_companion = (
            companion_characters is not None
            and next_name is not None
            and next_name in companion_characters
        )
        summary_lines = [
            f"Moonie said: {trigger.text}" if trigger.type != TriggerType.IDLE else "Current Situation: Idle chatter",
            "",
        ]
        for r in results:
            summary_lines.append(f"{r.display_name} said: {r.text}")
        if results:
            summary_lines.append("")

        if is_companion:
            closing = COMPANION_CLOSING
        else:
            closing = NORMAL_CLOSING

        summary_lines.append(closing)
        context_messages = [{"role": "user", "content": "\n".join(summary_lines)}]


async def orchestrate(trigger: Trigger) -> AsyncGenerator[Any, None]:
    """
    Full orchestration pipeline. Yields:
    1. (metadata) dict with character_names, router_method
    2. (results) CharacterResponse objects as they finish
    3. (final) Scene object (for persistence)
    """
    start = time.monotonic()

    character_names, router_method, companion_set = await _route_with_method(trigger)
    
    # Yield initial metadata so overlay/speech can prepare if needed
    yield {
        "event": "orchestration_start",
        "characters": character_names,
        "method": router_method,
    }

    final_results = []
    async for response in run_chain(trigger, character_names, companion_characters=companion_set):
        final_results.append(response)
        yield response

    total_latency_ms = int((time.monotonic() - start) * 1000)
    
    error = "all_providers_failed" if not final_results else None
    scene = Scene(
        trigger=trigger,
        characters=character_names,
        responses=final_results,
        router_method=router_method,
        total_latency_ms=total_latency_ms,
        error=error,
    )
    
    if not error:
        log.info("scene.complete", trigger_id=trigger.trigger_id, total_latency_ms=total_latency_ms)
    
    yield scene
