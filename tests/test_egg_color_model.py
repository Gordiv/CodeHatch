"""The egg color against an egg model, and an egg form saved without a change.

- utils/roblox_kit.egg_model / color_warning: the game stands the egg's own model (else "Default") instead of the colored
  egg, so a chosen color has no effect; the note says so, in every language, and only then;
- live_game.create_egg / save_egg_changes: the note comes with a chosen color other than white (white is the default, never
  worth a note), with a changed color or model, and not with other changes;
- EggDoneView: with a model the color menu says so and has no option picked; picking what the egg already has is
  eggs.already_set, not a second save;
- live_game.NothingToChange: an edit form saved without a change shows the egg card with its menus (and the short text),
  in place of the window or as a new private message; a gone egg is eggs.not_found; error_text keeps the ℹ️ texts as they are;
- the new texts exist in the three languages, with the same {placeholders}, and fit Discord's limits."""
import json
import os
import re
import time
import unittest
from unittest import mock

import discord

from tests import fakes
from tests.helpers import ROOT
from tests.test_egg_edit_checks import Base, row_dict
from utils import database, i18n, roblox_kit

LANGS = ("en", "pl", "es")
WITH_MODELS = {"values": [], "attributes": [], "spots": ["Spawn", "Lobby"], "templates": ["Default", "Golden"],
               "multipliers": [], "hooks": ["OnReward"], "at": 0, "studio": False}
NO_DEFAULT = dict(WITH_MODELS, templates=["Golden"])
NO_MODELS = dict(WITH_MODELS, templates=[])
GOLD = "#FFD700"


def locale(lang: str) -> dict:
    with open(os.path.join(ROOT, "locales", f"{lang}.json"), encoding="utf-8") as f:
        return json.load(f)


def placeholders(text: str) -> set:
    return set(re.findall(r"\{(\w+)\}", text))


class EggModelAndColorNotes(unittest.TestCase):
    def test_which_model_the_game_stands(self):
        cases = [(WITH_MODELS, "", "Default"), (WITH_MODELS, "Golden", "Golden"), (WITH_MODELS, "Missing", "Default"),
                 (WITH_MODELS, " Golden ", "Golden"), (WITH_MODELS, None, "Default"), (WITH_MODELS, "golden", "Default"),
                 (NO_DEFAULT, "", ""), (NO_DEFAULT, "Golden", "Golden"), (NO_DEFAULT, "Missing", ""), (NO_MODELS, "Golden", ""),
                 (NO_MODELS, "", ""), (None, "Golden", ""), ({}, "Golden", "")]
        for scan, template, expected in cases:
            self.assertEqual(roblox_kit.egg_model(scan, template), expected, (scan and scan["templates"], template))

    def test_the_note_exists_only_with_a_model_and_names_it_in_every_language(self):
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                note = roblox_kit.color_warning(WITH_MODELS, "Golden")
                self.assertEqual(note, i18n.t("scan.warn_color_model", model="Golden"), lang)
                self.assertIn("Golden", note, lang)
                self.assertNotIn("{", note, lang)
                self.assertEqual(roblox_kit.color_warning(WITH_MODELS, ""), i18n.t("scan.warn_color_model", model="Default"))
                for scan in (NO_MODELS, NO_DEFAULT, None):
                    self.assertEqual(roblox_kit.color_warning(scan, ""), "", f"{lang}: nothing to say without a model")


