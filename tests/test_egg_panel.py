"""Point 4: eggs in the panel - a new egg, an egg copied from the game catalog, editing an egg with its values filled in,
and its color, time and model right under the finished egg. /egg-edit uses the same checks."""
import json
import time
import unittest
from unittest import mock

import discord

from tests import fakes
from tests.helpers import TempBot
from utils import catalog, config_store, database, roblox_kit

SCAN = {"values": [], "attributes": [], "spots": ["Spawn", "Lobby"], "templates": ["Default", "Golden"],
        "multipliers": [], "hooks": [], "at": 0, "studio": False}
PRESETS = [("Basic Egg", "Cat:60, Dog:40", "Coins", 100), ("Rare Egg", "Dragon:5, Cat:95", "Gems", 50)]


class EggSetup(unittest.IsolatedAsyncioTestCase):
    """A temporary bot with two currencies, three pets, a game report with spots and models, two catalog eggs."""

    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import live_game, setup_roblox
        self.live, self.panel = live_game, setup_roblox
        config_store.write_json("game_economy.json", {"configured": True, "currencies": ["Coins", "Gems"],
                                                      "pets": ["Cat", "Dog", "Dragon"]})
        self.pushed = []

        async def push(kind, force=True):
            self.pushed.append(kind)
            return True, ""

        self.patches = [mock.patch.object(live_game, "push_live", push),
                        mock.patch.object(roblox_kit, "game_scan", return_value=SCAN),
                        mock.patch.object(catalog, "egg_presets", return_value=PRESETS)]
        for patch in self.patches:
            patch.start()

    async def asyncTearDown(self):
        for patch in self.patches:
            patch.stop()
        await database.close_db()
        self.temp.__exit__(None, None, None)

    async def make_egg(self, name="Dragon Egg", price=500):
        await self.live.create_egg(name, "Coins", price, "Cat:60, Dog:35, Dragon:5", spot="Spawn", author_id=7)
        return next(r for r in await database.get_active_eggs() if r["name"] == name)

    def fill(self, modal, name=None, price=None, pets=None, currency=None, spot=None):
        if name is not None:
            modal.egg_name._value = name
        if price is not None:
            modal.price._value = price
        if pets is not None:
            modal.pets._value = pets
        if currency is not None:
            modal.currency._values = [currency]
        if spot is not None:
            modal.spot._values = [spot]
        for item in (modal.egg_name, modal.price, modal.pets):  # untouched fields keep their filled-in value
            if getattr(item, "_value", None) is None:
                item._value = item.default or ""
        for select in (modal.currency, modal.spot):
            if isinstance(select, discord.ui.Select) and not select._values:
                select._values = [next((o.value for o in select.options if o.default), select.options[0].value)]
        return modal


