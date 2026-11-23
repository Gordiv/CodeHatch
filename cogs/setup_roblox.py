"""/setup-roblox: everything about the owner's Roblox game in one place.

Steps 1-4 connect the game (game link, API key, the Studio file, names from the game); the other buttons set up and
use the features that change the game from Discord (promo codes, eggs, events, gifts, announcements, bans,
leaderboard). The game reports what it has (utils/roblox_kit.game_scan), so the panels offer exact names
and warn when an option can't work in this game.
"""
import json
import re

import discord
from discord import app_commands
from discord.ext import commands

import logging

from cogs import game_codes
from cogs.game_codes import NONE
from cogs.setup import (ECONOMY_FILE, LIST_LIMITS, CloudSyncView, EconomyModal, GameModal, build_kit_embed, build_sync_embed,
                        sync_status_text)
from utils import action_log, catalog, cloud_sync, config_store, database, open_cloud, roblox_kit
from utils.i18n import L, t
from utils.ui import AdminView, CloseView, Panel, StaffView, close_message, defer_for, send_panel, show_in_place, staff_only

try:  # eggs, events, gifts and announcements
    from cogs import live_game
except Exception as e:  # broken: the other panels must still open
    live_game = None
    logging.getLogger("setup_roblox").error("cogs/live_game.py could not be loaded: %s", e)

MAX_OPTIONS = 25
PETS_FIELD = 1000  # the pets field of the egg form: a longer list is never cut, the field stays empty


def economy() -> dict:
    return config_store.read_json(ECONOMY_FILE, {})


def _color() -> int:
    return config_store.embed_color()


def _icon(ok) -> str:
    return "✅" if ok else "⚠️"


def _join(items: list, limit: int = 900) -> str:
    text = ", ".join(items)
    return text if len(text) <= limit else text[:limit].rsplit(",", 1)[0] + ", …"


def _lines(lines: list, limit: int = 1024) -> str:
    """Whole lines that fit in an embed field (1024 characters), with "…" when some were left out."""
    text = ""
    for line in lines:
        candidate = f"{text}\n{line}" if text else line
        if len(candidate) > limit - 2:
            return text + "\n…" if text else line[:limit - 1] + "…"
        text = candidate
    return text


def scan_summary(scan) -> str:
    if not scan:
        return t("rbx.scan_none")
    where = t("rbx.scan_studio") if scan["studio"] else t("rbx.scan_live")
    return t("rbx.scan_ok", names=len(scan["values"]) + len(scan["attributes"]), spots=len(scan["spots"]),
             time=f"<t:{scan['at']}:R>", where=where)


# ---------- Main panel ----------

async def roblox_panel_embed(force: bool = False) -> discord.Embed:
    """force: read the game's reports again now (🔄), not from the last few minutes."""
    await roblox_kit.refresh_quick(force)
    cfg = config_store.load()
    roblox = cfg.get("roblox", {})
    eco = economy()
    scan = roblox_kit.game_scan()
    kit = roblox_kit.evaluate()
    eggs = await database.get_active_eggs()
    events = await database.get_active_live_events()
    game_ok = bool(roblox.get("universe_id") and roblox.get("place_id"))
    sync_ok = cloud_sync.status() == "ready"
    kit_ok = kit["status"] == "ok"
    cat = catalog.game_catalog()
    names_ok = bool(eco.get("configured") and eco.get("currencies")) or catalog.has_names(cat)
    steps = [game_ok, sync_ok, kit_ok, names_ok]

    embed = discord.Embed(title=t("rbx.title"), description=t("rbx.description", done=sum(steps), total=len(steps)),
                          color=_color())
    embed.add_field(name=f"{_icon(game_ok)} {t('rbx.step_game')}", value=(
        f"Place ID: `{roblox.get('place_id') or '—'}` | Universe ID: `{roblox.get('universe_id') or '—'}`"
        if game_ok else t("rbx.game_missing")), inline=False)
    embed.add_field(name=f"{_icon(sync_ok)} {t('rbx.step_connection')}",
                    value=sync_status_text(include_kit=False) + ("" if sync_ok else "\n" + t("rbx.connection_hint")), inline=False)
    embed.add_field(name=f"{_icon(kit_ok)} {t('rbx.step_kit')}",
                    value=roblox_kit.status_line(kit) or t("rbx.kit_needs_connection"), inline=False)
    names = t("rbx.names_summary", currencies=_join(eco.get("currencies", []), 300) or "—",
              items=len(eco.get("items", [])), pets=len(eco.get("pets", [])))
    embed.add_field(name=f"{_icon(names_ok)} {t('rbx.step_names')}",
                    value=(catalog.summary(cat) + "\n" + names + "\n" + scan_summary(scan))[:1024], inline=False)

    board = cfg.get("leaderboard", {}).get("datastore")
    features = [t("rbx.sum_codes", count=len(await database.get_active_game_codes()))]
    features.append(t("rbx.sum_eggs", count=len(eggs), spots=len(scan["spots"]) if scan else "?"))
    features.append(t("rbx.sum_events", count=len(events),
                      used=_join(scan["multipliers"], 200) if scan and scan["multipliers"] else "—"))
    features.append(t("rbx.sum_gifts_ready") if sync_ok else t("rbx.sum_gifts_off"))
    features.append(t("rbx.sum_board", datastore=board) if board else t("rbx.sum_board_off"))
    embed.add_field(name=t("rbx.features_field"), value="\n".join(features)[:1024], inline=False)
    embed.set_footer(text=t("rbx.footer"))
    return embed


async def send_roblox_panel(interaction: discord.Interaction):
    # Building the panel may ask Roblox for the game's reports: answer Discord first (it waits only 3 s)
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True, thinking=True)
    await send_panel(interaction, RobloxPanelView(), embed=await roblox_panel_embed())