class NewTexts(unittest.TestCase):
    NEW = ("eggs.already_set", "scan.warn_color_model", "rbx.egg_color_model_ph", "live.sent", "announce.sent", "give.description")

    def test_every_new_text_is_in_all_three_languages_with_the_same_placeholders(self):
        texts = {lang: locale(lang) for lang in LANGS}
        for key in self.NEW:
            for lang in LANGS:
                self.assertIn(key, texts[lang], f"{key} [{lang}]")
                self.assertTrue(texts[lang][key].strip(), f"{key} [{lang}]")
            self.assertEqual(placeholders(texts["pl"][key]), placeholders(texts["en"][key]), key)
            self.assertEqual(placeholders(texts["es"][key]), placeholders(texts["en"][key]), key)
        self.assertEqual(placeholders(texts["en"]["scan.warn_color_model"]), {"model"})
        self.assertEqual(placeholders(texts["en"]["rbx.egg_color_model_ph"]), {"model"})

    def test_the_short_info_texts_start_with_the_info_sign(self):
        # error_text() leaves a text that starts with it as it is; any other text gets a red cross in front
        for lang in LANGS:
            texts = locale(lang)
            for key in ("eggs.already_set", "eggs.nothing_to_change"):
                self.assertTrue(texts[key].startswith("ℹ️"), f"{key} [{lang}]")

    def test_the_studio_notes_say_studio_in_every_language(self):
        for lang in LANGS:
            texts = locale(lang)
            for key in ("live.sent", "announce.sent", "give.description"):
                self.assertIn("Studio", texts[key], f"{key} [{lang}]")

    def test_the_texts_fit_where_they_are_sent(self):
        from cogs import live_game
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                text = i18n.t("announce.sent", text="x" * 200)  # the form takes 200 characters
                self.assertLessEqual(len(text), 2000, lang)
                self.assertNotIn("{", text)
                self.assertLessEqual(len(i18n.t("give.description", username="u" * 20)), 4096, lang)
                self.assertLessEqual(len(i18n.t("live.sent")), 1024, "it goes into an embed field")
                self.assertLessEqual(len(i18n.t("eggs.already_set")), 2000)
                self.assertLessEqual(len(roblox_kit.color_warning(WITH_MODELS, "M" * 100)) + len(live_game.sync_note(True, "")), 1024,
                                     f"{lang}: the color note with the longest model name fits an embed field with the sync line")

    def test_error_text_keeps_the_info_texts_and_marks_the_rest(self):
        from cogs import live_game
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                for text in (i18n.t("eggs.nothing_to_change"), i18n.t("eggs.already_set"), "⚠️ careful", "❌ no"):
                    self.assertEqual(live_game.error_text(RuntimeError(text)), text, (lang, text))
                self.assertEqual(live_game.error_text(live_game.RuleError("plain")), "❌ plain")
                self.assertEqual(live_game.error_text(live_game.NothingToChange(i18n.t("eggs.nothing_to_change"))),
                                 i18n.t("eggs.nothing_to_change"), "the /egg-edit answer has no red cross in front of ℹ️")

    def test_nothing_to_change_is_a_rule_error(self):
        from cogs import live_game
        self.assertTrue(issubclass(live_game.NothingToChange, live_game.RuleError), "every place that catches RuleError still does")


