"""Tester's checks of the egg edit flow (cogs/setup_roblox.py EggModal / EggDoneView / EggPickSelect / EggsView and
cogs/live_game.py egg_changes / save_egg_changes / pets_text / parse_pets), written to break it:
- pets_text -> parse_pets round trip for odd names and chances, also at random;
- a form saved without a change changes nothing and sends nothing;
- changes of other people meanwhile stay; a removed or expired egg is "not found" everywhere;
- two people at once and double clicks;
- Discord's limits with long names in the three languages;
- eggs copied from a game catalog with odd chances, currencies and prices.

Known defects are written as expectedFailure with the reason in the comment; remove the decorator when it is fixed."""
import asyncio
import json
import random
import time
import unittest
from unittest import mock

import discord

from tests import fakes
from tests.helpers import TempBot
from tests.panel_fakes import Message, interaction_for, make_guild
from utils import catalog, config_store, database, i18n, roblox_kit

LANGS = ("en", "pl", "es")
SCAN = {"values": [], "attributes": [], "spots": ["Spawn", "Lobby"], "templates": ["Default", "Golden"],
        "multipliers": [], "hooks": [], "at": 0, "studio": False}


def row_dict(row) -> dict:
    return {key: row[key] for key in row.keys()}


class Base(unittest.IsolatedAsyncioTestCase):
    """A temporary bot: two currencies, a game report with spots and egg models, nothing sent anywhere."""
    scan = SCAN
    presets = []

    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import live_game, setup_roblox
        self.live, self.panel = live_game, setup_roblox
        config_store.write_json("game_economy.json", {"configured": True, "currencies": ["Coins", "Gems"], "pets": []})
        self.pushed = []

        async def push(kind, force=True):
            self.pushed.append(kind)
            return True, ""

        self.patches = [mock.patch.object(live_game, "push_live", push),
                        mock.patch.object(roblox_kit, "game_scan", return_value=self.scan),
                        mock.patch.object(catalog, "egg_presets", return_value=self.presets)]
        for patch in self.patches:
            patch.start()

    async def asyncTearDown(self):
        for patch in self.patches:
            patch.stop()
        await database.close_db()
        self.temp.__exit__(None, None, None)

    async def make_egg(self, name="Test Egg", pets="Cat:60, Dog:35, Dragon:5", price=500, currency="Coins", spot="Spawn"):
        await self.live.create_egg(name, currency, price, pets, spot=spot, author_id=7)
        return next(r for r in await database.get_active_eggs() if r["name"] == name)

    def fill(self, modal, name=None, price=None, pets=None, currency=None, spot=None):
        """What Discord sends: a field nobody touched comes back with its filled-in value, a menu with its default."""
        if name is not None:
            modal.egg_name._value = name
        if price is not None:
            modal.price._value = price
        if pets is not None:
            modal.pets._value = pets
        if currency is not None:
            if isinstance(modal.currency, discord.ui.Select):
                modal.currency._values = [currency]
            else:
                modal.currency._value = currency
        if spot is not None and modal.spot is not None:
            modal.spot._values = [spot]
        for item in (modal.egg_name, modal.price, modal.pets):
            if getattr(item, "_value", None) is None:
                item._value = item.default or ""
        if isinstance(modal.currency, discord.ui.Select):
            if not modal.currency._values:
                modal.currency._values = [next((o.value for o in modal.currency.options if o.default), modal.currency.options[0].value)]
        elif getattr(modal.currency, "_value", None) is None:
            modal.currency._value = modal.currency.default or ""
        if modal.spot is not None and not modal.spot._values:
            modal.spot._values = [next((o.value for o in modal.spot.options if o.default), modal.spot.options[0].value)]
        return modal

    async def submit(self, modal, **changes):
        inter = fakes.Interaction()
        self.fill(modal, **changes)
        await modal.on_submit(inter)
        return inter

    @staticmethod
    def said(inter) -> str:
        """Every text the admin got from this interaction (answers, follow-ups and edits of the window)."""
        texts = [c for c, _ in inter.response.sent + inter.followup.sent if c]
        texts += [kw.get("content") for kw in inter.edited if kw.get("content")]
        return "\n".join(texts)


# ---------- the text of the pets: edit form <-> parse_pets ----------

