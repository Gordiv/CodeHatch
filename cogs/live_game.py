"""Live game content controlled from Discord: gifts for one player, on-screen announcements, multiplier events and eggs.
Everything goes into the game through Roblox Open Cloud (DataStore + MessagingService); the in-game "Live" module
(DiscordCodes.rbxmx) shows it on every server within seconds, without publishing the game."""
import asyncio
import json
import logging
import math
import re
import secrets
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.game_codes import ITEM_DURATIONS, MAX_AMOUNT, NONE, duration_label, made_in_game
from utils import action_log, catalog, cloud_sync, config_store, database, game_sync, open_cloud, roblox_api, roblox_kit
from utils.i18n import L, t

STATE_FILE = "live_sync_state.json"
ECONOMY_FILE = "game_economy.json"
MAX_EGGS = 20
MAX_PETS = 25
MAX_EVENTS = 10
MAX_PRICE = 1_000_000_000_000  # one limit for /egg-create, /egg-edit and the egg form in /setup-roblox
MAX_WEIGHT = 1_000_000_000
MAX_MULTIPLIER = 100  # same as CONFIG.MaxMultiplier in Live.luau
# Ready-made event times (the form's list and the /event-start suggestions); any other time can be typed (45m, 2h30m)
EVENT_DURATIONS = {"1m": 60, "5m": 5 * 60, "10m": 10 * 60, "20m": 20 * 60, "1h": 3600, "3h": 3 * 3600, "6h": 6 * 3600,
                   "12h": 12 * 3600, "24h": 86400, "3d": 3 * 86400, "7d": 7 * 86400}
MIN_EVENT_SECONDS, MAX_EVENT_SECONDS = 60, 30 * 86400
SHORT_EVENT_SECONDS = 5 * 60
START_COUNTDOWN = 10  # an event starts this many seconds after it was made: every player sees its countdown  # shorter events get a note when the game is tested in Studio
# Units of a typed time (EN, PL, ES); a number without a unit means minutes
DURATION_UNITS = {**dict.fromkeys(("m", "min", "mins", "minute", "minutes", "minuta", "minutę", "minuty", "minut",
                                   "minuto", "minutos"), 60),
                  **dict.fromkeys(("h", "hr", "hrs", "hour", "hours", "g", "godz", "godzina", "godzinę", "godziny", "godzin",
                                   "hora", "horas"), 3600),
                  **dict.fromkeys(("d", "day", "days", "dzien", "dzień", "dni", "dia", "día", "dias", "días"), 86400),
                  **dict.fromkeys(("w", "wk", "week", "weeks", "tyg", "tydz", "tydzien", "tydzień", "tygodnie", "tygodni",
                                   "semana", "semanas"), 7 * 86400)}
DURATION_JOINERS = {"i", "y", "and", "oraz", "+", "&"}  # "2h i 30m", "1 hora y 30 minutos"
_DURATION_PART = re.compile(r"(\d{1,6}(?:[.,]\d{1,3})?)(?!\d)([^\W\d_]*)\.?")
EGG_DURATIONS = {"24h": 86400, "3d": 3 * 86400, "7d": 7 * 86400, "14d": 14 * 86400, "30d": 30 * 86400, "unlimited": 0}
MULTIPLIERS = ["1.5", "2", "3", "5", "10"]
# The event animations the game has (scripts/DiscordCodes/Effects.luau; a test keeps the three lists equal)
ANIMATIONS = ["coin_storm", "aurora", "lucky_breeze", "meteor_shower", "sakura_festival"]
ANNOUNCE_SECONDS = [5, 10, 15, 30, 60]
ALL_CURRENCIES = "*"
EGG_COLORS = {"white": "#F5F5F5", "red": "#E74C3C", "orange": "#F39C12", "yellow": "#F1C40F", "green": "#2ECC71",
              "blue": "#3498DB", "purple": "#9B59B6", "pink": "#FF79C6", "black": "#2C2F33", "gold": "#FFD700",
              "rainbow": "rainbow"}
# "Dragon: 5" or "Dragon=5%". The ":" or "=" is required, so a pet called "Robot 2000" is never read as "Robot" with 2000
PET_RE = re.compile(r"^(.+?)\s*[:=]\s*(\d{1,12}(?:[.,]\d{1,10})?)\s*%?$")  # 10 decimals: as the catalog writes them

log = logging.getLogger("live_game")
_egg_names = {"lock": None, "loop": None}  # a new egg or a new egg name: checked and saved in one step


def _egg_names_lock() -> asyncio.Lock:
    """One lock per running event loop (the bot has one; tests start a new loop for every test)."""
    loop = asyncio.get_running_loop()
    if _egg_names["lock"] is None or _egg_names["loop"] is not loop:
        _egg_names.update(lock=asyncio.Lock(), loop=loop)
    return _egg_names["lock"]


class RuleError(Exception):
    pass


class LinkError(RuleError):
    """An announcement with a link (Roblox would show every player only ####): the form offers ✏️ Fix and Send anyway."""


class NothingToChange(RuleError):
    """egg_changes(): the given values are the egg's own (the egg panel then shows the egg with its menus)."""


# ---------- Rules (pure functions, tested separately) ----------

def parse_pets(text: str) -> list:
    """'Cat:60, Dog:30, Dragon:1' -> [{'name': 'Cat', 'chance': 65.934...}, ...] with chances turned into percentages.
    "egg:Basic Egg" (a suggestion of /egg-create) means the pets and chances of that egg from the game catalog."""
    text = catalog.expand_preset(text)
    pets, seen = [], set()
    # "0,5" is a decimal number (Polish/Spanish style), not two separate entries
    text = re.sub(r"(\d),(\d)", r"\1.\2", text or "")
    for part in re.split(r"[,;\n]", text):
        part = part.strip()
        if not part:
            continue
        match = PET_RE.match(part)
        if not match:
            raise RuleError(t("eggs.err_pet_format", part=part[:60]))
        name, weight = match.group(1).strip()[:50], float(match.group(2).replace(",", "."))
        if not name or not math.isfinite(weight) or weight <= 0 or weight > MAX_WEIGHT:
            raise RuleError(t("eggs.err_pet_format", part=part[:60]))
        if name.lower() in seen:
            raise RuleError(t("eggs.err_pet_duplicate", name=name))
        seen.add(name.lower())
        pets.append({"name": name, "weight": weight})
    if not pets:
        raise RuleError(t("eggs.err_no_pets"))
    if len(pets) > MAX_PETS:
        raise RuleError(t("eggs.err_too_many_pets", max=MAX_PETS))
    total = sum(p["weight"] for p in pets)
    # never rounded down to 0: a pet that has a chance must be able to drop (the game skips chance 0)
    return [{"name": p["name"], "chance": max(round(p["weight"] * 100 / total, 4), 0.0001)} for p in pets]