class Notes(Base):
    """The color note in the answers of create_egg and save_egg_changes."""

    def sync_field(self, embed: discord.Embed) -> str:
        return next(f.value for f in embed.fields if f.name == self.live.t("codes.sync_field"))

    def note(self, model: str) -> str:
        return self.live.t("scan.warn_color_model", model=model)

    async def create(self, name: str, scan, **kwargs) -> str:
        with mock.patch.object(roblox_kit, "game_scan", return_value=scan):
            embed = await self.live.create_egg(name, "Coins", 100, "Cat:60, Dog:40", author_id=7, **kwargs)
        return self.sync_field(embed)

    async def test_a_new_egg_with_a_color_and_a_model_gets_the_note(self):
        self.assertIn(self.note("Default"), await self.create("Gold Default", WITH_MODELS, color="gold"))
        self.assertIn(self.note("Golden"), await self.create("Gold Golden", WITH_MODELS, color="gold", template="Golden"))
        self.assertIn(self.note("Default"), await self.create("Red Missing", WITH_MODELS, color="red", template="Missing"),
                      "a model that isn't there: the game stands Default")
        self.assertIn(self.note("Golden"), await self.create("Rainbow Golden", NO_DEFAULT, color="rainbow", template="Golden"))

    async def test_no_note_for_white_for_no_model_or_for_no_report(self):
        for label, scan, kwargs in (("white", WITH_MODELS, {}), ("white, said", WITH_MODELS, {"color": "white"}),
                                    ("no models", NO_MODELS, {"color": "gold"}), ("no report", None, {"color": "gold"}),
                                    ("model missing, no Default", NO_DEFAULT, {"color": "gold", "template": "Missing"}),
                                    ("no Default, no template", NO_DEFAULT, {"color": "gold"})):
            field = await self.create(f"Egg {label}", scan, **kwargs)
            self.assertNotIn("DiscordEggs", field, label)
            self.assertNotIn(self.note("Default"), field, label)
            self.assertNotIn(self.note("Golden"), field, label)

    async def test_the_note_comes_after_the_other_notes_and_the_sync_line_and_survives_them(self):
        bare = dict(WITH_MODELS, spots=[], hooks=[])  # no spots, no way to pay: two more notes
        field = await self.create("Many notes", bare, color="gold", template="Golden")
        self.assertIn(self.live.t("scan.warn_no_spots"), field)
        self.assertIn(self.note("Golden"), field, "the color note is whole, not cut at 1024 characters")
        self.assertLessEqual(len(field), 1024)

    async def test_the_note_is_in_every_language(self):
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                field = await self.create(f"Egg {lang}", WITH_MODELS, color="gold", template="Golden")
                self.assertIn(i18n.t("scan.warn_color_model", model="Golden"), field, lang)
                self.assertNotIn("{", field, lang)

    async def edit(self, egg, scan, **changes) -> str:
        with mock.patch.object(roblox_kit, "game_scan", return_value=scan):
            embed = await self.live.edit_egg(egg["id"], **changes)
        return self.sync_field(embed)

    async def test_changing_the_color_or_the_model_of_an_egg_gets_the_note(self):
        egg = await self.make_egg("Plain edit")
        self.assertIn(self.note("Default"), await self.edit(egg, WITH_MODELS, color="gold"))
        self.assertIn(self.note("Golden"), await self.edit(egg, WITH_MODELS, template="Golden"), "the egg is gold now: a model hides it")
        self.assertIn(self.note("Golden"), await self.edit(egg, WITH_MODELS, color="red"), "gold -> red, under the model it has now")

    async def test_other_changes_or_a_white_egg_get_no_note(self):
        egg = await self.make_egg("White egg")
        self.assertNotIn("DiscordEggs", await self.edit(egg, WITH_MODELS, template="Golden"), "a white egg: the model changes nothing the owner chose")
        self.assertNotIn("DiscordEggs", await self.edit(egg, WITH_MODELS, price=777))
        await self.edit(egg, WITH_MODELS, color="gold")
        self.assertNotIn("DiscordEggs", await self.edit(egg, WITH_MODELS, price=888), "a gold egg, but the color wasn't touched")
        self.assertNotIn("DiscordEggs", await self.edit(egg, WITH_MODELS, duration="7d"))
        self.assertNotIn("DiscordEggs", await self.edit(egg, WITH_MODELS, name="Renamed"))
        self.assertNotIn("DiscordEggs", await self.edit(egg, WITH_MODELS, color="white"), "back to white: no note")
        self.assertEqual((await database.get_egg(egg["id"]))["color"], self.live.EGG_COLORS["white"])

    async def test_no_note_without_a_model_or_a_report(self):
        egg = await self.make_egg("No model edit")
        for scan in (NO_MODELS, None, NO_DEFAULT):
            await database.update_egg(egg["id"], color=self.live.EGG_COLORS["white"], template="")
            self.assertNotIn("DiscordEggs", await self.edit(egg, scan, color="gold"), scan and scan["templates"])
        await database.update_egg(egg["id"], color=GOLD, template="")
        self.assertNotIn("DiscordEggs", await self.edit(egg, NO_DEFAULT, template="Missing"))

    async def test_an_egg_with_an_empty_color_is_treated_as_white(self):
        egg = await self.make_egg("Empty color")
        await database.update_egg(egg["id"], color="")
        self.assertNotIn("DiscordEggs", await self.edit(egg, WITH_MODELS, template="Golden"))

    async def test_the_note_is_added_to_a_change_of_pets_too(self):
        egg = await self.make_egg("Pets and color")
        field = await self.edit(egg, dict(WITH_MODELS, spots=[]), color="gold", pets_text="Cat:10, Dog:90")
        self.assertIn(self.live.t("scan.warn_no_spots"), field)
        self.assertIn(self.note("Default"), field)


