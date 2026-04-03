import re
import time
import asyncio
from typing import Optional, AsyncGenerator, Any

from party.models import Trigger, Scene, Character, CharacterResponse, CHARACTERS, TriggerType
from party.providers.base import ProviderError
from party.providers.anthropic import AnthropicProvider
from party.providers.openai import OpenAIProvider
from party.providers.gemini import GeminiProvider
from party.providers.grok import GrokProvider
from party.providers.deepseek import DeepSeekProvider
from party.orchestration.router import route_trigger, RouterResult
from party.orchestration.modes import ExecutionMode
from party.orchestration.repair import repair_response, SENTENCE_LIMITS
from party.orchestration.context import (
    WarmContext,
    build_warm_context,
    format_warm_primary,
    format_warm_companion,
    build_primary_message,
    build_companion_sequential_message,
    build_companion_parallel_message,
    COMPANION_SEQUENTIAL_CLOSING,
    COMPANION_PARALLEL_CLOSING,
    NORMAL_CLOSING,
)
from party.config import settings
from party.log import get_logger

log = get_logger(__name__)

# Re-export for backward compatibility with existing tests
COMPANION_CLOSING = COMPANION_SEQUENTIAL_CLOSING

# ── Speaker limits (Task 11.4) ────────────────────────────────────────────────

MAX_SPEAKERS_DEFAULT = 2   # 1 primary + 1 companion
MAX_SPEAKERS_SYSTEM = 5    # full party for SYSTEM events

# ── Provider instances ────────────────────────────────────────────────────────

PROVIDERS = {
    "anthropic": AnthropicProvider(),
    "openai":    OpenAIProvider(),
    "gemini":    GeminiProvider(),
    "grok":      GrokProvider(),
    "deepseek":  DeepSeekProvider(),
}


# ── Budget and timeout helpers (Tasks 11.12, 11.13, 11.17, 11.18) ─────────────

_BUDGET_MAP: dict[TriggerType, str] = {
    TriggerType.HOTKEY:       "fast",
    TriggerType.IDLE:         "fast",
    TriggerType.SYSTEM:       "normal",
    TriggerType.CHAT_TRIGGER: "normal",
    TriggerType.STT:          "normal",
    TriggerType.TIMED:        "normal",
}


def _get_budget(trigger_type: TriggerType) -> int:
    """Return latency budget in milliseconds for this trigger class."""
    cls = _BUDGET_MAP.get(trigger_type, "normal")
    if cls == "fast":
        return settings.latency_budget_fast_ms
    if cls == "extended":
        return settings.latency_budget_extended_ms
    return settings.latency_budget_normal_ms


def _get_provider_timeout(trigger_type: TriggerType) -> float:
    """Return per-provider timeout in seconds for this trigger class."""
    cls = _BUDGET_MAP.get(trigger_type, "normal")
    if cls == "fast":
        return settings.provider_timeout_fast_seconds
    if cls == "extended":
        return settings.provider_timeout_extended_seconds
    return settings.provider_timeout_normal_seconds


def _get_provider_retries(trigger_type: TriggerType) -> int:
    """Return max retries for this trigger class."""
    cls = _BUDGET_MAP.get(trigger_type, "normal")
    if cls == "fast":
        return settings.provider_retries_fast
    return settings.provider_retries_normal


# ── Speaker limit enforcement (Task 11.4) ─────────────────────────────────────

def _enforce_speaker_limits(trigger: Trigger, result: RouterResult) -> None:
    limit = MAX_SPEAKERS_SYSTEM if trigger.type == TriggerType.SYSTEM else MAX_SPEAKERS_DEFAULT
    total = len(result.primary) + len(result.companions)
    if total > limit:
        result.companions = result.companions[:limit - len(result.primary)]
        log.warning(
            "speaker_limit_enforced",
            trigger_id=trigger.trigger_id,
            original=total,
            clamped=limit,
        )


# ── Character call interface ──────────────────────────────────────────────────

async def call_character(
    character: Character,
    session_snapshot: str,
    messages: list[dict],
    *,
    timeout: float = 10.0,
    max_retries: int = 1,
) -> CharacterResponse:
    """
    Call a single character's provider. Exposed for testing/mocking.
    session_snapshot is injected into the system prompt as [SESSION SNAPSHOT].
    """
    full_system_prompt = f"{character.prompt}\n\n[SESSION SNAPSHOT]\n{session_snapshot}"
    return await PROVIDERS[character.provider_type].call(
        character,
        full_system_prompt,
        messages,
        timeout=timeout,
        max_retries=max_retries,
    )