# Roblox (paid random items): a chance may be rounded only to four or more decimal places below its first non-zero
# digit, and rounded odds need this sentence (the same rule as on the egg's stand in the game)
ROUNDED_NOTE = "Probabilities are rounded; total of displayed individual probabilities may not equal 100%."


def chance_text(chance: float) -> str:
    return chance_parts(chance)[0]


def chance_parts(chance: float) -> tuple:
    """(text, rounded) of a chance in %: 33.3333 -> ("33.333%", True), 60 -> ("60%", False)."""
    chance = float(chance or 0)
    if chance <= 0:
        return "0%", False
    decimals = max(0, 4 - math.floor(math.log10(chance)))
    text = f"{chance:.{decimals}f}"
    rounded = abs(float(text) - chance) > 1e-9
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text + "%", rounded


def egg_gone(row) -> bool:
    """Removed or expired: such an egg is not in the game any more and can't be changed."""
    return not row or not row["active"] or bool(row["ends_at"] and row["ends_at"] <= time.time())


def build_multipliers(currency: str, currency_multiplier: str, exp_multiplier: str, luck_multiplier: str) -> dict:
    result = {}
    if currency_multiplier:
        key = ALL_CURRENCIES if not currency or currency == NONE else currency
        result[f"currency:{key}"] = float(currency_multiplier)
    if exp_multiplier:
        result["exp"] = float(exp_multiplier)
    if luck_multiplier:
        result["luck"] = float(luck_multiplier)
    return result


def multipliers_text(multipliers: dict) -> str:
    parts = []
    for key, value in multipliers.items():
        x = f"{value:g}×"
        if key == "exp":
            parts.append(t("events.mult_exp", x=x))
        elif key == "luck":
            parts.append(t("events.mult_luck", x=x))
        elif key == f"currency:{ALL_CURRENCIES}":
            parts.append(t("events.mult_all", x=x))
        else:
            parts.append(t("events.mult_currency", x=x, currency=key.split(":", 1)[1]))
    return ", ".join(parts)


def build_reward(currency: str, amount: int, exp: int, item: str, item_key: str) -> dict:
    reward = {}
    if currency and currency != NONE and amount > 0:
        reward["currency"] = {"name": currency, "amount": int(amount)}
    if exp > 0:
        reward["exp"] = int(exp)
    if item and item != NONE:
        seconds, temporary = ITEM_DURATIONS.get(item_key or "permanent", (0, 0))
        reward["item"] = {"name": item, "is_temporary": bool(temporary), "duration_seconds": seconds}
    return reward


def reward_text(reward: dict, show_permanent: bool = False) -> str:
    """show_permanent: also "(permanent)" after an item (a draft, where the time can still be changed)."""
    lines = []
    if "currency" in reward:
        lines.append(f"💰 **{reward['currency']['amount']:,}** {reward['currency']['name']}")
    if "exp" in reward:
        lines.append(f"⭐ **+{reward['exp']:,}** EXP")
    if "item" in reward:
        seconds = reward["item"]["duration_seconds"]
        key = next((k for k, v in ITEM_DURATIONS.items() if v[0] == seconds and v[1]), None)  # a time from the game may differ
        suffix = f" ({duration_label(key) if key else f'{seconds // 60} min'})" \
            if reward["item"]["is_temporary"] else (f" ({t('codes.permanent')})" if show_permanent else "")
        lines.append(f"🎁 **{reward['item']['name']}**{suffix}")
    return "\n".join(lines)


def events_snapshot(rows) -> dict:
    return {"version": 1, "events": [{"id": r["id"], "name": r["name"], "multipliers": json.loads(r["multipliers"]),
                                      "ends_at": int(r["ends_at"])} for r in rows]}


def eggs_snapshot(rows) -> dict:
    return {"version": 1, "eggs": [{"id": r["id"], "name": r["name"], "currency": r["currency"], "price": int(r["price"]),
                                    "pets": json.loads(r["pets"]), "color": r["color"] or "", "spot": r["spot"] or "",
                                    "template": r["template"] or "", "ends_at": int(r["ends_at"] or 0)} for r in rows]}


# ---------- Sending to the game ----------

async def push_live(kind: str) -> tuple:
    """Makes the events or eggs in the game and in the bot's database agree (utils/game_sync.py): what was changed here
    goes to the game, what the game's ⚙️ Manager made or removed comes here. Returns (ok, message). The game servers
    are told to read again ("at": the time of the save, the game reads again while Roblox serves an older copy)."""
    universe = cloud_sync.universe_id()
    state = config_store.read_json(STATE_FILE, {})
    try:
        await game_sync.sync(kind)
    except open_cloud.OpenCloudError as e:
        state[kind] = {"universe": universe, "error": str(e), "at": int(time.time())}
        config_store.write_json(STATE_FILE, state)
        return False, str(e)
    state[kind] = {"universe": universe, "error": "", "at": int(time.time())}
    config_store.write_json(STATE_FILE, state)
    return True, ""


def sync_note(ok: bool, error: str) -> str:
    return t("live.sent") if ok else t("live.not_sent", error=error)


def _economy(key: str) -> list:
    """Names for suggestions: the game catalog first, then the names picked in /setup-roblox."""
    return catalog.names_for(key, config_store.read_json(ECONOMY_FILE, {}).get(key, []))


def _color() -> int:
    return config_store.embed_color()


def combined_multipliers(rows) -> dict:
    """What the game applies right now: active events multiply each other, up to MAX_MULTIPLIER."""
    total = {}
    for row in rows:
        for key, value in json.loads(row["multipliers"]).items():
            total[key] = min(MAX_MULTIPLIER, total.get(key, 1) * float(value))
    return total


def check_egg_name(name: str, active, egg_id: int = None) -> str:
    """The egg's name, or RuleError when it is empty or another active egg has it."""
    name = (name or "").strip()
    if not name:
        raise RuleError(t("eggs.err_fields"))
    if any(r["name"].lower() == name.lower() and r["id"] != egg_id for r in active):
        raise RuleError(t("eggs.err_exists", name=name))
    return name


