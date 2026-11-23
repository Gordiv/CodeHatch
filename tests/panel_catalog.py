"""One list of every window (ui.Panel) the bot has, built with sample data, for the layout and access tests.

`covered_classes(build_windows())` is the set of classes this file builds. tests/test_panel_catalog.py fails when a new window class is
added to the bot without being added here, so a new window can't skip the layout and the access checks."""
import importlib
import json
import pkgutil
import sys
from unittest import mock

import discord

from tests import fakes
from tests.panel_fakes import Guild, Role, TextChannel
from utils import database, ui

BASES = {ui.Panel, ui.AdminView, ui.StaffView}


def import_every_module():
    """Imports every cogs/*.py that can be imported ."""
    import cogs
    modules = []
    for info in pkgutil.iter_modules(cogs.__path__):
        modules.append(importlib.import_module(f"cogs.{info.name}"))
    return modules


def _current(cls) -> bool:
    """The class is the one the module has now (another test may have loaded a module twice, leaving an old copy)."""
    module = sys.modules.get(cls.__module__)
    return module is not None and getattr(module, cls.__name__, None) is cls


def all_window_classes() -> set:
    """Every subclass of ui.Panel defined in the bot, except the three base classes."""
    found, queue = set(), list(ui.Panel.__subclasses__())
    while queue:
        cls = queue.pop()
        if cls in found:
            continue
        found.add(cls)
        queue.extend(cls.__subclasses__())
    return {cls for cls in found if cls not in BASES and cls.__module__.split(".")[0] in ("cogs", "utils") and _current(cls)}


def all_modal_classes() -> set:
    found, queue = set(), list(discord.ui.Modal.__subclasses__())
    while queue:
        cls = queue.pop()
        if cls in found:
            continue
        found.add(cls)
        queue.extend(cls.__subclasses__())
    return {cls for cls in found if cls.__module__.split(".")[0] in ("cogs", "utils") and _current(cls)}


class Row(dict):
    """A database row as the windows read it."""


