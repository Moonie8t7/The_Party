"""
Twitch API client for game detection.
Fetches current game/category from the Twitch API.
"""

import time
import httpx
from party.config import settings
from party.log import get_logger

log = get_logger(__name__)

_token_cache: dict = {"token": None, "expires_at": 0}


async def _get_app_token() -> str:
    """Get or refresh Twitch app access token."""
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id": settings.twitch_client_id,
                "client_secret": settings.twitch_client_secret,
                "grant_type": "client_credentials",
            },
        )
        response.raise_for_status()
        data = response.json()
        _token_cache["token"] = data["access_token"]
        _token_cache["expires_at"] = time.time() + data["expires_in"]
        return _token_cache["token"]


async def _get_broadcaster_id(login: str, token: str) -> str:
    """Resolve broadcaster login to user ID."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.twitch.tv/helix/users",
            params={"login": login},
            headers={
                "Client-ID": settings.twitch_client_id,
                "Authorization": f"Bearer {token}",
            },
        )
        response.raise_for_status()
        data = response.json()
        if data.get("data"):
            return data["data"][0]["id"]
    raise ValueError(f"Could not find broadcaster: {login}")


async def get_current_game(broadcaster_login: str) -> dict:
    """
    Fetch current game and stream title for a broadcaster.
    Returns dict with keys: game_name, stream_title
    """
    if not settings.twitch_client_id or not settings.twitch_client_secret:
        log.debug("twitch.credentials_not_set")
        return {"game_name": "", "stream_title": ""}

    try:
        token = await _get_app_token()
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.twitch.tv/helix/channels",
                params={"broadcaster_id": await _get_broadcaster_id(broadcaster_login, token)},
                headers={
                    "Client-ID": settings.twitch_client_id,
                    "Authorization": f"Bearer {token}",
                },
            )
            response.raise_for_status()
            data = response.json()
            if data.get("data"):
                channel = data["data"][0]
                return {
                    "game_name": channel.get("game_name", ""),
                    "stream_title": channel.get("title", ""),
                }
    except Exception as e:
        log.warning("twitch.fetch_failed", reason=str(e))

    return {"game_name": "", "stream_title": ""}