class PetsRoundTrip(Base):
    CASES = {
        "tiny chance": [("Common", 99.9999), ("Secret", 0.0001)],
        "one pet": [("Only", 100.0)],
        "thirds": [("A", 33.3333), ("B", 33.3333), ("C", 33.3334)],
        "spaces": [("Golden  Dragon Of Doom", 50.0), ("Robot 2000", 50.0)],
        "digits and signs": [("Pet 1:2", 10.0), ("X=5", 90.0)],
        "not ASCII": [("Smok Złoty 🐉", 40.0), ("Ñandú", 59.5), ("寿司", 0.5)],
        "percent in a name": [("100%", 50.0), ("A", 50.0)],
        "name ending with a colon": [("Fox:", 25.0), ("Dog", 75.0)],
        "like a preset": [("Egg", 60.0), ("Cat", 40.0)],
    }

    def trip(self, pets):
        text = self.live.pets_text({"pets": json.dumps(pets)})
        return text, self.live.parse_pets(text)

    async def test_names_and_chances_survive_the_form(self):
        for label, pets in self.CASES.items():
            text, back = self.trip([{"name": n, "chance": c} for n, c in pets])
            self.assertEqual([p["name"] for p in back], [n for n, _ in pets], f"{label}: {text!r}")
            for (name, chance), got in zip(pets, back):
                self.assertAlmostEqual(got["chance"], chance, delta=0.0002, msg=f"{label}: {name}")

    async def test_a_big_pet_list_survives_too(self):
        pets = [{"name": f"Pet number {i}", "chance": p["chance"]} for i, p in
                enumerate(self.live.parse_pets(", ".join(f"Pet number {i}:{i * i + 1}" for i in range(25))))]
        text, back = self.trip(pets)
        self.assertEqual([p["name"] for p in back], [p["name"] for p in pets])
        self.assertAlmostEqual(sum(p["chance"] for p in back), 100, delta=0.01)
        with self.assertRaises(self.live.RuleError):
            self.live.parse_pets(", ".join(f"Pet {i}:1" for i in range(26)))  # one over the limit of 25: said, not cut

    async def test_random_lists(self):
        rng = random.Random(20260714)
        alphabet = "abcXYZ 019:=%.-_ąęłñ🐉'\"()[]"
        checked = 0
        for _ in range(1500):
            names = []
            for _ in range(rng.randint(1, 25)):
                name = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 30))).strip()
                if name and name.lower() not in {n.lower() for n in names}:
                    names.append(name)
            weights = [rng.choice([1, 2, 5, 10, 0.5, 0.0001, 1e6, 123456.789, 3, 1e9, 7]) for _ in names]
            try:
                stored = self.live.parse_pets(", ".join(f"{n}:{w}" for n, w in zip(names, weights)))
            except self.live.RuleError:
                continue  # a name the parser can't tell from the number: refused when it is typed, never stored
            text, back = self.trip(stored)
            self.assertEqual([p["name"] for p in back], [p["name"] for p in stored], text)
            for a, b in zip(stored, back):
                self.assertGreater(b["chance"], 0, text)
                self.assertAlmostEqual(a["chance"], b["chance"], delta=0.003, msg=text)  # 25 tiny pets lift the sum above 100
            checked += 1
        self.assertGreater(checked, 1000, "most lists parse, so the loop really tested something")

    async def test_a_chance_never_drops_to_zero_and_ten_decimals_are_read(self):
        pets = self.live.parse_pets("Common:1000000000, Secret:1")
        self.assertGreaterEqual(pets[1]["chance"], 0.0001)
        self.assertEqual(len(self.live.parse_pets("Dog:33.3333333333, Cat:66.6666666667")), 2)
        self.assertEqual(len(self.live.parse_pets("Dog:0.0000000001, Cat:1")), 2, "10 decimals")
        with self.assertRaises(self.live.RuleError):
            self.live.parse_pets("Dog:0.00000000001, Cat:1")  # 11 decimals: said, not guessed
        with self.assertRaises(self.live.RuleError):
            self.live.parse_pets("Dog:0, Cat:1")

    async def test_odd_rows_give_an_empty_text_not_a_crash(self):
        for raw in (None, "", "not json", "[1, 2]", '[{"chance": 5}]', '{"a": 1}'):
            self.assertIsInstance(self.live.pets_text({"pets": raw}), str, repr(raw))
        self.assertEqual(self.live.pets_text({"pets": '[{"name": "Cat", "chance": 5}, 7, {"chance": 1}]'}), "Cat:5")

    async def test_a_stored_zero_chance_of_an_old_egg_is_kept_when_the_pets_are_not_touched(self):
        # an egg created before the minimum of 0.0001 may hold chance 0: the form shows "Secret:0", which parse_pets
        # refuses, so saving the other fields must not read that text again
        egg = await self.make_egg("Old Egg", "Cat:60, Dog:40")
        old = json.dumps([{"name": "Cat", "chance": 100.0}, {"name": "Secret", "chance": 0.0}])
        await database.update_egg(egg["id"], pets=old)
        egg = await database.get_egg(egg["id"])
        modal = self.panel.EggModal(egg=egg)
        self.assertIn("Secret:0", modal.pets.default)
        inter = await self.submit(modal, price="777")
        row = await database.get_egg(egg["id"])
        self.assertEqual((row["price"], row["pets"]), (777, old), self.said(inter))

    async def test_a_pet_with_a_tiny_chance_is_not_shown_as_zero_percent(self):
        # DEFECT (low): the minimum chance 0.0001 is shown as "0%" (chance_text rounds to two decimals), so the admin
        # sees "Secret - 0%" and thinks the pet can't drop. Fix: show "<0.01%" below 0.005.
        self.assertNotEqual(self.live.chance_text(0.0001), "0%")


# ---------- saving the edit form ----------

