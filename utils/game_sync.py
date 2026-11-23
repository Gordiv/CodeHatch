"""The codes, events and eggs live in the game's DataStore, and the game's ⚙️ Manager changes them there by itself, also
when the bot is off. The bot keeps a copy in its database (Discord lists them and changes them) and one sync, run after
every change on Discord and every 2 minutes, makes the two agree:
- what the game made, changed or removed is copied into the database (the game is right about what it has);
- what was changed on Discord and the game doesn't have yet (rows with pending > 0) goes into the game's entry;
- the entry is saved only if nobody changed it after it was read (Open Cloud matchVersion), so a code a game server
  saved in that very moment is never overwritten: the bot takes the newer entry and tries again.
Ended things (an event after its time, an egg or a code after its end) are left out of the entry. Other fields in the
entry and its items (e.g. "by_id", "next_id" of the game) are kept as they are.

The entries keep the shape older DiscordCodes files read: ActiveCodes {codes = {CODE = reward}} (+ "meta": who made
each code), Events {events = [...]}, Eggs {eggs = [...]}. An event or egg made in the game has the id "g<number>".
"""
import asyncio
import copy
import json
import time
from dataclasses import dataclass, field

from utils import cloud_sync, database, open_cloud
from utils.i18n import t

MAX_TRIES = 5
ENTRY_VERSION = 2
# seconds -> the name /code-add uses for an item's time (the same as ITEM_DURATIONS in cogs/game_codes.py)
ITEM_DURATION_LABELS = {3600: "1h", 3 * 3600: "3h", 6 * 3600: "6h", 12 * 3600: "12h", 86400: "24h", 3 * 86400: "3d",
                        7 * 86400: "7d", 14 * 86400: "14d", 30 * 86400: "30d"}
MAX_TEXT = 200  # a name from the game, at most (the game checks it too)


