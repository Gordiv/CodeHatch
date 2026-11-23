"""/setup (cogs/setup.py): at most 5 rows, and the language menu sits in the last row, under every button."""
import unittest
from unittest import mock

import discord

from tests.fakes import check_view
from tests.helpers import TempBot
from utils import i18n


class SetupPanel(unittest.IsolatedAsyncioTestCase):
    async def test_rows_and_the_language_menu_in_the_last_row(self):
        from cogs import setup
        with TempBot():
            for lang in ("en", "pl", "es"):
                with mock.patch.object(i18n, "language", return_value=lang):
                    view = setup.PanelView()
                    check_view(view, f"/setup {lang}")
                    menus = [c for c in view.children if isinstance(c, setup.LanguageSelect)]
                    self.assertEqual(len(menus), 1)
                    self.assertEqual(menus[0].row, max(c.row for c in view.children), "the language menu is the last row")
                    self.assertTrue(all(c.row < menus[0].row for c in view.children if c is not menus[0]))
                    self.assertEqual([o.value for o in menus[0].options if o.default], [lang])
                    self.assertTrue(all(b.label for b in view.children if isinstance(b, discord.ui.Button)))


if __name__ == "__main__":
    unittest.main()