class SavingTheForm(Base):
    async def test_a_form_saved_without_a_change_changes_and_sends_nothing(self):
        cases = {"odd chances": "Cat:4, Dog:1, Fox:1", "tiny": "Common:99.9999, Secret:0.0001",
                 "25 pets": ", ".join(f"Pet{i}:{i + 1}" for i in range(25)), "not ASCII": "Smok Złoty 🐉:40, Ñandú:60",
                 "colon in a name": "Pet 1:2:10, X=5:90", "thirds": "A:1, B:1, C:1"}
        for label, pets in cases.items():
            for number, spot in enumerate(("Spawn", "", "Old spot not in the game")):
                egg = await self.make_egg(f"{label} {number}", pets, spot=spot)
                before, pushed = row_dict(await database.get_egg(egg["id"])), len(self.pushed)
                inter = await self.submit(self.panel.EggModal(egg=egg))
                self.assertEqual(row_dict(await database.get_egg(egg["id"])), before, f"{label}/{spot}: the row is the same")
                self.assertEqual(len(self.pushed), pushed, f"{label}/{spot}: nothing sent to the game")
                self.assertIn(self.live.t("eggs.nothing_to_change"), self.said(inter), f"{label}/{spot}")

    async def test_the_same_without_a_game_report_and_with_a_currency_outside_the_menu(self):
        with mock.patch.object(roblox_kit, "game_scan", return_value=None):
            egg = await self.make_egg("No report egg", currency="Rubies", spot="")  # not in the economy: still pickable
            modal = self.panel.EggModal(egg=egg)
            self.assertIsNone(modal.spot, "no report and no spot: no spot menu")
            with_spot = self.panel.EggModal(egg=await self.make_egg("Own spot egg", spot="Spawn"))
            self.assertEqual([(o.value, o.default) for o in with_spot.spot.options], [("-", False), ("0", True)],
                             "no report: the egg's own spot is still shown, picked")
            self.assertEqual([o.value for o in modal.currency.options if o.default], ["Rubies"])
            before = row_dict(await database.get_egg(egg["id"]))
            inter = await self.submit(modal)
            self.assertEqual(row_dict(await database.get_egg(egg["id"])), before)
            self.assertIn(self.live.t("eggs.nothing_to_change"), self.said(inter))

    async def test_only_what_the_person_changed_is_written(self):
        egg = await self.make_egg("Three Fields")
        for field, kwargs, column, expected in (("name", {"name": "Renamed"}, "name", "Renamed"),
                                                ("price", {"price": "1 200"}, "price", 1200),
                                                ("currency", {"currency": "Gems"}, "currency", "Gems"),
                                                ("spot", {"spot": "1"}, "spot", "Lobby")):
            before = row_dict(await database.get_egg(egg["id"]))
            await self.submit(self.panel.EggModal(egg=await database.get_egg(egg["id"])), **kwargs)
            after = row_dict(await database.get_egg(egg["id"]))
            # pending: the change waits for the game (utils/game_sync.py), not a column of the egg
            changed = {k for k in before if before[k] != after[k]} - {"pending"}
            self.assertEqual(changed, {column}, f"{field}: only that column changed, got {changed}")
            self.assertGreater(after["pending"], 0, f"{field}: the next sync sends the change to the game")
            self.assertEqual(after[column], expected)

    async def test_what_somebody_else_changed_meanwhile_stays(self):
        others = {"price": {"price": 9999}, "currency": {"currency": "Gems"},
                  "pets": {"pets": json.dumps([{"name": "Cat", "chance": 50.0}, {"name": "Dog", "chance": 50.0}])},
                  "spot": {"spot": "Lobby"}, "color": {"color": self.live.EGG_COLORS["gold"]},
                  "template": {"template": "Golden"}, "ends_at": {"ends_at": int(time.time()) + 5000}}
        for column, change in others.items():
            egg = await self.make_egg(f"Egg {column}")
            modal = self.panel.EggModal(egg=egg)  # opened with the old values
            await database.update_egg(egg["id"], **change)
            await self.submit(modal, name=f"Renamed {column}")
            row = await database.get_egg(egg["id"])
            self.assertEqual(row["name"], f"Renamed {column}")
            self.assertEqual(row[column], change[column], f"{column}: the other person's change survived")

    async def test_the_pets_are_saved_when_they_are_changed_and_checked(self):
        egg = await self.make_egg("Pets Egg")
        await self.submit(self.panel.EggModal(egg=egg), pets="Cat:1, Fox:3")
        pets = json.loads((await database.get_egg(egg["id"]))["pets"])
        self.assertEqual([(p["name"], p["chance"]) for p in pets], [("Cat", 25.0), ("Fox", 75.0)])
        before = row_dict(await database.get_egg(egg["id"]))
        inter = await self.submit(self.panel.EggModal(egg=await database.get_egg(egg["id"])), pets="Cat:1, Cat:2")
        self.assertIn("❌", self.said(inter), "a double pet is refused")
        self.assertEqual(row_dict(await database.get_egg(egg["id"])), before)

    async def test_a_rename_to_the_name_of_another_egg_is_refused(self):
        a, b = await self.make_egg("Alpha"), await self.make_egg("Beta")
        inter = await self.submit(self.panel.EggModal(egg=b), name="alpha")
        self.assertIn(self.live.t("eggs.err_exists", name="alpha"), self.said(inter))
        self.assertEqual((await database.get_egg(b["id"]))["name"], "Beta")
        inter = await self.submit(self.panel.EggModal(egg=a), name="ALPHA")  # the same egg, other letters: allowed
        self.assertEqual((await database.get_egg(a["id"]))["name"], "ALPHA", self.said(inter))

    async def test_a_price_typed_in_many_ways(self):
        egg = await self.make_egg("Price Egg", price=500)
        for typed, expected in (("1.500", 1500), ("1,500", 1500), ("  2 500 ", 2500), ("1_000_000_000_000", 10 ** 12)):
            await self.submit(self.panel.EggModal(egg=await database.get_egg(egg["id"])), price=typed)
            self.assertEqual((await database.get_egg(egg["id"]))["price"], expected, typed)
        for typed in ("0", "abc", "-5", "²", "", "١٢٣"):
            inter = fakes.Interaction()
            modal = self.fill(self.panel.EggModal(egg=await database.get_egg(egg["id"])), price=typed)
            before = row_dict(await database.get_egg(egg["id"]))
            await modal.on_submit(inter)
            self.assertEqual(row_dict(await database.get_egg(egg["id"])), before, repr(typed))
            self.assertTrue(inter.response.sent and inter.response.sent[-1][1]["ephemeral"], f"{typed!r} is said privately")
        inter = await self.submit(self.panel.EggModal(egg=await database.get_egg(egg["id"])), price=str(10 ** 12 + 1))
        self.assertIn("1,000,000,000,000", self.said(inter), "above the limit: said, with the limit")

    async def test_the_answer_goes_where_it_was_asked(self):
        egg = await self.make_egg("Where Egg")
        card = self.panel.EggDoneView(egg["id"])
        inter = await self.submit(self.panel.EggModal(egg=egg, source=card), price="600")
        self.assertIsInstance(inter.edited[-1]["view"], self.panel.EggDoneView, "in place of the card")
        self.assertFalse(inter.followup.sent)
        inter = await self.submit(self.panel.EggModal(egg=await database.get_egg(egg["id"])), price="700")
        self.assertIsInstance(inter.followup.sent[-1][1]["view"], self.panel.EggDoneView, "no card: a new private message")
        self.assertTrue(inter.followup.sent[-1][1]["ephemeral"])

    async def test_a_card_that_was_closed_gets_the_answer_as_a_new_message(self):
        egg = await self.make_egg("Closed Egg")
        card = self.panel.EggDoneView(egg["id"])
        card.stop()  # closed with the cross or removed after five minutes
        inter = await self.submit(self.panel.EggModal(egg=egg, source=card), price="650")
        self.assertEqual((await database.get_egg(egg["id"]))["price"], 650)
        self.assertEqual(inter.response.defers[-1].get("ephemeral"), True, "a private 'thinking', not an edit of nothing")

    async def test_the_message_is_gone_and_the_answer_still_arrives(self):
        egg = await self.make_egg("Gone Egg")
        guild = make_guild()
        modal = self.fill(self.panel.EggModal(egg=egg, source=self.panel.EggDoneView(egg["id"])), price="660")
        inter = interaction_for(guild, "admin", message=Message(), gone=True)
        await modal.on_submit(inter)
        self.assertEqual((await database.get_egg(egg["id"]))["price"], 660)
        self.assertTrue(inter.followup.sent, "the card was removed meanwhile: the answer is a new message")


