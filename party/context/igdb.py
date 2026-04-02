"""
IGDB game lookup.
Uses Twitch API credentials (IGDB is owned by Twitch).
Returns a concise game summary for context injection.
"""

import httpx
from party.config import settings
from party.log import get_logger

log = get_logger(__name__)


async def _get_igdb_token() -> str:
    """IGDB uses the same OAuth as Twitch."""
    from party.context.twitch import _get_app_token
    return await _get_app_token()


async def get_game_summary(game_name: str) -> str:
    """
    Look up a game by name and return a concise summary for context.
    Returns empty string if lookup fails or credentials not set.
    """
    if not settings.igdb_enabled:
        return ""

    if not settings.twitch_client_id or not settings.twitch_client_secret:
        return ""

    if not game_name or game_name == "[not set]":
        return ""

    try:
        token = await _get_igdb_token()
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.igdb.com/v4/games",
                headers={
                    "Client-ID": settings.twitch_client_id,
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "text/plain",
                },
                content=(
                    f'search "{game_name}"; '
                    f'fields name,summary,genres.name,themes.name,'
                    f'game_modes.name,first_release_date,involved_companies.company.name;'
                    f'limit 1;'
                ),
            )
            response.raise_for_status()
            games = response.json()

            if not games:
                log.debug("igdb.no_results", game=game_name)
                return ""

            game = games[0]
            parts = []

            if game.get("summary"):
                summary = game["summary"]
                if len(summary) > 300:
                    summary = summary[:297] + "..."
                parts.append(summary)

            if game.get("genres"):
                genres = ", ".join(g["name"] for g in game["genres"][:3])
                parts.append(f"Genres: {genres}")

            if game.get("themes"):
                themes = ", ".join(t["name"] for t in game["themes"][:3])
                parts.append(f"Themes: {themes}")

            if game.get("game_modes"):
                modes = ", ".join(m["name"] for m in game["game_modes"][:2])
                parts.append(f"Modes: {modes}")

            result = " | ".join(parts)
            log.info("igdb.lookup_success", game=game_name, summary_len=len(result))
            return result

    except Exception as e:
        log.warning("igdb.lookup_failed", game=game_name, reason=str(e))
        return ""
