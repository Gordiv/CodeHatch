"""The Roblox Studio file scripts/DiscordCodes.rbxmx: the version this bot ships, the version the game runs and what
the game has.

Every game server with the file saves its version in the game's DataStore (key KitVersions, see Live.ReportVersion),
separately for the published game and for Studio. /setup-roblox compares it with the bot's own copy, so the owner
knows when a bot update changed the file and it must be replaced in Studio.

The game also reports what it has (key GameScan, see Live.ReportGame): names of the values in player data, egg spots
and models, the multipliers its code asks for and which own functions (OnReward, OnHatch...) are set. /setup-roblox
offers these exact names and the egg/event/gift tools warn about options that can't work in this game.
"""
import asyncio
import logging
import re
import time
from pathlib import Path

from utils import cloud_sync, config_store, open_cloud
from utils.i18n import t

KIT_FILE = Path(config_store.ROOT) / "scripts" / "DiscordCodes.rbxmx"
VERSION_RE = re.compile(rb"^local KIT_VERSION = (\d+)", re.M)
REPORT_KEY = "KitVersions"  # must match CONFIG.VersionKey in Live.luau
SCAN_KEY = "GameScan"  # must match CONFIG.ScanKey in Live.luau
CATALOG_KEY = "GameCatalog"  # must match CONFIG.CatalogKey in Report.luau (utils/catalog.py reads it)
NUMBER_CLASSES = ("IntValue", "NumberValue")
EXP_NAMES = ("exp", "xp", "experience")
STATE_FILE = "roblox_kit_state.json"
REFRESH_SECONDS = 300
STALE_SECONDS = 30 * 86400  # a place that hasn't started a server for 30 days is ignored
SEVERITY = {"ok": 0, "publish": 1, "outdated": 2}

log = logging.getLogger("roblox_kit")
_task = {"task": None, "forced": False}
_file_cache = {}  # path -> (mtime, size, version)


def version_in(data: bytes) -> int:
    """File version inside DiscordCodes.rbxmx (or Loader.server.luau). 0 = a file from before versions existed."""
    match = VERSION_RE.search(data or b"")
    return int(match.group(1)) if match else 0


def bundled_version(path: Path = KIT_FILE) -> int:
    """Version of the file, read again only when the file changed (it is 100+ KB)."""
    path = Path(path)
    try:
        info = path.stat()
    except OSError:
        return 0
    cached = _file_cache.get(str(path))
    if cached and cached[0] == info.st_mtime_ns and cached[1] == info.st_size:
        return cached[2]
    try:
        data = path.read_bytes()
    except OSError:
        return 0
    version = version_in(data)
    _file_cache[str(path)] = (info.st_mtime_ns, info.st_size, version)
    return version


def load_state() -> dict:
    return config_store.read_json(STATE_FILE, {})


async def refresh(force: bool = False) -> dict:
    """Reads the versions reported by the game (at most every 5 minutes unless forced)."""
    if cloud_sync.status() != "ready":
        return load_state()
    state = load_state()
    universe = cloud_sync.universe_id()
    if not force and state.get("universe") == universe and time.time() - state.get("checked_at", 0) < REFRESH_SECONDS:
        return state
    same_game = state.get("universe") == universe
    try:
        datastore = open_cloud.live_settings()["datastore"]
        data, scan, catalog = await asyncio.gather(*(open_cloud.read_entry(datastore, key)
                                                     for key in (REPORT_KEY, SCAN_KEY, CATALOG_KEY)))
        places = data.get("places") if isinstance(data, dict) else None
        scan_places = scan.get("places") if isinstance(scan, dict) else None
        catalog_places = catalog.get("places") if isinstance(catalog, dict) else None
        state = {"checked_at": int(time.time()), "universe": universe, "error": "",
                 "places": places if isinstance(places, dict) else {},
                 "scan": scan_places if isinstance(scan_places, dict) else {},
                 "catalog": catalog_places if isinstance(catalog_places, dict) else {}}
    except (open_cloud.OpenCloudError, ValueError) as e:  # ValueError: an answer that isn't valid JSON
        state = {"checked_at": int(time.time()), "universe": universe, "error": str(e)[:300],
                 "places": (state.get("places") if same_game else {}) or {},
                 "scan": (state.get("scan") if same_game else {}) or {},
                 "catalog": (state.get("catalog") if same_game else {}) or {}}
    config_store.write_json(STATE_FILE, state)
    return state