# ---------- an egg that is removed or expired in the middle of it all ----------

class GoneEggs(Base):
    async def remove(self, egg, how):
        if how == "removed":
            await database.remove_egg(egg["id"])
        else:
            await database.update_egg(egg["id"], ends_at=int(time.time()) - 5)

    async def test_the_form_of_a_gone_egg_says_not_found_and_changes_nothing(self):
        for how in ("removed", "expired"):
            for with_card in (False, True):
                egg = await self.make_egg(f"{how} {with_card}")
                card = self.panel.EggDoneView(egg["id"]) if with_card else None
                modal = self.panel.EggModal(egg=egg, source=card)
                await self.remove(egg, how)
                before, pushed = row_dict(await database.get_egg(egg["id"])), len(self.pushed)
                inter = await self.submit(modal, name="Too late", price="1")
                where = f"{how}, card={with_card}"
                self.assertIn(self.live.t("eggs.not_found"), self.said(inter), where)
                self.assertEqual(row_dict(await database.get_egg(egg["id"])), before, where)
                self.assertEqual(len(self.pushed), pushed, where)

    async def test_the_menus_under_a_gone_egg_say_not_found_and_the_card_stays_usable(self):
        for how in ("removed", "expired"):
            egg = await self.make_egg(f"menus {how}")
            card = self.panel.EggDoneView(egg["id"])
            await self.remove(egg, how)
            before, pushed = row_dict(await database.get_egg(egg["id"])), len(self.pushed)
            for select, value in ((card.color, "gold"), (card.duration, "7d"), (card.template, "1")):
                select._values = [value]
                inter = fakes.Interaction()
                await select.callback(inter)
                self.assertIn(self.live.t("eggs.not_found"), self.said(inter), f"{how} {value}")
                self.assertTrue(inter.response.sent[-1][1]["ephemeral"])
            self.assertEqual(row_dict(await database.get_egg(egg["id"])), before, how)
            self.assertEqual(len(self.pushed), pushed, how)
            self.assertFalse(card.is_finished(), "the card keeps working (e.g. for ✖️)")

    async def test_the_edit_button_of_a_removed_egg_says_not_found(self):
        egg = await self.make_egg("Edit removed")
        card = self.panel.EggDoneView(egg["id"])
        await database.remove_egg(egg["id"])
        inter = fakes.Interaction()
        await card.edit.callback(inter)
        self.assertFalse(inter.response.modals)
        self.assertIn(self.live.t("eggs.not_found"), self.said(inter))

    async def test_the_edit_button_of_an_expired_egg_says_not_found_at_once(self):
        # DEFECT (low): ✏️ (EggDoneView.edit) and the egg menu (EggPickSelect) check only row["active"], so an
        # EXPIRED egg opens a form that can only answer "not found" after the person filled it in. egg_changes()
        # treats an expired egg as gone; the buttons should too (ends_at past -> the same answer as for a removed egg).
        egg = await self.make_egg("Edit expired")
        card = self.panel.EggDoneView(egg["id"])
        await self.remove(egg, "expired")
        inter = fakes.Interaction()
        await card.edit.callback(inter)
        self.assertFalse(inter.response.modals, "no form for an egg that is gone")

    async def test_the_egg_menu_does_not_open_a_form_for_an_expired_egg(self):
        # DEFECT (low): same as above, for EggPickSelect.callback (kind "edit")
        first, second = await self.make_egg("Pick one"), await self.make_egg("Pick two")
        inter = fakes.Interaction()
        await self.panel.EggsView().edit.callback(inter)
        pick = next(c for c in inter.response.sent[-1][1]["view"].children if isinstance(c, self.panel.EggPickSelect))
        await self.remove(second, "expired")
        pick._values = ["1"]
        inter = fakes.Interaction()
        await pick.callback(inter)
        self.assertFalse(inter.response.modals, "no form for an egg that is gone")

    async def test_the_egg_menu_of_a_removed_egg_says_not_found(self):
        await self.make_egg("Pick A")
        second = await self.make_egg("Pick B")
        inter = fakes.Interaction()
        await self.panel.EggsView().edit.callback(inter)
        pick = next(c for c in inter.response.sent[-1][1]["view"].children if isinstance(c, self.panel.EggPickSelect))
        await database.remove_egg(second["id"])
        pick._values = ["1"]
        inter = fakes.Interaction()
        await pick.callback(inter)
        self.assertFalse(inter.response.modals)
        self.assertIn(self.live.t("eggs.not_found"), self.said(inter))

    async def test_remove_under_a_gone_egg(self):
        for how in ("removed", "expired"):
            egg = await self.make_egg(f"rm {how}")
            card = self.panel.EggDoneView(egg["id"])
            await self.remove(egg, how)
            inter = fakes.Interaction()
            await card.remove.callback(inter)
            self.assertTrue(inter.edited and inter.edited[-1]["content"], how)
            self.assertFalse((await database.get_egg(egg["id"]))["active"])
        gone = self.panel.EggDoneView(987654)  # an id that never existed
        inter = fakes.Interaction()
        await gone.remove.callback(inter)
        self.assertIn(self.live.t("eggs.not_found"), inter.edited[-1]["content"])

    async def test_removed_between_the_check_and_the_save(self):
        egg = await self.make_egg("Between")
        changes = await self.live.egg_changes(egg["id"], price=42)
        await database.remove_egg(egg["id"])
        pushed = len(self.pushed)
        with self.assertRaises(self.live.RuleError):
            await self.live.save_egg_changes(egg["id"], changes)
        self.assertEqual(len(self.pushed), pushed, "nothing reached the game")
        self.assertEqual((await database.get_egg(egg["id"]))["price"], 500)

    async def test_the_egg_list_of_the_panel_skips_expired_eggs(self):
        egg = await self.make_egg("Soon gone")
        await self.remove(egg, "expired")
        inter = fakes.Interaction()
        await self.panel.EggsView().edit.callback(inter)
        self.assertEqual(inter.response.sent[-1][0], self.live.t("eggs.list_empty"))
        self.assertFalse(inter.response.modals)


