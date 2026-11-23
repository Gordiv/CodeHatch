"""The game catalog: the exact names the game lists in its ModuleScript DiscordCatalog (currencies, items, pets with
rarity, eggs with chances, multipliers). The game reports it through the DataStore (scripts/DiscordCodes/Report.luau,
read by roblox_kit.refresh). Commands suggest these names and refuse a name the catalog doesn't have, so a typo can't
create a code, egg or gift that never works in the game.

A list the owner left empty (or a game without a catalog) never blocks anything: then the old hints from the game
scan (roblox_kit) still apply.

Names are compared exactly (letter case and outer spaces aside): "VIP" and "VIP+" are two names. Only when that finds
nothing, the looser rule of the game (no spaces or signs, see roblox_kit.normalize) may pick ONE name.
"""
import difflib
import math
import time

from utils import cloud_sync, i18n, roblox_kit
from utils.i18n import t

# "robux": what players can buy with Robux (Catalog.SoldForRobux), for the warning on codes and gifts
NAME_KINDS = ("currencies", "items", "multipliers", "robux")
MAX_NAME = 100  # same limit as CONFIG.CatalogMaxNameLength in Report.luau
PRESET_PREFIX = "egg:"  # /egg-create pets:"egg:Basic Egg" = the pets and chances of that egg from the catalog
PROBLEM_CODES = ("not_list", "bad_name", "too_many", "pet_no_name", "egg_no_name", "egg_no_pets", "error", "no_return",
                 "name_too_long", "timeout", "template")


def key(name) -> str:
    """How two catalog names are compared: letter case and outer spaces don't matter, every other sign does."""
    return " ".join(str(name).split()).casefold()


def _text(value) -> str:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return ""
    text = str(value).strip()
    return text if len(text) <= MAX_NAME else ""