def _int(value, default: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or abs(value) > 1e15:
        return default
    return int(value)


def _text(value, limit: int = MAX_TEXT) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _meta(item: dict) -> dict:
    """Who made an item in the game: {"origin", "by", "by_id"} from the item itself (events, eggs) or its meta (codes)."""
    return {"origin": "game" if item.get("origin") == "game" else "discord", "by": _text(item.get("by"), 40)}


# ---------- Codes ----------

def code_reward(row) -> dict:
    """A code as the game reads it (the same as the snapshot older versions sent)."""
    reward = {"expires_at": int(row["expires_at"] or 0)}
    if row["reward_currency"] and (row["currency_amount"] or 0) > 0:
        reward["currency"] = {"name": row["reward_currency"], "amount": int(row["currency_amount"])}
    if (row["exp_amount"] or 0) > 0:
        reward["exp"] = int(row["exp_amount"])
    if row["reward_item"]:
        reward["item"] = {"name": row["reward_item"], "is_temporary": bool(row["is_temporary_item"]),
                          "duration_seconds": int(row["item_duration_seconds"] or 0)}
    return reward


def clean_reward(reward) -> dict:
    """A reward from the game in the same shape as code_reward(), only the parts the bot knows."""
    reward = reward if isinstance(reward, dict) else {}
    clean = {"expires_at": max(0, _int(reward.get("expires_at")))}
    currency = reward.get("currency") if isinstance(reward.get("currency"), dict) else {}
    if _text(currency.get("name"), 100) and _int(currency.get("amount")) > 0:
        clean["currency"] = {"name": _text(currency.get("name"), 100), "amount": _int(currency.get("amount"))}
    if _int(reward.get("exp")) > 0:
        clean["exp"] = _int(reward.get("exp"))
    item = reward.get("item") if isinstance(reward.get("item"), dict) else {}
    if _text(item.get("name"), 100):
        temporary = item.get("is_temporary") is True
        clean["item"] = {"name": _text(item.get("name"), 100), "is_temporary": temporary,
                         "duration_seconds": max(0, _int(item.get("duration_seconds"))) if temporary else 0}
    return clean


def code_columns(code: str, reward: dict, meta: dict, now: int) -> dict:
    item = reward.get("item") or {}
    seconds = item.get("duration_seconds", 0) if item.get("is_temporary") else 0
    return {"code": code, "reward_currency": (reward.get("currency") or {}).get("name"),
            "currency_amount": (reward.get("currency") or {}).get("amount", 0), "exp_amount": reward.get("exp", 0),
            "reward_item": item.get("name"),
            "item_duration_label": ITEM_DURATION_LABELS.get(seconds, f"{seconds}s") if seconds else "permanent",
            "item_duration_seconds": seconds, "is_temporary_item": 1 if seconds else 0,
            "expires_at": reward.get("expires_at", 0), "is_active": 1, "origin": meta["origin"], "author": meta["by"],
            "pending": 0}


# ---------- Events and eggs ----------

def row_uid(kind: str, row) -> str:
    if kind == "codes":
        return str(row["code"])
    return str(row["uid"]) if row["uid"] else str(row["id"])


def _item_id(row):
    """The id an event or egg has in the game: its own number, or the id it came with ("g5")."""
    return row["uid"] if row["uid"] else row["id"]


def _json_list(text) -> list:
    try:
        value = json.loads(text or "[]")
    except (TypeError, ValueError):
        return []
    return value


def event_item(row) -> dict:
    item = {"id": _item_id(row), "name": row["name"], "multipliers": _json_list(row["multipliers"]) or {},
            "ends_at": int(row["ends_at"]), "starts_at": int(row["starts_at"] or 0)}
    if row["animation"]:
        item["animation"] = row["animation"]
    return item


def egg_item(row) -> dict:
    return {"id": _item_id(row), "name": row["name"], "currency": row["currency"], "price": int(row["price"]),
            "pets": _json_list(row["pets"]), "color": row["color"] or "", "spot": row["spot"] or "",
            "template": row["template"] or "", "ends_at": int(row["ends_at"] or 0)}


def clean_multipliers(value) -> dict:
    if not isinstance(value, dict):
        return {}
    return {str(k)[:110]: float(v) for k, v in value.items() if isinstance(v, (int, float)) and not isinstance(v, bool)
            and 0 < v <= 1000}


def clean_pets(value) -> list:
    pets = []
    for pet in value if isinstance(value, list) else []:
        if isinstance(pet, dict) and _text(pet.get("name"), 50) and isinstance(pet.get("chance"), (int, float)):
            pets.append({"name": _text(pet.get("name"), 50), "chance": float(pet["chance"])})
    return pets


def event_columns(item: dict, meta: dict, now: int) -> dict:
    return {"name": _text(item.get("name"), 50) or "?", "multipliers": json.dumps(clean_multipliers(item.get("multipliers"))),
            "starts_at": _int(item.get("starts_at")) or now, "ends_at": _int(item.get("ends_at")), "active": 1,
            "origin": meta["origin"], "author": meta["by"], "pending": 0, "animation": _text(item.get("animation"), 40)}


def egg_columns(item: dict, meta: dict, now: int) -> dict:
    return {"name": _text(item.get("name"), 40) or "?", "currency": _text(item.get("currency"), 100),
            "price": max(1, _int(item.get("price"), 1)), "pets": json.dumps(clean_pets(item.get("pets"))),
            "color": _text(item.get("color"), 20), "spot": _text(item.get("spot"), 100),
            "template": _text(item.get("template"), 50), "ends_at": max(0, _int(item.get("ends_at"))), "active": 1,
            "origin": meta["origin"], "author": meta["by"], "pending": 0}


# ---------- One kind: what is compared, how it is stored ----------

@dataclass
class Plan:
    imports: list = field(default_factory=list)  # column -> value of new rows
    updates: list = field(default_factory=list)  # (row key, column -> value)
    deactivate: list = field(default_factory=list)  # row keys
    done: list = field(default_factory=list)  # (row key, pending)
    puts: dict = field(default_factory=dict)  # uid -> item to save in the game
    deletes: set = field(default_factory=set)  # uids to take out of the game


def _empty_as_map(entry: dict, name: str) -> None:
    """Roblox saves an empty Lua table as [] (the game removed its last code): the same as {}."""
    if entry.get(name) == []:
        entry[name] = {}


def entry_items(kind: str, entry) -> dict:
    """uid -> item of an entry, in its order. A code's item is {"reward": ..., "meta": ...}."""
    entry = entry if isinstance(entry, dict) else {}
    if kind == "codes":
        _empty_as_map(entry, "codes")
        _empty_as_map(entry, "meta")
        codes = entry.get("codes") if isinstance(entry.get("codes"), dict) else {}
        meta = entry.get("meta") if isinstance(entry.get("meta"), dict) else {}
        return {str(code): {"reward": reward, "meta": meta.get(code) if isinstance(meta.get(code), dict) else {}}
                for code, reward in codes.items() if isinstance(reward, dict)}
    listed = entry.get(kind) if isinstance(entry.get(kind), list) else []
    return {str(item["id"]): item for item in listed if isinstance(item, dict) and item.get("id") not in (None, "")}


def expired(kind: str, item: dict, now: float) -> bool:
    if kind == "codes":
        ends = _int(item["reward"].get("expires_at"))
        return ends > 0 and ends <= now
    ends = _int(item.get("ends_at"))
    return ends <= now if kind == "events" else ends > 0 and ends <= now


def _row_active(kind: str, row) -> bool:
    return bool(row["is_active"] if kind == "codes" else row["active"])


def _row_key(kind: str, row):
    return row["code"] if kind == "codes" else row["id"]


def _same(kind: str, row, item: dict) -> bool:
    if kind == "codes":
        return code_reward(row) == clean_reward(item["reward"])
    if kind == "events":
        mine = event_item(row)
        return (mine["name"], clean_multipliers(mine["multipliers"]), mine["ends_at"], mine.get("animation", "")) == \
            (_text(item.get("name"), 50), clean_multipliers(item.get("multipliers")), _int(item.get("ends_at")),
             _text(item.get("animation"), 40))
    mine = egg_item(row)
    theirs = egg_columns(item, _meta(item), 0)
    return (mine["name"], mine["currency"], mine["price"], clean_pets(mine["pets"]), mine["color"], mine["spot"],
            mine["template"], mine["ends_at"]) == (theirs["name"], theirs["currency"], theirs["price"],
                                                   json.loads(theirs["pets"]), theirs["color"], theirs["spot"],
                                                   theirs["template"], theirs["ends_at"])


def _columns(kind: str, uid: str, item: dict, now: int) -> dict:
    if kind == "codes":
        meta = item["meta"] if isinstance(item.get("meta"), dict) else {}
        return code_columns(uid, clean_reward(item["reward"]), _meta(meta), now)
    meta = _meta(item)
    return event_columns(item, meta, now) if kind == "events" else egg_columns(item, meta, now)


def _new_item(kind: str, row, current) -> dict:
    """What the game gets for a row changed on Discord; fields only the game knows stay as they were."""
    if kind == "codes":
        meta = dict(current["meta"]) if current else {}
        meta["origin"] = row["origin"] or "discord"
        if row["author"]:
            meta["by"] = row["author"]
        return {"reward": code_reward(row), "meta": meta}
    item = dict(current) if current else {}
    item.update(event_item(row) if kind == "events" else egg_item(row))
    item["origin"] = row["origin"] or "discord"
    if row["author"]:
        item["by"] = row["author"]
    return item


def has_entry(kind: str, entry) -> bool:
    """The game has this entry (a missing or broken one never means "everything was removed")."""
    if isinstance(entry, dict) and kind == "codes":
        _empty_as_map(entry, "codes")
    return isinstance(entry, dict) and isinstance(entry.get(kind), dict if kind == "codes" else list)


def make_plan(kind: str, entry, rows, now: float) -> Plan:
    items = entry_items(kind, entry)
    by_uid = {row_uid(kind, row): row for row in rows}
    plan = Plan()
    for uid, item in items.items():
        if expired(kind, item, now):
            continue  # left out of the entry by the next save, never copied
        row = by_uid.get(uid)
        if row is None:
            columns = _columns(kind, uid, item, int(now))
            columns["created_by"] = 0
            if kind == "codes":
                columns["created_at"] = int(now)
            else:
                # a number is an id the bot gave (its database was lost or moved): the same id again when it is free
                columns["id" if uid.isdigit() else "uid"] = int(uid) if uid.isdigit() else uid
            plan.imports.append(columns)
        elif row["pending"]:
            continue  # changed on Discord: sent below
        elif not _row_active(kind, row) or not _same(kind, row, item):
            plan.updates.append((_row_key(kind, row), _columns(kind, uid, item, int(now))))
    missing = not has_entry(kind, entry)
    for row in rows:
        uid, key = row_uid(kind, row), _row_key(kind, row)
        ends = (row["expires_at"] if kind == "codes" else row["ends_at"]) or 0
        ended = ends <= now if kind == "events" else bool(ends) and ends <= now
        if row["pending"]:
            if _row_active(kind, row) and not ended:
                plan.puts[uid] = _new_item(kind, row, items.get(uid))
            else:
                plan.deletes.add(uid)
            plan.done.append((key, row["pending"]))
        elif _row_active(kind, row) and uid not in items:
            if missing and not ended:
                plan.puts[uid] = _new_item(kind, row, None)  # the game has no entry yet (or lost it): sent again
            else:
                plan.deactivate.append(key)  # removed (or ended) in the game
    return plan


def apply_plan(kind: str, entry, plan: Plan, now: float):
    """The entry with the plan applied and ended things left out, or None when nothing changes."""
    base = copy.deepcopy(entry) if isinstance(entry, dict) else {}
    items = entry_items(kind, base)
    changed = False
    for uid in plan.deletes:
        if items.pop(uid, None) is not None:
            changed = True
    for uid, item in plan.puts.items():
        if items.get(uid) != item:
            items[uid] = item
            changed = True
    for uid in [uid for uid, item in items.items() if expired(kind, item, now)]:
        del items[uid]
        changed = True
    if not changed:
        return None
    if kind == "codes":
        base["codes"] = {uid: item["reward"] for uid, item in items.items()}
        base["meta"] = {uid: item["meta"] for uid, item in items.items() if item.get("meta")}
    else:
        base[kind] = list(items.values())
        # the game's next id ("g<number>") stays above every id the entry has, also after the bot sent one back
        numbers = [int(uid[1:]) for uid in items if uid[:1] == "g" and uid[1:].isdigit()]
        if numbers:
            base["next_id"] = max(_int(base.get("next_id"), 1), max(numbers) + 1)
    base["version"] = max(ENTRY_VERSION, _int(base.get("version")))
    # ms: two saves in one second still differ; never older than the save before it (the game's clock may be ahead)
    before = base.get("updated_at") if isinstance(base.get("updated_at"), (int, float)) else 0
    base["updated_at"] = round(max(time.time(), before + 0.001), 3)
    return base


# ---------- The sync ----------

@dataclass
class Outcome:
    wrote: bool = False
    count: int = 0  # active things in the game now
    imported: int = 0  # made in the game, new here
    removed: int = 0  # removed in the game, ended here
    notify_error: str = ""


_locks = {}


def _lock(kind: str) -> asyncio.Lock:
    """One sync of a kind at a time (per running event loop: tests start a new loop for every test)."""
    loop = asyncio.get_running_loop()
    held = _locks.get(kind)
    if held is None or held[1] is not loop:
        held = (asyncio.Lock(), loop)
        _locks[kind] = held
    return held[0]


def location(kind: str) -> tuple:
    if kind == "codes":
        cfg = cloud_sync.settings()
        return cfg["datastore_name"], cfg["entry_key"]
    return open_cloud.live_settings()["datastore"], "Events" if kind == "events" else "Eggs"


async def _notify(kind: str, at: float) -> None:
    if kind == "codes":
        cfg = cloud_sync.settings()
        await open_cloud.messaging_publish(cloud_sync.universe_id(), cfg["topic"], {"type": "refresh", "at": at},
                                           t("sync.what_notify"))
    else:
        await open_cloud.publish({"type": kind, "at": at})


async def sync(kind: str, notify: bool = False) -> Outcome:
    """Makes the game and the database agree (see the top of this file). notify: tell the game servers to read again
    even when nothing was saved. Raises open_cloud.OpenCloudError (nothing in the database changes then)."""
    open_cloud.require_live()  # Game sync switched off: the game is never read or changed
    datastore, key = location(kind)
    what = t("sync.what_write") if kind == "codes" else t("cloud.what_write")
    async with _lock(kind):
        value, version = await open_cloud.read_entry_versioned(datastore, key)
        outcome = Outcome()
        for _ in range(MAX_TRIES):
            now = time.time()
            uids = list(entry_items(kind, value))
            plan = make_plan(kind, value, await database.sync_rows(kind, uids), now)
            new = apply_plan(kind, value, plan, now)
            if new is None:
                break
            try:
                await open_cloud.write_entry_if(datastore, key, new, version, what)
            except open_cloud.VersionConflict as conflict:
                value, version = conflict.value, conflict.version
                if value is None and version:  # the answer didn't carry the entry: read it
                    value, version = await open_cloud.read_entry_versioned(datastore, key)
                continue
            value, outcome.wrote = new, True
            break
        else:
            raise open_cloud.OpenCloudError(t("sync.busy"))
        for columns in plan.imports:
            if "id" in columns and await database.id_taken(kind, columns["id"]):
                columns["uid"] = str(columns.pop("id"))  # the number is taken here: kept as the game's id
        await database.apply_sync(kind, plan.imports, plan.updates, plan.deactivate, plan.done)
        outcome.imported, outcome.removed = len(plan.imports), len(plan.deactivate)
        outcome.count = sum(1 for item in entry_items(kind, value).values() if not expired(kind, item, time.time()))
        if outcome.wrote or notify:
            try:
                at = value.get("updated_at") if isinstance(value, dict) else None
                await _notify(kind, at if isinstance(at, (int, float)) else round(time.time(), 3))
            except open_cloud.OpenCloudError as e:
                outcome.notify_error = str(e)
        return outcome