# ---------- two people at once, double clicks ----------

class AtOnce(Base):
    async def test_two_people_changing_different_fields_of_one_egg_both_stay(self):
        egg = await self.make_egg("Shared")
        first, second = self.panel.EggModal(egg=egg), self.panel.EggModal(egg=egg)
        self.fill(first, name="Shared Renamed")
        self.fill(second, price="4242")
        a, b = fakes.Interaction(), fakes.Interaction()
        await asyncio.gather(first.on_submit(a), second.on_submit(b))
        row = await database.get_egg(egg["id"])
        self.assertEqual((row["name"], row["price"]), ("Shared Renamed", 4242))
        self.assertTrue(a.followup.sent and b.followup.sent, "each person got an answer")

    async def test_two_people_changing_the_same_field_the_later_one_wins_without_a_crash(self):
        egg = await self.make_egg("Same field")
        forms = [self.fill(self.panel.EggModal(egg=egg), price=p) for p in ("111", "222")]
        await asyncio.gather(*(f.on_submit(fakes.Interaction()) for f in forms))
        self.assertIn((await database.get_egg(egg["id"]))["price"], (111, 222))

    async def test_one_edits_while_the_other_removes(self):
        for order in ("edit first", "remove first"):
            egg = await self.make_egg(f"Race {order}")
            form = self.fill(self.panel.EggModal(egg=egg), price="999")
            card = self.panel.EggDoneView(egg["id"])
            edit, remove = fakes.Interaction(), fakes.Interaction()
            tasks = [form.on_submit(edit), card.remove.callback(remove)]
            await asyncio.gather(*(tasks if order == "edit first" else tasks[::-1]))
            self.assertFalse((await database.get_egg(egg["id"]))["active"], order)
            for inter in (edit, remove):
                self.assertTrue(inter.response.done, f"{order}: every click was answered")

    async def test_two_people_giving_two_eggs_the_same_name_at_once(self):
        # DEFECT (low): egg_changes() checks the name (check_egg_name) and save_egg_changes() writes it later, with
        # awaits in between and no lock, so two renames to the same name that run together both pass the check and
        # two active eggs end up with one name (same for two new eggs with one name: create_egg). Fix: do the name check
        # again inside the write (one lock around check + update, or a UNIQUE index on lower(name) WHERE active = 1).
        a, b = await self.make_egg("Egg One"), await self.make_egg("Egg Two")
        forms = [self.fill(self.panel.EggModal(egg=a), name="Same Name"), self.fill(self.panel.EggModal(egg=b), name="Same Name")]
        await asyncio.gather(*(f.on_submit(fakes.Interaction()) for f in forms))
        names = [r["name"].lower() for r in await database.get_active_eggs()]
        self.assertEqual(len(names), len(set(names)), names)

    async def test_a_double_click_on_a_menu(self):
        egg = await self.make_egg("Double menu")
        card = self.panel.EggDoneView(egg["id"])
        card.color._values = ["gold"]
        a, b = fakes.Interaction(), fakes.Interaction()
        await asyncio.gather(card.color.callback(a), card.color.callback(b))
        self.assertEqual((await database.get_egg(egg["id"]))["color"], self.live.EGG_COLORS["gold"])
        for inter in (a, b):
            self.assertTrue(inter.response.done, "every click was answered once")
        # the same value again, a moment later, on the card that was already replaced
        late = fakes.Interaction()
        await card.color.callback(late)
        self.assertIn(self.live.t("eggs.already_set"), self.said(late))

    async def test_a_double_click_on_remove(self):
        egg = await self.make_egg("Double remove")
        card = self.panel.EggDoneView(egg["id"])
        a, b = fakes.Interaction(), fakes.Interaction()
        await asyncio.gather(card.remove.callback(a), card.remove.callback(b))
        texts = sorted((a.edited[-1]["content"], b.edited[-1]["content"]))
        removed = [t for t in texts if self.live.t("eggs.removed", name="Double remove") in t]
        self.assertEqual(len(removed), 1, texts)
        self.assertTrue(any(self.live.t("eggs.not_found") in t for t in texts), texts)

    async def test_a_double_click_on_the_edit_button_and_a_double_send_of_the_form(self):
        egg = await self.make_egg("Double form")
        card = self.panel.EggDoneView(egg["id"])
        a, b = fakes.Interaction(), fakes.Interaction()
        await asyncio.gather(card.edit.callback(a), card.edit.callback(b))
        self.assertTrue(a.response.modals and b.response.modals)
        forms = [self.fill(self.panel.EggModal(egg=egg, source=card), price="321") for _ in range(2)]
        await asyncio.gather(*(f.on_submit(fakes.Interaction()) for f in forms))
        self.assertEqual((await database.get_egg(egg["id"]))["price"], 321)

    async def test_color_then_time_then_model_at_once_all_stay(self):
        egg = await self.make_egg("All three")
        card = self.panel.EggDoneView(egg["id"])
        card.color._values, card.duration._values, card.template._values = ["gold"], ["7d"], ["1"]
        inters = [fakes.Interaction() for _ in range(3)]
        await asyncio.gather(card.color.callback(inters[0]), card.duration.callback(inters[1]), card.template.callback(inters[2]))
        row = await database.get_egg(egg["id"])
        self.assertEqual((row["color"], row["template"]), (self.live.EGG_COLORS["gold"], "Golden"))
        self.assertGreater(row["ends_at"], time.time() + 6 * 86400)

    async def test_a_new_egg_from_two_forms_with_different_names(self):
        forms = []
        for name in ("Twin A", "Twin B"):
            forms.append(self.fill(self.panel.EggModal(), name=name, price="10", pets="Cat:1, Dog:1", currency="Coins", spot="-"))
        await asyncio.gather(*(f.on_submit(fakes.Interaction()) for f in forms))
        self.assertEqual(sorted(r["name"] for r in await database.get_active_eggs()), ["Twin A", "Twin B"])


# ---------- Discord's limits ----------

