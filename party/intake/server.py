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
    Updates viewer memory for any trigger that carries a viewer field.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("intake.bad_json", raw=raw[:200])
        return

    try:
        incoming = IncomingTrigger.model_validate(data)
    except ValidationError as e:
        log.warning("intake.invalid_payload", errors=str(e), data=str(data)[:200])
        return

    # Update viewer memory for any trigger that carries a viewer field.
    # Silent — failure here must never block the trigger from processing.
    if incoming.viewer:
        try:
            from party.context.viewer_memory import update_viewer
            viewer_data = {}

            # First chatter fields (viewer_event triggers)
            if incoming.history:
                viewer_data.update(incoming.history)  # firsts, seconds, thirds
            if incoming.level is not None:
                viewer_data["level"] = incoming.level
            if incoming.xp is not None:
                viewer_data["xp"] = incoming.xp
            if incoming.rank is not None:
                viewer_data["last_rank"] = incoming.rank
            if incoming.roll:
                roll_history = viewer_data.get("roll_history", [])
                roll_history.append(incoming.roll.get("value"))
                viewer_data["roll_history"] = roll_history[-20:]

            # Generic event data (raid, sub, gift sub — system triggers)
            if incoming.event_data:
                viewer_data.update(incoming.event_data)

            await update_viewer(incoming.viewer, viewer_data)
        except Exception as e:
            log.warning(
                "intake.viewer_memory_update_failed",
                viewer=incoming.viewer,
                reason=str(e),
            )

    # Enrich to Trigger
    trigger = Trigger(
        type=incoming.type,
        text=incoming.text,
        priority=incoming.priority,
        cooldown_key=incoming.cooldown_key,
        game=incoming.game,
        viewer=incoming.viewer,
    )

    structlog.contextvars.bind_contextvars(trigger_id=trigger.trigger_id)
    log.info(
        "trigger.received",
        trigger_id=trigger.trigger_id,
        type=trigger.type,
        text=trigger.text[:60],
        priority=trigger.priority,
        viewer=trigger.viewer,
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