# ── Response repair helper ────────────────────────────────────────────────────

def _repair(response: CharacterResponse, trigger: Trigger, name: str) -> CharacterResponse:
    repair = repair_response(response.text, trigger_id=trigger.trigger_id, character_name=name)
    if repair.length_violation:
        log.warning(
            "repair.length_violation",
            trigger_id=trigger.trigger_id,
            character=name,
            sentence_count=repair.sentence_count,
            limit=SENTENCE_LIMITS.get(name, 5),
        )
    log.info(
        "provider.call_end",
        trigger_id=trigger.trigger_id,
        character=name,
        provider=response.provider,
        latency_ms=response.latency_ms,
    )
    return response.model_copy(update={
        "text": repair.text,
        "repaired": repair.repaired,
        "length_chars": len(repair.text),
        "length_sentences": repair.sentence_count,
    })


# ── Parallel execution (Task 11.7) ────────────────────────────────────────────

async def _run_parallel(
    trigger: Trigger,
    result: RouterResult,
    warm: WarmContext,
    budget_ms: int,
    p_timeout: float,
    p_retries: int,
) -> AsyncGenerator[CharacterResponse, None]:
    """
    Fire primary and all companions simultaneously via asyncio tasks.
    Primary result is yielded first; companions yielded if within budget.
    Task 11.3 — parallel companion context: no primary response included.
    """
    primary_name = result.primary[0]
    companion_names = result.companions

    snap_primary = format_warm_primary(warm)
    snap_companion = format_warm_companion(warm)
    primary_msgs = build_primary_message(trigger, warm)

    # Create all tasks immediately so they all start at once
    primary_task = asyncio.create_task(
        call_character(CHARACTERS[primary_name], snap_primary, primary_msgs,
                       timeout=p_timeout, max_retries=p_retries)
    )
    companion_tasks: list[tuple[str, asyncio.Task]] = []
    for name in companion_names:
        msgs = build_companion_parallel_message(trigger, warm)
        companion_tasks.append((name, asyncio.create_task(
            call_character(CHARACTERS[name], snap_companion, msgs,
                           timeout=p_timeout, max_retries=p_retries)
        )))

    t_start = time.perf_counter()

    # Await primary first
    try:
        primary_response = await primary_task
        primary_response = _repair(primary_response, trigger, primary_name)
    except Exception as e:
        log.error("provider.error", trigger_id=trigger.trigger_id,
                  character=primary_name, reason=str(e))
        for _, task in companion_tasks:
            task.cancel()
        return

    # Capture LLM-only elapsed time BEFORE yielding — yield suspends until TTS finishes,
    # which would inflate elapsed_ms and incorrectly cancel companion tasks.
    primary_llm_elapsed_ms = (time.perf_counter() - t_start) * 1000

    yield primary_response

    # Await companions (Task 11.14).
    # Companion tasks have been running concurrently during primary LLM + TTS playback.
    # If the task is already done (completed during TTS), yield it immediately.
    # Only apply budget check if the task is still pending — using LLM-phase elapsed time.
    for companion_name, task in companion_tasks:
        if task.done():
            try:
                companion_response = task.result()
                companion_response = _repair(companion_response, trigger, companion_name)
                yield companion_response
            except Exception as e:
                log.error("provider.error", trigger_id=trigger.trigger_id,
                          character=companion_name, reason=str(e))
            continue
        remaining_ms = budget_ms - primary_llm_elapsed_ms
        if remaining_ms <= 0:
            log.warning(
                "budget_exceeded_skipping_companion",
                trigger_id=trigger.trigger_id,
                trigger_type=str(trigger.type),
                elapsed_ms=round(primary_llm_elapsed_ms),
                budget_ms=budget_ms,
            )
            task.cancel()
            continue
        try:
            companion_response = await asyncio.wait_for(task, timeout=remaining_ms / 1000)
            companion_response = _repair(companion_response, trigger, companion_name)
            yield companion_response
        except asyncio.TimeoutError:
            log.warning("companion_timeout", trigger_id=trigger.trigger_id,
                        character=companion_name, budget_ms=budget_ms)
        except Exception as e:
            log.error("provider.error", trigger_id=trigger.trigger_id,
                      character=companion_name, reason=str(e))


# ── Sequential execution ──────────────────────────────────────────────────────