class EggCard(Base):
    """EggDoneView: the color menu next to a model, and picking what the egg already has."""

    async def card(self, egg_id: int, scan=WITH_MODELS):
        with mock.patch.object(roblox_kit, "game_scan", return_value=scan):
            return self.panel.EggDoneView(egg_id, await database.get_egg(egg_id))

    async def test_without_a_model_the_menu_picks_the_current_color(self):
        egg = await self.make_egg()
        await database.update_egg(egg["id"], color=self.live.EGG_COLORS["gold"])
        for scan in (NO_MODELS, None, NO_DEFAULT):
            card = await self.card(egg["id"], scan)
            self.assertEqual([o.value for o in card.color.options if o.default], ["gold"], scan and scan["templates"])
            self.assertEqual(card.color.placeholder, self.live.t("rbx.egg_color_ph"))

    async def test_with_a_model_no_color_is_picked_and_the_placeholder_names_the_model(self):
        egg = await self.make_egg()
        await database.update_egg(egg["id"], color=self.live.EGG_COLORS["gold"])
        card = await self.card(egg["id"])
        self.assertEqual([o.value for o in card.color.options if o.default], [])
        self.assertEqual(card.color.placeholder, self.live.t("rbx.egg_color_model_ph", model="Default"))
        await database.update_egg(egg["id"], template="Golden")
        self.assertEqual((await self.card(egg["id"])).color.placeholder, self.live.t("rbx.egg_color_model_ph", model="Golden"))
        await database.update_egg(egg["id"], template="Missing")
        self.assertEqual((await self.card(egg["id"])).color.placeholder, self.live.t("rbx.egg_color_model_ph", model="Default"),
                         "a model the game doesn't have: Default")
        self.assertEqual(len(card.color.options), len(self.live.EGG_COLORS), "all colors can still be picked")

    async def test_the_card_without_a_row_is_the_plain_one(self):
        card = self.panel.EggDoneView(1)
        self.assertEqual(card.color.placeholder, self.live.t("rbx.egg_color_ph"))
        self.assertEqual([o.value for o in card.color.options if o.default], [])

    async def test_the_card_fits_discord_with_the_longest_model_name_in_every_language(self):
        long_scan = dict(WITH_MODELS, templates=["Default", "M" * 50])  # the form keeps 50 characters of a model name
        egg = await self.make_egg()
        await database.update_egg(egg["id"], template="M" * 50)
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                card = await self.card(egg["id"], long_scan)
                self.assertIn("M" * 50, card.color.placeholder, lang)
                self.assertLessEqual(len(card.color.placeholder), 150, lang)
                fakes.check_view(card, f"EggDoneView {lang}")

    async def test_picking_the_color_the_egg_already_has_is_a_short_private_note(self):
        egg = await self.make_egg()
        await database.update_egg(egg["id"], color=self.live.EGG_COLORS["gold"])
        card = await self.card(egg["id"])
        card.color._values = ["gold"]  # with a model nothing is shown picked, so this is easy to do
        inter = fakes.Interaction()
        before, pushed = row_dict(await database.get_egg(egg["id"])), len(self.pushed)
        with mock.patch.object(roblox_kit, "game_scan", return_value=WITH_MODELS):
            await card.color.callback(inter)
        content, kwargs = inter.response.sent[-1]
        self.assertEqual(content, self.live.t("eggs.already_set"))
        self.assertTrue(kwargs["ephemeral"])
        self.assertEqual(row_dict(await database.get_egg(egg["id"])), before)
        self.assertEqual(len(self.pushed), pushed, "nothing is sent to the game")
        self.assertFalse(card.is_finished(), "the card keeps working")
        self.assertFalse(inter.edited)

    async def test_the_same_model_again_is_the_same_short_note(self):
        egg = await self.make_egg()
        await database.update_egg(egg["id"], template="Golden")
        card = await self.card(egg["id"])
        card.template._values = ["1"]  # Golden (0 = Default, 1 = Golden in WITH_MODELS)
        inter = fakes.Interaction()
        with mock.patch.object(roblox_kit, "game_scan", return_value=WITH_MODELS):
            await card.template.callback(inter)
        self.assertEqual(inter.response.sent[-1][0], self.live.t("eggs.already_set"))
        self.assertEqual((await database.get_egg(egg["id"]))["template"], "Golden")

    async def test_a_new_color_under_a_model_is_saved_with_the_note_and_a_fresh_card(self):
        egg = await self.make_egg()
        card = await self.card(egg["id"])
        card.color._values = ["red"]
        inter = fakes.Interaction()
        with mock.patch.object(roblox_kit, "game_scan", return_value=WITH_MODELS):
            await card.color.callback(inter)
        self.assertEqual((await database.get_egg(egg["id"]))["color"], self.live.EGG_COLORS["red"])
        edited = inter.edited[-1]
        field = next(f.value for f in edited["embed"].fields if f.name == self.live.t("codes.sync_field"))
        self.assertIn(self.live.t("scan.warn_color_model", model="Default"), field)
        self.assertIsInstance(edited["view"], self.panel.EggDoneView)
        self.assertEqual(edited["view"].color.placeholder, self.live.t("rbx.egg_color_model_ph", model="Default"))
        self.assertEqual([o.value for o in edited["view"].color.options if o.default], [])
        self.assertIn("eggs", self.pushed)

    async def test_a_color_picked_for_a_gone_egg_is_not_found_not_already_set(self):
        egg = await self.make_egg()
        card = await self.card(egg["id"])
        await database.remove_egg(egg["id"])
        card.color._values = ["white"]
        inter = fakes.Interaction()
        await card.color.callback(inter)
        self.assertEqual(inter.response.sent[-1][0], self.live.error_text(self.live.RuleError(self.live.t("eggs.not_found"))))


