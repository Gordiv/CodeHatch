"""Roblox Open Cloud: the one client every game feature uses (code sync, events, eggs, gifts, messages to all game
servers, bans and the game's leaderboard). The API key and universe come from /setup-roblox -> Game connection.

All requests go through _request(): one shared HTTP session, a time limit, and an error text that says exactly what
to fix in Creator Hub.
"""
import asyncio
import base64
import hashlib
import json
from urllib.parse import quote

import aiohttp

from utils import cloud_sync, net
from utils.i18n import t

API = "https://apis.roblox.com"
DATASTORE_ENTRY = API + "/datastores/v1/universes/{u}/standard-datastores/datastore/entries/entry"
PUBLISH = API + "/cloud/v2/universes/{u}:publishMessage"
RESTRICTION = API + "/cloud/v2/universes/{u}/user-restrictions/{user}"
ORDERED_ENTRIES = API + "/cloud/v2/universes/{u}/ordered-data-stores/{name}/scopes/{scope}/entries"

DATASTORE_SCOPES = ("universe-datastores.objects:create, universe-datastores.objects:read, "
                    "universe-datastores.objects:update, universe-datastores.control:create")
MESSAGING_SCOPE = "universe-messaging-service:publish"
RESTRICTION_SCOPES = "universe.user-restriction:read, universe.user-restriction:write"
ORDERED_SCOPE = "universe.ordered-data-store.scope.entry:read"
MAX_MESSAGE_BYTES = 1000
TIMEOUT = 15


class OpenCloudError(Exception):
    pass


class VersionConflict(OpenCloudError):
    """The entry changed after it was read (e.g. the game's ⚙️ Manager saved something in that moment). Roblox answers
    with the entry as it is now: value and version, ready for the next try."""

    def __init__(self, value, version):
        super().__init__("the entry changed in the meantime")
        self.value, self.version = value, version


def live_settings() -> dict:
    cfg = cloud_sync.settings()
    return {"datastore": cfg.get("live_datastore") or "DiscordLiveContent",
            "gifts": cfg.get("gifts_datastore") or "DiscordGifts",
            "topic": cfg.get("live_topic") or "DiscordLive"}


def require_key() -> int:
    """Universe ID when the API key and game are set (bans and leaderboard don't need Game sync switched on)."""
    if not cloud_sync.api_key():
        raise OpenCloudError(t("sync.no_key"))
    universe = cloud_sync.universe_id()
    if not universe:
        raise OpenCloudError(t("sync.no_universe"))
    return universe


def require_live() -> int:
    """Universe ID when Game sync is fully ready (data sent into the game needs the in-game script and the switch on)."""
    state = cloud_sync.status()
    if state != "ready":
        raise OpenCloudError(t(f"sync.{state}") if state in ("off", "no_key", "no_universe", "config_error") else t("sync.off"))
    return cloud_sync.universe_id()


def error_text(status_code: int, body: str, what: str, kind: str = "datastore") -> str:
    """Message for the administrator: what exactly to fix in Creator Hub."""
    try:
        payload = json.loads(body)
    except ValueError:
        payload = {}
    if kind in ("datastore", "messaging"):
        permission = (t("sync.permission_datastore", scopes=DATASTORE_SCOPES) if kind == "datastore"
                      else t("sync.permission_messaging", scope=MESSAGING_SCOPE))
        if isinstance(payload, dict) and payload.get("error") == "INSUFFICIENT_SCOPE":
            return t("sync.error_scope", what=what, permission=permission)
        hints = {400: t("sync.error_400"), 401: t("sync.error_401"), 403: t("sync.error_403", permission=permission),
                 404: t("sync.error_404"), 429: t("sync.error_429")}
        text = hints.get(status_code) or (t("sync.error_5xx", status=status_code) if status_code >= 500
                                          else t("sync.error_other", status=status_code))
        return f"{what}: {text}"
    permission = t("cloud.permission", scopes=RESTRICTION_SCOPES if kind == "restriction" else ORDERED_SCOPE)
    if status_code in (401, 403):
        return f"{what}: {t('cloud.error_permission', permission=permission)}"
    if status_code == 404:
        return f"{what}: {t('cloud.error_404')}"
    if status_code == 429:
        return f"{what}: {t('sync.error_429')}"
    return f"{what}: {t('sync.error_5xx' if status_code >= 500 else 'sync.error_other', status=status_code)}"


async def _send(method: str, url: str, **kwargs) -> tuple:
    """(status, body, roblox-entry-version header) of one request."""
    headers = {"x-api-key": cloud_sync.api_key(), **kwargs.pop("headers", {})}
    try:
        async with net.session().request(method, url, headers=headers, timeout=net.timeout(TIMEOUT), **kwargs) as resp:
            return resp.status, await resp.text(), resp.headers.get("roblox-entry-version")
    except (aiohttp.ClientError, asyncio.TimeoutError):
        raise OpenCloudError(t("sync.connection_error"))


def _json(text: str, what: str):
    if not text.strip():
        return {}
    try:
        return json.loads(text)
    except ValueError:
        raise OpenCloudError(f"{what}: {t('roblox.bad_answer')}")


