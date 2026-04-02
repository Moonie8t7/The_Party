"""
Overlay broadcast server.
The orchestrator runs a WebSocket server on port 8766.
The OBS browser source connects to ws://localhost:8766 as a client.
Events are broadcast to all connected clients.
"""

import asyncio
import json
import websockets
from typing import Optional
from party.config import settings
from party.log import get_logger

log = get_logger(__name__)


class OverlayServer:
    def __init__(self):
        self._clients: set = set()
        self._server = None
        self._lock = asyncio.Lock()

    async def start(self):
        """Start the overlay WebSocket server."""
        self._server = await websockets.serve(
            self._handle_client,
            settings.overlay_host,
            settings.overlay_port,
        )
        log.info(
            "overlay.server_started",
            host=settings.overlay_host,
            port=settings.overlay_port,
        )

    async def _handle_client(self, websocket):
        """Handle a new overlay client connection."""
        async with self._lock:
            self._clients.add(websocket)
        log.info("overlay.client_connected", clients=len(self._clients))
        try:
            async for message in websocket:
                # Forward messages from test harness to all clients
                await self._broadcast_raw(message)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            async with self._lock:
                self._clients.discard(websocket)
            log.info("overlay.client_disconnected", clients=len(self._clients))

    async def _broadcast_raw(self, payload: str):
        """Broadcast a raw payload string to all connected clients."""
        async with self._lock:
            clients = set(self._clients)
        await asyncio.gather(
            *[self._send_safe(c, payload) for c in clients],
            return_exceptions=True,
        )

    async def notify(self, event: str, character: Optional[str] = None, text: Optional[str] = None, display_name: Optional[str] = None, response_type: str = "primary"):
        """Broadcast an event to all connected overlay clients."""
        if not self._clients:
            return

        payload = json.dumps({
            "event": event,
            "character": character,
            "text": text,
            "display_name": display_name,
            "type": response_type,
        })

        await self._broadcast_raw(payload)

    async def _send_safe(self, websocket, payload: str):
        """Send to a single client, ignoring connection errors."""
        try:
            await websocket.send(payload)
        except Exception:
            pass

    async def stop(self):
        """Stop the overlay server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            log.info("overlay.server_stopped")


# Module-level singleton
overlay_server = OverlayServer()


async def notify(event: str, character: Optional[str] = None, text: Optional[str] = None, display_name: Optional[str] = None, response_type: str = "primary"):
    """Public interface used by speech manager."""
    await overlay_server.notify(event, character, text, display_name, response_type)