class FormWithoutAChange(Base):
    """An edit form saved as it was: the egg card with its menus and the short text."""

    async def test_a_new_private_message_with_the_card(self):
        egg = await self.make_egg("Same as before")
        before, pushed = row_dict(await database.get_egg(egg["id"])), len(self.pushed)
        inter = await self.submit(self.panel.EggModal(egg=egg))
        content, kwargs = inter.followup.sent[-1]
        self.assertEqual(content, self.live.t("eggs.nothing_to_change"))
        self.assertTrue(kwargs["ephemeral"], "private")
        self.assertIsInstance(kwargs["view"], self.panel.EggDoneView)
        self.assertEqual(kwargs["view"].egg_id, egg["id"])
        self.assertIn("Same as before", kwargs["embed"].title)
        self.assertEqual(kwargs["embed"].footer.text, self.live.t("rbx.egg_done_footer"), "the footer points at the menus")
        self.assertEqual(row_dict(await database.get_egg(egg["id"])), before)
        self.assertEqual(len(self.pushed), pushed, "nothing sent to the game")

    async def test_in_place_of_the_window_it_came_from(self):
        egg = await self.make_egg("In place")
        card = self.panel.EggDoneView(egg["id"])
        inter = await self.submit(self.panel.EggModal(egg=egg, source=card))
        edited = inter.edited[-1]
        self.assertEqual(edited["content"], self.live.t("eggs.nothing_to_change"))
        self.assertIsInstance(edited["view"], self.panel.EggDoneView)
        self.assertIn("In place", edited["embed"].title)
        self.assertFalse(inter.followup.sent, "the same message, not a new one")

    async def test_the_new_card_works(self):
        egg = await self.make_egg("Works after")
        inter = await self.submit(self.panel.EggModal(egg=egg))
        card = inter.followup.sent[-1][1]["view"]
        card.duration._values = ["24h"]
        again = fakes.Interaction()
        await card.duration.callback(again)
        self.assertTrue(0 < (await database.get_egg(egg["id"]))["ends_at"] - time.time() <= 86400)

    async def test_the_card_shows_the_model_hint_for_a_colored_egg(self):
        egg = await self.make_egg("Colored")
        await database.update_egg(egg["id"], color=GOLD)
        inter = await self.submit(self.panel.EggModal(egg=await database.get_egg(egg["id"])))
        card = inter.followup.sent[-1][1]["view"]
        self.assertEqual(card.color.placeholder, self.live.t("rbx.egg_color_model_ph", model="Default"))

    async def test_a_gone_egg_is_not_found_with_no_card(self):
        for how in ("removed", "expired"):
            egg = await self.make_egg(f"Gone {how}")
            modal = self.panel.EggModal(egg=egg)
            if how == "removed":
                await database.remove_egg(egg["id"])
            else:
                await database.update_egg(egg["id"], ends_at=int(time.time()) - 5)
            inter = await self.submit(modal)  # nothing changed in the form, but the egg is gone
            content, kwargs = inter.followup.sent[-1]
            self.assertIn(self.live.t("eggs.not_found"), content, how)
            self.assertNotIn(self.live.t("eggs.nothing_to_change"), content, how)
            self.assertNotIsInstance(kwargs.get("view"), self.panel.EggDoneView, how)

    async def test_the_egg_that_goes_between_the_check_and_the_card(self):
        # egg_changes() found nothing to change, then the egg was removed before the card was built
        for how in ("removed", "expired"):
            egg = await self.make_egg(f"Between {how}")
            modal = self.fill(self.panel.EggModal(egg=egg))

            async def nothing(*args, _egg=egg, _how=how, **kwargs):
                if _how == "removed":
                    await database.remove_egg(_egg["id"])
                else:
                    await database.update_egg(_egg["id"], ends_at=int(time.time()) - 5)
                raise self.live.NothingToChange(self.live.t("eggs.nothing_to_change"))

            inter = fakes.Interaction()
            with mock.patch.object(self.live, "egg_changes", nothing):
                await modal.on_submit(inter)
            content, kwargs = inter.followup.sent[-1]
            self.assertEqual(content, self.live.t("eggs.not_found"), how)
            self.assertNotIsInstance(kwargs.get("view"), self.panel.EggDoneView, how)
            self.assertIsInstance(kwargs["view"], self.panel.CloseView, "a closable message")

    async def test_in_every_language(self):
        egg = await self.make_egg("Languages")
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                inter = await self.submit(self.panel.EggModal(egg=egg))
                self.assertEqual(inter.followup.sent[-1][0], i18n.t("eggs.nothing_to_change"), lang)

    async def test_a_changed_form_is_still_saved_as_before(self):
        egg = await self.make_egg("Still saved")
        inter = await self.submit(self.panel.EggModal(egg=egg), price="4321")
        self.assertEqual((await database.get_egg(egg["id"]))["price"], 4321)
        self.assertNotIn(self.live.t("eggs.nothing_to_change"), self.said(inter))

    async def test_egg_changes_raises_nothing_to_change_only_when_nothing_differs(self):
        egg = await self.make_egg("Differs")
        row = await database.get_egg(egg["id"])
        with self.assertRaises(self.live.NothingToChange):
            await self.live.egg_changes(egg["id"], name=row["name"], price=row["price"], color="white")
        with self.assertRaises(self.live.NothingToChange):
            await self.live.egg_changes(egg["id"])
        self.assertEqual(await self.live.egg_changes(egg["id"], price=row["price"] + 1), {"price": row["price"] + 1})
        with self.assertRaises(self.live.RuleError) as raised:
            await self.live.egg_changes(0)
        self.assertNotIsInstance(raised.exception, self.live.NothingToChange, "a missing egg is not 'nothing to change'")
        await database.remove_egg(egg["id"])
        with self.assertRaises(self.live.RuleError) as raised:
            await self.live.egg_changes(egg["id"])
        self.assertNotIsInstance(raised.exception, self.live.NothingToChange)


if __name__ == "__main__":
    unittest.main()