async def _request(method: str, url: str, what: str, kind: str, missing_ok: bool = False, **kwargs):
    status, text, _ = await _send(method, url, **kwargs)
    if missing_ok and status == 404:
        return None
    if status not in (200, 204):
        raise OpenCloudError(error_text(status, text, what, kind))
    return _json(text, what)


def _body(value) -> tuple:
    """The JSON of a value and the headers Roblox checks it with."""
    body = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return body, {"content-type": "application/json",
                  "content-md5": base64.b64encode(hashlib.md5(body, usedforsecurity=False).digest()).decode()}


async def datastore_write(universe: int, datastore: str, key: str, value, what: str = None) -> None:
    body, headers = _body(value)
    await _request("POST", DATASTORE_ENTRY.format(u=universe), what or t("cloud.what_write"), "datastore",
                   params={"datastoreName": datastore, "entryKey": key}, data=body, headers=headers)


async def read_entry_versioned(datastore: str, key: str, what: str = None) -> tuple:
    """(value, version) of an entry; (None, None) when nobody saved it yet. The version is what write_entry_if needs."""
    what = what or t("cloud.what_read")
    status, text, version = await _send("GET", DATASTORE_ENTRY.format(u=require_key()),
                                        params={"datastoreName": datastore, "entryKey": key})
    if status == 404:
        return None, None
    if status not in (200, 204):
        raise OpenCloudError(error_text(status, text, what, "datastore"))
    return _json(text, what), version


async def write_entry_if(datastore: str, key: str, value, version, what: str = None) -> None:
    """Saves an entry only if nobody changed it since it was read with this version (None: only if it doesn't exist
    yet). Otherwise raises VersionConflict with the entry as it is now (Roblox answers 412 with its value and version),
    so a change made in the game in that moment is never overwritten. Checked against Roblox on 2026-10-31."""
    what = what or t("cloud.what_write")
    body, headers = _body(value)
    params = {"datastoreName": datastore, "entryKey": key}
    if version:
        params["matchVersion"] = version
    else:
        params["exclusiveCreate"] = "true"
    status, text, current = await _send("POST", DATASTORE_ENTRY.format(u=require_live()), params=params, data=body,
                                        headers=headers)
    if status == 412:
        try:
            now = json.loads(text) if text.strip() else None
        except ValueError:
            now = None  # read again on the next try
        raise VersionConflict(now, current)
    if status == 404:  # removed after it was read (e.g. in Creator Hub): saved as a new entry on the next try
        raise VersionConflict(None, None)
    if status not in (200, 204):
        raise OpenCloudError(error_text(status, text, what, "datastore"))


async def messaging_publish(universe: int, topic: str, message: dict, what: str = None) -> None:
    text = json.dumps(message, separators=(",", ":"), ensure_ascii=False)
    if len(text.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise OpenCloudError(t("cloud.message_too_long"))
    await _request("POST", PUBLISH.format(u=universe), what or t("sync.what_notify"), "messaging",
                   json={"topic": topic, "message": text})


async def write_entry(datastore: str, key: str, value) -> None:
    await datastore_write(require_live(), datastore, key, value)


async def read_entry(datastore: str, key: str):
    """Value of a DataStore entry written by the game, or None when the game hasn't written it yet."""
    universe = require_key()
    return await _request("GET", DATASTORE_ENTRY.format(u=universe), t("cloud.what_read"), "datastore", missing_ok=True,
                          params={"datastoreName": datastore, "entryKey": key})


async def publish(message: dict) -> None:
    await messaging_publish(require_live(), live_settings()["topic"], message)


async def set_ban(user_id: int, active: bool, seconds: int = 0, display_reason: str = "", private_reason: str = "") -> dict:
    """Bans (active=True) or unbans a user in every place of the game. seconds=0 means permanent."""
    universe = require_key()
    restriction = {"active": active}
    if active:
        restriction.update({"displayReason": display_reason[:400], "privateReason": private_reason[:1000],
                            "excludeAltAccounts": False})
        if seconds:
            restriction["duration"] = f"{int(seconds)}s"
    return await _request("PATCH", RESTRICTION.format(u=universe, user=int(user_id)), t("cloud.what_ban"), "restriction",
                          params={"updateMask": "gameJoinRestriction"}, json={"gameJoinRestriction": restriction})


async def get_ban(user_id: int) -> dict:
    universe = require_key()
    data = await _request("GET", RESTRICTION.format(u=universe, user=int(user_id)), t("cloud.what_ban_check"), "restriction")
    restriction = data.get("gameJoinRestriction") if isinstance(data, dict) else None
    return restriction if isinstance(restriction, dict) else {}


async def top_entries(datastore: str, scope: str = "global", limit: int = 10) -> list:
    """[(entry name, value)] from the game's OrderedDataStore, highest first."""
    universe = require_key()
    url = ORDERED_ENTRIES.format(u=universe, name=quote(datastore, safe=""), scope=quote(scope or "global", safe=""))
    data = await _request("GET", url, t("cloud.what_leaderboard"), "ordered",
                          params={"maxPageSize": max(1, min(limit, 100)), "orderBy": "value desc"})
    entries = data.get("orderedDataStoreEntries") if isinstance(data, dict) else None
    return [(str(e.get("id", "")), e.get("value", 0)) for e in (entries or []) if isinstance(e, dict)]