class EggPanel(EggSetup):
    async def test_a_new_egg_gets_its_color_time_and_model_menus(self):
        modal = self.fill(self.panel.EggModal(), "Ice Egg", "250", "Cat:1, Dog:1", "Coins", "0")
        inter = fakes.Interaction()
        await modal.on_submit(inter)
        egg = next(r for r in await database.get_active_eggs() if r["name"] == "Ice Egg")
        content, kwargs = inter.followup.sent[-1]
        done = kwargs["view"]
        self.assertIsInstance(done, self.panel.EggDoneView)
        self.assertEqual(done.egg_id, egg["id"])
        self.assertIn(done.template, done.children, "the game has egg models: the model menu is there")
        self.assertTrue(kwargs["embed"].footer.text, "the footer points at the menus")
        self.assertEqual(egg["spot"], "Spawn")

    async def test_color_time_and_model_change_at_once(self):
        egg = await self.make_egg()
        done = self.panel.EggDoneView(egg["id"])
        for select, value, check in ((done.color, "gold", lambda r: r["color"] == self.live.EGG_COLORS["gold"]),
                                     (done.duration, "24h", lambda r: 0 < r["ends_at"] - time.time() <= 86400),
                                     (done.template, "1", lambda r: r["template"] == "Golden")):
            select._values = [value]
            inter = fakes.Interaction()
            await select.callback(inter)
            row = await database.get_egg(egg["id"])
            self.assertTrue(check(row), value)
            self.assertIsInstance(inter.edited[-1]["view"], self.panel.EggDoneView, "the same message, fresh menus")
            self.assertFalse(inter.followup.sent)
            done = inter.edited[-1]["view"]
        self.assertGreaterEqual(self.pushed.count("eggs"), 4, "every change is sent to the game")

    async def test_the_same_color_again_is_a_short_note_not_a_new_save(self):
        egg = await self.make_egg()
        done = self.panel.EggDoneView(egg["id"])
        done.color._values = ["white"]
        inter = fakes.Interaction()
        await done.color.callback(inter)
        self.assertTrue(inter.response.sent and inter.response.sent[-1][1]["ephemeral"])
        self.assertFalse(done.is_finished(), "the window keeps working")

    async def test_edit_opens_the_form_with_the_egg_values(self):
        egg = await self.make_egg(price=1500)
        modal = self.panel.EggModal(egg=egg)
        self.assertEqual(modal.egg_name.default, "Dragon Egg")
        self.assertEqual(modal.price.default, "1500")
        self.assertEqual(self.live.parse_pets(modal.pets.default), json.loads(egg["pets"]), "pets survive the round trip")
        self.assertEqual([o.label for o in modal.spot.options if o.default], ["Spawn"])
        self.assertEqual([o.value for o in modal.currency.options if o.default], ["Coins"])
        done = self.panel.EggDoneView(egg["id"])
        self.fill(modal, price="2 000")
        modal.source = done
        inter = fakes.Interaction()
        await modal.on_submit(inter)
        self.assertEqual((await database.get_egg(egg["id"]))["price"], 2000)
        self.assertIsInstance(inter.edited[-1]["view"], self.panel.EggDoneView, "the answer replaces the card")

    async def test_a_mistake_in_the_form_keeps_the_egg_card(self):
        egg = await self.make_egg()
        done = self.panel.EggDoneView(egg["id"])
        modal = self.fill(self.panel.EggModal(egg=egg, source=done), pets="not a pet list")
        inter = fakes.Interaction()
        await modal.on_submit(inter)
        self.assertEqual(list(inter.edited[-1]), ["content"], "only a note above the card, which stays")
        self.assertIn("❌", inter.edited[-1]["content"])
        self.assertEqual((await database.get_egg(egg["id"]))["pets"], egg["pets"])

    async def test_copy_an_egg_from_the_game_catalog(self):
        view = self.panel.EggsView()
        self.assertIn(view.copy, view.children)
        inter = fakes.Interaction()
        await view.copy.callback(inter)
        chooser = inter.response.sent[-1][1]["view"]
        pick = next(c for c in chooser.children if isinstance(c, self.panel.EggPickSelect))
        pick._values = ["1"]
        inter = fakes.Interaction()
        await pick.callback(inter)
        modal = inter.response.modals[-1]
        self.assertEqual((modal.egg_name.default, modal.pets.default, modal.price.default), ("Rare Egg", "Dragon:5, Cat:95", "50"))
        self.assertEqual([o.value for o in modal.currency.options if o.default], ["Gems"])
        self.fill(modal)
        inter = fakes.Interaction()
        await modal.on_submit(inter)
        egg = next(r for r in await database.get_active_eggs() if r["name"] == "Rare Egg")
        self.assertEqual((egg["currency"], egg["price"]), ("Gems", 50))
        self.assertIsInstance(inter.edited[-1]["view"], self.panel.EggDoneView, "the result replaces the chooser")
        with mock.patch.object(catalog, "egg_presets", return_value=[]):
            self.assertNotIn(self.panel.EggsView().copy, self.panel.EggsView().children, "no catalog eggs: no button")

    async def test_edit_picks_the_egg_and_reads_its_newest_values(self):
        view = self.panel.EggsView()
        inter = fakes.Interaction()
        await view.edit.callback(inter)
        self.assertEqual(inter.response.sent[-1][0], self.live.t("eggs.list_empty"), "no eggs yet: a short note")
        self.assertFalse(inter.response.modals)
        first = await self.make_egg("One Egg")
        inter = fakes.Interaction()
        await view.edit.callback(inter)
        self.assertEqual(inter.response.modals[-1].egg["id"], first["id"], "one egg: straight to its form")
        second = await self.make_egg("Two Egg")
        inter = fakes.Interaction()
        await view.edit.callback(inter)
        pick = next(c for c in inter.response.sent[-1][1]["view"].children if isinstance(c, self.panel.EggPickSelect))
        await database.update_egg(second["id"], price=777)  # changed after the list was shown
        pick._values = ["1"]
        inter = fakes.Interaction()
        await pick.callback(inter)
        self.assertEqual(inter.response.modals[-1].price.default, "777")

    async def test_remove_under_the_egg(self):
        egg = await self.make_egg()
        done = self.panel.EggDoneView(egg["id"])
        inter = fakes.Interaction()
        await done.remove.callback(inter)
        self.assertFalse((await database.get_egg(egg["id"]))["active"])
        self.assertIn("Dragon Egg", inter.edited[-1]["content"])

    async def test_egg_edit_command_uses_the_same_checks(self):
        cog = self.live.LiveGame.__new__(self.live.LiveGame)
        egg = await self.make_egg()
        await self.make_egg("Other Egg")
        inter = fakes.Interaction()
        await cog.egg_edit.callback(cog, inter, str(egg["id"]), name="other egg")
        self.assertTrue(inter.response.sent[-1][1]["ephemeral"], "a refusal stays private, within Discord's 3 seconds")
        inter = fakes.Interaction()
        await cog.egg_edit.callback(cog, inter, str(egg["id"]), price=900)
        self.assertEqual((await database.get_egg(egg["id"]))["price"], 900)
        self.assertIn("embed", inter.followup.sent[-1][1], "the answer after 'thinking', in the channel like before")
        inter = fakes.Interaction()
        await cog.egg_edit.callback(cog, inter, str(egg["id"]), price=900)
        self.assertTrue(inter.response.sent, "nothing to change: said privately")

    async def test_changes_hold_only_what_differs(self):
        egg = await self.make_egg()
        changes = await self.live.egg_changes(egg["id"], name="Dragon Egg", price=600, spot="Spawn")
        self.assertEqual(changes, {"price": 600})
        with self.assertRaises(self.live.RuleError):
            await self.live.egg_changes(egg["id"], price=0)
        with self.assertRaises(self.live.RuleError):
            await self.live.egg_changes(9999, price=5)