def _choices(names: list, current: str, extra=None):
    result = [app_commands.Choice(name=n[:100], value=n) for n in names if current.lower() in n.lower()]
    return (([extra] if extra else []) + result)[:25]


def warnings_text(warnings: list) -> str:
    return "\n".join(f"⚠️ {w}" for w in warnings)


def _with_kit_warning(note: str) -> str:
    """The note under a saved egg or event, with the line about an old DiscordCodes file in the game (eggs and events
    need a current one: "sent to the game" alone would look like a bug)."""
    return "\n".join(part for part in (note, roblox_kit.live_file_warning()) if part)


# Roblox's filter shows a whole text with a link as #### in the game, not only the link (published game, 2026-10-17)
# (a domain with a path like youtu.be/abc, or a known ending like roblox.com; "Awww." or "v1.2" are not links). Endings
# that are also words ("Super.To nowy event", "Wow.Co nowego?", "event.Fun") count only with a path.
_LINK = re.compile(r"https?://|\bwww\.\w|discord\s*\.\s*gg/|\b[\w-]+\.[a-z]{2,}/|\b[\w-]+\.(?:com|net|org|gg|io|xyz|pl|ru|de"
                   r"|tv|ly|link|app|dev|uk|es|fr|info|site|online|shop|store|ee|gl|eu|tk|cc|mx|ar|cl|pe)\b", re.IGNORECASE)


def has_link(text: str) -> bool:
    return bool(_LINK.search(text or ""))


def event_seconds(text: str) -> int:
    """Seconds of an event: a ready-made key (1h) or a typed time (45m, 2h30m, 1,5 h, 3 dni; 90 = 90 minutes), rounded to
    whole minutes. Raises RuleError with examples for the admin."""
    raw = (text or "").strip()
    words = [w.rstrip(",+") for w in raw.lower().split()]
    compact = "".join(w for w in words if w and w not in DURATION_JOINERS)
    if compact in EVENT_DURATIONS:
        return EVENT_DURATIONS[compact]
    total, pos = 0.0, 0
    while pos < len(compact):
        match = _DURATION_PART.match(compact, pos)
        if not match or match.group(2) and match.group(2) not in DURATION_UNITS:
            total, pos = 0.0, 0
            break
        total += float(match.group(1).replace(",", ".")) * DURATION_UNITS.get(match.group(2), 60)
        pos = match.end()
    seconds = int(total / 60 + 0.5) * 60
    if not compact or not MIN_EVENT_SECONDS <= seconds <= MAX_EVENT_SECONDS:
        shown = discord.utils.escape_mentions(discord.utils.escape_markdown(raw[:30]))
        raise RuleError(t("events.err_duration", text=shown))
    return seconds


def event_duration_text(seconds: int) -> str:
    """⏱️ 1 d 2 h 30 min, in the bot's language."""
    days, rest = divmod(int(seconds), 86400)
    hours, minutes = rest // 3600, rest % 3600 // 60
    parts = [t(f"duration.n_{unit}", n=n) for unit, n in (("days", days), ("hours", hours), ("minutes", minutes)) if n]
    return "⏱️ " + " ".join(parts or [t("duration.n_minutes", n=0)])


def error_text(error: Exception) -> str:
    text = str(error)
    return text if text.startswith(("❌", "⚠️", "ℹ️")) else f"❌ {text}"


# ---------- Actions shared by the slash commands and the /setup-roblox panels ----------

def egg_embed(title: str, egg: dict) -> discord.Embed:
    embed = discord.Embed(title=title, color=_color())
    embed.add_field(name=t("eggs.price"), value=f"**{egg['price']:,}** {egg['currency']}", inline=True)
    embed.add_field(name=t("eggs.available"), value=f"<t:{egg['ends_at']}:R>" if egg["ends_at"] else t("codes.unlimited"),
                    inline=True)
    if egg.get("spot"):
        embed.add_field(name=t("eggs.spot"), value=egg["spot"], inline=True)
    pets = sorted(egg["pets"], key=lambda p: -p["chance"])
    parts = [chance_parts(p["chance"]) for p in pets]
    lines = "\n".join(f"• {p['name']} — **{text}**" for p, (text, _) in zip(pets, parts))
    if any(rounded for _, rounded in parts):
        lines = lines[:1024 - len(ROUNDED_NOTE) - 3] + f"\n-# {ROUNDED_NOTE}"
    embed.add_field(name=t("eggs.pets"), value=lines[:1024], inline=False)
    return embed


def check_egg_names(currency: str, pets: list) -> tuple:
    """The egg's currency and pets in the game catalog's spelling. Raises RuleError for a name the catalog doesn't have
    (a typo would make an egg that can't give its pet)."""
    cat = catalog.game_catalog()
    currency, error = catalog.resolve("currencies", currency, cat)
    errors, checked = [error], []
    for pet in pets:
        name, error = catalog.resolve("pets", pet["name"], cat)
        errors.append(error)
        checked.append(dict(pet, name=name))
    message = catalog.error_message(errors)
    if message:
        raise RuleError(message)
    return currency, checked


def check_limit(reward: dict) -> None:
    """Raises RuleError when the currency is above the game's limit (Settings -> MaxCurrencyPerCode): the game would
    keep such a gift waiting forever. The gift draft only warns about it, sending is refused."""
    error = roblox_kit.limit_error(roblox_kit.game_scan(), reward)
    if error:
        raise RuleError(error)


def check_reward(reward: dict) -> dict:
    """The reward with names in the game catalog's spelling. Raises RuleError for a name the catalog doesn't have."""
    cat = catalog.game_catalog()
    errors = []
    if "currency" in reward:
        reward["currency"]["name"], error = catalog.resolve("currencies", reward["currency"]["name"], cat)
        errors.append(error)
    if "item" in reward:
        reward["item"]["name"], error = catalog.resolve("reward_item", reward["item"]["name"], cat)
        errors.append(error)
    message = catalog.error_message(errors)
    if message:
        raise RuleError(message)
    return reward


def pets_warning(pets: list) -> str:
    known = {p.lower() for p in _economy("pets") + _economy("items")}
    unknown = [p["name"] for p in pets if known and p["name"].lower() not in known]
    return t("eggs.unknown_pets", pets=", ".join(unknown)) if unknown else ""


