"""Run by tests/test_click_everything.py inside a TEMPORARY COPY of the bot (never in the real folder): loads main.py the
way the bot does (no login), then clicks every button and menu of the control panel and of /setup-roblox with strict
stand-ins for Discord, opens every window that comes out, submits every form that opens, and presses ✖️ Close on every
window. Prints one JSON line. Nothing connects to Discord, Roblox or Gemini: every network attempt is refused and counted.
Usage: python click_driver.py [en|pl|es]"""
import asyncio
import json
import os
import sys
from unittest import mock

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import aiohttp  # noqa: E402
import discord  # noqa: E402
from discord.ext import tasks  # noqa: E402

import main  # noqa: E402
from tests import fakes  # noqa: E402
from tests.panel_fakes import STAFF, Message, interaction_for, make_guild  # noqa: E402
from utils import access, config_store, database, i18n, net, open_cloud, roblox_api, ui  # noqa: E402

# A click may fail on the network (nothing is connected), but never because of a wrong name, a missing module or a
# wrong argument, and never because the bot answered Discord twice or sent something Discord refuses.
BAD = (ImportError, AttributeError, NameError, TypeError, KeyError, ValueError, IndexError, RuntimeError,
       fakes.DiscordRefused)
MAX_DEPTH = 3
result = {"errors": [], "clicks": 0, "windows": {}, "forms": [], "closed": [], "refused": [],
          "other_exceptions": {}}
attempts = []
COGS = {}  # what interaction.client.get_cog() finds, filled in once the bot has loaded its modules


def no_network():
    attempts.append(1)
    raise aiohttp.ClientConnectionError("the network is off in tests")


net.session = no_network
discord.ui.RoleSelect.values = property(lambda self: self._values)
discord.ui.ChannelSelect.values = property(lambda self: self._values)


def note(where: str, error: BaseException):
    result["errors"].append(f"{where}: {type(error).__name__}: {error}")


def label(item) -> str:
    return str(getattr(item, "label", None) or getattr(item, "custom_id", None) or type(item).__name__)


def prepare(item, guild):
    """Gives a menu a value, like a person choosing one."""
    if isinstance(item, discord.ui.RoleSelect):
        item._values = [guild.get_role(STAFF)]
    elif isinstance(item, discord.ui.ChannelSelect):
        item._values = [guild.get_channel(700)]
    elif isinstance(item, discord.ui.Select) and item.options:
        item._values = [pick(item)]


def pick(select) -> str:
    """The first real choice of a menu (not "none")."""
    return next((o.value for o in select.options if o.value != "none"), select.options[0].value)


async def click(view, item, who, guild, where, message=None):
    """One click, the way discord.py makes it: the window's check first, then the callback. Returns the interaction."""
    inter = interaction_for(guild, who, message=message or Message(), **COGS)
    inter.data = {"custom_id": getattr(item, "custom_id", None)}
    prepare(item, guild)
    result["clicks"] += 1
    try:
        if await view.interaction_check(inter):
            await item.callback(inter)
        else:
            result["refused"].append(where)
    except BAD as e:
        note(where, e)
    except Exception as e:  # the network, a missing API key...: not what this test looks for (counted, for the report)
        key = f"{type(e).__name__}"
        result["other_exceptions"][key] = result["other_exceptions"].get(key, 0) + 1
        result.setdefault("other_where", {}).setdefault(key, f"{where}: {e}"[:200])
    return inter


def produced(inter):
    """The windows (views) and forms an interaction brought out."""
    views, forms = [], list(inter.response.modals)
    candidates = [kw for _, kw in inter.response.sent] + [kw for _, kw in inter.followup.sent] + list(inter.response.edits) + \
        list(inter.edited)
    for kw in candidates:
        if isinstance(kw.get("view"), discord.ui.View):
            views.append(kw["view"])
    return views, forms