class AfterTheReview(EggSetup):
    """The critic's findings: the edit form saves only what the person changed, never cuts a pet list, chances never
    drop to 0, an expired egg is gone, the currency is found by its exact name."""

    async def submit_untouched(self, modal, **changes):
        self.fill(modal, **changes)
        inter = fakes.Interaction()
        await modal.on_submit(inter)
        return inter

    async def test_a_change_made_meanwhile_by_someone_else_stays(self):
        egg = await self.make_egg(price=500)
        modal = self.panel.EggModal(egg=egg)  # opened with price 500 and spot Spawn
        await database.update_egg(egg["id"], price=1000, spot="Lobby")  # someone else, meanwhile
        await self.submit_untouched(modal, name="Renamed Egg")
        row = await database.get_egg(egg["id"])
        self.assertEqual((row["name"], row["price"], row["spot"]), ("Renamed Egg", 1000, "Lobby"))

    async def test_saving_without_a_change_changes_nothing(self):
        await self.live.create_egg("Odd Egg", "Coins", 10, "Cat:4, Dog:1, Fox:1", author_id=7)
        egg = next(r for r in await database.get_active_eggs() if r["name"] == "Odd Egg")
        pushed = len(self.pushed)
        inter = await self.submit_untouched(self.panel.EggModal(egg=egg))
        self.assertEqual(len(self.pushed), pushed, "nothing sent to the game")
        self.assertIn(self.live.t("eggs.nothing_to_change"), inter.followup.sent[-1][0])
        self.assertEqual((await database.get_egg(egg["id"]))["pets"], egg["pets"], "no drift of the chances")

    async def test_a_tiny_chance_never_becomes_zero(self):
        pets = self.live.parse_pets("Common:99.99999, Secret:0.00001")
        self.assertGreater(pets[1]["chance"], 0)
        self.assertEqual(self.live.parse_pets(self.live.pets_text({"pets": json.dumps(pets)}))[1]["name"], "Secret")
        self.assertEqual(len(self.live.parse_pets("Dog:33.3333333333, Cat:66.6666666667")), 2, "10 decimals from the catalog")

    async def test_a_long_pet_list_is_left_out_of_the_form_not_cut(self):
        pets = ", ".join(f"Pet number {i} with a very long name:{i + 1}" for i in range(24))
        await self.live.create_egg("Long Egg", "Coins", 10, pets, author_id=7)
        egg = next(r for r in await database.get_active_eggs() if r["name"] == "Long Egg")
        modal = self.panel.EggModal(egg=egg)
        self.assertIsNone(modal.pets.default)
        self.assertFalse(modal.pets.required, "empty = the pets stay as they are")
        modal.pets._value = ""
        await self.submit_untouched(modal, price="20")
        row = await database.get_egg(egg["id"])
        self.assertEqual((row["price"], row["pets"]), (20, egg["pets"]))

    async def test_a_catalog_egg_too_long_for_the_form_is_refused_and_many_eggs_are_mentioned(self):
        long_preset = ("Huge Egg", ", ".join(f"Pet {i} with a long name:1" for i in range(60)), "Coins", 5)
        with mock.patch.object(catalog, "egg_presets", return_value=[long_preset] + PRESETS * 15):
            inter = fakes.Interaction()
            await self.panel.EggsView().copy.callback(inter)
            self.assertIn("31", inter.response.sent[-1][0], "first 25 of 31 eggs")
            pick = next(c for c in inter.response.sent[-1][1]["view"].children if isinstance(c, self.panel.EggPickSelect))
            pick._values = ["0"]
            inter = fakes.Interaction()
            await pick.callback(inter)
            self.assertFalse(inter.response.modals, "the list is not cut into a form")
            self.assertIn("/egg-create", inter.response.sent[-1][0])

    async def test_an_expired_egg_is_gone(self):
        egg = await self.make_egg()
        await database.update_egg(egg["id"], ends_at=int(time.time()) - 5)
        with self.assertRaises(self.live.RuleError):
            await self.live.egg_changes(egg["id"], duration="7d")  # can't bring it back past the limits
        await database.remove_egg(egg["id"])
        self.assertFalse(await database.update_egg(egg["id"], price=5), "a removed egg is not changed")

    async def test_the_currency_is_found_by_its_exact_name(self):
        config_store.write_json("game_economy.json", {"configured": True, "currencies": ["💎", "🪙"]})
        picker = self.panel._currency_component({"currencies": ["💎", "🪙"]}, "🪙")
        self.assertEqual([o.value for o in picker.options if o.default], ["🪙"])

    async def test_the_color_menu_shows_the_current_color(self):
        egg = await self.make_egg()
        await database.update_egg(egg["id"], color=self.live.EGG_COLORS["gold"])
        with mock.patch.object(roblox_kit, "game_scan", return_value=dict(SCAN, templates=[])):  # the plain egg
            view = self.panel.EggDoneView(egg["id"], await database.get_egg(egg["id"]))
        self.assertEqual([o.value for o in view.color.options if o.default], ["gold"])

    async def test_the_color_menu_says_when_a_model_hides_the_color(self):
        # The game has the model "Default": the kit stands it instead of the colored egg, so the menu says so
        # (and picks nothing, otherwise Discord shows the picked color instead of the note)
        egg = await self.make_egg()
        await database.update_egg(egg["id"], color=self.live.EGG_COLORS["gold"])
        view = self.panel.EggDoneView(egg["id"], await database.get_egg(egg["id"]))
        self.assertEqual([o.value for o in view.color.options if o.default], [])
        self.assertEqual(view.color.placeholder, self.live.t("rbx.egg_color_model_ph", model="Default"))
        await database.update_egg(egg["id"], template="Golden")
        view = self.panel.EggDoneView(egg["id"], await database.get_egg(egg["id"]))
        self.assertEqual(view.color.placeholder, self.live.t("rbx.egg_color_model_ph", model="Golden"))


if __name__ == "__main__":
    unittest.main()