async def _run_sequential(
    trigger: Trigger,
    result: RouterResult,
    warm: WarmContext,
    budget_ms: int,
    p_timeout: float,
    p_retries: int,
) -> AsyncGenerator[CharacterResponse, None]:
    """
    Call primary, then companion (with primary's response in context) if within budget.
    Task 11.3 — sequential companion context: primary response included.
    Task 11.11 — fixed window: companion gets only primary's response, not full history.
    """
    primary_name = result.primary[0]
    companion_names = result.companions

    snap_primary = format_warm_primary(warm)
    snap_companion = format_warm_companion(warm)
    primary_msgs = build_primary_message(trigger, warm)

    t_start = time.perf_counter()

    try:
        log.info("provider.call_start", trigger_id=trigger.trigger_id,
                 character=primary_name, provider=CHARACTERS[primary_name].provider_type)
        primary_response = await call_character(
            CHARACTERS[primary_name], snap_primary, primary_msgs,
            timeout=p_timeout, max_retries=p_retries,
        )
        primary_response = _repair(primary_response, trigger, primary_name)
        yield primary_response
    except Exception as e:
        log.error("provider.error", trigger_id=trigger.trigger_id,
                  character=primary_name, reason=str(e))
        return

    primary_elapsed_ms = (time.perf_counter() - t_start) * 1000

    if not companion_names:
        return

    companion_name = companion_names[0]

    # Budget enforcement (Task 11.14)
    if primary_elapsed_ms > budget_ms:
        log.warning(
            "budget_exceeded_skipping_companion",
            trigger_id=trigger.trigger_id,
            trigger_type=str(trigger.type),
            elapsed_ms=round(primary_elapsed_ms),
            budget_ms=budget_ms,
        )
        return

    # Companion receives primary's response — no full history (Task 11.11)
    companion_msgs = build_companion_sequential_message(
        trigger, warm,
        primary_response.display_name,
        primary_response.text,
    )

    try:
        log.info("provider.call_start", trigger_id=trigger.trigger_id,
                 character=companion_name, provider=CHARACTERS[companion_name].provider_type)
        companion_response = await call_character(
            CHARACTERS[companion_name], snap_companion, companion_msgs,
            timeout=p_timeout, max_retries=p_retries,
        )
        companion_response = _repair(companion_response, trigger, companion_name)
        yield companion_response
    except Exception as e:
        log.error("provider.error", trigger_id=trigger.trigger_id,
                  character=companion_name, reason=str(e))


# ── Public chain interface ────────────────────────────────────────────────────

async def run_chain(
    trigger: Trigger,
    router_result: RouterResult,
) -> AsyncGenerator[CharacterResponse, None]:
    """
    Execute the character chain for a routed trigger.
    Dispatches to _run_parallel or _run_sequential based on RouterResult.mode.
    Yields CharacterResponse objects as they are ready.
    """
    from party.context.obs_context import get_current_scene
    try:
        scene = await get_current_scene()
    except Exception:
        scene = "Unknown"

    warm = await build_warm_context(scene=scene)
    budget_ms = _get_budget(trigger.type)
    p_timeout = _get_provider_timeout(trigger.type)
    p_retries = _get_provider_retries(trigger.type)

    if router_result.mode == ExecutionMode.PARALLEL:
        async for response in _run_parallel(trigger, router_result, warm, budget_ms, p_timeout, p_retries):
            yield response
    else:
        async for response in _run_sequential(trigger, router_result, warm, budget_ms, p_timeout, p_retries):
            yield response


# ── Orchestrate (full pipeline) ───────────────────────────────────────────────

async def orchestrate(trigger: Trigger) -> AsyncGenerator[Any, None]:
    """
    Full orchestration pipeline. Yields:
    1. dict — metadata: {event, characters, method}
    2. CharacterResponse objects as they complete
    3. Scene — final scene object (for persistence/transcript)
    """
    start = time.monotonic()

    result: RouterResult = await route_trigger(trigger)
    if result.method == "ignored_redundant":
        return
    _enforce_speaker_limits(trigger, result)

    all_characters = result.primary + result.companions
    yield {
        "event": "orchestration_start",
        "characters": all_characters,
        "method": result.method,
    }

    final_results: list[CharacterResponse] = []
    async for response in run_chain(trigger, result):
        final_results.append(response)
        yield response

    total_latency_ms = int((time.monotonic() - start) * 1000)
    error = "all_providers_failed" if not final_results else None

    scene = Scene(
        trigger=trigger,
        characters=all_characters,
        responses=final_results,
        router_method=result.method,
        total_latency_ms=total_latency_ms,
        error=error,
    )

    if error:
        log.error("scene.error", trigger_id=trigger.trigger_id, reason=error)
    else:
        log.info("scene.complete", trigger_id=trigger.trigger_id,
                 total_latency_ms=total_latency_ms)

    yield scene