def _number(value):
    """A finite number >= 0 from the report, or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return None
    return float(value)


def _names(value) -> list:
    return [n for n in (_text(v) for v in roblox_kit._list(value)) if n]


def _pets(value) -> list:
    pets = []
    for pet in roblox_kit._list(value):
        name = _text(pet.get("name")) if isinstance(pet, dict) else _text(pet)
        if name:
            pets.append({"name": name, "rarity": _text(pet.get("rarity")) if isinstance(pet, dict) else ""})
    return pets


def _eggs(value) -> list:
    eggs = []
    for egg in roblox_kit._list(value):
        if not isinstance(egg, dict) or not _text(egg.get("name")):
            continue
        pets = [{"name": _text(pet["name"]), "chance": _number(pet.get("chance"))}
                for pet in roblox_kit._list(egg.get("pets")) if isinstance(pet, dict) and _text(pet.get("name"))]
        price = _number(egg.get("price"))
        eggs.append({"name": _text(egg["name"]), "currency": _text(egg.get("currency")),
                     "price": int(price) if price and price < 1e15 else 0, "pets": pets})
    return eggs


def _merge_names(target: list, names: list):
    seen = {key(n) for n in target}
    for name in names:
        if key(name) not in seen:
            seen.add(key(name))
            target.append(name)


def game_catalog(state: dict = None):
    """The catalog of every place (published game and Studio, last 30 days), newest first, or None when the game never
    reported one (an older DiscordCodes file, or nobody started a server yet). "missing" = the game has no
    DiscordCatalog. Names from several places are joined, so a name added in Studio but not published yet still works."""
    if cloud_sync.status() != "ready":
        return None
    state = roblox_kit.load_state() if state is None else state
    if state.get("universe") != cloud_sync.universe_id():
        return None
    now = time.time()
    entries = []
    for place in (state.get("catalog") or {}).values():
        if not isinstance(place, dict):
            continue
        for kind in ("live", "studio"):
            entry = place.get(kind)
            if isinstance(entry, dict) and now - roblox_kit._number(entry.get("at")) <= roblox_kit.STALE_SECONDS:
                entries.append((roblox_kit._number(entry.get("at")), kind == "studio", entry))
    if not entries:
        return None
    entries.sort(key=lambda e: -e[0])
    at, studio, newest = entries[0]
    result = {"currencies": [], "items": [], "multipliers": [], "robux": [], "pets": [], "eggs": [], "problems": [],
              "at": int(at), "studio": studio, "missing": all(e[2].get("missing") for e in entries)}
    pet_keys, egg_keys = set(), set()
    for _, _, entry in entries:
        if entry.get("missing"):
            continue
        for kind in NAME_KINDS:
            _merge_names(result[kind], _names(entry.get(kind)))
        for pet in _pets(entry.get("pets")):
            if key(pet["name"]) not in pet_keys:
                pet_keys.add(key(pet["name"]))
                result["pets"].append(pet)
        for egg in _eggs(entry.get("eggs")):
            if key(egg["name"]) not in egg_keys:
                egg_keys.add(key(egg["name"]))
                result["eggs"].append(egg)
    if not newest.get("missing"):
        result["problems"] = [p for p in roblox_kit._list(newest.get("problems")) if isinstance(p, dict)][:20]
    result["template"] = is_template(result)
    return result


# The example names of the DiscordCatalog template from older bot versions. A catalog that still has exactly them was
# never filled in: its names are examples, so they must not decide which names the commands accept.
TEMPLATE_NAMES = {"currencies": {"coins", "gems"}, "items": {"vip pass", "speed coil"}, "pets": {"dog", "cat", "dragon"},
                  "eggs": {"basic egg"}, "multipliers": {"coins"}}


def is_template(cat) -> bool:
    if not cat or cat.get("missing"):
        return False
    lists = {"currencies": {key(n) for n in cat["currencies"]}, "items": {key(n) for n in cat["items"]},
             "pets": {key(p["name"]) for p in cat["pets"]}, "eggs": {key(e["name"]) for e in cat["eggs"]},
             "multipliers": {key(n) for n in cat["multipliers"]}}
    if lists["currencies"] != TEMPLATE_NAMES["currencies"] or lists["items"] != TEMPLATE_NAMES["items"]:
        return False
    return all(not lists[kind] or lists[kind] == TEMPLATE_NAMES[kind] for kind in ("pets", "eggs", "multipliers"))


def has_names(cat) -> bool:
    return bool(cat) and not cat["missing"] and not cat.get("template") \
        and any(cat[k] for k in ("currencies", "items", "pets", "multipliers"))


def names(cat, kind: str) -> list:
    """Names of one list ("currencies", "items", "pets", "eggs", "multipliers"); empty when the catalog still has only
    the template's example names."""
    # SoldForRobux was never in the template: it counts even next to the old example names
    if not cat or cat["missing"] or (cat.get("template") and kind != "robux"):
        return []
    if kind in ("pets", "eggs"):
        return [entry["name"] for entry in cat[kind]]
    return list(cat.get(kind) or [])  # "robux" is missing from catalogs saved by older bots


def robux_rewards(reward: dict, cat=None) -> list:
    """Names in a code's or a gift's reward that the game's catalog lists as bought with Robux (Catalog.SoldForRobux).
    Compared like the game compares names (letter case, spaces and "_" don't matter): "VIP_Pass" marks "VIP Pass"."""
    cat = game_catalog() if cat is None else cat
    marked = {roblox_kit.normalize(n) for n in names(cat, "robux")}
    found = []
    for part in ("currency", "item"):
        entry = (reward or {}).get(part)
        if isinstance(entry, dict) and entry.get("name") and roblox_kit.normalize(entry["name"]) in marked:
            found.append(str(entry["name"]))
    return found


def robux_warnings(reward: dict, cat=None, gift: bool = False) -> list:
    """Roblox rules (Promo Offers for Virtual Rewards, checked 2026-10-17): a code posted outside Roblox may not give
    anything players can buy with Robux, and contests outside Roblox may not have such prizes. A gift to one player
    (e.g. a compensation) is fine, so its text only names the contest case."""
    found = robux_rewards(reward, cat)
    return [t("give.robux_warning" if gift else "catalog.robux_warning", names=", ".join(found))] if found else []


