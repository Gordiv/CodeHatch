"""Run by tests/test_bot_loads.py inside a TEMPORARY COPY of the bot (never in the real folder): loads main.py and every
module the way the bot does (without logging in to Discord) and prints one JSON line with what happened.
Usage: python load_driver.py"""
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import main  # noqa: E402
from discord.ext import tasks  # noqa: E402

import aiohttp  # noqa: E402

from utils import database, i18n, net  # noqa: E402

result = {"problems": []}
attempts = []


def no_network():
    """Nothing in this run may reach Roblox, Gemini or Discord: every attempt is counted and refused."""
    attempts.append(1)
    raise aiohttp.ClientConnectionError("the network is off in tests")


net.session = no_network


async def run():
    await database.init_db()
    async with main.bot:
        translator = i18n.Translator()
        await main.bot.tree.set_translator(translator)
        await main.load_extensions()
        result["failed"] = list(main.bot.failed_extensions)
        result["extensions"] = sorted(main.bot.extensions)
        result["modules_loaded_at_start"] = sorted(m for m in sys.modules if m in ("cogs.live_game", "cogs.roblox_admin"))
        commands = main.bot.tree.get_commands()
        result["commands"] = sorted(c.name for c in commands)
        for cmd in commands:
            payload = await cmd.get_translated_payload(main.bot.tree, translator)
            if len(payload.get("description", "")) > 100 or not payload.get("description"):
                result["problems"].append(f"/{cmd.name}: description")
            for loc, text in (payload.get("description_localizations") or {}).items():
                if len(text) > 100:
                    result["problems"].append(f"/{cmd.name} [{loc}]: description {len(text)}")

        # Build the panels (no click, no network)
        from cogs import setup_roblox
        setup_roblox.RobloxPanelView()
        setup_roblox.CodeModal().to_dict()
        setup_roblox.CodesView()
        setup_roblox.BansView()
        setup_roblox.GiftsView()
        for cog in list(main.bot.cogs.values()):
            for value in vars(type(cog)).values():
                if isinstance(value, tasks.Loop):
                    getattr(cog, value.coro.__name__).cancel()
        result["modules_after_panels"] = sorted(m for m in sys.modules if m in ("cogs.live_game", "cogs.roblox_admin"))
        # the panel as the bot shows it
        view = setup_roblox.RobloxPanelView()
        result["panel_buttons"] = sorted(item.label for item in view.children)
        result["panel_rows"] = len(view.to_components())

        # Click everything the panel offers, with strict stand-ins for Discord: a click may fail on the network
        # (nothing is connected), but never because a module is missing or a name is wrong
        from tests import fakes
        cog = main.bot.get_cog("GameCodes")
        from utils import config_store
        config_store.write_json("game_economy.json", {"configured": True, "currencies": ["Coins"], "items": ["VIP"]})
        errors = []

        async def click(label, coro):
            try:
                await coro
            except (ImportError, AttributeError, NameError, TypeError, KeyError, fakes.DiscordRefused) as e:
                errors.append(f"{label}: {type(e).__name__}: {e}")
            except Exception:
                pass

        for button in view.children:
            if button.label != "Roblox game":
                await click(f"button {button.label}", button.callback(fakes.Interaction(GameCodes=cog)))
        codes_view = setup_roblox.CodesView()
        await click("codes new", codes_view.new.callback(fakes.Interaction(GameCodes=cog)))
        await click("codes remove", codes_view.remove.callback(fakes.Interaction(GameCodes=cog)))
        modal = setup_roblox.CodeModal()
        modal.code._value = "BETA1"
        modal.validity._values = ["7d"]
        modal.currency._values = ["Coins"]
        modal.amount._value = "50"
        modal.item._values = ["none"]
        inter = fakes.Interaction(GameCodes=cog)
        await click("code form", modal.on_submit(inter))
        draft = inter.response.sent[-1][1]["view"] if inter.response.sent else None
        result["draft_shown"] = draft is not None
        if draft is not None:
            await click("draft save", draft.save.callback(fakes.Interaction(GameCodes=cog)))
        row = await database.get_game_code("BETA1")
        result["code_saved"] = bool(row and row["is_active"])
        add = fakes.Interaction(GameCodes=cog)
        from discord import app_commands
        await click("/code-add", cog.code_add.callback(cog, add, "CMD1", app_commands.Choice(name="7d", value="7d"), "Coins", 5,
                                                       0, "none", None))
        result["command_saved"] = bool(await database.get_game_code("CMD1"))
        result["click_errors"] = errors
        result["network_attempts"] = len(attempts)
    await database.close_db()


asyncio.run(run())
print("RESULT " + json.dumps(result))