def _log_task_error(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception() is not None:
        log.warning("Reading the game's reports failed: %s", task.exception())


async def refresh_quick(force: bool = False, timeout: float = 1.5) -> dict:
    """Like refresh(), but waits at most `timeout` seconds (Discord needs a reply within 3 s); a slow check finishes
    in the background and shows up after the next refresh. A forced refresh never just waits for a normal one that
    is still running (that one may skip reading because the last check was recent)."""
    running = _task["task"]
    if running is None or running.done() or (force and not _task["forced"]):
        running = asyncio.create_task(refresh(force))
        running.add_done_callback(_log_task_error)
        _task.update(task=running, forced=force)
    try:
        await asyncio.wait_for(asyncio.shield(running), timeout)
    except Exception:
        pass
    return load_state()


def live_place_versions(state: dict = None) -> dict:
    """{place ID: version of the published place} as the game's live servers reported it (Report.ReportCatalog sends
    game.PlaceVersion when a server starts). A higher number means the game was published again."""
    state = load_state() if state is None else state
    if state.get("universe") != cloud_sync.universe_id():
        return {}
    versions = {}
    for place_id, place in (state.get("catalog") or {}).items():
        entry = place.get("live") if isinstance(place, dict) else None
        if isinstance(entry, dict):
            version = int(_number(entry.get("placeVersion")))
            if version:
                versions[str(place_id)] = version
    return versions


def _reported(place: dict, kind: str, now: float) -> int:
    entry = place.get(kind) if isinstance(place, dict) else None
    if not isinstance(entry, dict) or now - (_number(entry.get("at"))) > STALE_SECONDS:
        return 0
    return int(_number(entry.get("version")))


def _number(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0


def evaluate(state: dict = None, bundled: int = None) -> dict:
    """status: off | unknown | unchecked | error | no_report | ok | publish | outdated.
    publish = the new file is in Studio, but the published game still runs an older one (or nobody played it yet)."""
    bundled = bundled_version() if bundled is None else bundled
    info = {"status": "off", "bundled": bundled, "places": [], "old": 0, "error": ""}
    if cloud_sync.status() != "ready":
        return info
    if not bundled:
        info["status"] = "unknown"
        return info
    state = load_state() if state is None else state
    if not state.get("checked_at") or state.get("universe") != cloud_sync.universe_id():
        info["status"] = "unchecked"
        return info
    now = time.time()
    for place_id, place in sorted((state.get("places") or {}).items()):
        live, studio = _reported(place, "live", now), _reported(place, "studio", now)
        if not live and not studio:
            continue
        if live >= bundled:
            status = "ok"
        elif studio >= bundled:
            status = "publish"
        else:
            status = "outdated"
        info["places"].append({"place": str(place_id), "live": live, "studio": studio, "status": status})
    info["error"] = state.get("error", "")
    if not info["places"]:
        info["status"] = "error" if info["error"] else "no_report"
        return info
    info["status"] = max((p["status"] for p in info["places"]), key=SEVERITY.get)
    outdated = [max(p["live"], p["studio"]) for p in info["places"] if p["status"] == "outdated"]
    info["old"] = min(outdated) if outdated else 0
    return info


def live_file_warning(info: dict = None) -> str:
    """For the egg and event windows and answers: the game runs an older DiscordCodes file, so what is sent may not
    show in the game. "" when the file is fine or unknown."""
    info = info or evaluate()
    return status_line(info) if info["status"] == "outdated" else ""


def status_line(info: dict = None) -> str:
    """One line for /setup and the diagnostics; empty when the game isn't connected (Game sync off)."""
    info = info or evaluate()
    status = info["status"]
    if status in ("off", "unknown"):
        return ""
    if status == "ok":
        return t("kit.line_ok", version=info["bundled"])
    if status == "publish":
        return t("kit.line_publish", version=info["bundled"])
    if status == "outdated":
        return t("kit.line_outdated", old=info["old"], new=info["bundled"])
    if status == "no_report":
        return t("kit.line_no_report")
    if status == "error":
        return t("kit.line_error", error=info["error"])
    return t("kit.line_checking")


# ---------- What the game has (GameScan) ----------

def normalize(name) -> str:
    """Same rule as the game: letter case, spaces and other signs don't matter."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _list(value) -> list:
    if isinstance(value, dict):
        return list(value.values())
    return value if isinstance(value, list) else []


def _split(entry) -> tuple:
    name, _, kind = str(entry).rpartition(":")
    return (name, kind) if name else (str(entry), "")


def leaf(path: str) -> str:
    return str(path).rsplit(".", 1)[-1]


def game_scan(state: dict = None):
    """What the game reported (every place, published game and Studio, last 30 days), or None if nothing yet:
    {"values": [(path, class)], "attributes": [(name, type)], "spots", "templates", "multipliers", "hooks",
     "at", "studio", "players", "max_currency", "spot_count"}. spot_count: the most parts with the spot tag in one
    place (copies of a part share a name, so it can be more than the names in "spots"). Spots, templates, hooks and the limit Settings -> MaxCurrencyPerCode
    come from the newest report of each place. max_currency is the lowest limit of every report of the last 30 days,
    published game and Studio alike (a code or gift above it fails where that limit is set), 0 = none or not reported
    by a file older than version 15 (a server of an older file still running after the publish may also drop it from
    the report for up to 12 hours)."""
    if cloud_sync.status() != "ready":
        return None
    state = load_state() if state is None else state
    if state.get("universe") != cloud_sync.universe_id():
        return None
    now = time.time()
    values, attributes, multipliers = {}, {}, {}
    spots, templates, hooks = set(), set(), set()
    newest, studio, players, found, spot_count = 0, False, 0, False, 0
    limits = []
    for place in (state.get("scan") or {}).values():
        if not isinstance(place, dict):
            continue
        fresh = []  # (when it was written, kind, entry); "saved" since file version 14, "at" before
        for kind in ("live", "studio"):
            entry = place.get(kind)
            if not isinstance(entry, dict) or now - _number(entry.get("at")) > STALE_SECONDS:
                continue
            found = True
            limit = _number(entry.get("maxCurrency"))
            if 0 < limit < 1e18:  # not NaN or infinity
                limits.append(int(limit))
            fresh.append((_number(entry.get("saved")) or _number(entry.get("at")), kind, entry))
            for item in _list(entry.get("values")):
                path, cls = _split(item)
                values[path] = cls
            for item in _list(entry.get("attributes")):
                name, kind_name = _split(item)
                attributes[name] = kind_name
            for name in _list(entry.get("multipliers")):
                multipliers[normalize(name)] = str(name)
            players = max(players, int(_number(entry.get("players"))))
        if fresh:
            # Egg spots, egg models and the game's own functions: the newest report of this place (Studio or the
            # published game), so a spot or function removed since an older test doesn't stay for 30 days
            written, kind, entry = max(fresh, key=lambda f: f[0])
            spots.update(str(s) for s in _list(entry.get("spots")))
            # parts with the spot tag in this place (copies share a name); a file older than version 30 sends names only
            count = _number(entry.get("spotCount"))
            spot_count = max(spot_count, int(count) if 0 < count < 1e6 else len(_list(entry.get("spots"))))
            templates.update(str(s) for s in _list(entry.get("templates")))
            hooks.update(str(s) for s in _list(entry.get("hooks")))
            if written > newest:
                newest, studio = int(written), kind == "studio"
    if not found:
        return None
    return {"values": sorted(values.items(), key=lambda v: v[0].lower()),
            "attributes": sorted(attributes.items(), key=lambda v: v[0].lower()),
            "spots": sorted(spots, key=str.lower), "templates": sorted(templates, key=str.lower),
            "multipliers": sorted(multipliers.values(), key=str.lower), "hooks": sorted(hooks),
            "at": newest, "studio": studio, "players": players, "max_currency": min(limits) if limits else 0,
            "spot_count": spot_count}


def has_hook(scan: dict, name: str) -> bool:
    return bool(scan) and name in scan["hooks"]


def find_name(scan: dict, name: str, item: bool = False) -> list:
    """Where the game's reward system would put this name ("leaderstats.Coins", "@Gems" for an attribute).
    Currencies need a number; items may also be true/false values and may be called Has<Name>."""
    wanted = {normalize(name)}
    if item:
        wanted.add(normalize("Has" + str(name)))
    paths = [p for p, cls in scan["values"] if normalize(leaf(p)) in wanted and (item or cls in NUMBER_CLASSES)]
    paths += [f"@{n}" for n, kind in scan["attributes"] if normalize(n) in wanted and (item or kind == "number")]
    return paths


def exp_paths(scan: dict) -> list:
    return [p for name in EXP_NAMES for p in find_name(scan, name)]


def ambiguous_warning(name: str, paths: list, hook: str) -> str:
    """The game gives a reward only where exactly one value fits; with several (e.g. leaderstats.Coins and Data.Coins)
    it doesn't know which one to change and refuses it. "" when there is at most one."""
    if len(paths) < 2:
        return ""
    return t("scan.warn_ambiguous", name=name, count=len(paths), paths=", ".join(paths[:4]), hook=hook)


def name_mark(scan: dict, name: str, item: bool = False) -> str:
    """For the lists of names: ✅ found in one place, ⚠️ nowhere or in several places (the game refuses both)."""
    count = len(find_name(scan, name, item=item))
    if count == 1:
        return f"✅ {name}"
    return "⚠️ " + (t("rbx.names_ambiguous", name=name, count=count) if count > 1 else name)


def name_groups(scan: dict, numbers_only: bool) -> list:
    """[(name, [paths])] of the names in player data, grouped by the last part of the path."""
    groups = {}
    for path, cls in scan["values"]:
        if not numbers_only or cls in NUMBER_CLASSES:
            groups.setdefault(leaf(path), []).append(path)
    for name, kind in scan["attributes"]:
        if not numbers_only or kind == "number":
            groups.setdefault(name, []).append(f"@{name}")
    return sorted(groups.items(), key=lambda g: g[0].lower())


def uses_multiplier(scan: dict, key: str, declared: list = ()) -> bool:
    """Whether the game's own code applies this multiplier (it calls Live.GetMultiplier for it, or the catalog lists
    it). Luck always works."""
    used = {normalize(m) for m in list(scan["multipliers"]) + list(declared)}
    if key == "luck":
        return True
    if key == "exp":
        return bool(used & set(EXP_NAMES))
    if key == "*":
        return bool(used - set(EXP_NAMES) - {"luck"})
    return normalize(key) in used


def egg_model(scan: dict, template: str = "") -> str:
    """The model the game stands for an egg (ReplicatedStorage → DiscordEggs): the egg's own model, else "Default".
    "" = the plain egg, the only one that has the bot's color (or no report from the game: unknown)."""
    if not scan:
        return ""
    templates = set(scan["templates"])
    return next((name for name in ((template or "").strip() or "Default", "Default") if name in templates), "")


def color_warning(scan: dict, template: str = "") -> str:
    """For a chosen egg color: a note when the game shows a model instead of the colored egg."""
    model = egg_model(scan, template)
    return t("scan.warn_color_model", model=model) if model else ""


def _unknown_game() -> list:
    """No report from the game: one hint, only when the game connection works (otherwise the sync error says enough)."""
    return [t("scan.warn_unknown_game")] if cloud_sync.status() == "ready" else []


def spots_warning(scan: dict, eggs: int) -> str:
    """Each egg needs its own spot in the game: with more eggs than spots the extra ones don't show at all."""
    scan = scan or {}
    spots = scan.get("spot_count") or len(scan.get("spots") or [])
    if not spots or eggs <= spots:
        return ""
    return t("scan.warn_too_few_spots", eggs=eggs, spots=spots)


def egg_warnings(scan: dict, currency: str, pets: list) -> list:
    if not scan:
        return _unknown_game()
    warnings = []
    if not scan["spots"]:
        warnings.append(t("scan.warn_no_spots"))
    if not has_hook(scan, "OnSpend"):
        paths = find_name(scan, currency)
        if not paths:
            warnings.append(t("scan.warn_price_currency", currency=currency))
        warnings.append(ambiguous_warning(currency, paths, "Core.OnSpend"))
    if not has_hook(scan, "OnHatch") and not has_hook(scan, "OnReward"):
        missing = [p for p in pets if not find_name(scan, p, item=True)]
        if missing:
            warnings.append(t("scan.warn_pets", pets=", ".join(missing[:10])))
        warnings += [ambiguous_warning(p, find_name(scan, p, item=True), "Live.OnHatch") for p in pets]
    return [w for w in warnings if w]


def event_warnings(scan: dict, multipliers: dict, declared: list = ()) -> list:
    """declared: the multipliers the game's catalog lists (utils/catalog.py)."""
    if not scan and not declared:
        return _unknown_game() if any(k != "luck" for k in multipliers) else []
    scan = scan or {"multipliers": []}
    warnings = []
    for key in multipliers:
        if key == "exp" and not uses_multiplier(scan, "exp", declared):
            warnings.append(t("scan.warn_mult_exp"))
        elif key.startswith("currency:"):
            currency = key.split(":", 1)[1]
            if not uses_multiplier(scan, currency, declared):
                name = t("events.all_currencies") if currency == "*" else currency
                warnings.append(t("scan.warn_mult_currency", currency=name))
    return warnings


def _above_limit(scan: dict, reward: dict) -> dict:
    """{amount, currency, limit} as texts when the reward's currency is above the game's limit, else {}."""
    limit = (scan or {}).get("max_currency") or 0
    currency = (reward or {}).get("currency")
    if not limit or not currency or currency["amount"] <= limit:
        return {}
    return {"amount": f"{currency['amount']:,}", "currency": currency["name"], "limit": f"{limit:,}"}


def limit_error(scan: dict, reward: dict) -> str:
    """The refusal for a code or gift with more currency than Settings -> MaxCurrencyPerCode allows (the game would
    refuse it: a code nobody can redeem, a gift that waits forever), or "" when it fits or the limit is unknown."""
    above = _above_limit(scan, reward)
    return t("scan.err_reward_limit", **above) if above else ""


def reward_warnings(scan: dict, reward: dict) -> list:
    """For gifts and codes: a currency amount above the game's limit (the game refuses it, also with Core.OnReward) and
    parts of the reward the game has no place for (unless the game uses Core.OnReward)."""
    if not scan:
        return []
    warnings = []
    above = _above_limit(scan, reward)
    if above:
        warnings.append(t("scan.warn_reward_limit", **above))
    if has_hook(scan, "OnReward"):
        return warnings
    if "currency" in reward:
        paths = find_name(scan, reward["currency"]["name"])
        if not paths:
            warnings.append(t("scan.warn_reward_currency", currency=reward["currency"]["name"]))
        warnings.append(ambiguous_warning(reward["currency"]["name"], paths, "Core.OnReward"))
    if "exp" in reward:
        paths = exp_paths(scan)
        if not paths:
            warnings.append(t("scan.warn_reward_exp"))
        warnings.append(ambiguous_warning("EXP", paths, "Core.OnReward"))
    item = reward.get("item")
    if item:
        name = f"{item['name']}_ExpiresAt" if item.get("is_temporary") else item["name"]
        paths = find_name(scan, name, item=not item.get("is_temporary"))
        if not paths:
            warnings.append(t("scan.warn_reward_item", item=name))
        warnings.append(ambiguous_warning(name, paths, "Core.OnReward"))
    return [w for w in warnings if w]
