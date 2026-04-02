import json
import websockets
from typing import Callable, Awaitable
from pydantic import ValidationError
from party.models import IncomingTrigger, Trigger
from party.log import get_logger
import structlog

log = get_logger(__name__)


async def handle_message(
    raw: str,
    enqueue_fn: Callable[[Trigger], Awaitable[None]],
) -> None:
    """
    Parse, validate, and enqueue a single raw WebSocket message.
    Extracted for testability - no WebSocket dependency.
    """
    # Parse JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("intake.bad_json", raw=raw[:200])
        return

    # Validate against IncomingTrigger model
    try:
        incoming = IncomingTrigger.model_validate(data)
    except ValidationError as e:
        log.warning("intake.invalid_payload", errors=str(e), data=str(data)[:200])
        return

    # Enrich to Trigger
    trigger = Trigger(
        type=incoming.type,
        text=incoming.text,
        priority=incoming.priority,
        cooldown_key=incoming.cooldown_key,
        game=incoming.game,
    )

    structlog.contextvars.bind_contextvars(trigger_id=trigger.trigger_id)
    log.info(
        "trigger.received",
        trigger_id=trigger.trigger_id,
        type=trigger.type,
        text=trigger.text[:60],
        priority=trigger.priority,
    )

    await enqueue_fn(trigger)


async def ws_handler(websocket, enqueue_fn: Callable[[Trigger], Awaitable[None]]) -> None:
    """
    Handles a single WebSocket connection from Streamer.bot.
    Delegates all validation and enqueue logic to handle_message.
    """
    remote = getattr(websocket, 'remote_address', 'unknown')
    log.info("intake.connected", remote=str(remote))
    try:
        async for message in websocket:
            await handle_message(message, enqueue_fn)
    except websockets.exceptions.ConnectionClosed:
        log.info("intake.disconnected", remote=str(remote))
