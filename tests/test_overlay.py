import pytest
import asyncio
import json
import websockets
from party.output.obs import OverlayServer


@pytest.mark.asyncio
async def test_overlay_server_starts():
    server = OverlayServer()
    from unittest.mock import patch
    with patch("party.output.obs.settings") as mock_settings:
        mock_settings.overlay_host = "localhost"
        mock_settings.overlay_port = 8767
        await server.start()
        await server.stop()


@pytest.mark.asyncio
async def test_overlay_broadcasts_to_connected_client():
    server = OverlayServer()
    received = []

    from unittest.mock import patch
    with patch("party.output.obs.settings") as mock_settings:
        mock_settings.overlay_host = "localhost"
        mock_settings.overlay_port = 8768
        await server.start()

        async with websockets.connect("ws://localhost:8768") as ws:
            await server.notify("speaking_start", "grokthar")
            msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            received.append(json.loads(msg))

        await server.stop()

    assert len(received) == 1
    assert received[0]["event"] == "speaking_start"
    assert received[0]["character"] == "grokthar"


@pytest.mark.asyncio
async def test_overlay_notify_with_no_clients_does_not_crash():
    server = OverlayServer()
    # Should not raise even with no clients
    await server.notify("idle", None)


@pytest.mark.asyncio
async def test_overlay_idle_event_has_null_character():
    server = OverlayServer()
    received = []

    from unittest.mock import patch
    with patch("party.output.obs.settings") as mock_settings:
        mock_settings.overlay_host = "localhost"
        mock_settings.overlay_port = 8769
        await server.start()

        async with websockets.connect("ws://localhost:8769") as ws:
            await server.notify("idle", None)
            msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            received.append(json.loads(msg))

        await server.stop()

    assert received[0]["character"] is None