async def create_egg(name: str, currency: str, price: int, pets_text: str, color: str = "white", duration: str = "unlimited",
                     spot: str = "", template: str = "", author_id: int = 0) -> discord.Embed:
    """Checks, saves and sends a new egg to the game. Raises RuleError with a message for the admin."""
    name, currency = name.strip(), currency.strip()
    if not name or not currency or price < 1:
        raise RuleError(t("eggs.err_fields"))
    if price > MAX_PRICE:
        raise RuleError(t("eggs.err_price", max=f"{MAX_PRICE:,}"))
    pet_list = parse_pets(pets_text)
    currency, pet_list = check_egg_names(currency, pet_list)
    async with _egg_names_lock():  # the limit and the name are checked again right before saving
        active = await database.get_active_eggs()
        if len(active) >= MAX_EGGS:
            raise RuleError(t("eggs.err_too_many", max=MAX_EGGS))
        name = check_egg_name(name, active)
        seconds = EGG_DURATIONS.get(duration or "unlimited", 0)
        egg = {"name": name, "currency": currency, "price": int(price), "pets": pet_list,
               "color": EGG_COLORS.get(color or "white", EGG_COLORS["white"]), "spot": spot.strip(),
               "template": template.strip(), "ends_at": int(time.time()) + seconds if seconds else 0}
        await database.add_egg(egg["name"], egg["currency"], egg["price"], json.dumps(pet_list), egg["color"], egg["spot"],
                               egg["template"], egg["ends_at"], author_id)
    ok, error = await push_live("eggs")
    embed = egg_embed(t("eggs.created_title", name=egg["name"]), egg)
    scan = roblox_kit.game_scan()
    notes = [pets_warning(pet_list)] + roblox_kit.egg_warnings(scan, currency, [p["name"] for p in pet_list])
    notes.append(roblox_kit.spots_warning(scan, len(await database.get_active_eggs())))
    if (color or "white") != "white":  # the default white is never a choice worth a note
        notes.append(roblox_kit.color_warning(scan, egg["template"]))
    note = _with_kit_warning(warnings_text([n for n in notes if n]))
    embed.add_field(name=t("codes.sync_field"), value=(sync_note(ok, error) + ("\n" + note if note else ""))[:1024], inline=False)
    return embed


async def egg_changes(egg_id: int, name: str = None, currency: str = None, price: int = None, pets_text: str = None,
                      color: str = None, duration: str = None, spot: str = None, template: str = None) -> dict:
    """The checked changes of an active egg (only what is given and differs). Quick (no Roblox call), so a command can
    still refuse privately within Discord's 3 seconds. Raises RuleError with a message for the admin. Used by
    /egg-edit and by the egg panel in /setup-roblox, so both check the same things."""
    row = await database.get_egg(egg_id) if egg_id else None
    if egg_gone(row):
        raise RuleError(t("eggs.not_found"))  # an expired egg is gone (changing it would bring it back past the limits)
    changes = {}
    if pets_text is not None:
        changes["pets"] = json.dumps(parse_pets(pets_text))
    if name is not None:
        changes["name"] = check_egg_name(name, await database.get_active_eggs(), egg_id)
    if currency is not None:
        if not currency.strip():
            raise RuleError(t("eggs.err_fields"))
        changes["currency"] = currency.strip()
    if price is not None:
        if not 1 <= int(price) <= MAX_PRICE:
            raise RuleError(t("eggs.err_price", max=f"{MAX_PRICE:,}") if price > MAX_PRICE else t("eggs.err_fields"))
        changes["price"] = int(price)
    if color is not None:
        changes["color"] = EGG_COLORS[color]
    if duration is not None:
        seconds = EGG_DURATIONS[duration]
        changes["ends_at"] = int(time.time()) + seconds if seconds else 0
    if spot is not None:
        changes["spot"] = spot.strip()[:30]
    if template is not None:
        changes["template"] = template.strip()[:50]
    if "pets" in changes or "currency" in changes:
        checked_currency, checked_pets = check_egg_names(changes.get("currency", row["currency"]),
                                                         json.loads(changes.get("pets", row["pets"])))
        if "currency" in changes:
            changes["currency"] = checked_currency
        if "pets" in changes:
            changes["pets"] = json.dumps(checked_pets)
    changes = {key: value for key, value in changes.items() if value != row[key]}
    if not changes:
        raise NothingToChange(t("eggs.nothing_to_change"))
    return changes


async def save_egg_changes(egg_id: int, changes: dict) -> discord.Embed:
    """Saves checked changes (egg_changes), sends the eggs to the game and returns the answer for the admin."""
    async with _egg_names_lock():
        if "name" in changes:  # another egg may have taken this name since the check
            check_egg_name(changes["name"], await database.get_active_eggs(), egg_id)
        if not await database.update_egg(egg_id, **changes):
            raise RuleError(t("eggs.not_found"))  # removed in the very moment between the check and the save
    ok, error = await push_live("eggs")
    updated = eggs_snapshot([await database.get_egg(egg_id)])["eggs"][0]
    embed = egg_embed(t("eggs.edited_title", name=updated["name"]), updated)
    scan, notes = roblox_kit.game_scan(), []
    if "pets" in changes or "currency" in changes:
        notes += roblox_kit.egg_warnings(scan, updated["currency"], [p["name"] for p in updated["pets"]])
    if ("color" in changes or "template" in changes) and updated["color"] not in ("", EGG_COLORS["white"]):
        notes.append(roblox_kit.color_warning(scan, updated["template"]))  # the white default is never worth a note
    note = _with_kit_warning(warnings_text([n for n in notes if n]))
    embed.add_field(name=t("codes.sync_field"), value=(sync_note(ok, error) + ("\n" + note if note else ""))[:1024], inline=False)
    return embed


async def edit_egg(egg_id: int, **fields) -> discord.Embed:
    """egg_changes() and save_egg_changes() in one go."""
    return await save_egg_changes(egg_id, await egg_changes(egg_id, **fields))


def pets_text(row) -> str:
    """A stored egg's pets as the text the egg form takes ("Cat:60, Dog:35"): to change it, not to type it again."""
    try:
        pets = json.loads(row["pets"])
    except (TypeError, ValueError):
        return ""
    return ", ".join(f"{p['name']}:{float(p['chance']):.6g}" for p in pets if isinstance(p, dict) and p.get("name"))