class Limits(Base):
    scan = {"values": [], "attributes": [], "spots": [f"Spot {i} " + "y" * 95 for i in range(30)],
            "templates": [f"Model {i} " + "z" * 94 for i in range(30)], "multipliers": [], "hooks": [], "at": 0, "studio": False}

    async def long_egg(self, name="Ж" * 40, currency="C" * 100, price=10 ** 12, spot="Spot " + "y" * 25):
        pets = ", ".join(f"Pet{i}{'q' * 10}:{i + 1}" for i in range(25))
        await self.live.create_egg(name, currency, price, pets, spot=spot, author_id=7)
        return next(r for r in await database.get_active_eggs() if r["name"] == name)

    async def test_every_form_and_window_fits_in_every_language(self):
        config_store.write_json("game_economy.json", {"configured": True, "currencies": ["C" * 100, "Gems"], "pets": []})
        egg = await self.long_egg()
        presets = [("Preset " + "x" * 90, "Cat:60, Dog:40", "C" * 100, 10 ** 14)] * 30
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                where = f"[{lang}]"
                fakes.check_modal(self.panel.EggModal(), f"EggModal new {where}")
                modal = self.panel.EggModal(egg=egg)
                fakes.check_modal(modal, f"EggModal edit {where}")
                self.assertLessEqual(len(modal.title), 45)
                fakes.check_modal(self.panel.EggModal(preset=presets[0]), f"EggModal preset {where}")
                card = self.panel.EggDoneView(egg["id"], egg)
                fakes.check_view(card, f"EggDoneView {where}")
                self.assertEqual(len(card.template.options), 25, "30 egg models: the first 24 and the default model")
                for kind, items in (("edit", [egg] * 20), ("preset", presets)):
                    view = self.panel.StaffView()
                    view.add_item(self.panel.EggPickSelect(kind, items))
                    fakes.check_view(view, f"EggPickSelect {kind} {where}")
                fakes.check_embed(await self.panel.EggsView().embed(), f"EggsView {where}")
                with mock.patch.object(catalog, "egg_presets", return_value=presets):
                    shown = self.panel.EggsView()
                    self.assertIn(shown.copy, shown.children)
                    fakes.check_view(shown, f"EggsView with catalog eggs {where}")
                    inter = fakes.Interaction()
                    await shown.copy.callback(inter)  # 30 catalog eggs with 100 character names: the strict fake checks the message
                    self.assertEqual(len(inter.response.sent[-1][1]["view"].children[0].options), 25)

    async def test_the_answer_of_a_long_egg_fits_in_every_language(self):
        egg = await self.long_egg("Long Egg")
        for index, lang in enumerate(LANGS):
            with mock.patch.object(i18n, "language", return_value=lang):
                modal = self.panel.EggModal(egg=await database.get_egg(egg["id"]))
                inter = await self.submit(modal, price=str(5 + index))  # the strict fake refuses what Discord would refuse
                self.assertIsInstance(inter.followup.sent[-1][1]["view"], self.panel.EggDoneView, lang)
                self.assertEqual((await database.get_egg(egg["id"]))["price"], 5 + index)

    async def test_the_pet_list_of_exactly_1000_characters_fits_and_1001_is_left_out(self):
        for length, filled in ((1000, True), (1001, False)):
            row = {"id": 1, "name": "Edge", "currency": "Coins", "price": 5, "spot": "", "color": "", "template": "", "ends_at": 0,
                   "pets": json.dumps([{"name": "P" * (length - len(":100")), "chance": 100}])}
            self.assertEqual(len(self.live.pets_text(row)), length)
            modal = self.panel.EggModal(egg=row)
            self.assertEqual(modal.pets.default is not None, filled, length)
            self.assertFalse(modal.pets.required, "an edit never forces the pets")
            fakes.check_modal(modal, f"EggModal {length}")



# ---------- random typing ----------

class RandomTyping(Base):
    """Whatever is typed in the forms, Discord is answered exactly once with something it accepts (the strict fake refuses
    anything else) and the eggs in the database stay sane: a name nobody else has, a price in range, chances above 0."""

    def junk(self, rng, alphabet, longest):
        return "".join(rng.choice(alphabet) for _ in range(rng.randint(0, longest)))

    async def test_new_edit_and_copied_eggs_survive_random_input(self):
        rng = random.Random(7)
        alphabet = "abcXYZ 0123456789:=%.,;-_ąęłñ🐉'\"()[]\n\t"
        presets = [("Preset one", "Cat:60, Dog:40", "Coins", 100), ("Preset two", "Dragon:1, Cat:99", "Gems", 0)]
        with mock.patch.object(catalog, "egg_presets", return_value=presets):
            for step in range(150):
                rows = await database.get_active_eggs()
                kind = rng.choice(["new", "edit", "preset"]) if rows else rng.choice(["new", "preset"])
                if kind == "edit":
                    modal = self.panel.EggModal(egg=rng.choice(rows), source=rng.choice([None, self.panel.EggDoneView(1)]))
                elif kind == "preset":
                    modal = self.panel.EggModal(preset=rng.choice(presets))
                else:
                    modal = self.panel.EggModal()
                self.fill(modal)
                if rng.random() < 0.7:
                    modal.egg_name._value = self.junk(rng, alphabet, 45)
                if rng.random() < 0.7:
                    modal.price._value = rng.choice(["", "0", "-1", "1e9", "١٢٣", str(rng.randint(1, 10 ** 13)), self.junk(rng, "0123456789 ,._x", 18)])
                if rng.random() < 0.7:
                    modal.pets._value = rng.choice(["", "Cat", "Cat:0", "Cat:-1", "Cat:1, Cat:2", self.junk(rng, alphabet, 120),
                                                    ", ".join(f"Pet{i}:{rng.randint(1, 9)}" for i in range(rng.randint(1, 27)))])
                inter = fakes.Interaction()
                await modal.on_submit(inter)  # DiscordRefused (an answer twice, a message over a limit...) fails the test
                self.assertTrue(inter.response.done, f"step {step}: Discord was answered")
                names = [r["name"].lower() for r in await database.get_active_eggs()]
                self.assertEqual(len(names), len(set(names)), f"step {step}: two active eggs with one name: {names}")
                for row in await database.get_active_eggs():
                    self.assertTrue(row["name"].strip(), f"step {step}")
                    self.assertTrue(1 <= row["price"] <= self.live.MAX_PRICE, f"step {step}: price {row['price']}")
                    pets = json.loads(row["pets"])
                    self.assertTrue(1 <= len(pets) <= self.live.MAX_PETS, f"step {step}")
                    self.assertTrue(all(p["chance"] > 0 and p["name"] for p in pets), f"step {step}: {pets}")
                    self.assertAlmostEqual(sum(p["chance"] for p in pets), 100, delta=0.01 if len(pets) < 20 else 0.1)
        self.assertGreater(len(self.pushed), 5, "a good part of the random forms was really saved")


