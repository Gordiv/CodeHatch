"""Public Roblox web APIs (no API key): users, games, thumbnails.

Every function either returns data, returns None when the thing doesn't exist, or raises RobloxApiError with a text
for the user (Roblox didn't answer, answered with an error page, or limited the requests).
"""
import asyncio
import logging

import aiohttp

from utils import net
from utils.i18n import t

TIMEOUT = 10

log = logging.getLogger("roblox_api")


class RobloxApiError(Exception):
    pass


async def _request(method: str, url: str, missing=(404,), **kwargs):
    """JSON of the answer, None for a status in `missing`, RobloxApiError for anything else."""
    try:
        async with net.session().request(method, url, timeout=net.timeout(kwargs.pop("seconds", TIMEOUT)), **kwargs) as resp:
            if resp.status in missing:
                return None
            if resp.status == 429:
                raise RobloxApiError(t("roblox.rate_limited"))
            if resp.status != 200:
                raise RobloxApiError(t("roblox.status_error", status=resp.status))
            return await net.json_body(resp)
    except net.BadResponse:
        raise RobloxApiError(t("roblox.bad_answer"))
    except (aiohttp.ClientError, asyncio.TimeoutError):
        raise RobloxApiError(t("roblox.connection_error"))


def _data_list(payload) -> list:
    data = payload.get("data") if isinstance(payload, dict) else None
    return data if isinstance(data, list) else []


async def resolve_user(username: str, exclude_banned: bool = False):
    """(user_id, exact username) for a Roblox username, or None if it doesn't exist."""
    payload = {"usernames": [username.strip()[:50]], "excludeBannedUsers": exclude_banned}
    data = await _request("POST", "https://users.roblox.com/v1/usernames/users", missing=(400,), json=payload)
    users = _data_list(data)
    try:
        return (int(users[0]["id"]), str(users[0]["name"])) if users else None
    except (KeyError, TypeError, ValueError):
        raise RobloxApiError(t("roblox.bad_answer"))


async def find_users(text: str) -> list:
    """Every account the text can mean: [(user_id, exact username, "name" or "id")]. A username (an "@" in front is
    fine) and, for a number, also the account with that user ID: a name made only of digits is still a name, so a
    number can mean two different accounts. The caller lets the admin choose then, never guesses."""
    text = (text or "").strip().lstrip("@").strip()
    if not text:
        return []
    found = []
    user = await resolve_user(text)
    if user:
        found.append((user[0], user[1], "name"))
    if text.isascii() and text.isdigit() and len(text) <= 19 and not any(f[0] == int(text) for f in found):
        profile = await get_user(int(text))
        if profile and profile.get("name"):
            found.append((int(text), str(profile["name"]), "id"))
    return found


async def usernames(user_ids: list) -> dict:
    """{user_id: username} for up to 100 Roblox user IDs (missing ones are left out). A failed request is written
    to the log and gives an empty result, so a leaderboard still shows the entry names."""
    ids = [int(i) for i in user_ids][:100]
    if not ids:
        return {}
    try:
        data = await _request("POST", "https://users.roblox.com/v1/users", missing=(),
                              json={"userIds": ids, "excludeBannedUsers": False})
    except RobloxApiError as e:
        log.warning("Could not read Roblox user names: %s", e)
        return {}
    result = {}
    for user in _data_list(data):
        try:
            result[int(user["id"])] = str(user["name"])
        except (KeyError, TypeError, ValueError):
            continue
    return result


async def get_user(user_id: int):
    """The public profile ({"name", "displayName", "description", "created", ...}) or None."""
    data = await _request("GET", f"https://users.roblox.com/v1/users/{int(user_id)}", missing=(400, 404))
    return data if isinstance(data, dict) else None


async def universe_of_place(place_id: int):
    data = await _request("GET", f"https://apis.roblox.com/universes/v1/places/{int(place_id)}/universe", missing=(400, 404))
    if not isinstance(data, dict):
        return None
    try:
        return int(data.get("universeId") or 0) or None
    except (TypeError, ValueError):
        return None


async def get_game(universe_id: int):
    """The game's public data ({"name", "playing", "visits", "favoritedCount", "rootPlaceId", "updated"...}) or None."""
    data = await _request("GET", f"https://games.roblox.com/v1/games?universeIds={int(universe_id)}", missing=(400, 404))
    games = _data_list(data)
    return games[0] if games and isinstance(games[0], dict) else None


_owner_cache = {}


async def game_owner_id(universe_id) -> int:
    """The Roblox user who owns the game (the group's owner for a group game), 0 when unknown. Remembered."""
    if not universe_id:
        return 0
    if universe_id in _owner_cache:
        return _owner_cache[universe_id]
    try:
        game = await get_game(int(universe_id)) or {}
        creator = game.get("creator") or {}
        owner = int(creator.get("id") or 0)
        if creator.get("type") == "Group" and owner:
            group = await _request("GET", f"https://groups.roblox.com/v1/groups/{owner}") or {}
            owner = int(((group.get("owner") or {}).get("userId")) or 0)
    except (RobloxApiError, TypeError, ValueError):
        return 0  # not known now: asked again next time
    if owner:
        _owner_cache[universe_id] = owner
    return owner


async def avatar_url(user_id: int, size: str = "352x352") -> str:
    data = await _request("GET", f"https://thumbnails.roblox.com/v1/users/avatar?userIds={int(user_id)}&size={size}"
                                 "&format=Png&isCircular=false", missing=(400, 404))
    images = _data_list(data)
    return str(images[0].get("imageUrl") or "") if images and isinstance(images[0], dict) else ""
