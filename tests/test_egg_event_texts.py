"""Texts of the egg and event windows: every new key in all three languages with the same {placeholders}, nothing left
untranslated or unused, every text fits where it is shown, and the guide, tutorial and /setup-roblox window talk about
eggs, events and the rest of the game."""
import json
import os
import re
import unittest
from unittest import mock

from tests import fakes
from tests.helpers import ROOT, TempBot
from utils import database, i18n

LANGS = ("en", "pl", "es")
# the keys of the egg edit / catalog copy / event changes
NEW_KEYS = ["events.err_all_and_one", "rbx.btn_edit_egg", "rbx.btn_preset_egg", "rbx.btn_remove_this_egg", "rbx.btn_end_this_event",
            "rbx.eggs_footer", "rbx.egg_edit_title", "rbx.egg_pick_preset", "rbx.egg_pick_preset_ph", "rbx.egg_pets_too_long",
            "rbx.egg_preset_too_long", "rbx.egg_presets_limited", "rbx.egg_pick_edit", "rbx.egg_pick_edit_ph", "rbx.egg_no_presets",
            "rbx.egg_color_ph", "rbx.egg_duration_ph", "rbx.egg_template_ph", "rbx.egg_default_model", "rbx.egg_done_footer",
            "rbx.event_kind", "rbx.event_value", "rbx.event_more_options"]
REMOVED_KEYS = ["rbx.egg_more_options"]
PLACEHOLDER = re.compile(r"\{(\w+)\}")
EGG_EVENT_WORDS = re.compile(r"egg|jaj[kaeo]|huevo|\bevents?\b|eventy|eventos?|/egg|/event|multiplier|mnożnik|multiplicador|DiscordEggSpot", re.I)
# The in-game features (gifts, on-screen announcements, bans, the leaderboard) in the three languages
FULL_ONLY_WORDS = re.compile(
    r"gifts?|prezent|regalo|/give(?![a-z-])|/announce-game|/roblox-(?:un)?ban|/leaderboard|on-screen announcement|"
    r"ogłoszeni\w* na ekranie|anuncios? en pantalla|leaderboard|ranking gry|clasificación del juego|player card|karta gracza|"
    r"ficha del jugador|zbanuj|odbanuj|desbanear|banear|bans? (?:a |the )?player|ban w grze|bany w grze|roblox-ban|OnGift",
    re.I)


def locale(lang: str) -> dict:
    with open(os.path.join(ROOT, "locales", f"{lang}.json"), encoding="utf-8") as f:
        return json.load(f)


class NewKeys(unittest.TestCase):
    def test_every_new_key_is_in_every_language_with_the_same_placeholders(self):
        texts = {lang: locale(lang) for lang in LANGS}
        for key in NEW_KEYS:
            for lang in LANGS:
                self.assertTrue(texts[lang].get(key, "").strip(), f"{key} [{lang}]")
            holders = {lang: sorted(PLACEHOLDER.findall(texts[lang][key])) for lang in LANGS}
            self.assertEqual(holders["en"], holders["pl"], key)
            self.assertEqual(holders["en"], holders["es"], key)

    def test_nothing_is_left_in_english_in_the_other_languages(self):
        texts = {lang: locale(lang) for lang in LANGS}
        for key in NEW_KEYS:
            self.assertNotEqual(texts["pl"][key], texts["en"][key], f"{key} [pl] is the English text")
            self.assertNotEqual(texts["es"][key], texts["en"][key], f"{key} [es] is the English text")

    def test_removed_keys_are_gone_everywhere_and_new_keys_are_used(self):
        code = ""
        for folder in ("cogs", "utils"):
            for name in os.listdir(os.path.join(ROOT, folder)):
                if name.endswith(".py"):
                    with open(os.path.join(ROOT, folder, name), encoding="utf-8") as f:
                        code += f.read()
        for key in REMOVED_KEYS:
            for lang in LANGS:
                self.assertNotIn(key, locale(lang), f"{key} [{lang}] is not used any more")
            self.assertNotIn(f'"{key}"', code)
        for key in NEW_KEYS:
            self.assertIn(f'"{key}"', code, f"{key} is not used by any code")

    def test_the_texts_fit_where_they_are_shown(self):
        for lang in LANGS:
            texts = locale(lang)
            for key in ("rbx.btn_edit_egg", "rbx.btn_preset_egg", "rbx.btn_remove_this_egg", "rbx.btn_end_this_event"):
                self.assertLessEqual(len(texts[key]) + 3, 80, f"{key} [{lang}]: a button label (80) with its emoji")
            for key in ("rbx.event_kind", "rbx.event_value"):
                self.assertLessEqual(len(texts[key]), 45, f"{key} [{lang}]: the label of a form part")
            for key in ("rbx.egg_pets_too_long",):
                self.assertLessEqual(len(texts[key]), 100, f"{key} [{lang}]: the placeholder of a form field")
            for key in ("rbx.egg_pick_preset_ph", "rbx.egg_pick_edit_ph", "rbx.egg_color_ph", "rbx.egg_duration_ph", "rbx.egg_template_ph"):
                self.assertLessEqual(len(texts[key]), 150, f"{key} [{lang}]: a menu placeholder")
            self.assertLessEqual(len(texts["rbx.egg_edit_title"].replace("{name}", "")), 20, f"[{lang}] the form title keeps room for the name")
            self.assertLessEqual(len(texts["rbx.eggs_footer"]), 2048)
            for key in ("rbx.egg_pick_edit", "rbx.egg_pick_preset", "rbx.egg_no_presets", "rbx.egg_preset_too_long", "events.err_all_and_one"):
                self.assertLessEqual(len(texts[key].replace("{name}", "x" * 100)), 2000, f"{key} [{lang}]")

    def test_the_keys_built_from_a_name_exist_in_every_language(self):
        """t(f"eggs.color.{key}") and t(f"duration.choice.{key}") are built at run time, so no static check sees a missing one
        (a missing text would show the key itself as the label of a menu option)."""
        from cogs import live_game
        wanted = [f"eggs.color.{k}" for k in live_game.EGG_COLORS] +                  [f"duration.choice.{k}" for k in list(live_game.EGG_DURATIONS) + list(live_game.EVENT_DURATIONS)]
        for lang in LANGS:
            texts = locale(lang)
            for key in wanted:
                self.assertTrue(texts.get(key, "").strip(), f"{key} [{lang}]")
                self.assertLessEqual(len(texts[key]), 100, f"{key} [{lang}]: the label of a menu option")

    def test_the_commands_named_in_the_texts_exist(self):
        from cogs import live_game
        names = {c.name for c in live_game.LiveGame.__cog_app_commands__}
        for lang in LANGS:
            for key in NEW_KEYS:
                for command in re.findall(r"`?/([a-z]+(?:-[a-z]+)?)`?", locale(lang)[key]):
                    if command in ("setup", "tutorial", "setup-roblox"):
                        continue
                    self.assertIn(command, names | {"setup-roblox"}, f"{key} [{lang}] names /{command}")