def color_key(row) -> str:
    """The name of a stored egg's color ("white" when it isn't one of the colors)."""
    return next((key for key, value in EGG_COLORS.items() if value == row["color"]), "white")


def animation_name(key: str) -> str:
    return t(f"events.anim.{key}") if key in ANIMATIONS else ""


async def start_event(name: str, duration: str, multipliers: dict, author_id: int = 0, with_id: bool = False,
                      animation: str = ""):
    """Saves and sends a multiplier event; returns the answer for the admin (and the event's id with with_id). Raises
    RuleError with a message for the admin."""
    seconds = event_seconds(duration)
    if not multipliers:
        raise RuleError(t("events.no_multiplier"))
    currencies = [key for key in multipliers if key.startswith("currency:")]
    if f"currency:{ALL_CURRENCIES}" in currencies and len(currencies) > 1:
        # the game multiplies both for that currency: "all ×2" with "Coins ×2" would give Coins ×4
        raise RuleError(t("events.err_all_and_one"))
    errors = []
    for key in list(multipliers):
        if key.startswith("currency:") and key != f"currency:{ALL_CURRENCIES}":
            currency, error = catalog.resolve("currencies", key.split(":", 1)[1])
            errors.append(error)
            multipliers[f"currency:{currency}"] = multipliers.pop(key)
    message = catalog.error_message(errors)
    if message:
        raise RuleError(message)
    if len(await database.get_active_live_events()) >= MAX_EVENTS:
        raise RuleError(t("events.err_too_many", max=MAX_EVENTS))
    name = name.strip()
    if not name:
        raise RuleError(t("events.err_name"))
    now = int(time.time()) + START_COUNTDOWN  # the players see a countdown first (the same in the game's Manager)
    ends_at = now + seconds
    if animation and animation not in ANIMATIONS:
        raise RuleError(t("events.err_animation"))
    event_id = await database.add_live_event(name, json.dumps(multipliers), now, ends_at, author_id, animation)
    ok, error = await push_live("events")
    embed = discord.Embed(title=t("events.started_title", name=name), color=discord.Color.gold(),
                          description=multipliers_text(multipliers))
    embed.add_field(name=t("events.starts"), value=f"<t:{now}:R>", inline=True)
    embed.add_field(name=t("events.duration"), value=event_duration_text(seconds), inline=True)
    embed.add_field(name=t("events.ends"), value=f"<t:{ends_at}:R>", inline=True)
    if animation:
        embed.add_field(name=t("events.animation"), value=animation_name(animation), inline=True)
    declared = catalog.names(catalog.game_catalog(), "multipliers")
    scan = roblox_kit.game_scan()
    notes = list(roblox_kit.event_warnings(scan, multipliers, declared))
    if seconds < SHORT_EVENT_SECONDS and (scan or {}).get("studio"):
        # Studio Play gets no notifications: it reads the events every 60 s, so a 1-minute event may never show there
        notes.append(t("events.short_in_studio"))
    note = _with_kit_warning(warnings_text(notes))
    embed.add_field(name=t("codes.sync_field"), value=(sync_note(ok, error) + ("\n" + note if note else ""))[:1024], inline=False)
    return (embed, event_id) if with_id else embed


async def find_player(player, by_id: bool = False) -> tuple:
    """(user_id, username) of the player a gift goes to. Raises RuleError with a message for the admin.
    player: a username, or (user_id, username) from the player card. by_id: the text may also be a Roblox user ID (the
    gift form and /give); a number that means two different accounts is refused instead of guessed."""
    if isinstance(player, tuple):
        return player
    try:
        if by_id:
            found = await roblox_api.find_users(player)
            if len(found) > 1:
                raise RuleError(t("give.ambiguous", player=discord.utils.escape_markdown(player.strip())))
            user = found[0][:2] if found else None
        else:
            user = await roblox_api.resolve_user(player)
    except roblox_api.RobloxApiError as e:
        raise RuleError(str(e))
    if not user:
        raise RuleError(t("card.not_found", player=discord.utils.escape_markdown(player.strip())) if by_id
                        else t("verify.user_not_found", username=player))
    return user


async def send_gift(player, reward: dict, message: str, author_name: str, author_id: int, by_id: bool = False) -> discord.Embed:
    """Sends a gift to one player (delivered when they join if offline). Raises RuleError with a message for the admin.
    player and by_id: see find_player."""
    if not reward:
        raise RuleError(t("give.no_reward"))
    reward = check_reward(reward)
    check_limit(reward)
    user_id, username = await find_player(player, by_id)
    key = f"gift_{user_id}_{int(time.time())}{secrets.token_hex(2)}"
    try:  # a RuleError from here on means nothing reached the game, so sending again is safe
        await open_cloud.write_entry(open_cloud.live_settings()["gifts"], key, {
            "reward": reward, "message": message, "from": author_name, "created_at": int(time.time())})
    except open_cloud.OpenCloudError as e:
        raise RuleError(t("live.failed", error=e))
    not_notified = ""
    try:  # the gift is saved: without the notice the player still gets it at the next join
        await open_cloud.publish({"type": "gift", "user_id": user_id})
    except open_cloud.OpenCloudError as e:
        not_notified = t("give.not_notified", error=e)
    await database.add_gift(key, user_id, username, json.dumps(reward), message, author_id)
    embed = discord.Embed(title=t("give.title"), color=discord.Color.green(), description=t("give.description", username=username))
    embed.add_field(name=t("codes.rewards"), value=reward_text(reward), inline=False)
    if message:
        embed.add_field(name=t("give.message"), value=message, inline=False)
    warnings = (roblox_kit.reward_warnings(roblox_kit.game_scan(), reward) + catalog.robux_warnings(reward, gift=True)
                + ([t("give.link_warning")] if has_link(message) else []))
    note = "\n".join(n for n in (not_notified, warnings_text(warnings)) if n)
    if note:
        embed.add_field(name=t("scan.check_title"), value=note[:1024], inline=False)
    embed.set_thumbnail(url=f"https://www.roblox.com/headshot-thumbnail/image?userId={user_id}&width=150&height=150&format=png")
    embed.set_footer(text=t("give.footer", user=author_name))
    return embed