class RobloxPanelView(AdminView):
    def __init__(self):
        super().__init__()
        labels = {"game": "rbx.btn_game", "connection": "rbx.btn_connection", "kit": "kit.btn", "names": "rbx.btn_names",
                  "catalog": "catalog.btn",
                  "manual": "rbx.btn_manual", "codes": "rbx.btn_codes",
                  "eggs": "rbx.btn_eggs",
                  "events": "rbx.btn_events", "gifts": "rbx.btn_gifts", "bans": "rbx.btn_bans", "ranking": "rbx.btn_ranking",
                  "player": "rbx.btn_player", "control": "rbx.btn_control", "check": "rbx.btn_check",
                  "refresh": "setup.btn_refresh",
                  "tutorial": "setup.btn_tutorial"}
        for attr, key in labels.items():
            getattr(self, attr).label = t(key)

    # 1-4: connecting the game
    @discord.ui.button(label="Roblox game", emoji="🎮", style=discord.ButtonStyle.primary, row=0)
    async def game(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GameModal(config_store.load().get("roblox", {})))

    @discord.ui.button(label="Game connection", emoji="🔑", style=discord.ButtonStyle.primary, row=0)
    async def connection(self, interaction: discord.Interaction, button: discord.ui.Button):
        await send_panel(interaction, CloudSyncView(), embed=build_sync_embed())

    @discord.ui.button(label="Studio file", emoji="📥", style=discord.ButtonStyle.primary, row=0)
    async def kit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await roblox_kit.refresh(force=True)
        await send_panel(interaction, CloseView(), embed=build_kit_embed(roblox_kit.evaluate()))

    @discord.ui.button(label="What your game has", emoji="🔍", style=discord.ButtonStyle.primary, row=1)
    async def names(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await roblox_kit.refresh(force=True)
        view = GameNamesView()
        await send_panel(interaction, view, embed=view.embed())

    @discord.ui.button(label="Game catalog", emoji="📒", style=discord.ButtonStyle.primary, row=1)
    async def catalog(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await roblox_kit.refresh(force=True)
        await send_panel(interaction, CatalogView(), embed=catalog_embed())

    @discord.ui.button(label="Type names", emoji="✏️", style=discord.ButtonStyle.secondary, row=1)
    async def manual(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EconomyModal())

    # features
    @discord.ui.button(label="Promo codes", emoji="📜", style=discord.ButtonStyle.success, row=2)
    async def codes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        view = CodesView()
        await send_panel(interaction, view, embed=await view.embed())

    @discord.ui.button(label="Eggs", emoji="🥚", style=discord.ButtonStyle.success, row=2)
    async def eggs(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        view = EggsView()
        await send_panel(interaction, view, embed=await view.embed())

    @discord.ui.button(label="Events", emoji="⚡", style=discord.ButtonStyle.success, row=2)
    async def events(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        view = EventsView()
        await send_panel(interaction, view, embed=await view.embed())

    @discord.ui.button(label="Gifts & announcements", emoji="🎁", style=discord.ButtonStyle.success, row=2)
    async def gifts(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = GiftsView()
        await send_panel(interaction, view, embed=view.embed())

    @discord.ui.button(label="Bans", emoji="🔨", style=discord.ButtonStyle.success, row=3)
    async def bans(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = BansView()
        await send_panel(interaction, view, embed=view.embed())

    @discord.ui.button(label="Leaderboard", emoji="🏆", style=discord.ButtonStyle.success, row=3)
    async def ranking(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = RankingView()
        await send_panel(interaction, view, embed=view.embed())

    @discord.ui.button(label="Player card", emoji="👤", style=discord.ButtonStyle.success, row=3)
    async def player(self, interaction: discord.Interaction, button: discord.ui.Button):
        await open_player_lookup(interaction)

    @discord.ui.button(label="Control panel", emoji="🕹️", style=discord.ButtonStyle.primary, row=3)
    async def control(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs import game_panel  # game_panel imports this module
        await game_panel.send_manager(interaction)

    # checking
    @discord.ui.button(label="Check everything", emoji="🧪", style=discord.ButtonStyle.secondary, row=4)
    async def check(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await send_panel(interaction, CloseView(), embed=await run_checks())

    @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.secondary, row=4)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.edit_original_response(embed=await roblox_panel_embed(force=True), view=self)

    @discord.ui.button(label="Tutorial", emoji="📖", style=discord.ButtonStyle.secondary, row=4)
    async def tutorial(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.tutorial import send_tutorial
        await send_tutorial(interaction, chapter="roblox")


# ---------- What your game has (names from the game) ----------

def _ordered(groups: list, configured: list, first) -> list:
    """Names already picked first (so they never fall out of the 25 options), then the most likely ones (e.g. leaderstats
    values for currencies), then alphabetical."""
    picked = {roblox_kit.normalize(n) for n in configured}
    return sorted(groups, key=lambda g: (0 if roblox_kit.normalize(g[0]) in picked else 1, 0 if first(g) else 1, g[0].lower()))


class NamesSelect(discord.ui.Select):
    """Picks which names from the game are currencies / items / pets. Names typed by hand that are not in the list stay."""

    def __init__(self, key: str, groups: list, configured: list, row: int):
        self.key = key
        configured_norm = {roblox_kit.normalize(n) for n in configured}
        shown = groups[:MAX_OPTIONS]
        self.shown_norm = {roblox_kit.normalize(name) for name, _ in shown}
        # The value is the position, not the name: two long names cut to 100 characters would give the same value
        self.names = [name for name, _ in shown]
        options = [discord.SelectOption(label=name[:100], value=str(index), description=_join(paths, 95)[:100],
                                        default=roblox_kit.normalize(name) in configured_norm)
                   for index, (name, paths) in enumerate(shown)]
        super().__init__(placeholder=t(f"rbx.names_pick_{key}"), min_values=0, max_values=len(options), options=options, row=row)

    async def callback(self, interaction: discord.Interaction):
        eco = economy()
        limit = LIST_LIMITS.get(self.key, 25)
        picked = [self.names[int(v)][:100] for v in self.values]
        kept = [n for n in eco.get(self.key, []) if roblox_kit.normalize(n) not in self.shown_norm]
        names = (picked + kept)[:limit]
        eco[self.key] = names
        eco["configured"] = True
        config_store.write_json(ECONOMY_FILE, eco)
        note = ("\n" + t("rbx.names_cut", max=limit)) if len(picked) + len(kept) > limit else ""
        await interaction.response.send_message(
            t("rbx.names_saved", what=t(f"rbx.names_{self.key}"), names=_join(names, 1500) or "—") + note
            + catalog.manual_note((self.key,)), ephemeral=True)


class GameNamesView(AdminView):
    def __init__(self):
        super().__init__()
        self.scan = roblox_kit.game_scan()
        self.refresh.label = t("setup.btn_refresh")
        self.manual.label = t("rbx.btn_manual")
        if not self.scan:
            return
        eco = economy()
        exp = set(roblox_kit.EXP_NAMES)
        numbers = [g for g in roblox_kit.name_groups(self.scan, True) if roblox_kit.normalize(g[0]) not in exp]
        everything = [g for g in roblox_kit.name_groups(self.scan, False) if roblox_kit.normalize(g[0]) not in exp]
        self.counts = {"currencies": len(numbers), "items": len(everything), "pets": len(everything)}
        bools = {p for p, cls in self.scan["values"] if cls == "BoolValue"}
        if numbers:
            currencies = eco.get("currencies", [])
            self.add_item(NamesSelect("currencies", _ordered(numbers, currencies, lambda g: any(
                p.startswith("leaderstats.") for p in g[1])), currencies, 0))
        if everything:
            items, pets = eco.get("items", []), eco.get("pets", [])
            self.add_item(NamesSelect("items", _ordered(everything, items, lambda g: any(p in bools for p in g[1])), items, 1))
            self.add_item(NamesSelect("pets", _ordered(everything, pets, lambda g: any("pet" in p.lower() for p in g[1])),
                                      pets, 2))

    def embed(self) -> discord.Embed:
        embed = discord.Embed(title=t("rbx.names_title"), color=_color())
        scan = self.scan
        if not scan:
            embed.description = t("rbx.names_no_scan")
            return embed
        embed.description = t("rbx.names_intro") + "\n" + t("rbx.names_source") + "\n" + scan_summary(scan) + "\n" + catalog.summary(catalog.game_catalog())
        numbers = roblox_kit.name_groups(scan, True)
        number_names = {name for name, _ in numbers}
        others = [g for g in roblox_kit.name_groups(scan, False) if g[0] not in number_names]
        embed.add_field(name=t("rbx.names_numbers"), value=_join([f"`{', '.join(p)}`" for _, p in numbers], 1000) or "—",
                        inline=False)
        embed.add_field(name=t("rbx.names_others"), value=_join([f"`{', '.join(p)}`" for _, p in others], 1000) or "—",
                        inline=False)
        exp = roblox_kit.exp_paths(scan)
        embed.add_field(name="⭐ EXP", value=t("rbx.names_exp_ok", paths=_join(exp, 300)) if exp else t("rbx.names_exp_missing"),
                        inline=False)

        eco = economy()
        lines = []
        for key, item in (("currencies", False), ("items", True), ("pets", True)):
            names = eco.get(key, [])
            if not names:
                continue
            marks = []
            for name in names[:25]:
                if roblox_kit.find_name(scan, name, item=item):
                    marks.append(roblox_kit.name_mark(scan, name, item=item))
                elif key == "items" and roblox_kit.find_name(scan, f"{name}_ExpiresAt"):
                    # only <Name>_ExpiresAt: works as a timed item (codes, gifts with a time), not a permanent one
                    marks.append("✅ " + t("rbx.names_timed_only", name=name))
                else:
                    marks.append(f"⚠️ {name}")
            lines.append(f"**{t(f'rbx.names_{key}')}:** " + ", ".join(marks))
        hooks = scan["hooks"]
        if roblox_kit.has_hook(scan, "OnReward"):
            lines.append(t("rbx.names_hook_reward"))
        embed.add_field(name=t("rbx.names_in_bot"), value=("\n".join(lines) or t("rbx.names_none_in_bot"))[:1024], inline=False)
        embed.add_field(name=t("rbx.names_hooks"), value=", ".join(f"`{h}`" for h in hooks) if hooks else t("rbx.names_no_hooks"),
                        inline=False)
        more = [k for k, c in getattr(self, "counts", {}).items() if c > MAX_OPTIONS]
        embed.set_footer(text=t("rbx.names_footer") + (" " + t("rbx.names_more", max=MAX_OPTIONS) if more else ""))
        return embed

    @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.secondary, row=3)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await roblox_kit.refresh(force=True)
        view = GameNamesView()
        view.message = self.message
        self.stop()
        await interaction.edit_original_response(embed=view.embed(), view=view)

    @discord.ui.button(label="Type names", emoji="✏️", style=discord.ButtonStyle.secondary, row=3)
    async def manual(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EconomyModal())


# ---------- Game catalog (DiscordCatalog: the exact names the game lists) ----------

def _pets_by_rarity(cat) -> str:
    groups = {}
    for pet in cat["pets"]:
        groups.setdefault(pet["rarity"] or t("catalog.no_rarity"), []).append(pet["name"])
    return "\n".join(f"**{rarity}:** {_join(names, 250)}" for rarity, names in groups.items())


def _egg_line(egg: dict) -> str:
    total = sum(p["chance"] or 1 for p in egg["pets"]) or 1
    pets = ", ".join(f"{p['name']} {(p['chance'] or 1) * 100 / total:.3g}%" for p in egg["pets"])
    price = f" ({egg['price']:,} {egg['currency']})" if egg["price"] else ""
    return f"**{egg['name']}**{price}: {pets}"


def catalog_embed() -> discord.Embed:
    cat = catalog.game_catalog()
    embed = discord.Embed(title=t("catalog.title"), color=_color())
    if cat is None:
        embed.description = t("catalog.description_unknown")
    elif cat["missing"]:
        embed.description = t("catalog.description_missing")
    else:
        where = t("rbx.scan_studio") if cat["studio"] else t("rbx.scan_live")
        embed.description = t("catalog.description_ok", time=f"<t:{cat['at']}:R>", where=where)
        for kind in ("currencies", "items"):
            found = catalog.names(cat, kind)
            embed.add_field(name=t(f"catalog.field_{kind}", count=len(found)), value=_join(found, 1000) or t("catalog.empty"),
                            inline=False)
        embed.add_field(name=t("catalog.field_pets", count=len(cat["pets"])),
                        value=(_pets_by_rarity(cat) or t("catalog.empty"))[:1024], inline=False)
        lines = [_egg_line(egg) for egg in cat["eggs"][:10]]
        if len(cat["eggs"]) > 10:
            lines.append(t("catalog.more", count=len(cat["eggs"]) - 10))
        embed.add_field(name=t("catalog.field_eggs", count=len(cat["eggs"])),
                        value=("\n".join(lines) or t("catalog.empty"))[:1024], inline=False)
        embed.add_field(name=t("catalog.field_multipliers", count=len(cat["multipliers"])),
                        value=_join(cat["multipliers"], 1000) or t("catalog.empty"), inline=False)
        robux = catalog.names(cat, "robux")
        embed.add_field(name=t("catalog.field_robux", count=len(robux)),
                        value=_join(robux, 1000) or t("catalog.robux_empty"), inline=False)
        problems = catalog.problems(cat)
        if problems:
            embed.add_field(name=t("catalog.problems_title"), value="\n".join(f"⚠️ {p}" for p in problems[:8])[:1024], inline=False)
    if not catalog.has_names(cat):
        embed.add_field(name=t("catalog.howto_title"), value=t("catalog.howto"), inline=False)
    embed.set_footer(text=t("catalog.footer"))
    limit = 1000
    while len(embed) > 5800 and limit > 100:  # a huge catalog: shorter lists, never a refused message
        limit -= 150
        for index, field in enumerate(embed.fields):
            if len(field.value) > limit:
                embed.set_field_at(index, name=field.name, value=field.value[:limit].rsplit(",", 1)[0] + " …", inline=False)
    return embed


class CatalogView(AdminView):
    def __init__(self):
        super().__init__()
        self.refresh.label = t("setup.btn_refresh")
        self.ai.label = t("catalog.btn_ai")
        self.tutorial.label = t("setup.btn_tutorial")

    @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.secondary)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await roblox_kit.refresh(force=True)
        await interaction.edit_original_response(embed=catalog_embed(), view=self)

    @discord.ui.button(label="Text for an AI assistant", emoji="🤖", style=discord.ButtonStyle.secondary)
    async def ai(self, interaction: discord.Interaction, button: discord.ui.Button):
        intro = t("catalog.ai_intro")
        prompt = catalog.ai_prompt(roblox_kit.game_scan(), max_length=1990 - len(intro) - len("\n```\n\n```"))
        await interaction.response.send_message(intro + "\n```\n" + prompt + "\n```", ephemeral=True)

    @discord.ui.button(label="Tutorial", emoji="📖", style=discord.ButtonStyle.secondary)
    async def tutorial(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.tutorial import send_tutorial
        await send_tutorial(interaction, chapter="catalog")


# ---------- Eggs ----------

def _currency_component(eco: dict, current: str = ""):
    """A menu of the game's currencies (the current one, or the first, picked), or a text field when there are none
    or too many for a menu."""
    currencies = catalog.names_for("currencies", eco.get("currencies", []))
    exact = next((c for c in currencies if current and catalog.key(c) == catalog.key(current)), None)
    if current and currencies and exact is None:
        currencies = [current] + currencies  # the egg's own currency stays pickable even if the list changed
        exact = current
    if currencies and len(currencies) <= MAX_OPTIONS:
        chosen = exact or currencies[0]
        return discord.ui.Select(options=[discord.SelectOption(label=c[:100], value=c[:100], default=c == chosen)
                                          for c in currencies], min_values=1, max_values=1)
    return discord.ui.TextInput(label=t("rbx.egg_currency"), max_length=100, default=current or None,
                                placeholder=_join(currencies[:4], 95) or "Coins")


def _optional_pick(label: str, names: list, example: str = ""):
    """A menu with "none" first, or a text field when there are more names than a menu can show or no names yet (a
    typo is still caught by the catalog check)."""
    if names and len(names) <= MAX_OPTIONS - 1:
        return discord.ui.Select(options=[discord.SelectOption(label=t("codes.none_option")[:100], value=NONE, default=True)]
                                 + [discord.SelectOption(label=n[:100], value=n[:100]) for n in names])
    return discord.ui.TextInput(label=label[:45], max_length=100, required=False,
                                placeholder=_join(names[:4], 95) or example or None)


def _add_pick(modal, label: str, component, description: str = None):
    """description: a hint under the menu's name (a text field has no room for one)."""
    modal.add_item(discord.ui.Label(text=label, component=component, description=description[:100] if description else None)
                   if isinstance(component, discord.ui.Select) else component)


def _pick_value(component) -> str:
    return _component_value(component) or NONE


def _component_value(component) -> str:
    if isinstance(component, discord.ui.Select):
        return component.values[0] if component.values else ""
    return component.value.strip()


def _price(text: str) -> int:
    digits = re.sub(r"[\s_.,]", "", text or "")
    return int(digits) if digits.isascii() and digits.isdigit() else 0  # "²" is a digit for isdigit, not for int


# ---------- Promo codes ----------

class CodeModal(discord.ui.Modal):
    """A new code without typing a command: name, how long it works, currency + amount and an item. The answer is a
    draft: EXP and the item's time are added there (⚙️, a form holds at most 5 parts) and the code reaches the game
    only after ✅ Save."""

    def __init__(self):
        super().__init__(title=t("rbx.code_modal_title"))
        eco = economy()
        self.code = discord.ui.TextInput(label=t("rbx.code_name"), max_length=30, placeholder=t("rbx.code_name_ph"))
        self.validity = discord.ui.Select(options=[discord.SelectOption(label=t(f"duration.choice.{k}")[:100], value=k,
                                                                        default=k == "7d")
                                                   for k in game_codes.CODE_VALIDITY])
        self.currency = _optional_pick(t("rbx.gift_currency"), catalog.names_for("currencies", eco.get("currencies", [])),
                                       "Coins")
        self.amount = discord.ui.TextInput(label=t("rbx.gift_amount"), max_length=15, required=False, placeholder="500")
        self.item = _optional_pick(t("rbx.gift_item"), catalog.reward_names(eco.get("items", []), eco.get("pets", [])), "VIP")
        self.add_item(self.code)
        self.add_item(discord.ui.Label(text=t("rbx.code_validity"), component=self.validity))
        _add_pick(self, t("rbx.gift_currency"), self.currency)
        self.add_item(self.amount)
        _add_pick(self, t("rbx.gift_item"), self.item)

    async def on_submit(self, interaction: discord.Interaction):
        if not await staff_only(interaction, "codes"):  # the role may have been taken away while the form was open
            return
        currency, item = _pick_value(self.currency), _pick_value(self.item)
        digits = re.sub(r"[\s_.,]", "", self.amount.value or "")
        if digits and (not (digits.isascii() and digits.isdigit()) or int(digits) > game_codes.MAX_AMOUNT):
            await interaction.response.send_message(t("give.err_amount", max=f"{game_codes.MAX_AMOUNT:,}"), ephemeral=True)
            return
        cog = interaction.client.get_cog("GameCodes")
        if cog is None:
            await interaction.response.send_message(t("errors.unexpected"), ephemeral=True)
            return
        try:  # EXP may still come in the draft (⚙️), so a code without rewards is refused only when saving
            params = game_codes.code_params(self.code.value, self.validity.values[0] if self.validity.values else "7d",
                                            currency, int(digits or 0), 0, item, allow_empty=True)
        except game_codes.CodeError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        existing = await database.get_game_code(params["code"])
        replaces = game_codes.describe_code(existing) if game_codes.is_live(existing) else ""
        await send_panel(interaction, game_codes.CodeDraftView(cog, interaction.user.id, params, replaces),
                         embed=game_codes.draft_embed(params, replaces))


class CodesView(StaffView):

    permission = "codes"
    def __init__(self):
        super().__init__()
        self.new.label = t("rbx.btn_new_code")
        self.remove.label = t("rbx.btn_remove_codes")
        self.refresh.label = t("setup.btn_refresh")

    async def embed(self) -> discord.Embed:
        codes = list(await database.get_active_game_codes())
        embed = discord.Embed(title=t("rbx.codes_title"), description=t("rbx.codes_intro"), color=_color())
        shown = codes[:game_codes.CODES_PER_PAGE]
        lines = []
        for code in shown:
            name, value = game_codes.code_field(code)
            lines.append(f"**{name}**\n{value}")
        if len(codes) > len(shown):
            lines.append(t("rbx.codes_more", count=len(codes) - len(shown)))
        embed.add_field(name=t("rbx.codes_active", count=len(codes)), value=_lines(lines, 1024) or t("rbx.codes_none"),
                        inline=False)
        if not catalog.has_names(catalog.game_catalog()) and not economy().get("currencies"):
            embed.add_field(name=t("rbx.codes_names_title"), value=t("rbx.codes_names_hint"), inline=False)
        embed.set_footer(text=t("rbx.codes_footer"))
        return embed

    @discord.ui.button(label="New code", emoji="➕", style=discord.ButtonStyle.success, row=0)
    async def new(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CodeModal())

    @discord.ui.button(label="Remove codes", emoji="🗑️", style=discord.ButtonStyle.secondary, row=0)
    async def remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.get_cog("GameCodes")
        active = await database.get_active_game_codes()
        if not active or cog is None:
            await interaction.response.send_message(t("codes.none_active"), ephemeral=True)
            return
        note = "\n" + t("codes.list_limited", total=len(active)) if len(active) > MAX_OPTIONS else ""
        await send_panel(interaction, game_codes.CodeRemoveView(cog, interaction.user.id, active[:MAX_OPTIONS]),
                         content=t("codes.remove_intro") + note)

    @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.secondary, row=0)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.edit_original_response(embed=await self.embed(), view=self)


class EggModal(discord.ui.Modal):
    """A new egg, an egg copied from the game catalog (preset) or a change of an active egg (egg = its row). source: the
    window it was opened from, which the answer replaces; without one the answer is a new private message."""

    def __init__(self, egg=None, preset=None, source=None):
        title = t("rbx.egg_edit_title", name=egg["name"]) if egg else t("rbx.egg_modal_title")
        super().__init__(title=title[:45])
        self.egg, self.source = egg, source
        eco = economy()
        scan = roblox_kit.game_scan()
        pets = catalog.names_for("pets", eco.get("pets", []))
        presets = catalog.egg_presets()
        example = presets[0][1] if presets else (
            ", ".join(f"{p}:{w}" for p, w in zip(pets[:3], (60, 35, 5))) if len(pets) >= 3 else "Cat:60, Dog:35, Dragon:5")
        if egg:
            name, currency, price, pets_value = egg["name"], egg["currency"], str(egg["price"]), live_game.pets_text(egg)
        elif preset:  # (egg name, "Dog:60, Cat:35", currency, price) from the game catalog
            name, pets_value, currency, price = preset[0], preset[1], preset[2] or "", str(preset[3] or "") or None
        else:
            name = currency = pets_value = price = None
        # what the form showed: only fields the person changed are saved, so a change made meanwhile by someone else
        # (or a rounding of the chances) is never written back
        self.shown = {"name": name or "", "currency": currency or "", "price": price or "", "pets": pets_value or ""}
        self.egg_name = discord.ui.TextInput(label=t("rbx.egg_name"), max_length=40, placeholder=t("rbx.egg_name_ph"),
                                             default=(name or "")[:40] or None)
        self.currency = _currency_component(eco, currency or "")
        self.price = discord.ui.TextInput(label=t("rbx.egg_price"), max_length=15, placeholder="500", default=price)
        too_long = len(pets_value or "") > PETS_FIELD  # never cut a pet list in the middle: empty = unchanged
        self.pets = discord.ui.TextInput(label=t("rbx.egg_pets"), style=discord.TextStyle.paragraph, max_length=PETS_FIELD,
                                         placeholder=(t("rbx.egg_pets_too_long") if too_long else example)[:100],
                                         default=None if too_long else pets_value or None, required=not egg)
        self.add_item(self.egg_name)
        if isinstance(self.currency, discord.ui.Select):
            self.add_item(discord.ui.Label(text=t("rbx.egg_currency"), component=self.currency))
        else:
            self.add_item(self.currency)
        self.add_item(self.price)
        self.add_item(self.pets)
        self.spot = None
        self.spots = scan["spots"][:MAX_OPTIONS - 1] if scan else []
        current_spot = (egg["spot"] or "") if egg else ""
        self.shown["spot"] = current_spot
        if current_spot and current_spot not in self.spots:
            self.spots = [current_spot] + self.spots[:MAX_OPTIONS - 2]  # keep the egg's own spot pickable
        if self.spots:
            # Positions as values: two long spot names cut to the same text would otherwise be one option
            self.spot = discord.ui.Select(options=[discord.SelectOption(label=t("rbx.egg_any_spot"), value="-",
                                                                        default=not current_spot)]
                                          + [discord.SelectOption(label=s[:100], value=str(i), default=s == current_spot)
                                             for i, s in enumerate(self.spots)], min_values=1, max_values=1)
            self.add_item(discord.ui.Label(text=t("rbx.egg_spot"), component=self.spot))

    async def on_submit(self, interaction: discord.Interaction):
        if not await staff_only(interaction, "eggs"):  # the role may have been taken away while the form was open
            return
        price = _price(self.price.value)
        if price < 1:
            await interaction.response.send_message(t("rbx.err_price"), ephemeral=True)
            return
        if self.source is not None:
            await defer_for(interaction, self.source)
        else:
            await interaction.response.defer(ephemeral=True, thinking=True)
        spot = None
        if self.spot is not None:
            picked = self.spot.values[0] if self.spot.values else "-"
            spot = self.spots[int(picked)][:30] if picked.isdigit() and int(picked) < len(self.spots) else ""
        try:
            if self.egg:
                shown = self.shown
                name, currency, pets = self.egg_name.value.strip(), _component_value(self.currency), self.pets.value.strip()
                changes = await live_game.egg_changes(
                    self.egg["id"], name=None if name == shown["name"] else name,
                    currency=None if currency == shown["currency"] else currency,
                    price=None if str(price) == str(shown["price"]) else price,
                    pets_text=None if not pets or pets == shown["pets"].strip() else pets,
                    spot=None if spot is None or spot == shown["spot"] else spot)
                embed = await live_game.save_egg_changes(self.egg["id"], changes)
                egg_id = self.egg["id"]
            else:
                embed = await live_game.create_egg(self.egg_name.value, _component_value(self.currency), price,
                                                   self.pets.value, spot=spot or "", author_id=interaction.user.id)
                egg_id = next((r["id"] for r in await database.get_active_eggs()
                               if r["name"].lower() == self.egg_name.value.strip().lower()), None)
        except live_game.NothingToChange as e:
            # nothing changed in the form: the egg with its menus, where its color, time and model are changed
            row = await database.get_egg(self.egg["id"])
            if live_game.egg_gone(row):
                await _answer(interaction, self.source, content=t("eggs.not_found"))
                return
            embed = live_game.egg_embed(f"🥚 {row['name']}", live_game.eggs_snapshot([row])["eggs"][0])
            embed.set_footer(text=t("rbx.egg_done_footer"))
            await _answer(interaction, self.source, content=str(e), embed=embed, view=EggDoneView(row["id"], row))
            return
        except live_game.RuleError as e:
            if self.source is not None:  # written above the window it came from, which stays as it was
                await show_in_place(interaction, content=live_game.error_text(e))
            else:
                await send_panel(interaction, CloseView(), content=live_game.error_text(e))
            return
        if egg_id:
            embed.set_footer(text=t("rbx.egg_done_footer"))
        view = EggDoneView(egg_id, await database.get_egg(egg_id)) if egg_id else None
        await _answer(interaction, self.source, embed=embed, view=view)
        await action_log.discord_action(interaction, "egg_edit" if self.egg else "egg_create", embed)


async def _answer(interaction: discord.Interaction, source, content: str = None, embed=None, view=None):
    """An egg form's answer: in place of the window it came from, or as a new private message; always closable."""
    view = view or CloseView()
    if source is not None:
        await show_in_place(interaction, view=view, content=content, embed=embed)
    else:
        kwargs = {key: value for key, value in (("content", content), ("embed", embed)) if value is not None}
        await send_panel(interaction, view, **kwargs)


class EggDoneView(StaffView):
    """Under a new or changed egg: its color, how long it stays and its model straight away (each change is sent to
    the game at once), ✏️ the form again and 🗑️ removing it."""

    permission = "eggs"

    def __init__(self, egg_id: int, row=None):
        super().__init__()
        self.egg_id = egg_id
        self.edit.label = t("rbx.btn_edit_egg")
        self.remove.label = t("rbx.btn_remove_this_egg")
        scan = roblox_kit.game_scan()
        model = roblox_kit.egg_model(scan, row["template"] or "") if row else ""
        # the game shows a model instead of the colored egg: the menu says so before anyone picks a color for nothing
        # (no option picked then, otherwise Discord shows the picked color instead of this note)
        self.color.placeholder = (t("rbx.egg_color_model_ph", model=model) if model else t("rbx.egg_color_ph"))[:150]
        current = live_game.color_key(row) if row and not model else None
        self.color.options = [discord.SelectOption(label=t(f"eggs.color.{key}")[:100], value=key, default=key == current)
                              for key in live_game.EGG_COLORS]
        self.duration.placeholder = t("rbx.egg_duration_ph")
        self.duration.options = [discord.SelectOption(label=t(f"duration.choice.{key}")[:100], value=key)
                                 for key in live_game.EGG_DURATIONS]
        templates = (scan["templates"] if scan else [])[:MAX_OPTIONS - 1]
        if templates:
            self.template.placeholder = t("rbx.egg_template_ph")
            self.template.options = [discord.SelectOption(label=t("rbx.egg_default_model")[:100], value="-")] + \
                [discord.SelectOption(label=name[:100], value=str(i)) for i, name in enumerate(templates)]
            self.templates = templates
        else:
            self.remove_item(self.template)
            self.templates = []

    async def change(self, interaction: discord.Interaction, **fields):
        try:
            changes = await live_game.egg_changes(self.egg_id, **fields)
        except live_game.NothingToChange:  # picked what the egg already has (with a model no color is shown picked)
            await interaction.response.send_message(t("eggs.already_set"), ephemeral=True)
            return
        except live_game.RuleError as e:
            await interaction.response.send_message(live_game.error_text(e), ephemeral=True)
            return
        self.stop()
        await interaction.response.defer()  # sending to the game may take a moment
        try:
            embed = await live_game.save_egg_changes(self.egg_id, changes)
        except live_game.RuleError as e:  # removed in the very moment
            await show_in_place(interaction, view=CloseView(), content=live_game.error_text(e), embed=None)
            return
        embed.set_footer(text=t("rbx.egg_done_footer"))
        view = EggDoneView(self.egg_id, await database.get_egg(self.egg_id))
        await show_in_place(interaction, view=view, content=None, embed=embed)
        await action_log.discord_action(interaction, "egg_edit", embed)

    @discord.ui.select(row=0)
    async def color(self, interaction: discord.Interaction, select: discord.ui.Select):
        await self.change(interaction, color=select.values[0])

    @discord.ui.select(row=1)
    async def duration(self, interaction: discord.Interaction, select: discord.ui.Select):
        await self.change(interaction, duration=select.values[0])

    @discord.ui.select(row=2)
    async def template(self, interaction: discord.Interaction, select: discord.ui.Select):
        picked = select.values[0]
        await self.change(interaction, template=self.templates[int(picked)] if picked.isdigit() else "")

    @discord.ui.button(label="Edit", emoji="✏️", style=discord.ButtonStyle.primary, row=3)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        row = await database.get_egg(self.egg_id)
        if live_game.egg_gone(row):  # removed or expired: no form to fill in for nothing
            await interaction.response.send_message(t("eggs.not_found"), ephemeral=True)
            return
        self.hold_for_form()
        await interaction.response.send_modal(EggModal(egg=row, source=self))

    @discord.ui.button(label="Remove this egg", emoji="🗑️", style=discord.ButtonStyle.danger, row=3)
    async def remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.defer()
        row = await database.get_egg(self.egg_id)
        done = row and await database.remove_egg(self.egg_id)
        ok, error = await live_game.push_live("eggs")
        text = t("eggs.removed", name=row["name"]) if done else t("eggs.not_found")
        text += "\n" + live_game.sync_note(ok, error)
        await show_in_place(interaction, view=CloseView(), content=text, embed=None)
        if done:
            await action_log.discord_action(interaction, "egg_remove", text)


class EggPickSelect(discord.ui.Select):
    """Which egg to change, or which egg of the game catalog to copy: the form opens with its values filled in."""

    def __init__(self, kind: str, items: list):
        self.kind, self.items = kind, items[:MAX_OPTIONS]
        if kind == "edit":
            options = [discord.SelectOption(label=r["name"][:100], value=str(i),
                                            description=f"{r['price']:,} {r['currency']}"[:100])
                       for i, r in enumerate(self.items)]
            placeholder = t("rbx.egg_pick_edit_ph")
        else:
            options = [discord.SelectOption(label=p[0][:100], value=str(i), description=p[1][:100])
                       for i, p in enumerate(self.items)]
            placeholder = t("rbx.egg_pick_preset_ph")
        super().__init__(placeholder=placeholder, options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        item = self.items[int(self.values[0])]
        if self.kind == "edit":
            item = await database.get_egg(item["id"])  # the newest values, not the ones from when the list was made
            if live_game.egg_gone(item):
                await interaction.response.send_message(t("eggs.not_found"), ephemeral=True)
                return
        elif len(item[1]) > 1000:  # the pets of this catalog egg don't fit in the form: never cut the list
            await interaction.response.send_message(t("rbx.egg_preset_too_long", name=item[0]), ephemeral=True)
            return
        self.view.hold_for_form()
        modal = EggModal(egg=item, source=self.view) if self.kind == "edit" else EggModal(preset=item, source=self.view)
        await interaction.response.send_modal(modal)


class RemoveSelect(discord.ui.Select):
    """Removes an egg or stops an event."""

    def __init__(self, kind: str, rows):
        self.kind = kind
        options = [discord.SelectOption(label=r["name"][:100], value=str(r["id"]),
                                        description=(f"{r['price']:,} {r['currency']}" if kind == "egg"
                                                     else live_game.multipliers_text(json.loads(r["multipliers"])))[:100])
                   for r in rows[:MAX_OPTIONS]]
        super().__init__(placeholder=t(f"rbx.remove_{kind}_ph"), min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.view is not None:
            self.view.stop()
        await interaction.response.defer()  # the answer replaces this menu
        item_id = int(self.values[0])
        if self.kind == "egg":
            row = await database.get_egg(item_id)
            done = row and await database.remove_egg(item_id)
            ok, error = await live_game.push_live("eggs")
            text = t("eggs.removed", name=row["name"]) if done else t("eggs.not_found")
        else:
            done = await database.stop_live_event(item_id)
            ok, error = await live_game.push_live("events")
            text = t("events.stopped") if done else t("events.not_found")
        text += "\n" + live_game.sync_note(ok, error)
        await show_in_place(interaction, view=CloseView(), content=text)
        if done:
            await action_log.discord_action(interaction, "egg_remove" if self.kind == "egg" else "event_stop", text)


def _add_kit_warning(embed: discord.Embed) -> None:
    """Eggs and events need a current DiscordCodes file in the game: say so at the top of their windows."""
    warning = roblox_kit.live_file_warning()
    if warning:
        embed.add_field(name=f"⚠️ {t('rbx.step_kit')}", value=warning[:1024], inline=False)


class EggsView(StaffView):

    permission = "eggs"
    def __init__(self):
        super().__init__()
        self.new.label = t("rbx.btn_new_egg")
        self.copy.label = t("rbx.btn_preset_egg")
        self.edit.label = t("rbx.btn_edit_egg")
        self.remove.label = t("rbx.btn_remove_egg")
        if not catalog.egg_presets():
            self.remove_item(self.copy)  # the game catalog lists no eggs: nothing to copy

    async def embed(self) -> discord.Embed:
        scan = roblox_kit.game_scan()
        eco = economy()
        rows = await database.get_active_eggs()
        embed = discord.Embed(title=t("rbx.eggs_title"), description=t("rbx.eggs_intro"), color=_color())
        _add_kit_warning(embed)
        if not scan:
            embed.add_field(name=t("rbx.no_scan_title"), value=t("rbx.no_scan_hint"), inline=False)
        else:
            embed.add_field(name=t("rbx.eggs_spots"), value=(_join(scan["spots"]) if scan["spots"] else t("rbx.eggs_spots_none")),
                            inline=False)
            embed.add_field(name=t("rbx.eggs_models"), value=(_join(scan["templates"]) if scan["templates"]
                                                              else t("rbx.eggs_models_none")), inline=False)
            if roblox_kit.has_hook(scan, "OnHatch"):
                pets = t("rbx.eggs_pets_hook")
            elif roblox_kit.has_hook(scan, "OnReward"):
                pets = t("rbx.eggs_pets_reward")
            else:
                names = eco.get("pets", [])
                marks = [roblox_kit.name_mark(scan, p, item=True) for p in names[:20]]
                pets = t("rbx.eggs_pets_values") + ("\n" + ", ".join(marks) if marks else "\n" + t("rbx.eggs_pets_none"))
            embed.add_field(name=t("rbx.eggs_pets"), value=pets[:1024], inline=False)
            if roblox_kit.has_hook(scan, "OnSpend"):
                pay = t("rbx.eggs_pay_hook")
            else:
                marks = [roblox_kit.name_mark(scan, c) for c in eco.get("currencies", [])[:20]]
                pay = t("rbx.eggs_pay_values") + ("\n" + ", ".join(marks) if marks else "")
            embed.add_field(name=t("rbx.eggs_pay"), value=pay[:1024], inline=False)
        active = [f"🥚 **{r['name']}** — {r['price']:,} {r['currency']} ({len(json.loads(r['pets']))} 🐾)" for r in rows[:15]]
        embed.add_field(name=t("rbx.eggs_active", count=len(rows)), value=_lines(active, 1024) or t("eggs.list_empty"),
                        inline=False)
        embed.set_footer(text=t("rbx.eggs_footer"))
        return embed

    @discord.ui.button(label="New egg", emoji="🥚", style=discord.ButtonStyle.success, row=0)
    async def new(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EggModal())

    @discord.ui.button(label="Egg from the game catalog", emoji="📋", style=discord.ButtonStyle.success, row=0)
    async def copy(self, interaction: discord.Interaction, button: discord.ui.Button):
        presets = catalog.egg_presets()
        if not presets:
            await interaction.response.send_message(t("rbx.egg_no_presets"), ephemeral=True)
            return
        view = StaffView(permission="eggs")
        view.add_item(EggPickSelect("preset", presets))
        note = "\n" + t("rbx.egg_presets_limited", total=len(presets)) if len(presets) > MAX_OPTIONS else ""
        await send_panel(interaction, view, content=t("rbx.egg_pick_preset") + note)

    @discord.ui.button(label="Edit an egg", emoji="✏️", style=discord.ButtonStyle.primary, row=0)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        rows = await database.get_active_eggs()
        if not rows:
            await interaction.response.send_message(t("eggs.list_empty"), ephemeral=True)
            return
        if len(rows) == 1:  # one egg: straight to its form
            await interaction.response.send_modal(EggModal(egg=rows[0]))
            return
        view = StaffView(permission="eggs")
        view.add_item(EggPickSelect("edit", rows))
        await send_panel(interaction, view, content=t("rbx.egg_pick_edit"))

    @discord.ui.button(label="Remove an egg", emoji="🗑️", style=discord.ButtonStyle.secondary, row=1)
    async def remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        rows = await database.get_active_eggs()
        if not rows:
            await interaction.response.send_message(t("eggs.list_empty"), ephemeral=True)
            return
        view = StaffView(permission="eggs")
        view.add_item(RemoveSelect("egg", rows))
        await send_panel(interaction, view, content=t("rbx.remove_egg_ph"))


# ---------- Events ----------

def multiplier_options(scan) -> list:
    """(value, label, description) for the event modal: every currency, all currencies, EXP and luck in eggs."""
    options = []
    declared = catalog.names(catalog.game_catalog(), "multipliers")
    known = scan is not None or bool(declared)
    scan = scan or {"multipliers": []}
    for currency in catalog.names_for("currencies", economy().get("currencies", []))[:20]:
        works = not known or roblox_kit.uses_multiplier(scan, currency, declared)
        options.append((f"currency:{currency}", f"{'✅' if works else '⚠️'} {currency}",
                        t("rbx.mult_works") if known and works else t("rbx.mult_unknown") if not known else t("rbx.mult_missing")))
    works = not known or roblox_kit.uses_multiplier(scan, "*", declared)
    options.append((f"currency:{live_game.ALL_CURRENCIES}", f"{'✅' if works else '⚠️'} {t('events.all_currencies')}",
                    t("rbx.mult_all_desc")))
    works = not known or roblox_kit.uses_multiplier(scan, "exp", declared)
    options.append(("exp", f"{'✅' if works else '⚠️'} EXP",
                    t("rbx.mult_works") if known and works else t("rbx.mult_unknown") if not known else t("rbx.mult_missing")))
    options.append(("luck", f"✅ {t('rbx.mult_luck')}", t("rbx.mult_luck_desc")))
    return options


class EventAnimationSelect(discord.ui.Select):
    """The first step of a new event: the animation the players see (a form holds 5 fields at most and the event's
    form is full, so the choice comes before it)."""

    def __init__(self):
        options = [discord.SelectOption(label=t("rbx.event_no_animation")[:100], value="none",
                                        description=t("rbx.event_no_animation_desc")[:100], emoji="➖")]
        options += [discord.SelectOption(label=live_game.animation_name(key)[:100], value=key,
                                         description=t(f"rbx.event_anim_desc.{key}")[:100])
                    for key in live_game.ANIMATIONS]
        super().__init__(placeholder=t("rbx.event_animation_ph"), min_values=1, max_values=1, options=options[:MAX_OPTIONS])

    async def callback(self, interaction: discord.Interaction):
        self.view.hold_for_form()  # the form answers in this panel: time to fill it in
        animation = "" if self.values[0] == "none" else self.values[0]
        await interaction.response.send_modal(EventModal(animation, source=self.view))


class EventModal(discord.ui.Modal):
    """A new event: several things at once (e.g. Coins, EXP and luck in eggs) with one multiplier for all of them,
    and the animation picked just before. Different multipliers for different things (2× Coins, 3× EXP): /event-start."""

    def __init__(self, animation: str = "", source=None):
        title = t("rbx.event_modal_title")
        if animation in live_game.ANIMATIONS:  # the short name: "🌸 Sakura Festival" without the words in brackets
            title = f"{title} · {live_game.animation_name(animation).split(' (')[0]}"
        super().__init__(title=title[:45])
        self.animation = animation if animation in live_game.ANIMATIONS else ""
        self.source = source  # the list of animations: the answer replaces it
        scan = roblox_kit.game_scan()
        self.event_name = discord.ui.TextInput(label=t("rbx.event_name"), max_length=50, placeholder=t("rbx.event_name_ph"))
        self.duration = discord.ui.Select(options=[discord.SelectOption(label=t(f"duration.choice.{k}")[:100], value=k,
                                                                        default=k == "1h") for k in live_game.EVENT_DURATIONS])
        # any other time (45m, 2h30m, 2d): typed here, it wins over the list
        self.custom_duration = discord.ui.TextInput(label=t("rbx.event_custom_duration")[:45], required=False, max_length=30,
                                                    placeholder=t("rbx.event_custom_duration_ph")[:100])
        options = multiplier_options(scan)
        # several things at once, nothing picked in advance: a preselected currency would stay next to what the
        # admin picks (e.g. luck x10 would also give Coins x10)
        self.kind = discord.ui.Select(options=[discord.SelectOption(label=label[:100], value=value[:100], description=desc[:100])
                                               for value, label, desc in options],
                                      min_values=1, max_values=len(options))
        self.value = discord.ui.Select(options=[discord.SelectOption(label=f"{m}×", value=m, default=m == "2")
                                                for m in live_game.MULTIPLIERS])
        self.add_item(self.event_name)
        self.add_item(discord.ui.Label(text=t("rbx.event_duration"), component=self.duration))
        self.add_item(self.custom_duration)
        self.add_item(discord.ui.Label(text=t("rbx.event_kind"), component=self.kind))
        self.add_item(discord.ui.Label(text=t("rbx.event_value"), component=self.value))

    async def on_submit(self, interaction: discord.Interaction):
        if not await staff_only(interaction, "events"):  # the role may have been taken away while the form was open
            return
        if self.source is not None:
            await defer_for(interaction, self.source)
        else:
            await interaction.response.defer(ephemeral=True, thinking=True)
        value = float(self.value.values[0]) if self.value.values else 2.0
        multipliers = {kind: value for kind in self.kind.values}
        try:
            duration = self.custom_duration.value.strip() or (self.duration.values[0] if self.duration.values else "1h")
            embed, event_id = await live_game.start_event(self.event_name.value, duration, multipliers,
                                                          interaction.user.id, with_id=True, animation=self.animation)
        except live_game.RuleError as e:
            await _answer(interaction, self.source, content=live_game.error_text(e))
            return
        embed.set_footer(text=t("rbx.event_more_options"))
        await _answer(interaction, self.source, embed=embed, view=EventDoneView(event_id))
        await action_log.discord_action(interaction, "event_start", embed)


class EventDoneView(StaffView):
    """Under a started event: end it early without looking for it in a list."""

    permission = "events"

    def __init__(self, event_id: int):
        super().__init__()
        self.event_id = event_id
        self.end.label = t("rbx.btn_end_this_event")

    @discord.ui.button(label="End this event", emoji="⏹️", style=discord.ButtonStyle.danger)
    async def end(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.defer()
        done = await database.stop_live_event(self.event_id)
        ok, error = await live_game.push_live("events")
        text = t("events.stopped") if done else t("events.not_found")
        text += "\n" + live_game.sync_note(ok, error)
        await show_in_place(interaction, view=CloseView(), content=text, embed=None)
        if done:
            await action_log.discord_action(interaction, "event_stop", text)


class EventsView(StaffView):

    permission = "events"
    def __init__(self):
        super().__init__()
        self.new.label = t("rbx.btn_new_event")
        self.stop_event.label = t("rbx.btn_stop_event")

    async def embed(self) -> discord.Embed:
        scan = roblox_kit.game_scan()
        rows = await database.get_active_live_events()
        embed = discord.Embed(title=t("rbx.events_title"), description=t("rbx.events_intro"), color=_color())
        _add_kit_warning(embed)
        if not scan:
            embed.add_field(name=t("rbx.no_scan_title"), value=t("rbx.no_scan_hint"), inline=False)
        lines = [f"{label} — {desc}" for _, label, desc in multiplier_options(scan)]
        embed.add_field(name=t("rbx.events_support"), value="\n".join(lines)[:1024], inline=False)
        embed.add_field(name=t("rbx.events_how"), value=t("rbx.events_code"), inline=False)
        active = [f"⚡ **{r['name']}** — {live_game.multipliers_text(json.loads(r['multipliers']))} • <t:{r['ends_at']}:R>"
                  + (f" • ✨ {live_game.animation_name(r['animation'])}" if live_game.animation_name(r["animation"]) else "")
                  for r in rows[:10]]
        embed.add_field(name=t("rbx.events_active", count=len(rows)), value=_lines(active) or t("events.list_empty"),
                        inline=False)
        return embed

    @discord.ui.button(label="New event", emoji="⚡", style=discord.ButtonStyle.success, row=0)
    async def new(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = StaffView(permission="events")
        view.add_item(EventAnimationSelect())
        await send_panel(interaction, view, content=t("rbx.event_pick_animation"))

    @discord.ui.button(label="Stop an event", emoji="⏹️", style=discord.ButtonStyle.secondary, row=0)
    async def stop_event(self, interaction: discord.Interaction, button: discord.ui.Button):
        rows = await database.get_active_live_events()
        if not rows:
            await interaction.response.send_message(t("events.list_empty"), ephemeral=True)
            return
        view = StaffView(permission="events")
        view.add_item(RemoveSelect("event", rows))
        await send_panel(interaction, view, content=t("rbx.remove_event_ph"))


# ---------- Gifts and announcements ----------

class GiftModal(discord.ui.Modal):
    """A gift without typing a command: the player, a currency with its amount, an item and a message. The answer is a
    draft (GiftDraftView) with the exact account: EXP and the item's time are added there (⚙️, a form holds at most 5
    parts) and the player gets nothing before ✅ Send."""

    def __init__(self, target: tuple = None):
        super().__init__(title=t("rbx.gift_modal_title"))
        eco = economy()
        # target = (user_id, username) from the player card: the gift goes to that exact account unless the admin
        # types another player. A Roblox user ID may be shorter than a username, "@" + 20 characters must fit.
        self.target = target
        self.player = discord.ui.TextInput(label=t("rbx.gift_player"), min_length=1, max_length=25,
                                           placeholder=t("rbx.gift_player_ph"), default=target[1] if target else None)
        self.currency = _optional_pick(t("rbx.gift_currency"), catalog.names_for("currencies", eco.get("currencies", [])))
        self.amount = discord.ui.TextInput(label=t("rbx.gift_amount"), max_length=15, required=False, placeholder="1000")
        self.item = _optional_pick(t("rbx.gift_item"), catalog.reward_names(eco.get("items", []), eco.get("pets", [])))
        self.message = discord.ui.TextInput(label=t("rbx.gift_message"), max_length=150, required=False)
        self.add_item(self.player)
        _add_pick(self, t("rbx.gift_currency"), self.currency)
        self.add_item(self.amount)
        _add_pick(self, t("rbx.gift_item"), self.item, t("rbx.gift_item_hint"))
        self.add_item(self.message)

    async def on_submit(self, interaction: discord.Interaction):
        if not await staff_only(interaction, "gifts"):  # the role may have been taken away while the form was open
            return
        currency = _pick_value(self.currency)
        item = _pick_value(self.item)
        amount = _price(self.amount.value)
        if amount > live_game.MAX_AMOUNT:  # the same limit as the amount of /give
            await interaction.response.send_message(t("give.err_amount", max=f"{live_game.MAX_AMOUNT:,}"), ephemeral=True)
            return
        if (currency != NONE) != (amount > 0):  # a currency without an amount (or the other way) gives nothing
            await interaction.response.send_message(t("codes.err_currency_amount"), ephemeral=True)
            return
        draft = {"currency": currency, "amount": amount, "exp": 0, "item": item, "item_key": "permanent",
                 "message": self.message.value.strip()}
        try:  # a name the game catalog doesn't have is refused now; an empty reward only at ✅ (EXP may still come)
            reward = live_game.check_reward(gift_reward(draft))
        except live_game.RuleError as e:
            await interaction.response.send_message(live_game.error_text(e), ephemeral=True)
            return
        if "currency" in reward:
            draft["currency"] = reward["currency"]["name"]
        if "item" in reward:
            draft["item"] = reward["item"]["name"]
        await interaction.response.defer(ephemeral=True, thinking=True)
        player = self.player.value.strip()
        try:  # the exact account is shown in the draft before anything reaches the game
            draft["user"] = self.target if self.target and player == self.target[1] else \
                await live_game.find_player(player, by_id=True)
        except live_game.RuleError as e:
            await send_panel(interaction, CloseView(), content=live_game.error_text(e))
            return
        await send_panel(interaction, GiftDraftView(interaction.user.id, draft), embed=gift_draft_embed(draft))


def gift_reward(draft: dict) -> dict:
    return live_game.build_reward(draft["currency"], draft["amount"], draft["exp"], draft["item"], draft["item_key"])


def gift_draft_embed(draft: dict) -> discord.Embed:
    """A gift from the form before it is sent: the player gets nothing until ✅ Send the gift."""
    reward = gift_reward(draft)
    user_id, username = draft["user"]
    embed = discord.Embed(title=t("give.draft_title")[:256], color=discord.Color.orange(),
                          description=t("give.draft_description", username=discord.utils.escape_markdown(username),
                                        user_id=user_id))
    embed.add_field(name=t("codes.rewards"), value=live_game.reward_text(reward, show_permanent=True)
                    or t("give.draft_no_reward"), inline=False)
    if draft["message"]:
        embed.add_field(name=t("give.message"), value=draft["message"][:1024], inline=False)
    warnings = roblox_kit.reward_warnings(roblox_kit.game_scan(), reward) + catalog.robux_warnings(reward, gift=True) if reward else []
    if live_game.has_link(draft["message"]):
        warnings = warnings + [t("give.link_warning")]
    if warnings:
        embed.add_field(name=t("codes.draft_warnings"), value=live_game.warnings_text(warnings)[:1024], inline=False)
    embed.set_thumbnail(url=f"https://www.roblox.com/headshot-thumbnail/image?userId={user_id}&width=150&height=150&format=png")
    embed.set_footer(text=t("give.draft_footer"))
    return embed


class GiftExtrasModal(discord.ui.Modal):
    """EXP and how long the item lasts: the parts of a gift that don't fit in the first form (5 fields at most).
    Changes only the draft: the gift reaches the game when the admin clicks ✅ Send."""

    def __init__(self, view: "GiftDraftView"):
        draft = view.draft
        super().__init__(title=t("give.extras_title", player=draft["user"][1])[:45])
        self.draft_view = view
        self.exp = discord.ui.TextInput(label=t("give.extras_exp")[:45], max_length=15, required=False, placeholder="1000",
                                        default=str(draft["exp"]) if draft["exp"] else None)
        self.add_item(self.exp)
        self.duration = None
        if draft["item"] != NONE:
            self.duration = discord.ui.Select(options=[
                discord.SelectOption(label=t(f"duration.choice.{key}")[:100], value=key, default=key == draft["item_key"])
                for key in game_codes.ITEM_DURATIONS])
            self.add_item(discord.ui.Label(text=t("give.extras_duration"), component=self.duration))
        self.message = discord.ui.TextInput(label=t("give.extras_message")[:45], max_length=150, required=False,
                                            default=draft["message"] or None)
        self.add_item(self.message)

    async def on_submit(self, interaction: discord.Interaction):
        if not await staff_only(interaction, "gifts"):
            return
        view = self.draft_view
        if view.closed:  # ⚙️ opened, then the draft was sent or cancelled before this form was sent
            await interaction.response.send_message(t("give.draft_closed"), ephemeral=True)
            return
        digits = re.sub(r"[\s_.,]", "", self.exp.value or "")
        if digits and (not (digits.isascii() and digits.isdigit()) or int(digits) > live_game.MAX_AMOUNT):
            await interaction.response.send_message(t("codes.err_exp", max=f"{live_game.MAX_AMOUNT:,}"), ephemeral=True)
            return
        view.draft = dict(view.draft, exp=int(digits or 0), message=self.message.value.strip())
        if self.duration is not None and self.duration.values:
            view.draft["item_key"] = self.duration.values[0]
        if view.is_finished():  # the draft removed itself while the form was open: nothing is lost, a new one comes
            view = GiftDraftView(view.admin_id, view.draft)
            await send_panel(interaction, view, embed=gift_draft_embed(view.draft))
            return
        await interaction.response.defer()
        await show_in_place(interaction, view=view, embed=gift_draft_embed(view.draft))


class GiftDraftView(Panel):
    """A gift from the form, not sent yet: ⚙️ adds EXP or the item's time, ✅ sends it to the game, Cancel drops it.
    Everything happens in this one message: the draft becomes the "Gift sent" card."""
    close_button = False  # its Cancel removes the message

    def __init__(self, admin_id: int, draft: dict):
        super().__init__()
        self.admin_id, self.draft = admin_id, draft
        self.closed = False  # sent or cancelled (not just removed after a while)
        self.confirm.label = t("give.btn_send")
        self.extras.label = t("give.btn_extras")
        self.cancel.label = t("common.cancel")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await game_codes.owner_and_staff(interaction, self.admin_id, "gifts")

    @discord.ui.button(label="Send the gift", emoji="✅", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.closed:  # a double click: the first one already sends the gift
            await interaction.response.send_message(t("give.draft_closed"), ephemeral=True)
            return
        reward = gift_reward(self.draft)
        if not reward:
            await interaction.response.send_message(t("give.no_reward"), ephemeral=True)
            return
        try:  # checked again: the game catalog may have changed since the form; above the game's limit: refused
            reward = live_game.check_reward(reward)
            live_game.check_limit(reward)
        except live_game.RuleError as e:
            await interaction.response.send_message(live_game.error_text(e), ephemeral=True)
            return
        self.closed = True
        self.stop()
        await interaction.response.defer()  # the draft message itself turns into the answer
        try:
            embed = await live_game.send_gift(self.draft["user"], reward, self.draft["message"],
                                              interaction.user.display_name, interaction.user.id)
        except live_game.RuleError as e:  # nothing reached the game: the draft comes back, so ✅ can be tried again
            draft = GiftDraftView(self.admin_id, self.draft)
            await show_in_place(interaction, view=draft, content=live_game.error_text(e), embed=gift_draft_embed(self.draft))
            return
        await show_in_place(interaction, view=CloseView(), content=None, embed=embed)
        await action_log.discord_action(interaction, "gift", embed)

    @discord.ui.button(label="EXP and item time", emoji="⚙️", style=discord.ButtonStyle.secondary)
    async def extras(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.hold_for_form()
        await interaction.response.send_modal(GiftExtrasModal(self))

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.closed = True
        self.stop()
        await close_message(interaction, t("give.draft_cancelled"))


class AnnounceModal(discord.ui.Modal):
    """text, seconds: what to fill in again after a link was refused. in_place: opened from ✏️ Fix, so the answer
    replaces that message (one flow, one message)."""

    def __init__(self, text: str = None, seconds: int = 10, in_place: bool = False):
        super().__init__(title=t("rbx.announce_modal_title"))
        self.in_place = in_place
        self.text = discord.ui.TextInput(label=t("rbx.announce_text"), style=discord.TextStyle.paragraph, max_length=200,
                                         default=text, placeholder=t("rbx.announce_text_ph")[:100])
        self.seconds = discord.ui.Select(options=[discord.SelectOption(label=f"{s} s", value=str(s), default=s == seconds)
                                                  for s in live_game.ANNOUNCE_SECONDS])
        self.add_item(self.text)
        self.add_item(discord.ui.Label(text=t("rbx.announce_seconds"), component=self.seconds))

    async def on_submit(self, interaction: discord.Interaction):
        if not await staff_only(interaction, "announce"):  # the role may have been taken away while the form was open
            return
        if self.in_place:
            await interaction.response.defer()
        else:
            await interaction.response.defer(ephemeral=True, thinking=True)
        seconds = int(self.seconds.values[0]) if self.seconds.values else 10
        view, sent = CloseView(), False
        try:
            content, sent = await live_game.announce(self.text.value, seconds), True
        except live_game.LinkError as e:  # the text comes back in the form, nothing to type again
            view, content = AnnounceFixView(self.text.value, seconds), live_game.error_text(e)
        except live_game.RuleError as e:
            content = live_game.error_text(e)
        if self.in_place:
            await show_in_place(interaction, view=view, content=content)
        else:
            await send_panel(interaction, view, content=content)
        if sent:
            await action_log.discord_action(interaction, "announce", content)


class AnnounceFixView(StaffView):
    """Under an announcement refused for a link: ✏️ Fix opens the form again with the text and the seconds; Send anyway
    is for a text the check took for a link by mistake (e.g. a game name with a dot)."""

    permission = "announce"

    def __init__(self, text: str, seconds: int):
        super().__init__()
        self.text, self.seconds = text, seconds
        self.sent = False
        self.fix.label = t("rbx.btn_fix_announcement")
        self.send_anyway.label = t("rbx.btn_send_anyway")

    @discord.ui.button(label="Fix", emoji="✏️", style=discord.ButtonStyle.primary)
    async def fix(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.hold_for_form()
        await interaction.response.send_modal(AnnounceModal(self.text, self.seconds, in_place=True))

    @discord.ui.button(label="Send anyway", style=discord.ButtonStyle.secondary)
    async def send_anyway(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.sent:  # a double click: the first one already sends it
            await interaction.response.send_message(t("announce.already_sent"), ephemeral=True)
            return
        self.sent = True
        self.stop()
        await interaction.response.defer()
        try:
            content = await live_game.announce(self.text, self.seconds, allow_link=True)
        except live_game.RuleError as e:  # nothing was sent: the text stays under ✏️ for another try
            await show_in_place(interaction, view=AnnounceFixView(self.text, self.seconds), content=live_game.error_text(e))
            return
        await show_in_place(interaction, view=CloseView(), content=content)
        await action_log.discord_action(interaction, "announce", content)


class GiftsView(StaffView):

    permission = "gifts"
    def __init__(self):
        super().__init__()
        self.gift.label = t("rbx.btn_gift")
        self.announce.label = t("rbx.btn_announce")

    def embed(self) -> discord.Embed:
        scan = roblox_kit.game_scan()
        embed = discord.Embed(title=t("rbx.gifts_title"), description=t("rbx.gifts_intro"), color=_color())
        if scan:
            exp = roblox_kit.exp_paths(scan)
            embed.add_field(name=t("rbx.gifts_places"), value=(
                (t("rbx.names_hook_reward") if roblox_kit.has_hook(scan, "OnReward") else t("rbx.gifts_places_auto"))
                + "\n" + (t("rbx.names_exp_ok", paths=_join(exp, 200)) if exp else t("rbx.names_exp_missing")))[:1024], inline=False)
        else:
            embed.add_field(name=t("rbx.no_scan_title"), value=t("rbx.no_scan_hint"), inline=False)
        embed.add_field(name=t("rbx.gifts_commands"), value=t("rbx.gifts_commands_text"), inline=False)
        return embed

    @discord.ui.button(label="Send a gift", emoji="🎁", style=discord.ButtonStyle.success, row=0)
    async def gift(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GiftModal())

    @discord.ui.button(label="Announcement", emoji="📢", style=discord.ButtonStyle.success, row=0)
    async def announce(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AnnounceModal())


# ---------- Bans and leaderboard ----------

async def ban_permission() -> tuple:
    """(ok, message): checks the API key's user-restrictions permission with a harmless read."""
    try:
        await open_cloud.get_ban(1)
    except open_cloud.OpenCloudError as e:
        return False, str(e)
    return True, t("rbx.bans_ok")


async def open_player_lookup(interaction: discord.Interaction):
    """The player card's first step (a username or an ID). cogs/roblox_admin.py is imported on click: it imports this
    module itself."""
    from cogs.roblox_admin import PlayerLookupModal
    await interaction.response.send_modal(PlayerLookupModal())


class BansView(AdminView):
    def __init__(self):
        super().__init__()
        self.find.label = t("rbx.btn_find_player")
        self.test.label = t("rbx.btn_test_permission")

    def embed(self) -> discord.Embed:
        embed = discord.Embed(title=t("rbx.bans_title"), description=t("rbx.bans_intro"), color=_color())
        embed.add_field(name=t("rbx.bans_permission"), value=t("rbx.bans_permission_text"), inline=False)
        embed.add_field(name=t("rbx.gifts_commands"), value=t("rbx.bans_commands"), inline=False)
        return embed

    @discord.ui.button(label="Find a player", emoji="🔍", style=discord.ButtonStyle.success, row=0)
    async def find(self, interaction: discord.Interaction, button: discord.ui.Button):
        await open_player_lookup(interaction)

    @discord.ui.button(label="Check the permission", emoji="🧪", style=discord.ButtonStyle.secondary, row=0)
    async def test(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        ok, message = await ban_permission()
        await send_panel(interaction, CloseView(), content=("✅ " if ok else "❌ ") + message)


class RankingView(AdminView):
    def __init__(self):
        super().__init__()
        self.connect.label = t("rbx.btn_connect_board")

    def embed(self) -> discord.Embed:
        board = config_store.load().get("leaderboard", {})
        embed = discord.Embed(title=t("rbx.board_title"), description=t("rbx.board_intro"), color=_color())
        embed.add_field(name=t("rbx.board_find"), value=t("rbx.board_find_text"), inline=False)
        embed.add_field(name=t("rbx.board_now"), value=(t("rbx.sum_board", datastore=board["datastore"]) if board.get("datastore")
                                                         else t("rbx.sum_board_off")), inline=False)
        return embed

    @discord.ui.button(label="Connect the leaderboard", emoji="🏆", style=discord.ButtonStyle.success, row=0)
    async def connect(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.roblox_admin import LeaderboardModal
        await interaction.response.send_modal(LeaderboardModal())


# ---------- Check everything ----------

async def run_checks() -> discord.Embed:
    lines = []
    cfg = config_store.load()
    roblox = cfg.get("roblox", {})
    lines.append(t("rbx.chk_game_ok") if roblox.get("universe_id") else t("rbx.chk_game_missing"))
    status = cloud_sync.status()
    if status != "ready":
        lines.append(t(f"rbx.chk_sync_{status}"))
        lines.append(t("rbx.chk_rest_needs_sync"))
        return _checks_embed(lines)

    state = await roblox_kit.refresh(force=True)
    lines.append(t("rbx.chk_read_error", error=state["error"]) if state.get("error") else t("rbx.chk_read_ok"))
    sync_state = cloud_sync.load_state()
    if sync_state.get("last_error"):
        lines.append(t("rbx.chk_write_error", error=sync_state["last_error"]))
    elif sync_state.get("last_ok"):
        lines.append(t("rbx.chk_write_ok"))
    else:
        lines.append(t("rbx.chk_write_unknown"))
    try:
        await open_cloud.publish({"type": "ping"})
        lines.append(t("rbx.chk_publish_ok"))
    except open_cloud.OpenCloudError as e:
        lines.append(t("rbx.chk_publish_error", error=e))

    kit = roblox_kit.evaluate()
    kit_line = roblox_kit.status_line(kit)
    lines.append(("✅ " if kit["status"] == "ok" else "⚠️ ") + kit_line if kit_line else t("rbx.chk_kit_unknown"))

    scan = roblox_kit.game_scan()
    if not scan:
        lines.append(t("rbx.chk_scan_missing"))
    else:
        lines.append(t("rbx.chk_scan_ok", names=len(scan["values"]) + len(scan["attributes"]), time=f"<t:{scan['at']}:R>"))
        eco = economy()
        if not roblox_kit.has_hook(scan, "OnReward"):
            missing = [c for c in eco.get("currencies", []) if not roblox_kit.find_name(scan, c)]
            if missing:
                lines.append(t("rbx.chk_currencies_missing", names=_join(missing, 300)))
            elif eco.get("currencies"):
                lines.append(t("rbx.chk_currencies_ok"))
        eggs = await database.get_active_eggs()
        for egg in eggs:
            for warning in roblox_kit.egg_warnings(scan, egg["currency"], [p["name"] for p in json.loads(egg["pets"])]):
                lines.append(f"⚠️ 🥚 {egg['name']}: {warning}")
        too_few = roblox_kit.spots_warning(scan, len(eggs))
        if too_few:
            lines.append(f"⚠️ 🥚 {too_few}")
        declared = catalog.names(catalog.game_catalog(), "multipliers")
        for event in await database.get_active_live_events():
            for warning in roblox_kit.event_warnings(scan, json.loads(event["multipliers"]), declared):
                lines.append(f"⚠️ ⚡ {event['name']}: {warning}")
    lines += await catalog_checks()

    ok, message = await ban_permission()
    lines.append(t("rbx.chk_bans_ok") if ok else t("rbx.chk_bans_missing"))
    board = cfg.get("leaderboard", {})
    if board.get("datastore"):
        try:
            await open_cloud.top_entries(board["datastore"], board.get("scope") or "global", 1)
            lines.append(t("rbx.chk_board_ok", datastore=board["datastore"]))
        except open_cloud.OpenCloudError as e:
            lines.append(t("rbx.chk_board_error", error=e))
    else:
        lines.append(t("rbx.chk_board_off"))
    return _checks_embed(lines)


async def catalog_checks() -> list:
    """The game catalog in "Check everything": is there one, what to fix in it, and active codes or eggs with names
    the catalog doesn't have (they can't work in the game)."""
    cat = catalog.game_catalog()
    if cat is None:
        return [t("catalog.chk_unknown")]
    if cat["missing"]:
        return [t("catalog.chk_missing")]
    lines = [t("catalog.chk_ok", summary=catalog.summary(cat))]
    lines += [f"⚠️ 📒 {p}" for p in catalog.problems(cat)[:10]]
    for code in await database.get_active_game_codes():
        for kind, name in (("currencies", code["reward_currency"]), ("reward_item", code["reward_item"])):
            if name and catalog.resolve(kind, name, cat)[1]:
                lines.append(t("catalog.chk_code_unknown", code=code["code"], name=name))
        sold = catalog.robux_rewards({"currency": {"name": code["reward_currency"]}, "item": {"name": code["reward_item"]}}, cat)
        if sold:  # a code made before the name was added to SoldForRobux
            lines.append(t("catalog.chk_code_robux", code=code["code"], names=", ".join(sold)))
    for egg in await database.get_active_eggs():
        unknown = [p["name"] for p in json.loads(egg["pets"]) if catalog.resolve("pets", p["name"], cat)[1]]
        if catalog.resolve("currencies", egg["currency"], cat)[1]:
            unknown.append(egg["currency"])
        if unknown:
            lines.append(t("catalog.chk_egg_unknown", egg=egg["name"], names=", ".join(unknown[:10])))
    return lines


def _checks_embed(lines: list) -> discord.Embed:
    problems = sum(1 for line in lines if line.startswith("❌"))
    warnings = sum(1 for line in lines if line.startswith("⚠️"))
    color = discord.Color.red() if problems else discord.Color.orange() if warnings else discord.Color.green()
    embed = discord.Embed(title=t("rbx.chk_title"), description="\n".join(lines)[:4000], color=color)
    embed.set_footer(text=t("rbx.chk_footer", problems=problems, warnings=warnings))
    return embed


class SetupRoblox(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup-roblox", description=L("cmd.setup_roblox"))
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def setup_roblox(self, interaction: discord.Interaction):
        await send_roblox_panel(interaction)


async def setup(bot):
    await bot.add_cog(SetupRoblox(bot))