async def build_windows(guild: Guild = None, owner_id: int = 7) -> list:
    """[(name, window)] for every window class of the bot, built in the language set by the caller.
    owner_id: the person who "opened" the windows that belong to one person (a code draft, the role panel...)."""
    # by name from sys.modules (another test may have loaded a module again, as discord.py's load_extension does)
    game_codes, game_panel, roblox_admin, setup, setup_guide, setup_roblox, tutorial = (
        importlib.import_module(f"cogs.{name}") for name in (
            "game_codes", "game_panel", "roblox_admin", "setup", "setup_guide", "setup_roblox", "tutorial"))
    guild = guild or Guild([Role(300 + i, f"Role {i}", members=i) for i in range(30)], [TextChannel(700)])
    admin = type("Owner", (), {"id": owner_id, "mention": f"<@{owner_id}>", "display_name": "Owner", "guild": guild,
                               "guild_permissions": discord.Permissions(administrator=True)})()
    cog = game_codes.GameCodes.__new__(game_codes.GameCodes)
    cog.bot = mock.Mock(get_cog=lambda name: None)
    for index in range(30):  # many long codes: the remove window shows 25
        await cog.store_code(admin, f"CODE{index}".ljust(50, "X"), "24h", "Name0_" + "x" * 80, 10 ** 9, 10 ** 9,
                             "Name1_" + "x" * 80, "30d")
    codes = list(await database.get_active_game_codes())
    params = game_codes.code_params("SAFE", "7d", "Coins", 5)
    rows = [Row(id=i, name="Name " + "x" * 120, price=10 ** 9, currency="Coins", multipliers=json.dumps({"exp": 2.0}))
            for i in range(30)]
    cards = [roblox_admin.PlayerCardView(4242, "Builderman", banned) for banned in (True, False, None)]

    windows = [
        ("CloseView", ui.CloseView()),
        ("setup.PanelView", setup.PanelView()),
        ("setup.ChannelsView", setup.ChannelsView()),
        ("setup.CloudSyncView", setup.CloudSyncView()),
        ("setup.ServersView", setup.ServersView(mock.Mock(get_guild=lambda guild_id: None), guild)),
        ("setup_guide.GuideView", setup_guide.GuideView(0x00A2FF, 0)),
        ("tutorial.TutorialView", tutorial.TutorialView(guild, 0, None)),
        ("setup_roblox.RobloxPanelView", setup_roblox.RobloxPanelView()),
        ("setup_roblox.GameNamesView", setup_roblox.GameNamesView()),
        ("setup_roblox.CatalogView", setup_roblox.CatalogView()),
        ("setup_roblox.CodesView", setup_roblox.CodesView()),
        ("setup_roblox.EggsView", setup_roblox.EggsView()),
        ("setup_roblox.EggDoneView", setup_roblox.EggDoneView(1)),
        ("pick an egg", _pick_window("edit", rows)),
        ("copy an egg", _pick_window("preset", [("Basic Egg " + "x" * 120, "Cat:60, Dog:40" * 20, "Coins", 100)] * 30)),
        ("setup_roblox.EventsView", setup_roblox.EventsView()),
        ("setup_roblox.EventDoneView", setup_roblox.EventDoneView(1)),
        ("setup_roblox.GiftsView", setup_roblox.GiftsView()),
        ("setup_roblox.AnnounceFixView", setup_roblox.AnnounceFixView("Join us on discord.gg/abc", 15)),
        ("setup_roblox.GiftDraftView", setup_roblox.GiftDraftView(admin.id, {
            "user": (10 ** 11, "N" * 20), "currency": "C" * 100, "amount": 10 ** 9, "exp": 10 ** 9, "item": "I" * 100,
            "item_key": "30d", "message": "M" * 150})),
        ("setup_roblox.BansView", setup_roblox.BansView()),
        ("setup_roblox.RankingView", setup_roblox.RankingView()),
        ("remove an egg", _remove_window("egg", rows)),
        ("stop an event", _remove_window("event", rows)),
        ("roblox_admin.BanConfirmView", roblox_admin.BanConfirmView(None, admin, 1, "Builderman", 86400, "Exploiting", "")),
        ("roblox_admin.PlayerChoiceView", roblox_admin.PlayerChoiceView([(1, "Builderman", "name"), (2, "Roblox", "id")])),
        ("roblox_admin.PlayerCardView banned", cards[0]),
        ("roblox_admin.PlayerCardView not banned", cards[1]),
        ("roblox_admin.PlayerCardView unknown", cards[2]),
        ("roblox_admin.UnbanConfirmView", roblox_admin.UnbanConfirmView(cards[0])),
        ("game_codes.CodeRemoveView", game_codes.CodeRemoveView(cog, admin.id, codes[:25])),
        ("game_codes.OverwriteView", game_codes.OverwriteView(cog, admin.id, params)),
        ("game_codes.CodeDraftView", game_codes.CodeDraftView(cog, admin.id, params)),
        ("game_panel.GamePanelManager", game_panel.GamePanelManager(guild)),
        ("game_panel.PermissionsHubView", game_panel.PermissionsHubView()),
        ("game_panel.RolePermissionsView", game_panel.RolePermissionsView(guild)),
        ("game_panel.ManagerUsersView", game_panel.ManagerUsersView()),
    ]
    return windows


def _remove_window(kind: str, rows: list):
    setup_roblox = importlib.import_module("cogs.setup_roblox")
    view = ui.StaffView(permission="eggs" if kind == "egg" else "events")
    view.add_item(setup_roblox.RemoveSelect(kind, rows))
    return view


def _pick_window(kind: str, items: list):
    setup_roblox = importlib.import_module("cogs.setup_roblox")
    view = ui.StaffView(permission="eggs")
    view.add_item(setup_roblox.EggPickSelect(kind, items))
    return view


def covered_classes(windows: list) -> set:
    """The window classes of build_windows() (the two inline StaffView windows count for StaffView, a base class)."""
    return {type(view) for _, view in windows}