def rarities(cat) -> dict:
    """{key(pet name): rarity} for showing rarities in suggestions without searching the list for every name."""
    return {key(p["name"]): p["rarity"] for p in (cat or {}).get("pets", []) if p["rarity"]}


def rarity(cat, pet: str) -> str:
    return rarities(cat).get(key(pet), "")


def manual_note(kinds: tuple) -> str:
    """For messages after names are picked or typed in /setup-roblox: when the catalog has that list, the commands use
    the catalog, so a new name must be added there. Empty otherwise."""
    cat = game_catalog()
    return ("\n" + t("catalog.note_catalog_wins")) if any(names(cat, kind) for kind in kinds) else ""


def names_for(kind: str, extra: list = None) -> list:
    """Names for suggestions: the catalog's list when it has one (only names that will be accepted), otherwise the
    names typed or picked in /setup-roblox."""
    result = names(game_catalog(), kind)
    if not result:
        _merge_names(result, [str(n) for n in (extra or [])])
    return result


def _candidates(cat, kind: str) -> list:
    if kind == "reward_item":  # a code or a gift can give an item or a pet
        result = names(cat, "items")
        _merge_names(result, names(cat, "pets"))
        return result
    return names(cat, kind)


def reward_names(items: list = None, pets: list = None) -> list:
    """What a code or a gift can give: the catalog's items and pets when it lists them, otherwise the names from
    /setup-roblox."""
    result = _candidates(game_catalog(), "reward_item")
    if not result:
        _merge_names(result, [str(n) for n in (items or []) + (pets or [])])
    return result


def resolve(kind: str, name: str, cat=None) -> tuple:
    """(name in the catalog's spelling, "") or (name, error line for the admin) when the catalog has a list of this
    kind and the name isn't on it. No catalog or an empty list: the name is accepted as it is. Join the error lines
    with error_message()."""
    cat = game_catalog() if cat is None else cat
    candidates = _candidates(cat, kind)
    if not candidates:
        return name, ""
    by_key = {key(c): c for c in candidates}
    if key(name) in by_key:
        return by_key[key(name)], ""
    # the looser rule of the game ("Uncle Pet" = "UnclePet"), only when it points at exactly one name
    loose = roblox_kit.normalize(name)
    matches = [c for c in candidates if loose and roblox_kit.normalize(c) == loose]
    if len(matches) == 1:
        return matches[0], ""
    close = difflib.get_close_matches(key(name), list(by_key), n=3, cutoff=0.6)
    close += [k for k in by_key if key(name) and (key(name) in k or k in key(name)) and k not in close][:3 - len(close)]
    text = t(f"catalog.err_{kind}", name=name)
    if close:
        text += " " + t("catalog.err_suggest", names=", ".join(f"`{by_key[k]}`" for k in close))
    return name, text


def error_message(errors: list) -> str:
    """The error lines from resolve() with one hint how to add a name to the catalog; empty when there are none."""
    errors = [e for e in errors if e]
    return ("\n".join(errors)[:1700] + "\n" + t("catalog.err_hint")) if errors else ""


def _weight(value: float) -> str:
    """A chance as /egg-create reads it: plain digits, never 1e+06 or 5e-05; a chance above 0 never becomes "0"."""
    if value > 0:
        value = max(value, 1e-10)
    return f"{value:.10f}".rstrip("0").rstrip(".")


def egg_presets(cat=None) -> list:
    """The game's own eggs as ready pet lists for /egg-create: [(egg, "Dog:60, Cat:35", currency, price)]. Pets with
    chance 0 never drop, so they are left out; no chances at all = equal chances; an egg where only some pets have a
    chance gets no preset (problems() tells the owner)."""
    cat = game_catalog() if cat is None else cat
    presets = []
    for egg in (cat or {}).get("eggs", []) if names(cat, "eggs") else []:
        chances = [p["chance"] for p in egg["pets"]]
        if not egg["pets"] or (None in chances and any(c is not None for c in chances)):
            continue
        pets = [p for p in egg["pets"] if p["chance"] is None or p["chance"] > 0]
        if pets:
            text = ", ".join(f"{p['name']}:{_weight(p['chance'])}" if p["chance"] else f"{p['name']}:1" for p in pets)
            presets.append((egg["name"], text, egg["currency"], egg["price"]))
    return presets