# ---------- eggs copied from the game catalog ----------

def catalog_with(eggs: list) -> dict:
    return {"missing": False, "template": False, "currencies": ["Coins", "Gems"], "items": [], "multipliers": [],
            "pets": [{"name": n, "rarity": ""} for n in ("A", "B", "C", "Common", "Secret", "Cat", "Dog", "Fox")],
            "eggs": eggs, "problems": [], "at": 0, "studio": False}


def pets_of(*items):
    return [{"name": n, "chance": c} for n, c in items]


class FromTheCatalog(Base):
    def use(self, eggs: list):
        patch = mock.patch.object(catalog, "game_catalog", return_value=catalog_with(eggs))
        patch.start()
        self.addCleanup(patch.stop)
        self.patches[2].stop()  # the real catalog.egg_presets now reads this catalog (stopping twice is harmless)

    async def copy(self, name, source=None, **fill_kwargs):
        """Opens 'Egg from the game catalog', picks the egg like a person and sends the form as it is filled in."""
        inter = fakes.Interaction()
        view = self.panel.EggsView()
        await view.copy.callback(inter)
        chooser = inter.response.sent[-1][1]["view"]
        pick = next(c for c in chooser.children if isinstance(c, self.panel.EggPickSelect))
        index = next(i for i, p in enumerate(pick.items) if p[0] == name)
        pick._values = [str(index)]
        inter = fakes.Interaction()
        await pick.callback(inter)
        if not inter.response.modals:
            return inter, None
        modal = inter.response.modals[-1]
        answer = fakes.Interaction()
        self.fill(modal, **fill_kwargs)
        await modal.on_submit(answer)
        return answer, modal

    async def test_odd_chances_become_chances_that_work(self):
        self.use([{"name": "Thirds", "currency": "Coins", "price": 100, "pets": pets_of(("A", 100 / 3), ("B", 100 / 3), ("C", 100 / 3))},
                  {"name": "Tiny", "currency": "Gems", "price": 50, "pets": pets_of(("Common", 99.9999999), ("Secret", 0.0000001))},
                  {"name": "No chances", "currency": "Coins", "price": 10, "pets": pets_of(("Cat", None), ("Dog", None))},
                  {"name": "A zero", "currency": "Coins", "price": 10, "pets": pets_of(("Cat", 50.0), ("Dog", 0.0), ("Fox", 50.0))}])
        expected = {"Thirds": [("A", 33.3333), ("B", 33.3333), ("C", 33.3333)], "Tiny": [("Common", 100.0), ("Secret", 0.0001)],
                    "No chances": [("Cat", 50.0), ("Dog", 50.0)], "A zero": [("Cat", 50.0), ("Fox", 50.0)]}
        for name, pets in expected.items():
            answer, modal = await self.copy(name)
            self.assertIsNotNone(modal, name)
            egg = next((r for r in await database.get_active_eggs() if r["name"] == name), None)
            self.assertIsNotNone(egg, f"{name}: created ({self.said(answer)})")
            got = [(p["name"], p["chance"]) for p in json.loads(egg["pets"])]
            self.assertEqual([n for n, _ in got], [n for n, _ in pets], name)
            for (_, chance), (_, want) in zip(got, pets):
                self.assertAlmostEqual(chance, want, delta=0.0002, msg=name)
                self.assertGreater(chance, 0, f"{name}: a pet that was listed can drop")
            self.assertIsInstance(answer.edited[-1]["view"], self.panel.EggDoneView, f"{name}: the card replaces the chooser")

    async def test_eggs_without_a_usable_chance_list_are_not_offered(self):
        self.use([{"name": "Only zero", "currency": "Coins", "price": 10, "pets": pets_of(("Cat", 0.0))},
                  {"name": "Half known", "currency": "Coins", "price": 10, "pets": pets_of(("Cat", None), ("Dog", 5.0))},
                  {"name": "No pets", "currency": "Coins", "price": 10, "pets": []}])
        self.assertEqual(catalog.egg_presets(), [])
        self.assertNotIn(self.panel.EggsView().copy, self.panel.EggsView().children, "no preset: no button")
        inter = fakes.Interaction()
        await self.panel.EggsView().copy.callback(inter)
        self.assertEqual(inter.response.sent[-1][0], self.live.t("rbx.egg_no_presets"))

    async def test_a_currency_the_catalog_does_not_list_is_refused_in_the_chooser(self):
        self.use([{"name": "Outside", "currency": "Tokens", "price": 20, "pets": pets_of(("Cat", 1.0))}])
        answer, modal = await self.copy("Outside")
        self.assertEqual(await database.get_active_eggs(), [], "nothing created")
        self.assertIn("Tokens", self.said(answer))
        self.assertEqual(list(answer.edited[-1]), ["content"], "a note above the chooser, which stays")
        self.assertEqual(self.pushed, [])
        # and picking a listed currency in the same form works
        modal.currency._values = ["Coins"]
        again = fakes.Interaction()
        await modal.on_submit(again)
        self.assertEqual([r["currency"] for r in await database.get_active_eggs()], ["Coins"])

    async def test_a_currency_outside_the_economy_is_kept_when_the_catalog_lists_no_currencies(self):
        # the catalog lists eggs but no currencies: nothing to check the currency against, so the egg's own currency is
        # shown (picked, on top of the economy's) and accepted
        cat = catalog_with([{"name": "Tokens egg", "currency": "Tokens", "price": 20, "pets": pets_of(("Cat", 1.0))}]) | {"currencies": []}
        patch = mock.patch.object(catalog, "game_catalog", return_value=cat)
        patch.start()
        self.addCleanup(patch.stop)
        self.patches[2].stop()
        modal = self.panel.EggModal(preset=catalog.egg_presets()[0])
        self.assertEqual([(o.value, o.default) for o in modal.currency.options], [("Tokens", True), ("Coins", False), ("Gems", False)])
        answer, _ = await self.copy("Tokens egg")
        self.assertEqual([(r["name"], r["currency"]) for r in await database.get_active_eggs()], [("Tokens egg", "Tokens")], self.said(answer))

    async def test_a_price_of_zero_or_none_leaves_the_field_empty_and_a_typed_price_works(self):
        self.use([{"name": "No price", "currency": "Coins", "price": 0, "pets": pets_of(("Cat", 1.0))},
                  {"name": "No currency", "currency": "", "price": 0, "pets": pets_of(("Dog", 1.0))}])
        for name in ("No price", "No currency"):
            modal = self.panel.EggModal(preset=next(p for p in catalog.egg_presets() if p[0] == name))
            self.assertIsNone(modal.price.default, name)
            self.assertEqual([o.value for o in modal.currency.options if o.default], ["Coins"], "no currency: the first one")
            fakes.check_modal(modal)
            answer, _ = await self.copy(name, price="300")
            self.assertEqual(next(r for r in await database.get_active_eggs() if r["name"] == name)["price"], 300, name)

    async def test_a_price_over_the_limit_is_said_and_nothing_is_created(self):
        self.use([{"name": "Huge price", "currency": "Coins", "price": 10 ** 14, "pets": pets_of(("Cat", 1.0))}])
        answer, modal = await self.copy("Huge price")
        self.assertIn("1,000,000,000,000", self.said(answer))
        self.assertEqual(await database.get_active_eggs(), [])

    async def test_a_name_longer_than_the_form_field_is_cut_to_40_not_refused(self):
        self.use([{"name": "L" * 90, "currency": "Coins", "price": 5, "pets": pets_of(("Cat", 1.0))}])
        answer, modal = await self.copy("L" * 90)
        self.assertEqual([r["name"] for r in await database.get_active_eggs()], ["L" * 40], self.said(answer))

    async def test_too_many_pets_for_one_egg_is_said(self):
        self.use([{"name": "Zoo", "currency": "Coins", "price": 5, "pets": pets_of(*((f"A{i}", 1.0) for i in range(26)))}])
        answer, modal = await self.copy("Zoo")
        self.assertIn("❌", self.said(answer))
        self.assertEqual(await database.get_active_eggs(), [])

    async def test_a_preset_of_exactly_1000_characters_is_filled_in_and_a_longer_one_is_refused_with_a_note(self):
        for length in (1000, 1001):
            preset = ("Edge", "x" * (length - 2) + ":1", "Coins", 5)
            with mock.patch.object(catalog, "egg_presets", return_value=[preset]):
                inter = fakes.Interaction()
                await self.panel.EggsView().copy.callback(inter)
                pick = next(c for c in inter.response.sent[-1][1]["view"].children if isinstance(c, self.panel.EggPickSelect))
                pick._values = ["0"]
                inter = fakes.Interaction()
                await pick.callback(inter)
                self.assertEqual(bool(inter.response.modals), length == 1000, length)
                if length == 1000:
                    self.assertEqual(len(inter.response.modals[-1].pets.default), 1000)
                else:
                    self.assertIn("/egg-create", inter.response.sent[-1][0])


    async def test_a_catalog_chance_below_five_in_ten_billion_gives_a_form_that_can_be_sent(self):
        # DEFECT (very low): catalog._weight() writes a chance with 10 decimals, so 1e-11 becomes "Dog:0", which
        # parse_pets refuses ("Can't read Dog:0") for the WHOLE egg. Fix: write at least 0.0000000001 for a chance > 0.
        self.use([{"name": "Sub", "currency": "Coins", "price": 5, "pets": pets_of(("Cat", 50.0), ("Dog", 1e-11))}])
        answer, modal = await self.copy("Sub")
        self.assertEqual([r["name"] for r in await database.get_active_eggs()], ["Sub"], self.said(answer))

    async def test_a_game_with_26_catalog_eggs_shows_25_and_says_so(self):
        self.use([{"name": f"Egg {i}", "currency": "Coins", "price": 5, "pets": pets_of(("Cat", 1.0))} for i in range(26)])
        inter = fakes.Interaction()
        await self.panel.EggsView().copy.callback(inter)
        self.assertIn("26", inter.response.sent[-1][0])
        select = next(c for c in inter.response.sent[-1][1]["view"].children if isinstance(c, self.panel.EggPickSelect))
        self.assertEqual(len(select.options), 25)

    async def test_the_pets_of_an_egg_can_be_replaced_by_a_catalog_egg_typed_as_egg_colon_name(self):
        self.use([{"name": "Thirds", "currency": "Coins", "price": 100, "pets": pets_of(("A", 1.0), ("B", 1.0), ("C", 2.0))}])
        egg = await self.make_egg("Replace pets", "Cat:1, Dog:1")
        await self.submit(self.panel.EggModal(egg=egg), pets="egg:Thirds")
        pets = json.loads((await database.get_egg(egg["id"]))["pets"])
        self.assertEqual([(p["name"], p["chance"]) for p in pets], [("A", 25.0), ("B", 25.0), ("C", 50.0)])

    async def test_an_egg_whose_pet_left_the_catalog_can_still_be_renamed_and_repriced(self):
        egg = await self.make_egg("Old pets", "Cat:1, Dog:1")
        # the catalog now lists only Fox: Cat and Dog are not names the game knows any more
        patch = mock.patch.object(catalog, "game_catalog", return_value=catalog_with([]) | {"pets": [{"name": "Fox", "rarity": ""}]})
        patch.start()
        self.addCleanup(patch.stop)
        inter = await self.submit(self.panel.EggModal(egg=egg), name="Renamed old", price="9")
        row = await database.get_egg(egg["id"])
        self.assertEqual((row["name"], row["price"]), ("Renamed old", 9), self.said(inter))
        self.assertEqual(row["pets"], egg["pets"], "the pets were not re-read, so they were not re-checked")



if __name__ == "__main__":
    unittest.main()
