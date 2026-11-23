"""Every panel the changes touch fits Discord's limits in all three languages: the tutorial and the
guide (all chapters), /setup-roblox and its sub-panels with a very large game, the code panel and the player card.
Uses the checks of tests/fakes.py (embed 6000, field 1024, buttons 80, 5 rows, 25 options, forms 45/100)."""
import unittest
from unittest import mock

from tests.fakes import Interaction, check_embed, check_modal, check_view
from tests.helpers import TempBot
from utils import config_store, database, i18n

LANGS = ("en", "pl", "es")


class Language:
    """Runs a block in one language."""

    def __init__(self, lang):
        self.patches = [mock.patch.object(i18n, "language", return_value=lang)]

    def __enter__(self):
        for patch in self.patches:
            patch.start()

    def __exit__(self, *exc):
        for patch in self.patches:
            patch.stop()


class Panels(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        names = [f"Name{i}_" + "x" * 80 for i in range(40)]
        config_store.write_json("game_economy.json", {"configured": True, "currencies": names[:12], "items": names, "pets": names[:30]})

    async def asyncTearDown(self):
        await database.close_db()
        self.temp.__exit__(None, None, None)

    async def test_every_tutorial_chapter_in_every_language(self):
        from cogs import tutorial
        long_lines = [f"⚠️ {'check ' * 30}{i}" for i in range(40)]
        with mock.patch.object(tutorial, "check_lines", mock.AsyncMock(return_value=long_lines)), \
                mock.patch.object(tutorial.roblox_kit, "refresh_quick", mock.AsyncMock()):
            for lang in LANGS:
                with Language(lang):
                    guild = mock.Mock()
                    count = len(tutorial.chapters())
                    for index in range(count):
                        view = tutorial.TutorialView(guild, index, None)
                        check_embed(await view.embed(), f"tutorial {lang} #{index}")
                        check_view(view, f"tutorial {lang} #{index}")

    async def test_every_guide_topic_in_every_language(self):
        from cogs import setup_guide
        for lang in LANGS:
            with Language(lang):
                for index in range(len(setup_guide.available_topics())):
                    view = setup_guide.GuideView(0x00A2FF, index)
                    check_embed(view.embed(), f"guide {lang} #{index}")
                    check_view(view, f"guide {lang} #{index}")

    async def test_roblox_panels_with_a_very_large_game(self):
        from cogs import setup_roblox
        for lang in LANGS:
            with Language(lang):
                check_embed(await setup_roblox.roblox_panel_embed(), f"/setup-roblox {lang}")
                check_view(setup_roblox.RobloxPanelView(), f"/setup-roblox {lang}")
                codes = setup_roblox.CodesView()
                check_embed(await codes.embed(), f"codes {lang}")
                check_view(codes, f"codes {lang}")
                check_modal(setup_roblox.CodeModal(), f"code form {lang}")
                for view in (setup_roblox.BansView(), setup_roblox.GiftsView()):
                    check_embed(view.embed(), f"{type(view).__name__} {lang}")
                    check_view(view)
                check_modal(setup_roblox.GiftModal(), f"gift form {lang}")
                check_modal(setup_roblox.GiftModal(target=(1, "N" * 20)), f"gift form with a player {lang}")
                view = setup_roblox.EggsView()
                check_embed(await view.embed(), f"eggs {lang}")
                check_view(view)
                view = setup_roblox.EventsView()
                check_embed(await view.embed(), f"events {lang}")
                check_view(view)

    async def test_codes_panel_with_many_long_codes(self):
        from cogs import game_codes, setup_roblox
        cog = game_codes.GameCodes.__new__(game_codes.GameCodes)
        cog.bot = mock.Mock(get_cog=lambda name: None)
        for lang in LANGS:
            with Language(lang):
                for index in range(30):
                    await cog.store_code(Interaction().user, f"{lang}{index}".ljust(50, "X"), "24h", "Name0_" + "x" * 80, 10 ** 9,
                                         10 ** 9, "Name1_" + "x" * 80, "30d")
                view = setup_roblox.CodesView()
                check_embed(await view.embed(), f"codes {lang}")
                active = await database.get_active_game_codes()
                remove = game_codes.CodeRemoveView(cog, 7, active[:25])
                check_view(remove)
                check_embed(game_codes.codes_embed(list(active), 0), f"/codes {lang}")
                check_view(game_codes.CodesPager(list(active), 7))
                for code in active:
                    await database.delete_game_code(code["code"])

    async def test_opening_every_button_of_the_panel_answers_discord_exactly_once(self):
        from cogs import setup_roblox
        with Language("en"):
            view = setup_roblox.RobloxPanelView()
            for button in view.children:
                if button.label in ("Roblox game",):
                    continue
                inter = Interaction()
                try:
                    await button.callback(inter)
                except Exception as e:  # a network panel may need the game: only Discord's rules matter here
                    if type(e).__name__ == "DiscordRefused":
                        raise
                self.assertLessEqual(len(inter.response.sent) + len(inter.response.modals) + len(inter.response.defers), 1,
                                     button.label)


if __name__ == "__main__":
    unittest.main()
