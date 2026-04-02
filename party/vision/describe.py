"""
GPT-4o Vision description of a burst of screenshots.
Accepts 1-N base64-encoded frames and returns a concise description.
"""

import asyncio
from typing import Optional
from openai import OpenAI
from party.config import settings
from party.log import get_logger

log = get_logger(__name__)

SEQUENCE_PROMPT = (
    "You are watching a live game stream. "
    "You have been given a short sequence of screenshots taken a few seconds apart. "
    "Describe what is happening on screen as a brief narrative (2-3 sentences). "
    "Mention the game state, what the player is doing, any notable changes between frames, "
    "and any relevant UI elements (health, ammo, objectives). "
    "Write in present tense. Be concise and specific. "
    "CRITICAL: Ignore the character portraits and any speech panels at the very bottom of the screen. These are stream overlays, NOT the game itself. Focus ONLY on the actual gameplay footage behind them."
)

SINGLE_PROMPT = (
    "You are watching a live game stream. "
    "Describe what is currently happening on screen in 2-3 sentences. "
    "Be specific: mention the game state, what the player is doing, "
    "any notable UI elements (health, ammo, objectives), and the general "
    "situation. Do not speculate about what might happen next. "
    "Write in present tense. Be concise. "
    "CRITICAL: Ignore the character portraits and any speech panels at the very bottom of the screen. These are stream overlays, NOT the game itself. Focus ONLY on the actual gameplay footage behind them."
)


async def describe_burst(frames: list[str]) -> Optional[str]:
    """
    Send a burst of base64 screenshots to GPT-4o Vision.
    Returns a 2-3 sentence description, or None on failure.
    """
    if not frames:
        return None

    try:
        loop = asyncio.get_event_loop()
        description = await asyncio.wait_for(
            loop.run_in_executor(None, _describe_sync, frames),
            timeout=20.0,
        )
        return description

    except asyncio.TimeoutError:
        log.warning("vision.describe_timeout")
        return None
    except Exception as e:
        log.warning("vision.describe_failed", reason=str(e))
        return None


def _describe_sync(frames: list[str]) -> Optional[str]:
    """Synchronous Vision API call. Run in thread pool."""
    client = OpenAI(api_key=settings.openai_api_key)

    prompt = SEQUENCE_PROMPT if len(frames) > 1 else SINGLE_PROMPT

    content: list[dict] = [{"type": "text", "text": prompt}]
    for frame in frames:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{frame}",
                    "detail": "low",
                },
            }
        )

    response = client.chat.completions.create(
        model=settings.vision_model,
        max_tokens=settings.vision_max_tokens,
        messages=[{"role": "user", "content": content}],
    )

    return response.choices[0].message.content.strip()
