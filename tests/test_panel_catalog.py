"""Every window of the bot (ui.Panel and its children) in three languages: it fits Discord's limits
with the ✖️ Close button, the language menu of /setup stays last, every window removes itself after a while, and a
window added to the bot without a place in tests/panel_catalog.py is reported (so it can't skip these checks)."""
import ast
import asyncio
import glob
import inspect
import os
import unittest
from unittest import mock

import discord

from tests import fakes
from tests.helpers import ROOT, TempBot
from tests.panel_catalog import all_window_classes, build_windows, covered_classes, import_every_module
from tests.panel_fakes import make_guild
from tests.test_panels_limits import Language
from utils import database, ui

LANGS = ("en", "pl", "es")
# Windows whose own Cancel closes them: they get no second Close button. The attribute is that Cancel.
OWN_CANCEL = {"UnbanConfirmView": "no", "CodeRemoveView": "cancel", "OverwriteView": "cancel", "CodeDraftView": "cancel", "GiftDraftView": "cancel"}


class Catalog(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        import_every_module()

    async def asyncTearDown(self):
        await database.close_db()
        self.temp.__exit__(None, None, None)

    async def test_every_window_class_of_the_bot_is_in_the_catalog(self):
        built = covered_classes(await build_windows(make_guild()))
        missing = sorted(f"{cls.__module__}.{cls.__name__}" for cls in all_window_classes() - built)
        self.assertEqual(missing, [], "a new window: add it to tests/panel_catalog.py so its layout and access are checked")

    async def test_every_window_fits_with_close_in_three_languages(self):
        from cogs import tutorial
        for lang in LANGS:
            with Language(lang), \
                    mock.patch.object(tutorial, "check_lines", mock.AsyncMock(return_value=["✅ ok"])), \
                    mock.patch.object(tutorial.roblox_kit, "refresh_quick", mock.AsyncMock()):
                for name, view in await build_windows(make_guild()):
                    where = f"{name} [{lang}]"
                    fakes.check_view(view, where)
                    closes = [item for item in view.children if isinstance(item, ui.CloseButton)]
                    if type(view).__name__ in OWN_CANCEL:
                        self.assertEqual(closes, [], f"{where}: its own Cancel closes it")
                        self.assertTrue(hasattr(view, OWN_CANCEL[type(view).__name__]), where)
                    else:
                        self.assertEqual(len(closes), 1, f"{where}: exactly one ✖️ Close")
                        self.assertTrue(closes[0].label and closes[0].emoji, where)
                    self.assertTrue(view.timeout and view.timeout <= ui.PANEL_TIMEOUT,
                                    f"{where}: every window removes itself ({view.timeout})")
                    for item in view.children:
                        if isinstance(item, discord.ui.Button) and not item.url:
                            self.assertTrue(item.label or item.emoji, where)
                    embed = view.embed() if hasattr(view, "embed") else None
                    if inspect.isawaitable(embed):
                        embed = await embed
                    if isinstance(embed, discord.Embed):
                        fakes.check_embed(embed, f"{where} embed")

    async def test_the_setup_language_menu_is_the_last_row_alone_with_close_above_it(self):
        from cogs import setup
        for lang in LANGS:
            with Language(lang):
                view = setup.PanelView()
                rows = view.to_components()
                self.assertLessEqual(len(rows), 5)
                last = rows[-1]["components"]
                self.assertEqual([c["type"] for c in last], [3], f"[{lang}] the language menu alone in the last row")
                self.assertIn("Language", last[0]["placeholder"])
                close = next(item for item in view.children if isinstance(item, ui.CloseButton))
                self.assertLess(close._rendered_row, len(rows) - 1, "Close is above the menu, never next to it")

    async def test_a_window_with_a_full_set_of_buttons_still_gets_removed_by_its_timer(self):
        view = ui.Panel()
        for row in range(5):
            for _ in range(5):
                view.add_item(discord.ui.Button(label="x", row=row))
        fakes.check_view(view)
        self.assertFalse(any(isinstance(i, ui.CloseButton) for i in view.children))
        self.assertEqual(view.timeout, ui.CLOSE_AFTER)


class EveryForm(unittest.IsolatedAsyncioTestCase):
    """Every form (modal) of the bot in three languages: title 45, labels 45, placeholders 100, 5 parts."""

    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        import_every_module()

    async def asyncTearDown(self):
        await database.close_db()
        self.temp.__exit__(None, None, None)

    async def build(self) -> list:
        import importlib
        mod = {name: importlib.import_module(f"cogs.{name}") for name in (
            "game_codes", "game_panel", "roblox_admin", "setup", "setup_roblox")}
        windows = dict(await build_windows(make_guild()))
        return [
            ("CodeModal", mod["setup_roblox"].CodeModal()), ("EggModal", mod["setup_roblox"].EggModal()),
            ("EventModal", mod["setup_roblox"].EventModal()), ("GiftModal", mod["setup_roblox"].GiftModal()),
            ("GiftModal for a player", mod["setup_roblox"].GiftModal(target=(1, "N" * 20))),
            ("AnnounceModal", mod["setup_roblox"].AnnounceModal()), ("PlayerLookupModal", mod["roblox_admin"].PlayerLookupModal()),
            ("BanModal", mod["roblox_admin"].BanModal(windows["roblox_admin.PlayerCardView not banned"])),
            ("CodeExtrasModal", mod["game_codes"].CodeExtrasModal(windows["game_codes.CodeDraftView"])),
            ("GiftExtrasModal", mod["setup_roblox"].GiftExtrasModal(windows["setup_roblox.GiftDraftView"])),
            ("LeaderboardModal", mod["roblox_admin"].LeaderboardModal()), ("GameModal", mod["setup"].GameModal({})),
            ("EconomyModal", mod["setup"].EconomyModal()),
            ("ApiKeyModal", mod["setup"].ApiKeyModal()), ("AddServerModal", mod["setup"].AddServerModal(windows["setup.ServersView"])),
            ("AddManagerUserModal", mod["game_panel"].AddManagerUserModal(windows["game_panel.ManagerUsersView"])),
        ]

    async def test_every_form_fits_in_three_languages(self):
        seen = set()
        for lang in LANGS:
            with Language(lang):
                for name, modal in await self.build():
                    fakes.check_modal(modal, f"{name} [{lang}]")
                    self.assertTrue(modal.timeout is None or isinstance(modal.timeout, (int, float)), name)
                    seen.add(type(modal))
        from tests.panel_catalog import all_modal_classes
        self.assertEqual(sorted(c.__name__ for c in all_modal_classes() - seen), [], "a form that no test builds")


class NamesDiscordUses(unittest.TestCase):
    """The NumbersModal bug: `self.timeout = <a text field>` replaced the form's own time limit and broke it. A window,
    form, button or menu must not give one of its attributes a name discord.py already uses."""
    ALLOWED = {"interaction_check", "on_timeout", "on_error", "on_submit", "message", "close_button", "close_row", "callback"}  # close_*: our own Panel settings (utils/ui.py)
    # known and harmless today: a private method of an ephemeral window that discord.py would call only for
    # public messages it keeps in sync (it would be called with other arguments). Rename it to be safe.
    KNOWN = set()

    def test_no_attribute_hides_a_name_of_discord_py(self):
        async def reserved_names():
            return {"Modal": set(dir(discord.ui.Modal(title="x"))), "View": set(dir(ui.Panel())),
                    "Select": set(dir(discord.ui.Select(options=[discord.SelectOption(label="a")]))),
                    "RoleSelect": set(dir(discord.ui.RoleSelect())), "ChannelSelect": set(dir(discord.ui.ChannelSelect())),
                    "Button": set(dir(discord.ui.Button()))}
        reserved = asyncio.run(reserved_names())
        found = []
        for path in glob.glob(os.path.join(ROOT, "cogs", "*.py")):
            with open(path, encoding="utf-8") as source:
                tree = ast.parse(source.read())
            for cls in [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]:
                bases = " ".join(ast.unparse(b) for b in cls.bases)
                kind = next((k for k in ("RoleSelect", "ChannelSelect", "Modal", "Select", "Button", "View", "Panel")
                             if k in bases), None)
                if kind is None:
                    continue
                names = set()
                for node in ast.walk(cls):
                    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self" \
                            and isinstance(node.ctx, ast.Store):
                        names.add(node.attr)
                for node in cls.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        names.add(node.name)
                    elif isinstance(node, ast.Assign):
                        names.update(t.id for t in node.targets if isinstance(t, ast.Name))
                taken = reserved["View" if kind == "Panel" else kind]
                for name in sorted(names & taken):
                    if name not in self.ALLOWED and not (name.startswith("__") and name.endswith("__")) \
                            and (cls.name, name) not in self.KNOWN:
                        found.append(f"{os.path.basename(path)}: {cls.name}.{name}")
        self.assertEqual(found, [], "these names are used by discord.py itself")


if __name__ == "__main__":
    unittest.main()


class NoPublicPanels(unittest.TestCase):
    """A window with ✖️ Close lets whoever sees it delete it, so it must be private (ephemeral): the bot's windows are
    sent only through send_panel (private by default) or as the first answer of a click, never to a channel."""

    def test_no_window_is_sent_publicly(self):
        import_every_module()
        offenders = []
        for path in glob.glob(os.path.join(ROOT, "cogs", "*.py")):
            with open(path, encoding="utf-8") as source:
                tree = ast.parse(source.read())
            panel_names = {cls.__name__ for cls in all_window_classes()} | {"Panel", "AdminView", "StaffView"}
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                keywords = {k.arg: k.value for k in node.keywords}
                function = ast.unparse(node.func)
                public = isinstance(keywords.get("ephemeral"), ast.Constant) and keywords["ephemeral"].value is False
                if function.endswith("send_panel") and public:
                    offenders.append(f"{os.path.basename(path)}:{node.lineno} send_panel(ephemeral=False)")
                # a channel message with a window as its view
                if function.endswith("channel.send") and "view" in keywords:
                    shown = ast.unparse(keywords["view"])
                    built = ast.unparse(keywords["view"].func) if isinstance(keywords["view"], ast.Call) else shown
                    if built.split(".")[-1] in panel_names:
                        offenders.append(f"{os.path.basename(path)}:{node.lineno} channel.send(view={shown})")
        self.assertEqual(offenders, [])
