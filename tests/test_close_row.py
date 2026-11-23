"""Panel.close_row (utils/ui.py): the row the ✖️ Close button goes to when a window needs it somewhere else than the default place.
Used by the Game connection window (cogs/setup.py CloudSyncView), so that the "Studio file" button stays alone in its row."""
import unittest
from unittest import mock

import discord

from tests import fakes
from tests.helpers import TempBot
from utils import i18n, ui

LANGS = ("en", "pl", "es")


class CloseRow(unittest.TestCase):
    def setUp(self):
        self.temp = TempBot()
        self.temp.__enter__()

    def tearDown(self):
        self.temp.__exit__(None, None, None)

    def buttons(self, view_class, layout):
        """A window with the given buttons per row (a number) or a menu (the text "menu")."""
        view = view_class()
        for row, spec in enumerate(layout):
            if spec == "menu":
                view.add_item(discord.ui.Select(options=[discord.SelectOption(label="a", value="a")], row=row))
            else:
                for n in range(spec):
                    view.add_item(discord.ui.Button(label=f"b{row}{n}", row=row))
        return view

    def test_the_game_connection_window_keeps_the_studio_file_button_alone(self):
        from cogs import setup
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                view = setup.CloudSyncView()
                fakes.check_view(view, f"CloudSyncView [{lang}]")
                rows = view.to_components()
                self.assertEqual(len(rows), 2, lang)
                self.assertEqual(len(rows[0]["components"]), 5, f"[{lang}] the four buttons and ✖️ Close in the first row")
                self.assertEqual(len(rows[1]["components"]), 1, f"[{lang}] the Studio file button alone")
                self.assertEqual(rows[1]["components"][0]["label"], i18n.t("kit.btn"))
                self.assertEqual(sum(isinstance(c, ui.CloseButton) for c in view.children), 1)

    def test_the_default_place_is_unchanged_without_a_close_row(self):
        class Plain(ui.Panel):
            pass
        self.assertIsNone(Plain.close_row)
        self.assertEqual(len(self.buttons(Plain, [2, 2]).to_components()[1]["components"]), 3, "joins the last row of buttons")
        self.assertEqual(len(self.buttons(Plain, [5]).to_components()), 2, "a full row: a new row below")
        self.assertEqual(len(self.buttons(Plain, ["menu"]).to_components()), 2, "never next to a menu")
        self.assertEqual(len(ui.CloseView().to_components()), 1)

    def test_a_close_row_with_room_is_used(self):
        class First(ui.Panel):
            close_row = 0
        rows = self.buttons(First, [2, 1]).to_components()
        self.assertEqual([len(r["components"]) for r in rows], [3, 1])

    def test_a_full_row_or_a_menu_row_falls_back_to_the_default_place(self):
        class First(ui.Panel):
            close_row = 0
        full = self.buttons(First, [5, 2]).to_components()
        self.assertEqual([len(r["components"]) for r in full], [5, 3], "row 0 is full: the default place (the last row of buttons)")
        menu = self.buttons(First, ["menu", 1]).to_components()
        self.assertEqual([len(r["components"]) for r in menu], [1, 2], "row 0 holds a menu: the default place")

    def test_a_close_row_that_is_still_empty_is_used_and_two_calls_add_one_button(self):
        class Third(ui.Panel):
            close_row = 3
        view = self.buttons(Third, [1])
        first = view.to_components()
        second = view.to_components()
        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 2, "the second call adds no second ✖️")
        self.assertEqual(sum(isinstance(c, ui.CloseButton) for c in view.children), 1)
        fakes.check_view(view)

    def test_a_close_row_never_breaks_a_view_of_five_full_rows(self):
        class First(ui.Panel):
            close_row = 0
        view = self.buttons(First, [5, 5, 5, 5, 5])
        rows = view.to_components()
        self.assertEqual(len(rows), 5)
        self.assertEqual(sum(isinstance(c, ui.CloseButton) for c in view.children), 0, "no room: the window still closes itself later")

    def test_only_the_connection_window_sets_a_close_row(self):
        from tests.panel_catalog import all_window_classes, import_every_module
        import_every_module()
        with_row = sorted(cls.__name__ for cls in all_window_classes() if cls.close_row is not None)
        self.assertEqual(with_row, ["CloudSyncView"])


if __name__ == "__main__":
    unittest.main()