async def announce(text: str, seconds: int = 10, allow_link: bool = False) -> str:
    """Shows a message on every player's screen. Raises RuleError with a message for the admin; LinkError when the text
    has a link (allow_link: "Send anyway" after the admin saw the warning, e.g. the check took a game name for a link)."""
    if has_link(text) and not allow_link:  # every player would see only ####: refused, with the text to copy and fix
        raise LinkError(t("announce.err_link", text=text.strip().replace("`", "'")))
    try:
        await open_cloud.publish({"type": "announce", "text": text.strip(), "seconds": seconds})
    except open_cloud.OpenCloudError as e:
        raise RuleError(t("live.failed", error=e))
    return t("announce.sent", text=text.strip())


class LiveGame(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.failures = {}
        self.sync_loop.start()

    def cog_unload(self):
        self.sync_loop.cancel()

    # Every 2 minutes: what the game's ⚙️ Manager changed comes here, failed sends are tried again, ended events
    # and eggs leave the game
    @tasks.loop(minutes=2)
    async def sync_loop(self):
        if cloud_sync.status() != "ready":
            return
        for kind in ("events", "eggs"):
            try:
                ok, error = await push_live(kind)
            except Exception as e:  # e.g. the database is busy for a moment: never stop the loop for good
                ok, error = False, str(e)
            if not ok:
                self.failures[kind] = self.failures.get(kind, 0) + 1
                # Written to the log after the 1st, 2nd, 4th, 8th... failure in a row, not every 2 minutes
                if self.failures[kind] & (self.failures[kind] - 1) == 0:
                    log.warning("Could not send %s to the game (%s attempt(s)): %s", kind, self.failures[kind], error)
            else:
                self.failures[kind] = 0

    @sync_loop.before_loop
    async def before_sync_loop(self):
        await self.bot.wait_until_ready()

    async def currency_autocomplete(self, interaction: discord.Interaction, current: str):
        return _choices(_economy("currencies"), current)

    async def event_currency_autocomplete(self, interaction: discord.Interaction, current: str):
        return _choices(_economy("currencies"), current, app_commands.Choice(name=t("events.all_currencies"), value=ALL_CURRENCIES))

    async def item_autocomplete(self, interaction: discord.Interaction, current: str):
        eco = config_store.read_json(ECONOMY_FILE, {})
        return _choices(catalog.reward_names(eco.get("items", []), eco.get("pets", [])), current,
                        app_commands.Choice(name=t("codes.none_option"), value=NONE))

    async def event_duration_autocomplete(self, interaction: discord.Interaction, current: str):
        """The ready-made times that fit what is typed, and first the typed time as the bot understood it when no
        ready-made time means the same (e.g. "45" -> ⏱️ 45 min; "24" -> ⏱️ 24 min and ⏱️ 24 hours)."""
        typed = current.strip()
        compact = re.sub(r"\s+", "", typed.lower())
        presets = [(key, seconds) for key, seconds in EVENT_DURATIONS.items()
                   if not compact or compact in key or compact in re.sub(r"\s+", "", t(f"duration.choice.{key}").lower())]
        choices = []
        try:
            seconds = event_seconds(typed) if typed else None
        except RuleError:
            seconds = None
        if seconds and seconds not in {s for _, s in presets}:
            choices.append(app_commands.Choice(name=event_duration_text(seconds)[:100], value=typed[:30]))
        choices += [app_commands.Choice(name=t(f"duration.choice.{key}")[:100], value=key) for key, _ in presets]
        return choices[:25]

    async def event_autocomplete(self, interaction: discord.Interaction, current: str):
        rows = await database.get_active_live_events()
        return [app_commands.Choice(name=f"{r['name']} (#{r['id']})"[:100], value=str(r["id"]))
                for r in rows if current.lower() in r["name"].lower()][:25]

    async def egg_autocomplete(self, interaction: discord.Interaction, current: str):
        rows = await database.get_active_eggs()
        return [app_commands.Choice(name=f"{r['name']} — {r['price']:,} {r['currency']}"[:100], value=str(r["id"]))
                for r in rows if current.lower() in r["name"].lower()][:25]

    # ---------- /give ----------
    @app_commands.command(name="give", description=L("cmd.give"))
    @app_commands.guild_only()
    @app_commands.describe(player=L("cmd.give.player"), currency=L("cmd.give.currency"), amount=L("cmd.give.amount"),
                           exp=L("cmd.give.exp"), item=L("cmd.give.item"), item_duration=L("cmd.give.item_duration"),
                           message=L("cmd.give.message"))
    @app_commands.choices(item_duration=[app_commands.Choice(name=L(f"duration.choice.{k}"), value=k) for k in ITEM_DURATIONS])
    @app_commands.autocomplete(currency=currency_autocomplete, item=item_autocomplete)
    async def give(self, interaction: discord.Interaction, player: app_commands.Range[str, 1, 25], currency: str = NONE,
                   amount: app_commands.Range[int, 0, MAX_AMOUNT] = 0, exp: app_commands.Range[int, 0, MAX_AMOUNT] = 0,
                   item: str = NONE, item_duration: app_commands.Choice[str] = None, message: app_commands.Range[str, 0, 150] = ""):
        reward = build_reward(currency, amount, exp, item, item_duration.value if item_duration else "permanent")
        if not reward:
            await interaction.response.send_message(t("give.no_reward"), ephemeral=True)
            return
        try:
            reward = check_reward(reward)
            check_limit(reward)  # refused privately, before anything is sent
        except RuleError as e:
            await interaction.response.send_message(error_text(e), ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        try:
            embed = await send_gift(player, reward, message, interaction.user.display_name, interaction.user.id, by_id=True)
        except RuleError as e:
            await interaction.followup.send(error_text(e))
            return
        await interaction.followup.send(embed=embed)
        await action_log.discord_action(interaction, "gift", embed)

    # ---------- /announce-game ----------
    @app_commands.command(name="announce-game", description=L("cmd.announce_game"))
    @app_commands.guild_only()
    @app_commands.describe(text=L("cmd.announce_game.text"), seconds=L("cmd.announce_game.seconds"))
    @app_commands.choices(seconds=[app_commands.Choice(name=f"{s} s", value=s) for s in ANNOUNCE_SECONDS])
    async def announce_game(self, interaction: discord.Interaction, text: app_commands.Range[str, 1, 200],
                            seconds: app_commands.Choice[int] = None):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            content = await announce(text, seconds.value if seconds else 10)
            await interaction.followup.send(content, ephemeral=True)
            await action_log.discord_action(interaction, "announce", content)
        except LinkError as e:  # not a link after all (e.g. a game name with a dot): the panel can send it anyway
            await interaction.followup.send(f"{e}\n{t('announce.link_hint_command')}", ephemeral=True)
        except RuleError as e:
            await interaction.followup.send(str(e), ephemeral=True)

    # ---------- events ----------
    @app_commands.command(name="event-start", description=L("cmd.event_start"))
    @app_commands.guild_only()
    @app_commands.describe(name=L("cmd.event_start.name"), duration=L("cmd.event_start.duration"),
                           currency=L("cmd.event_start.currency"), currency_multiplier=L("cmd.event_start.currency_multiplier"),
                           exp_multiplier=L("cmd.event_start.exp_multiplier"), luck_multiplier=L("cmd.event_start.luck_multiplier"),
                           animation=L("cmd.event_start.animation"))
    @app_commands.choices(currency_multiplier=[app_commands.Choice(name=f"{m}×", value=m) for m in MULTIPLIERS],
                          exp_multiplier=[app_commands.Choice(name=f"{m}×", value=m) for m in MULTIPLIERS],
                          luck_multiplier=[app_commands.Choice(name=f"{m}×", value=m) for m in MULTIPLIERS],
                          animation=[app_commands.Choice(name=L(f"events.anim.{a}"), value=a) for a in ANIMATIONS])
    @app_commands.autocomplete(currency=event_currency_autocomplete, duration=event_duration_autocomplete)
    async def event_start(self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 50],
                          duration: app_commands.Range[str, 1, 30], currency: str = ALL_CURRENCIES,
                          currency_multiplier: app_commands.Choice[str] = None, exp_multiplier: app_commands.Choice[str] = None,
                          luck_multiplier: app_commands.Choice[str] = None, animation: app_commands.Choice[str] = None):
        multipliers = build_multipliers(currency, currency_multiplier.value if currency_multiplier else "",
                                        exp_multiplier.value if exp_multiplier else "", luck_multiplier.value if luck_multiplier else "")
        if not multipliers:
            await interaction.response.send_message(t("events.no_multiplier"), ephemeral=True)
            return
        try:
            event_seconds(duration)  # a typed time the bot doesn't understand: only the admin sees the hint
        except RuleError as e:
            await interaction.response.send_message(error_text(e), ephemeral=True)
            return
        if currency not in (ALL_CURRENCIES, NONE) and currency_multiplier:
            _, error = catalog.resolve("currencies", currency)
            if error:
                await interaction.response.send_message(catalog.error_message([error]), ephemeral=True)
                return
        if len(await database.get_active_live_events()) >= MAX_EVENTS:
            await interaction.response.send_message(t("events.err_too_many", max=MAX_EVENTS), ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        try:
            embed = await start_event(name, duration, multipliers, interaction.user.id,
                                      animation=animation.value if animation else "")
        except RuleError as e:
            await interaction.followup.send(error_text(e))
            return
        await interaction.followup.send(embed=embed)
        await action_log.discord_action(interaction, "event_start", embed)

    @app_commands.command(name="event-stop", description=L("cmd.event_stop"))
    @app_commands.guild_only()
    @app_commands.describe(event=L("cmd.event_stop.event"))
    @app_commands.autocomplete(event=event_autocomplete)
    async def event_stop(self, interaction: discord.Interaction, event: str):
        if not event.isdigit() or not await database.stop_live_event(int(event)):
            await interaction.response.send_message(t("events.not_found"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        ok, error = await push_live("events")
        content = t("events.stopped") + "\n" + sync_note(ok, error)
        await interaction.followup.send(content, ephemeral=True)
        await action_log.discord_action(interaction, "event_stop", content)

    @app_commands.command(name="events", description=L("cmd.events"))
    @app_commands.guild_only()
    async def events(self, interaction: discord.Interaction):
        rows = await database.get_active_live_events()
        embed = discord.Embed(title=t("events.list_title"), color=_color())
        if not rows:
            embed.description = t("events.list_empty")
        else:
            embed.description = t("events.combined", multipliers=multipliers_text(combined_multipliers(rows)))[:4096]
        for r in rows[:MAX_EVENTS]:
            extra = [line for line in (animation_name(r["animation"]) and f"✨ {animation_name(r['animation'])}",
                                       made_in_game(r)) if line]
            embed.add_field(name=f"⚡ {r['name']}"[:256], value=(f"{multipliers_text(json.loads(r['multipliers']))}\n"
                            f"{t('events.ends')}: <t:{r['ends_at']}:R>" + "".join(f"\n{x}" for x in extra))[:1024],
                            inline=False)
        await interaction.response.send_message(embed=embed)

    # ---------- eggs ----------
    async def spot_autocomplete(self, interaction: discord.Interaction, current: str):
        scan = roblox_kit.game_scan()
        return _choices(scan["spots"] if scan else [], current)

    async def template_autocomplete(self, interaction: discord.Interaction, current: str):
        scan = roblox_kit.game_scan()
        return _choices(scan["templates"] if scan else [], current)

    async def pet_autocomplete(self, interaction: discord.Interaction, current: str):
        """Suggests the game's own eggs from the catalog (all their pets and chances at once) and pet names with their
        rarity (the part after the last comma is what is being typed)."""
        if len(current) > 80:  # a suggestion may be at most 100 characters long
            return []
        done, _, typing = current.rpartition(",")
        prefix = (done + ", ") if done else ""
        cat = catalog.game_catalog()
        # the game's eggs: the value is "egg:<name>", so an egg with many pets still fits the 100 characters
        presets = [] if done else [
            app_commands.Choice(name=t("catalog.preset", egg=egg, pets=text)[:100], value=f"{catalog.PRESET_PREFIX}{egg}")
            for egg, text, _, _ in catalog.egg_presets(cat)
            if len(catalog.PRESET_PREFIX + egg) <= 100 and typing.strip().lower() in (egg + " " + text).lower()]
        used = {p.split(":")[0].strip().lower() for p in done.split(",") if p.strip()}
        names = [p for p in _economy("pets") if p.lower() not in used and typing.strip().lower() in p.lower()]
        rarities = catalog.rarities(cat)
        choices = []
        for name in names[:24]:
            if len(prefix + name) < 99:
                rarity = rarities.get(catalog.key(name), "")
                label = (prefix + f"{name}:").strip() + (f"  · {rarity}" if rarity else "")
                choices.append(app_commands.Choice(name=label[-100:], value=prefix + f"{name}:"))
        head = [app_commands.Choice(name=current[-100:], value=current)] if current else []
        return (head + presets[:5] + choices)[:25]

    @app_commands.command(name="egg-create", description=L("cmd.egg_create"))
    @app_commands.guild_only()
    @app_commands.describe(name=L("cmd.egg_create.name"), currency=L("cmd.egg_create.currency"), price=L("cmd.egg_create.price"),
                           pets=L("cmd.egg_create.pets"), color=L("cmd.egg_create.color"), duration=L("cmd.egg_create.duration"),
                           spot=L("cmd.egg_create.spot"), template=L("cmd.egg_create.template"))
    @app_commands.choices(color=[app_commands.Choice(name=L(f"eggs.color.{c}"), value=c) for c in EGG_COLORS],
                          duration=[app_commands.Choice(name=L(f"duration.choice.{k}"), value=k) for k in EGG_DURATIONS])
    @app_commands.autocomplete(currency=currency_autocomplete, pets=pet_autocomplete, spot=spot_autocomplete,
                               template=template_autocomplete)
    async def egg_create(self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 40], currency: str,
                         price: app_commands.Range[int, 1, MAX_PRICE], pets: app_commands.Range[str, 1, 1000],
                         color: app_commands.Choice[str] = None, duration: app_commands.Choice[str] = None,
                         spot: app_commands.Range[str, 0, 30] = "", template: app_commands.Range[str, 0, 50] = ""):
        try:
            check_egg_names(currency, parse_pets(pets))
        except RuleError as e:
            await interaction.response.send_message(error_text(e), ephemeral=True)
            return
        active = await database.get_active_eggs()
        if len(active) >= MAX_EGGS or any(r["name"].lower() == name.strip().lower() for r in active):
            await interaction.response.send_message(
                t("eggs.err_too_many", max=MAX_EGGS) if len(active) >= MAX_EGGS else t("eggs.err_exists", name=name.strip()),
                ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        try:
            embed = await create_egg(name, currency, price, pets, color.value if color else "white",
                                     duration.value if duration else "unlimited", spot, template, interaction.user.id)
        except RuleError as e:
            await interaction.followup.send(error_text(e))
            return
        await interaction.followup.send(embed=embed)
        await action_log.discord_action(interaction, "egg_create", embed)

    @app_commands.command(name="egg-edit", description=L("cmd.egg_edit"))
    @app_commands.guild_only()
    @app_commands.describe(egg=L("cmd.egg_edit.egg"), name=L("cmd.egg_create.name"), currency=L("cmd.egg_create.currency"),
                           price=L("cmd.egg_create.price"), pets=L("cmd.egg_create.pets"), color=L("cmd.egg_create.color"),
                           duration=L("cmd.egg_edit.duration"), spot=L("cmd.egg_create.spot"), template=L("cmd.egg_create.template"))
    @app_commands.choices(color=[app_commands.Choice(name=L(f"eggs.color.{c}"), value=c) for c in EGG_COLORS],
                          duration=[app_commands.Choice(name=L(f"duration.choice.{k}"), value=k) for k in EGG_DURATIONS])
    @app_commands.autocomplete(egg=egg_autocomplete, currency=currency_autocomplete, pets=pet_autocomplete,
                               spot=spot_autocomplete, template=template_autocomplete)
    async def egg_edit(self, interaction: discord.Interaction, egg: str, name: app_commands.Range[str, 1, 40] = None,
                       currency: str = None, price: app_commands.Range[int, 1, MAX_PRICE] = None,
                       pets: app_commands.Range[str, 1, 1000] = None, color: app_commands.Choice[str] = None,
                       duration: app_commands.Choice[str] = None, spot: app_commands.Range[str, 0, 30] = None,
                       template: app_commands.Range[str, 0, 50] = None):
        egg_id = int(egg) if egg.isdigit() else 0
        try:
            changes = await egg_changes(egg_id, name=name, currency=currency, price=price, pets_text=pets,
                                        color=color.value if color else None,
                                        duration=duration.value if duration else None, spot=spot, template=template)
        except RuleError as e:
            await interaction.response.send_message(error_text(e), ephemeral=True)
            return
        await interaction.response.defer(thinking=True)  # sending to the game may take longer than Discord waits
        embed = await save_egg_changes(egg_id, changes)
        await interaction.followup.send(embed=embed)
        await action_log.discord_action(interaction, "egg_edit", embed)

    @app_commands.command(name="egg-remove", description=L("cmd.egg_remove"))
    @app_commands.guild_only()
    @app_commands.describe(egg=L("cmd.egg_edit.egg"))
    @app_commands.autocomplete(egg=egg_autocomplete)
    async def egg_remove(self, interaction: discord.Interaction, egg: str):
        row = await database.get_egg(int(egg)) if egg.isdigit() else None
        if not row or not await database.remove_egg(int(egg)):
            await interaction.response.send_message(t("eggs.not_found"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        ok, error = await push_live("eggs")
        content = t("eggs.removed", name=row["name"]) + "\n" + sync_note(ok, error)
        await interaction.followup.send(content, ephemeral=True)
        await action_log.discord_action(interaction, "egg_remove", content)

    @app_commands.command(name="eggs", description=L("cmd.eggs"))
    @app_commands.guild_only()
    async def eggs(self, interaction: discord.Interaction):
        rows = await database.get_active_eggs()
        if not rows:
            await interaction.response.send_message(embed=discord.Embed(title=t("eggs.list_title"), color=_color(),
                                                                        description=t("eggs.list_empty")))
            return
        embeds = []
        for row, egg in zip(rows, eggs_snapshot(rows)["eggs"]):
            embed = egg_embed(f"🥚 {egg['name']}"[:256], egg)
            if made_in_game(row):
                embed.set_footer(text=made_in_game(row))
            embeds.append(embed)
        # A message holds at most 10 embeds and 6000 characters in all of them together
        batches, batch, size = [], [], 0
        for embed in embeds:
            if batch and (len(batch) == 10 or size + len(embed) > 6000):
                batches.append(batch)
                batch, size = [], 0
            batch.append(embed)
            size += len(embed)
        batches.append(batch)
        await interaction.response.send_message(embeds=batches[0])
        for extra in batches[1:]:
            await interaction.followup.send(embeds=extra)


async def setup(bot):
    await bot.add_cog(LiveGame(bot))
