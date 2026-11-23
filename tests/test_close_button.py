"""✖️ Close on every panel and windows that remove themselves after 5 minutes without a click (the user asked for
this: finished windows used to pile up under the game control panel until dismissed by hand)."""
import unittest
from unittest import mock

import discord

from tests import fakes
from tests.helpers import TempBot
from utils import database, i18n, ui

LANGS = ("en", "pl", "es")


def close_buttons(view):
    view.to_components()
    return [item for item in view.children if isinstance(item, ui.CloseButton)]


def row_of(item):
    row = getattr(item, "_rendered_row", None)
    return item.row if row is None else row


class Message:
    def __init__(self, refuse=False):
        self.deleted, self.edits, self.refuse = False, [], refuse

    async def delete(self):
        if self.refuse:
            raise discord.NotFound(type("R", (), {"status": 404, "reason": "Not Found"})(), "Unknown Webhook")
        self.deleted = True

    async def edit(self, **kwargs):
        self.edits.append(kwargs)


class CloseButtonPlacement(unittest.IsolatedAsyncioTestCase):
    async def test_under_the_panel_buttons_and_never_next_to_a_menu(self):
        class Buttons(ui.Panel):
            @discord.ui.button(label="a", row=0)
            async def a(self, interaction, button):
                pass

            @discord.ui.button(label="b", row=1)
            async def b(self, interaction, button):
                pass

        found = close_buttons(Buttons())
        self.assertEqual(len(found), 1)
        self.assertEqual(row_of(found[0]), 1, "in the last row of buttons (it has room)")

        menu_last = ui.Panel()
        menu_last.add_item(discord.ui.Button(label="x", row=0))
        menu_last.add_item(discord.ui.Select(options=[discord.SelectOption(label="o")], row=4))
        found = close_buttons(menu_last)
        self.assertEqual(row_of(found[0]), 0, "a menu in the last row (/setup's language) stays last")

        only_menu = ui.Panel()
        only_menu.add_item(discord.ui.Select(options=[discord.SelectOption(label="o")]))
        self.assertEqual(row_of(close_buttons(only_menu)[0]), 1, "under a menu when there is nothing else")

        full = ui.Panel()
        for row in range(5):
            for _ in range(5):
                full.add_item(discord.ui.Button(label="x", row=row))
        self.assertEqual(close_buttons(full), [], "no room: the panel still removes itself later")
        self.assertEqual(len(close_buttons(Buttons())), 1, "added once, also when rendered again")

    async def test_panels_with_their_own_cancel_have_no_second_close(self):
        from cogs import game_codes
        with TempBot():
            for view in (game_codes.OverwriteView(None, 7, {"code": "X"}),
                         game_codes.CodeDraftView(None, 7, game_codes.code_params("X", "7d", "Coins", 5))):
                self.assertEqual(close_buttons(view), [], type(view).__name__)

    async def test_every_panel_of_the_bot_fits_with_close_in_every_language(self):
        from cogs import game_panel, setup, setup_roblox
        with TempBot():
            await database.init_db()
            try:
                for lang in LANGS:
                    with mock.patch.object(i18n, "language", return_value=lang):
                        views = [setup_roblox.RobloxPanelView(), setup_roblox.CodesView(), setup_roblox.BansView(),
                                 setup_roblox.RankingView(), setup_roblox.CatalogView(), setup.PanelView(),
                                 game_panel.GamePanelManager(fakes.Guild()), setup_roblox.EggsView(),
                                 setup_roblox.EventsView(), setup_roblox.GiftsView()]
                        for view in views:
                            fakes.check_view(view, f"{type(view).__name__} [{lang}]")
                            self.assertEqual(len(close_buttons(view)), 1, f"{type(view).__name__} [{lang}]")
                            self.assertTrue(all(b.label for b in close_buttons(view)))
            finally:
                await database.close_db()


class ClosingAndExpiring(unittest.IsolatedAsyncioTestCase):
    async def test_close_removes_the_message(self):
        view = ui.CloseView()
        button = close_buttons(view)[0]
        inter = fakes.Interaction()
        await button.callback(inter)
        self.assertTrue(inter.deleted)
        self.assertTrue(view.is_finished(), "the panel stops listening")

    async def test_close_empties_the_message_when_discord_refuses_to_delete_it(self):
        inter = fakes.Interaction()

        async def refuse():
            raise discord.NotFound(type("R", (), {"status": 404, "reason": "Not Found"})(), "Unknown Message")
        inter.delete_original_response = refuse
        await ui.close_message(inter, "nothing changed")
        self.assertEqual(inter.edited[-1], {"content": "nothing changed", "embed": None, "view": None})

    async def test_a_panel_nobody_clicks_removes_itself(self):
        self.assertEqual(ui.Panel().timeout, ui.CLOSE_AFTER)
        self.assertEqual(ui.CLOSE_AFTER, 300, "5 minutes, as the user asked")
        view = ui.Panel()
        view.message = Message()
        await view.on_timeout()
        self.assertTrue(view.message.deleted)
        old = ui.Panel()
        old.message = Message(refuse=True)  # older than 15 minutes: Discord doesn't let the bot delete it
        old.add_item(discord.ui.Button(label="x"))
        await old.on_timeout()
        self.assertTrue(old.message.edits and all(item.disabled for item in old.children), "turned off instead")

    async def test_reading_windows_stay_longer(self):
        from cogs import setup_guide, tutorial
        with TempBot():
            self.assertEqual(setup_guide.GuideView(0).timeout, ui.PANEL_TIMEOUT)
            self.assertEqual(tutorial.TutorialView(fakes.Guild()).timeout, ui.PANEL_TIMEOUT)

    async def test_an_answer_in_place_of_a_message_that_is_gone_comes_as_a_new_one(self):
        inter = fakes.Interaction()
        await inter.response.defer()

        async def gone(**kwargs):
            raise discord.NotFound(type("R", (), {"status": 404, "reason": "Not Found"})(), "Unknown Message")
        inter.edit_original_response = gone
        await ui.show_in_place(inter, content="🔨 banned", embed=None)
        content, kwargs = inter.followup.sent[-1]
        self.assertEqual(content, "🔨 banned")
        self.assertIsInstance(kwargs["view"], ui.CloseView)
        self.assertNotIn("embed", kwargs, "an empty value is not sent")


if __name__ == "__main__":
    unittest.main()