class GameTexts(unittest.IsolatedAsyncioTestCase):
    """The guide, tutorial and /setup-roblox window talk about eggs, events, gifts, bans and the leaderboard."""

    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()

    async def asyncTearDown(self):
        await database.close_db()
        self.temp.__exit__(None, None, None)

    async def test_the_guide_and_tutorial_talk_about_the_game(self):
        from cogs import setup_guide, tutorial
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                topics = setup_guide.available_topics()
                self.assertGreater(len(topics), 10)
                self.assertIn("game_live", [t["id"] for t in topics], f"[{lang}] the game page is in the guide")
                shown = ""
                for index, topic in enumerate(topics):
                    embed = setup_guide.build_embed(topics, index, 0)
                    fakes.check_embed(embed, f"guide {topic['id']} [{lang}]")
                    shown += "\n".join([embed.description or ""] + [f"{f.name} {f.value}" for f in embed.fields])
                self.assertGreater(len(EGG_EVENT_WORDS.findall(shown)), 5, lang)
                self.assertGreater(len(FULL_ONLY_WORDS.findall(shown)), 3, f"[{lang}] the guide names gifts, bans...")
                chapters = json.dumps(tutorial.chapters(lang), ensure_ascii=False)
                self.assertGreater(len(EGG_EVENT_WORDS.findall(chapters)), 5, lang)
                self.assertGreater(len(FULL_ONLY_WORDS.findall(chapters)), 3, lang)
                ids = [c["id"] for c in tutorial.chapters(lang)]
                for chapter in ("eggs", "events", "gifts"):
                    self.assertIn(chapter, ids, f"[{lang}] the {chapter} chapter")

    async def test_the_roblox_window_has_every_button(self):
        from cogs import setup_roblox
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                view = setup_roblox.RobloxPanelView()
                for attr in ("eggs", "events", "codes", "control", "gifts", "bans", "ranking", "player"):
                    self.assertIn(getattr(view, attr), view.children, f"[{lang}] the {attr} button")
                embed = await setup_roblox.roblox_panel_embed()
                self.assertGreater(len(json.dumps(embed.to_dict(), ensure_ascii=False)), 500, "the embed was really built")
                features = next(f.value for f in embed.fields if f.name == i18n.t("rbx.features_field"))
                self.assertEqual(len(features.splitlines()), 5, f"[{lang}] codes, eggs, events, gifts, leaderboard: {features}")
                self.assertTrue(EGG_EVENT_WORDS.search(features), f"[{lang}] eggs and events are listed")

    async def test_the_guide_and_tutorial_have_the_same_structure_in_every_language(self):
        """The same chapter ids and fields in all three languages, and no leftover full_only flag."""
        for kind in ("guide", "tutorial"):
            data = {}
            for lang in LANGS:
                with open(os.path.join(ROOT, "locales", f"{kind}_{lang}.json"), encoding="utf-8") as f:
                    data[lang] = json.load(f)
            shape = {lang: [(item.get("id"), [len(f) for f in item["fields"]]) for item in items] for lang, items in data.items()}
            self.assertEqual(shape["en"], shape["pl"], kind)
            self.assertEqual(shape["en"], shape["es"], kind)
            for lang, items in data.items():
                self.assertEqual([i.get("id") for i in items if i.get("full_only")], [], f"{kind} [{lang}]: no part is full-only any more")


if __name__ == "__main__":
    unittest.main()
