"""
Entry point for The Party orchestrator.
Run with: python -m party.main
"""

import asyncio
import websockets
from party.log import configure_logging, get_logger
from party.config import settings
from party.models import CHARACTERS
from party.queue.scheduler import Scheduler
from party.orchestration.chain import orchestrate
from party.output.speech import speech_manager
from party.output.obs import overlay_server
from party.persistence.transcript import write_transcript
from party.intake.server import ws_handler
from party.context.session import update_auto_fields, ensure_session_file
from party.context.twitch import get_current_game
from party.context.igdb import get_game_summary
from party.stt.coordinator import STTCoordinator
from party.vision.loop import start_vision_loop, stop_vision_loop

log = get_logger(__name__)


async def _full_pipeline(trigger):
    """Orchestrate, speak, and persist a single trigger."""
    from party.models import CharacterResponse, Scene
    
    async for item in orchestrate(trigger):
        if isinstance(item, CharacterResponse):
            await speech_manager.play_item(item)
        elif isinstance(item, Scene):
            await write_transcript(item)
        elif isinstance(item, dict) and item.get("event") == "orchestration_start":
            log.debug("pipeline.orchestration_start", trigger_id=trigger.trigger_id, characters=item.get("characters"))


async def main():
    # 1. Configure logging first
    configure_logging()
    log.info("startup.begin")

    # 2. Validate config - log non-secret values
    log.info(
        "startup.config",
        ws_host=settings.ws_host,
        ws_port=settings.ws_port,
        overlay_port=settings.overlay_port,
        router_model=settings.router_model,
        queue_max_size=settings.queue_max_size,
        trigger_cooldown_seconds=settings.trigger_cooldown_seconds,
        dedup_window_seconds=settings.dedup_window_seconds,
        provider_timeout_normal_seconds=settings.provider_timeout_normal_seconds,
        provider_retries_normal=settings.provider_retries_normal,
        elevenlabs_enabled=bool(settings.elevenlabs_api_key),
        log_level=settings.log_level,
        transcript_path=settings.transcript_path,
    )

    # 3. Validate all five prompt files loaded
    for name, char in CHARACTERS.items():
        if not char.prompt:
            raise RuntimeError(f"Prompt for '{name}' is empty - check prompts/{name}.txt")
    log.info("startup.prompts_ok", count=len(CHARACTERS))

    # 3b. Populate session context
    ensure_session_file()
    try:
        channel_info = await get_current_game(settings.twitch_broadcaster_login)
        game_name = channel_info.get("game_name", "")
        stream_title = channel_info.get("stream_title", "")
        game_summary = await get_game_summary(game_name) if game_name else ""

        update_auto_fields(
            game=game_name,
            game_summary=game_summary,
            stream_title=stream_title,
        )
        log.info(
            "startup.context_populated",
            game=game_name,
            has_summary=bool(game_summary),
            stream_title=stream_title[:40] if stream_title else "",
        )
    except Exception as e:
        log.warning("startup.context_population_failed", reason=str(e))
        update_auto_fields()  # Write at minimum the date/time

    # 3c. Log voice config for each character
    for name, character in CHARACTERS.items():
        vs = character.voice_settings
        log.info(
            "startup.voice_config",
            character=character.display_name,
            voice_id=character.voice_id[:8] + "...",
            speed=vs.speed,
            stability=vs.stability,
            style=vs.style,
            use_speaker_boost=vs.use_speaker_boost,
        )

    # 4. Wire up the scheduler (no auto-start - we start manually below)
    scheduler = Scheduler()
    scheduler.set_handler(_full_pipeline)

    # 5. Start overlay server
    await overlay_server.start()
    log.info("startup.overlay_started", port=settings.overlay_port)

    # 5b. Start vision loop
    await start_vision_loop()
    if settings.vision_enabled:
        log.info("startup.vision_started", interval=settings.vision_interval_seconds)
    else:
        log.info("startup.vision_disabled")

    # 6. Start queue consumer task
    consumer_task = asyncio.create_task(scheduler.run_consumer())
    log.info("startup.consumer_started")

    # 6b. Start Idle Coordinator
    from party.orchestration.idle import IdleCoordinator
    idle_coordinator = IdleCoordinator(scheduler)
    await idle_coordinator.start()

    # 6c. Start STT coordinator
    stt_coordinator = STTCoordinator(
        enqueue_fn=scheduler.enqueue,
        poke_fn=scheduler.poke_activity
    )
    if settings.stt_enabled:
        await stt_coordinator.start()
        log.info("startup.stt_started", model=settings.stt_model)
    else:
        log.info("startup.stt_disabled")

    # 7. Start WebSocket server
    async def _ws_handler(websocket):
        await ws_handler(websocket, scheduler.enqueue)

    server = await websockets.serve(
        _ws_handler,
        settings.ws_host,
        settings.ws_port,
    )
    log.info(
        "startup.complete",
        address=f"ws://{settings.ws_host}:{settings.ws_port}",
    )
    print(f"[Server] Starting Dungeon Arcade Orchestrator...")
    print(f"[Server] Listening on ws://{settings.ws_host}:{settings.ws_port}")

    try:
        await asyncio.Future()  # run forever
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        pass
    finally:
        log.info("shutdown.initiated")
        print("\n[Server] Shutting down...")

        server.close()
        await server.wait_closed()
        consumer_task.cancel()
        try:
            await asyncio.wait_for(consumer_task, timeout=10.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

        await stt_coordinator.stop()
        await idle_coordinator.stop()
        await stop_vision_loop()
        await overlay_server.stop()
        log.info("shutdown.complete")
        print("[Server] Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