def fill(modal):
    def walk(items):
        for item in items:
            if isinstance(item, discord.ui.Label):
                walk([item.component])
            elif isinstance(item, discord.ui.TextInput):
                item._value = ("Cat:60, Dog:40" if item.style == discord.TextStyle.paragraph
                               else "5" if (item.max_length or 4000) <= 15 else "Builderman")
            elif isinstance(item, discord.ui.Select) and item.options:
                item._values = [pick(item)]
    walk(modal.children)


async def submit(modal, who, guild, where):
    """A form filled in and sent. Returns the interaction of the sending."""
    fill(modal)
    inter = interaction_for(guild, who, message=Message(), **COGS)
    result["forms"].append(type(modal).__name__)
    try:
        await modal.on_submit(inter)
    except BAD as e:
        note(f"{where} -> form {type(modal).__name__}", e)
    except Exception as e:
        key = f"form {type(e).__name__}"
        result["other_exceptions"][key] = result["other_exceptions"].get(key, 0) + 1
        result.setdefault("other_where", {}).setdefault(key, f"{where}: {e}"[:200])
    return inter


async def close(view, who, guild, where):
    """✖️ Close removes the message and stops the window."""
    view.to_components()
    buttons = [item for item in view.children if isinstance(item, ui.CloseButton)]
    if not buttons:
        return  # a window with its own Cancel, or not a Panel
    message = Message()
    view.message = message
    inter = await click(view, buttons[0], who, guild, f"{where} -> Close", message=message)
    if not (inter.deleted and view.is_finished()) and f"{where} -> Close" not in result["refused"]:
        result["errors"].append(f"{where} -> Close: the message was not removed or the window kept running")
    result["closed"].append(type(view).__name__)


async def crawl(name, make_root, who, guild):
    """Clicks everything under one root window. A step of a path is (the number of the button, through a form?): the
    window is opened again by repeating the path, so every click is made on a fresh window."""
    seen, queue = set(), [(name, [], 0)]

    async def step(view, index, via_form, where, send_forms=True):
        inter = await click(view, view.children[index], who, guild, where)
        views, forms = produced(inter)
        if forms and send_forms:
            sent = await submit(forms[0], who, guild, where)
            for extra in forms[1:]:
                await submit(extra, who, guild, where)
            if via_form:
                views, _ = produced(sent)
        return views, forms, sent if forms else None

    async def open_at(path):
        view = make_root()
        for index, via_form in path:
            views, _, _ = await step(view, index, via_form, f"{name} {path}", send_forms=via_form)
            if not views:
                return None
            view = views[0]
        view.to_components()  # the window as Discord shows it (with ✖️ Close)
        return view

    while queue:
        where, path, depth = queue.pop(0)
        view = await open_at(path)
        if view is None:
            continue
        kind = type(view).__name__
        if kind in seen:
            continue
        seen.add(kind)
        result["windows"][kind] = result["windows"].get(kind, 0) + 1
        view.to_components()
        count = len(view.children)
        again = await open_at(path)
        if again is not None:
            await close(again, who, guild, f"{where} / {kind}")
        for index in range(count):
            fresh = await open_at(path)
            if fresh is None or len(fresh.children) != count or isinstance(fresh.children[index], ui.CloseButton):
                continue
            here = f"{where} / {kind} / {label(fresh.children[index])}"
            views, forms, sent = await step(fresh, index, False, here)
            if os.environ.get("CLICK_DEBUG"):
                print("STEP", here, "->", [type(v).__name__ for v in views], [type(f).__name__ for f in forms],
                      [type(v).__name__ for v in produced(sent)[0]] if sent else None, flush=True)
            if depth >= MAX_DEPTH:
                continue
            for new in views:  # a window the click opened
                if new is not fresh and type(new).__name__ not in seen:
                    queue.append((here, path + [(index, False)], depth + 1))
                    break
            if sent is not None:  # a window the form's answer opened
                answer, _ = produced(sent)
                if answer and type(answer[0]).__name__ not in seen:
                    queue.append((here + " (form)", path + [(index, True)], depth + 1))


