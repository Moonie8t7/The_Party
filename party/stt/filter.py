"""
STT reaction filter.

A single fast LLM call that decides whether a transcribed utterance
warrants a party response. Prevents The Party from reacting to every
word Moonie says.
"""

import asyncio
from anthropic import Anthropic
from party.config import settings
from party.log import get_logger

log = get_logger(__name__)

FILTER_PROMPT = """You are monitoring a Twitch streamer's microphone.
Your job is to decide if what they just said warrants a reaction from their AI party members.

Say YES if the streamer:
- Had a strong emotional reaction to something in the game (surprise, frustration, excitement, fear)
- Said something interesting or questionable about what they're doing or planning
- Made an observation worth responding to
- Asked a question out loud (even if not directed at chat)
- Experienced something notable (died, won, found something, failed)

Say NO if the streamer:
- Is talking to chat (answering questions, reading donations, etc.)
- Is doing routine commentary with no emotional content
- Said fewer than 5 meaningful words
- Is mid-sentence or trailing off
- Said something generic like "let me just grab this" or "ok ok"

Respond with ONLY the word YES or NO. Nothing else."""


async def should_react(utterance: str) -> bool:
    """
    Returns True if the utterance warrants a party reaction.
    Fast Haiku call — should complete in under 1 second.
    """
    try:
        client = Anthropic(api_key=settings.anthropic_api_key)
        loop = asyncio.get_event_loop()

        response = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: client.messages.create(
                    model=settings.stt_reaction_model,
                    max_tokens=5,
                    system=FILTER_PROMPT,
                    messages=[{"role": "user", "content": utterance}],
                ),
            ),
            timeout=5.0,
        )

        answer = response.content[0].text.strip().upper()
        result = answer.startswith("YES")

        log.info(
            "stt.filter_decision",
            result="react" if result else "ignore",
            utterance=utterance[:60],
        )
        return result

    except Exception as e:
        log.warning("stt.filter_failed", reason=str(e))
        return False  # Safe default: ignore if filter fails