def expand_preset(text: str, cat=None) -> str:
    """"egg:Basic Egg" (picked from the /egg-create suggestions) -> that egg's pets and chances; any other text as it is."""
    stripped = (text or "").strip()
    if not stripped.lower().startswith(PRESET_PREFIX):
        return text
    wanted = key(stripped[len(PRESET_PREFIX):])
    for egg, pets, _, _ in egg_presets(cat):
        if key(egg) == wanted:
            return pets
    return text


def problems(cat) -> list:
    """Texts of everything to fix in DiscordCatalog: what the game reported, plus eggs that use a pet or currency the
    catalog doesn't list, or give chances to only some of their pets."""
    if not cat or cat["missing"]:
        return []
    texts = [t("catalog.problem.template")] if cat.get("template") else []
    for problem in cat["problems"]:
        code = str(problem.get("code") or "")
        if code == "template" and cat.get("template"):
            continue  # the game says the same as the line above
        text_key = f"catalog.problem.{code}" if code in PROBLEM_CODES else "catalog.problem.other"
        texts.append(t(text_key, what=problem.get("what") or "", detail=str(problem.get("detail") or "")[:200]))
    pets = {key(n) for n in names(cat, "pets")}
    currencies = {key(n) for n in names(cat, "currencies")}
    for egg in cat["eggs"]:
        unknown = [p["name"] for p in egg["pets"] if pets and key(p["name"]) not in pets]
        if unknown:
            texts.append(t("catalog.problem.egg_unknown_pets", egg=egg["name"], pets=", ".join(unknown[:10])))
        if egg["currency"] and currencies and key(egg["currency"]) not in currencies:
            texts.append(t("catalog.problem.egg_unknown_currency", egg=egg["name"], currency=egg["currency"]))
        chances = [p["chance"] for p in egg["pets"]]
        if None in chances and any(c is not None for c in chances):
            texts.append(t("catalog.problem.egg_missing_chances", egg=egg["name"]))
    # a SoldForRobux name the other lists don't have is probably a typo: the warning would never match it
    known = {roblox_kit.normalize(n) for kind in ("currencies", "items", "pets") for n in names(cat, kind)}
    unknown = [n for n in names(cat, "robux") if known and roblox_kit.normalize(n) not in known]
    if unknown:
        texts.append(t("catalog.problem.robux_unknown", names=", ".join(unknown[:10])))
    return texts


def summary(cat) -> str:
    """One line for /setup-roblox and /tutorial."""
    if cat is None:
        return t("catalog.summary_unknown")
    if cat["missing"]:
        return t("catalog.summary_missing")
    if cat.get("template"):
        return t("catalog.summary_template")
    return t("catalog.summary_ok", currencies=len(cat["currencies"]), items=len(cat["items"]), pets=len(cat["pets"]),
             eggs=len(cat["eggs"]), multipliers=len(cat["multipliers"]))


def ai_prompt(scan=None, max_length: int = 1700) -> str:
    """A ready text to paste into an AI assistant that fills DiscordCatalog from the owner's game. When it would be
    too long for one message, the list of names is shortened, never the instructions."""
    reported = [roblox_kit.leaf(p) for p, _ in scan["values"]] + [n for n, _ in scan["attributes"]] if scan else []
    seen, hints = set(), []
    for name in reported:
        if key(name) not in seen:
            seen.add(key(name))
            hints.append(name)
    # The instructions contain Luau tables with { }, so they are used as written (never formatted)
    text = i18n.raw("catalog.ai_prompt")
    hints = hints[:60]
    while hints:
        names = t("catalog.ai_names", names=", ".join(hints))
        if len(text) + 2 + len(names) <= max_length:
            return text + "\n\n" + names
        hints.pop()
    return text[:max_length]