async def run():
    if len(sys.argv) > 1:
        i18n.set_language(sys.argv[1])  # config.json of the temporary copy
    result["language"] = i18n.language()
    await database.init_db()
    async with main.bot:
        translator = i18n.Translator()
        await main.bot.tree.set_translator(translator)
        await main.load_extensions()
        result["failed"] = list(main.bot.failed_extensions)
        result["extensions"] = sorted(main.bot.extensions)
        for cog in list(main.bot.cogs.values()):
            for value in vars(type(cog)).values():
                if isinstance(value, tasks.Loop):
                    getattr(cog, value.coro.__name__).cancel()

        from cogs import game_panel, setup_roblox
        guild = make_guild([STAFF])
        config_store.write_json("game_economy.json", {"configured": True, "currencies": ["Coins"], "items": ["VIP"]})

        # Roblox answers (nothing is connected): one player, a ban that can be switched on and off
        ban = {"active": False}

        async def get_ban(user_id):
            return {"active": ban["active"], "duration": "", "displayReason": "Exploiting", "privateReason": "note"}

        async def get_user(user_id):
            return {"name": "Builderman", "displayName": "Builder", "created": "2020-01-01T00:00:00Z"}

        patches = [mock.patch.object(roblox_api, "find_users", mock.AsyncMock(return_value=[(4242, "Builderman", "name")])),
                   mock.patch.object(roblox_api, "resolve_user", mock.AsyncMock(return_value=(4242, "Builderman"))),
                   mock.patch.object(roblox_api, "get_user", get_user),
                   mock.patch.object(roblox_api, "avatar_url", mock.AsyncMock(return_value="")),
                   mock.patch.object(open_cloud, "get_ban", get_ban),
                   mock.patch.object(open_cloud, "set_ban", mock.AsyncMock())]
        for patch in patches:
            patch.start()

        # something to remove, replace and stop
        codes = main.bot.get_cog("GameCodes")
        COGS["GameCodes"] = codes
        admin = interaction_for(guild, "admin").user
        for name in ("SEED1", "SEED2", "BUILDERMAN"):
            await codes.store_code(admin, name, "7d", "Coins", 5, 0, "none", "permanent")
        import json as _json
        await database.add_egg("Seed egg", "Coins", 100, _json.dumps([{"name": "Cat", "chance": 1}]), "", "", "", 0, 7)
        await database.add_live_event("Seed event", _json.dumps({"exp": 2.0}), 0, 4_000_000_000, 7)

        # the panel as the bot registered it for restarts: every button
        registered = [v for v in main.bot.persistent_views if any(str(getattr(c, "custom_id", "")).startswith("gpanel:")
                                                                  for c in v.children)]
        result["registered_views"] = len(registered)
        panel = registered[0] if registered else None
        result["registered_ids"] = sorted(c.custom_id for c in panel.children) if panel else []
        result["posted_ids"] = [c.custom_id for c in game_panel.GamePanelView().children]
        if panel is not None:
            result["old_buttons"] = {}
            for item in panel.children:  # nobody without a role gets in through the posted panel
                if await panel.interaction_check(interaction_for(guild, "player")):
                    result["errors"].append(f"posted panel {item.custom_id}: a player was let in")
                # what a button of an old panel answers
                inter = await click(panel, item, "staff", guild, f"old button {item.custom_id}")
                result["old_buttons"][item.custom_id] = (inter.response.sent[0][0] if inter.response.sent else None)
            for state in (False, True):  # the player is not banned / is banned (the card offers Ban / Unban)
                ban["active"] = state
                await crawl(f"gpanel (banned={state})", lambda: game_panel.GamePanelView(), "staff", guild)
        ban["active"] = False
        from cogs import setup
        await crawl("setup", lambda: setup.PanelView(), "admin", guild)
        await crawl("setup-roblox", lambda: setup_roblox.RobloxPanelView(), "admin", guild)
        await crawl("control settings", lambda: game_panel.GamePanelManager(guild), "admin", guild)
        result["network_attempts"] = len(attempts)
        result["modules"] = sorted(m for m in sys.modules if m in ("cogs.live_game", "cogs.roblox_admin"))
    await database.close_db()


asyncio.run(run())
print("RESULT " + json.dumps(result))
