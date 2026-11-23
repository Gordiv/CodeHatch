"""Tester's checks of the events and of the commands that share code with the egg panel:
- the event form with several things picked (only currencies, all currencies with EXP and luck, 20 currencies, everything);
- the multiplier cap (MAX_MULTIPLIER) with several events at once, and its twin in Live.luau;
- /event-start, /egg-create, /egg-edit, /egg-remove still answer as before;
- ⏹️ End this event: twice, after the event ended some other way, after it expired.

Known defects are written as expectedFailure with the reason in the comment."""
import asyncio
import json
import os
import re
import time
import unittest
from unittest import mock

import discord
from discord import app_commands

from tests import fakes
from tests.helpers import ROOT, TempBot
from utils import catalog, config_store, database, i18n, roblox_kit

LANGS = ("en", "pl", "es")
SCAN = {"values": [], "attributes": [], "spots": ["Spawn"], "templates": ["Default"], "multipliers": ["Coins", "EXP"],
        "hooks": [], "at": 0, "studio": False}


class Base(unittest.IsolatedAsyncioTestCase):
    currencies = ["Coins", "Gems"]

    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import live_game, setup_roblox
        self.live, self.panel = live_game, setup_roblox
        config_store.write_json("game_economy.json", {"configured": True, "currencies": self.currencies, "pets": []})
        self.pushed = []

        async def push(kind, force=True):
            self.pushed.append(kind)
            return True, ""

        self.patches = [mock.patch.object(live_game, "push_live", push),
                        mock.patch.object(roblox_kit, "game_scan", return_value=SCAN)]
        for patch in self.patches:
            patch.start()
        self.cog = live_game.LiveGame.__new__(live_game.LiveGame)

    async def asyncTearDown(self):
        for patch in self.patches:
            patch.stop()
        await database.close_db()
        self.temp.__exit__(None, None, None)

    def form(self, kinds, value="2", name="Weekend", duration="3h"):
        modal = self.panel.EventModal()
        modal.event_name._value = name
        modal.duration._values = [duration]
        modal.kind._values = list(kinds)
        modal.value._values = [value] if value is not None else []
        return modal

    async def send(self, modal):
        inter = fakes.Interaction()
        await modal.on_submit(inter)
        return inter

    @staticmethod
    def said(inter) -> str:
        texts = [c for c, _ in inter.response.sent + inter.followup.sent if c]
        texts += [kw.get("content") for kw in inter.edited if kw.get("content")]
        return "\n".join(texts)

    async def multipliers_of_all(self):
        return [json.loads(r["multipliers"]) for r in await database.get_active_live_events()]


class EventForm(Base):
    async def test_every_combination_of_things_gets_the_same_multiplier(self):
        every = f"currency:{self.live.ALL_CURRENCIES}"
        cases = [(["currency:Coins"], "2"), (["currency:Coins", "currency:Gems"], "5"), ([every], "3"), ([every, "exp", "luck"], "10"),
                 (["exp"], "1.5"), (["luck"], "10"), (["currency:Gems", "exp"], "2"), (["currency:Coins", "currency:Gems", "exp", "luck"], "3")]
        for kinds, value in cases:
            before = len(await database.get_active_live_events())
            inter = await self.send(self.form(kinds, value, name=f"E {'+'.join(kinds)}"[:50]))
            events = await self.multipliers_of_all()
            self.assertEqual(len(events), before + 1, f"{kinds}: {self.said(inter)}")
            saved = json.loads(max(await database.get_active_live_events(), key=lambda r: r["id"])["multipliers"])
            self.assertEqual(saved, {k: float(value) for k in kinds}, kinds)
            view = inter.followup.sent[-1][1]["view"]
            self.assertIsInstance(view, self.panel.EventDoneView)
            for event in await database.get_active_live_events():
                await database.stop_live_event(event["id"])

    async def test_all_currencies_with_a_single_currency_is_refused_and_nothing_starts(self):
        every = f"currency:{self.live.ALL_CURRENCIES}"
        for kinds in ([every, "currency:Coins"], [every, "currency:Coins", "currency:Gems"], [every, "currency:Gems", "exp", "luck"]):
            inter = await self.send(self.form(kinds))
            self.assertIn(self.live.t("events.err_all_and_one"), self.said(inter), kinds)
            self.assertEqual(await database.get_active_live_events(), [], kinds)
            self.assertEqual(self.pushed, [], "nothing reached the game")

    async def test_picking_everything_in_the_menu_gets_the_explanation_not_a_broken_event(self):
        modal = self.panel.EventModal()
        everything = [o.value for o in modal.kind.options]
        self.assertGreaterEqual(len(everything), 5)
        inter = await self.send(self.form(everything))
        self.assertIn("❌", self.said(inter))
        self.assertEqual(await database.get_active_live_events(), [])

    async def test_nothing_picked_and_a_blank_name_are_said(self):
        inter = await self.send(self.form([]))
        self.assertIn(self.live.t("events.no_multiplier"), self.said(inter))
        inter = await self.send(self.form(["exp"], name="   "))
        self.assertIn(self.live.t("events.err_name"), self.said(inter))
        self.assertEqual(await database.get_active_live_events(), [])

    async def test_no_multiplier_chosen_means_two_and_a_name_of_50_characters_fits(self):
        inter = await self.send(self.form(["exp"], value=None, name="N" * 50))
        saved = (await database.get_active_live_events())[0]
        self.assertEqual(json.loads(saved["multipliers"]), {"exp": 2.0}, self.said(inter))
        fakes.check_embed(inter.followup.sent[-1][1]["embed"])

    async def test_every_duration_of_the_form_works(self):
        # more ready-made times than events at once (MAX_EVENTS): each one is ended before the next
        for key, seconds in self.live.EVENT_DURATIONS.items():
            await self.send(self.form(["exp"], duration=key, name=f"D {key}"))
            rows = await database.get_active_live_events()
            self.assertEqual(len(rows), 1, key)
            self.assertEqual(rows[0]["ends_at"] - rows[0]["starts_at"], seconds, key)
            self.assertAlmostEqual(rows[0]["starts_at"] - int(time.time()), self.live.START_COUNTDOWN, delta=5,
                                   msg="it starts after the players' countdown")
            await database.stop_live_event(rows[0]["id"])

    async def test_a_typed_time_wins_over_the_list(self):
        modal = self.form(["exp"], duration="3h", name="Typed")
        modal.custom_duration._value = " 45m "
        inter = await self.send(modal)
        row = (await database.get_active_live_events())[0]
        self.assertEqual(row["ends_at"] - row["starts_at"], 45 * 60)
        embed = inter.followup.sent[-1][1]["embed"]
        self.assertIn("45", " ".join(f.value for f in embed.fields), "the answer says how the time was understood")

    async def test_a_short_event_while_the_game_is_tested_in_studio_gets_a_note(self):
        note = self.live.t("events.short_in_studio")
        for studio, duration, wanted in ((True, "1m", True), (True, "5m", False), (False, "1m", False)):
            with mock.patch.object(roblox_kit, "game_scan", return_value={**SCAN, "studio": studio}):
                embed = await self.live.start_event(f"S {studio} {duration}", duration, {"exp": 2.0})
            text = " ".join(f.value for f in embed.fields)
            self.assertEqual(note in text, wanted, (studio, duration))
            fakes.check_embed(embed)
        with mock.patch.object(roblox_kit, "game_scan", return_value=None):
            await self.live.start_event("No scan", "1m", {"exp": 2.0})

    async def test_a_time_the_bot_does_not_understand_starts_nothing(self):
        for typed in ("soon", "0m", "31d", "5x", "@everyone"):
            modal = self.form(["exp"], name="Bad")
            modal.custom_duration._value = typed
            inter = await self.send(modal)
            self.assertIn("45m", self.said(inter), typed)
            self.assertNotIn("@everyone", self.said(inter).replace("@​everyone", ""), "a typed mention never pings")
        self.assertEqual(await database.get_active_live_events(), [])

    def test_typed_times(self):
        seconds = self.live.event_seconds
        for typed, want in {"1m": 60, "45m": 2700, "45": 2700, "45 min": 2700, "2h": 7200, "2h30m": 9000, "2h30": 9000,
                            "1,5h": 5400, "1.5 h": 5400, "2 godz.": 7200, "3 dni": 3 * 86400, "1d12h": 129600, "3D": 3 * 86400,
                            "30d": 30 * 86400, "90 minutos": 5400, "2 horas": 7200, "7d": 7 * 86400,
                            "1 godzinę": 3600, "1 minutę": 60, "2h i 30m": 9000, "1 hora y 30 minutos": 5400,
                            "2 hours and 30 minutes": 9000, "2h, 30m": 9000, "1w": 7 * 86400, "2 tygodnie": 14 * 86400,
                            "1 semana": 7 * 86400}.items():
            self.assertEqual(seconds(typed), want, typed)
        for typed in ("", "   ", "h", "abc", "0", "30s", "31d", "2x", "1h-30m", "999999999m", "1.2345h", "0000045", "5w"):
            with self.assertRaises(self.live.RuleError, msg=typed):
                seconds(typed)

    async def test_the_command_suggests_the_list_and_the_typed_time(self):
        suggest = self.cog.event_duration_autocomplete
        everything = await suggest(fakes.Interaction(), "")
        self.assertEqual([c.value for c in everything], list(self.live.EVENT_DURATIONS))
        typed = await suggest(fakes.Interaction(), "45")
        self.assertEqual(typed[0].value, "45")
        self.assertIn("45", typed[0].name)
        self.assertEqual(await suggest(fakes.Interaction(), "nonsense"), [])
        self.assertEqual([c.value for c in await suggest(fakes.Interaction(), "1 h")], ["1h"], "a space doesn't hide the list")
        self.assertEqual([c.value for c in await suggest(fakes.Interaction(), "5")], ["5m"], "no second line meaning the same")
        self.assertEqual([c.value for c in await suggest(fakes.Interaction(), "24")], ["24", "24h"], "24 minutes or 24 hours")
        inter = fakes.Interaction()
        await self.cog.event_start.callback(self.cog, inter, "Bad time", "soon", exp_multiplier=app_commands.Choice(name="2×", value="2"))
        self.assertTrue(inter.response.sent[-1][1]["ephemeral"], "a time the bot doesn't understand is said only to the admin")
        self.assertEqual(await database.get_active_live_events(), [])
        inter = fakes.Interaction()
        await self.cog.event_start.callback(self.cog, inter, "Typed", "1h30m", exp_multiplier=app_commands.Choice(name="2×", value="2"))
        row = (await database.get_active_live_events())[0]
        self.assertEqual(row["ends_at"] - row["starts_at"], 5400)

    async def test_the_eleventh_event_is_refused(self):
        for i in range(self.live.MAX_EVENTS):
            await self.send(self.form(["exp"], name=f"Event {i}"))
        inter = await self.send(self.form(["luck"], name="One too many"))
        self.assertIn(self.live.t("events.err_too_many", max=self.live.MAX_EVENTS), self.said(inter))
        self.assertEqual(len(await database.get_active_live_events()), self.live.MAX_EVENTS)

    async def test_the_menu_has_nothing_picked_and_takes_every_option_at_once(self):
        modal = self.panel.EventModal()
        self.assertFalse([o for o in modal.kind.options if o.default])
        self.assertEqual((modal.kind.min_values, modal.kind.max_values), (1, len(modal.kind.options)))
        self.assertLessEqual(len(modal.kind.options), 25)
        self.assertEqual([o.value for o in modal.value.options if o.default], ["2"])
        self.assertEqual([o.value for o in modal.duration.options if o.default], ["1h"])
        self.assertLessEqual(max(float(m) for m in self.live.MULTIPLIERS), self.live.MAX_MULTIPLIER)


class TwentyCurrencies(Base):
    currencies = [f"Currency number {i:02d}" for i in range(20)]

    async def test_all_20_currencies_in_one_event(self):
        kinds = [f"currency:{c}" for c in self.currencies]
        modal = self.panel.EventModal()
        self.assertTrue(set(kinds) <= {o.value for o in modal.kind.options}, "all 20 are offered")
        inter = await self.send(self.form(kinds, "5"))
        saved = await self.multipliers_of_all()
        self.assertEqual(saved, [{k: 5.0 for k in kinds}], self.said(inter))
        embed = inter.followup.sent[-1][1]["embed"]
        fakes.check_embed(embed)
        for lang in LANGS:  # the events window and the /events list with such an event
            with mock.patch.object(i18n, "language", return_value=lang):
                fakes.check_embed(await self.panel.EventsView().embed(), f"EventsView [{lang}]")
                inter = fakes.Interaction()
                await self.cog.events.callback(self.cog, inter)
                for embed in [kw["embed"] for _, kw in inter.response.sent if "embed" in kw]:
                    fakes.check_embed(embed, f"/events [{lang}]")

    async def test_20_currencies_plus_exp_and_luck_in_every_language(self):
        kinds = [f"currency:{c}" for c in self.currencies] + ["exp", "luck"]
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                fakes.check_modal(self.panel.EventModal(), f"EventModal [{lang}]")
                inter = await self.send(self.form(kinds, "2", name=f"All {lang}"))
                self.assertIsInstance(inter.followup.sent[-1][1]["view"], self.panel.EventDoneView, lang)
                fakes.check_embed(inter.followup.sent[-1][1]["embed"], lang)
        self.assertEqual(len(await database.get_active_live_events()), 3)

    async def test_the_form_with_each_animation_fits_in_every_language(self):
        # the title shows the picked animation's short name: never longer than Discord's 45 (counted as UTF-16 too)
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                select = self.panel.EventAnimationSelect()
                self.assertEqual(select.options[0].value, "none")
                self.assertEqual([o.value for o in select.options[1:]], list(self.live.ANIMATIONS))
                for animation in self.live.ANIMATIONS:
                    modal = self.panel.EventModal(animation)
                    fakes.check_modal(modal, f"EventModal {animation} [{lang}]")
                    self.assertLessEqual(len(modal.title.encode("utf-16-le")) // 2, 45, f"{animation} [{lang}]")
                    self.assertNotIn("(", modal.title, "the short name, without the words in brackets")
                    self.assertEqual(modal.animation, animation)

    async def test_what_the_game_gets_is_small_enough(self):
        kinds = [f"currency:{c}" for c in self.currencies] + ["exp", "luck"]
        await self.send(self.form(kinds, "2"))
        snapshot = self.live.events_snapshot(await database.get_active_live_events())
        self.assertLess(len(json.dumps(snapshot)), 4000, "one event with 22 multipliers is a small DataStore entry")


class TheCap(Base):
    async def test_three_events_of_ten_on_one_thing_are_capped_in_the_bot_like_in_the_game(self):
        for i in range(3):
            await self.send(self.form(["currency:Coins", "exp"], "10", name=f"Ten {i}"))
        rows = await database.get_active_live_events()
        self.assertEqual(self.live.combined_multipliers(rows), {"currency:Coins": 100, "exp": 100}, "10 x 10 x 10 = 1000, shown as 100")
        inter = fakes.Interaction()
        await self.cog.events.callback(self.cog, inter)
        text = json.dumps(inter.response.sent[-1][1]["embed"].to_dict(), ensure_ascii=False)
        self.assertIn("100×", text)
        self.assertNotIn("1000", text)

    async def test_the_cap_of_the_bot_is_the_cap_of_the_game(self):
        with open(os.path.join(ROOT, "scripts", "DiscordCodes", "Live.luau"), encoding="utf-8") as f:
            source = f.read()
        match = re.search(r"MaxMultiplier\s*=\s*(\d+)", source)
        self.assertIsNotNone(match)
        self.assertEqual(int(match.group(1)), self.live.MAX_MULTIPLIER)

    async def test_two_events_below_the_cap_multiply(self):
        await self.send(self.form(["currency:Coins"], "3", name="A"))
        await self.send(self.form(["currency:Coins"], "5", name="B"))
        self.assertEqual(self.live.combined_multipliers(await database.get_active_live_events()), {"currency:Coins": 15})


class CommandsStillWork(Base):
    """Commands that share code with the panel (cogs/live_game.py): the same answers as before the panel got the new forms."""

    def choice(self, value):
        return app_commands.Choice(name=f"{value}×", value=value)

    async def test_event_start(self):
        inter = fakes.Interaction()
        await self.cog.event_start.callback(self.cog, inter, "Command event", "1h",
                                            currency="Coins", currency_multiplier=self.choice("3"), exp_multiplier=self.choice("2"))
        self.assertEqual(await self.multipliers_of_all(), [{"currency:Coins": 3.0, "exp": 2.0}])
        self.assertIsInstance(inter.followup.sent[-1][1]["embed"], discord.Embed)
        self.assertNotIn("view", inter.followup.sent[-1][1], "the command has no ⏹️ button")
        inter = fakes.Interaction()  # all currencies (the default) with luck
        await self.cog.event_start.callback(self.cog, inter, "Luck", "1h",
                                            currency_multiplier=self.choice("2"), luck_multiplier=self.choice("10"))
        self.assertIn({"currency:*": 2.0, "luck": 10.0}, await self.multipliers_of_all())

    async def test_event_start_refusals_stay_private(self):
        hour = "1h"
        inter = fakes.Interaction()
        await self.cog.event_start.callback(self.cog, inter, "Nothing", hour)
        self.assertEqual(inter.response.sent[-1][0], self.live.t("events.no_multiplier"))
        self.assertTrue(inter.response.sent[-1][1]["ephemeral"])
        cat = {"missing": False, "template": False, "currencies": ["Coins"], "items": [], "multipliers": [], "pets": [], "eggs": [],
               "problems": [], "at": 0, "studio": False}
        with mock.patch.object(catalog, "game_catalog", return_value=cat):
            inter = fakes.Interaction()
            await self.cog.event_start.callback(self.cog, inter, "Tokens", hour, currency="Tokens", currency_multiplier=self.choice("2"))
            self.assertIn("Tokens", inter.response.sent[-1][0])
        self.assertEqual(await database.get_active_live_events(), [])
        for i in range(self.live.MAX_EVENTS):
            await self.live.start_event(f"E{i}", "1h", {"exp": 2.0})
        inter = fakes.Interaction()
        await self.cog.event_start.callback(self.cog, inter, "Eleventh", hour, exp_multiplier=self.choice("2"))
        self.assertIn(str(self.live.MAX_EVENTS), inter.response.sent[-1][0])

    async def test_start_event_for_other_callers_keeps_returning_the_embed_alone(self):
        self.assertIsInstance(await self.live.start_event("Plain", "1h", {"exp": 2.0}), discord.Embed)
        embed, event_id = await self.live.start_event("With id", "1h", {"luck": 2.0}, with_id=True)
        self.assertIsInstance(event_id, int)
        self.assertEqual((await database.get_active_live_events())[-1]["id"], event_id)
        with self.assertRaises(self.live.RuleError):
            await self.live.start_event("Twice", "1h", {"currency:*": 2.0, "currency:Coins": 2.0})
        with self.assertRaises(self.live.RuleError):
            await self.live.start_event("Empty", "1h", {})

    async def test_event_start_takes_the_aurora_animation_and_refuses_an_unknown_one(self):
        self.assertIn("aurora", self.live.ANIMATIONS)
        embed, event_id = await self.live.start_event("Northern", "1h", {"exp": 2.0}, with_id=True, animation="aurora")
        event = next(r for r in await database.get_active_live_events() if r["id"] == event_id)
        self.assertEqual(event["animation"], "aurora")
        self.assertTrue(self.live.animation_name("aurora"), "Discord has a name for it")
        self.assertIn(self.live.animation_name("aurora"), [f.value for f in embed.fields])
        self.assertEqual(self.live.animation_name("laser_show"), "")
        before = len(await database.get_active_live_events())
        with self.assertRaises(self.live.RuleError):
            await self.live.start_event("Bad", "1h", {"exp": 2.0}, animation="laser_show")
        self.assertEqual(len(await database.get_active_live_events()), before, "an unknown animation saves nothing")
        inter = fakes.Interaction()
        await self.cog.event_start.callback(self.cog, inter, "Cmd aurora", "1h", exp_multiplier=self.choice("2"), animation=self.choice("aurora"))
        self.assertTrue(any(r["animation"] == "aurora" and r["name"] == "Cmd aurora" for r in await database.get_active_live_events()))

    async def test_event_start_takes_the_lucky_breeze_animation(self):
        self.assertIn("lucky_breeze", self.live.ANIMATIONS)
        embed, event_id = await self.live.start_event("Breezy", "1h", {"luck": 2.0}, with_id=True, animation="lucky_breeze")
        event = next(r for r in await database.get_active_live_events() if r["id"] == event_id)
        self.assertEqual(event["animation"], "lucky_breeze")
        self.assertTrue(self.live.animation_name("lucky_breeze"), "Discord has a name for it")
        self.assertIn(self.live.animation_name("lucky_breeze"), [f.value for f in embed.fields])
        inter = fakes.Interaction()
        await self.cog.event_start.callback(self.cog, inter, "Cmd breeze", "1h", luck_multiplier=self.choice("2"), animation=self.choice("lucky_breeze"))
        self.assertTrue(any(r["animation"] == "lucky_breeze" and r["name"] == "Cmd breeze" for r in await database.get_active_live_events()))

    async def test_event_start_takes_the_meteor_shower_animation(self):
        self.assertIn("meteor_shower", self.live.ANIMATIONS)
        embed, event_id = await self.live.start_event("Meteors", "1h", {"exp": 2.0}, with_id=True, animation="meteor_shower")
        event = next(r for r in await database.get_active_live_events() if r["id"] == event_id)
        self.assertEqual(event["animation"], "meteor_shower")
        self.assertTrue(self.live.animation_name("meteor_shower"), "Discord has a name for it")
        self.assertIn(self.live.animation_name("meteor_shower"), [f.value for f in embed.fields])
        inter = fakes.Interaction()
        await self.cog.event_start.callback(self.cog, inter, "Cmd meteors", "1h", exp_multiplier=self.choice("2"), animation=self.choice("meteor_shower"))
        self.assertTrue(any(r["animation"] == "meteor_shower" and r["name"] == "Cmd meteors" for r in await database.get_active_live_events()))

    async def test_event_start_takes_the_sakura_festival_animation(self):
        self.assertIn("sakura_festival", self.live.ANIMATIONS)
        embed, event_id = await self.live.start_event("Blossoms", "1h", {"exp": 2.0}, with_id=True, animation="sakura_festival")
        event = next(r for r in await database.get_active_live_events() if r["id"] == event_id)
        self.assertEqual(event["animation"], "sakura_festival")
        self.assertTrue(self.live.animation_name("sakura_festival"), "Discord has a name for it")
        self.assertIn(self.live.animation_name("sakura_festival"), [f.value for f in embed.fields])
        inter = fakes.Interaction()
        await self.cog.event_start.callback(self.cog, inter, "Cmd blossoms", "1h", exp_multiplier=self.choice("2"), animation=self.choice("sakura_festival"))
        self.assertTrue(any(r["animation"] == "sakura_festival" and r["name"] == "Cmd blossoms" for r in await database.get_active_live_events()))

    async def test_egg_create(self):
        inter = fakes.Interaction()
        await self.cog.egg_create.callback(self.cog, inter, "Cmd Egg", "Coins", 500, "Cat:60, Dog:40")
        egg = next(r for r in await database.get_active_eggs() if r["name"] == "Cmd Egg")
        self.assertEqual((egg["currency"], egg["price"], egg["color"], egg["ends_at"]), ("Coins", 500, self.live.EGG_COLORS["white"], 0))
        self.assertIsInstance(inter.followup.sent[-1][1]["embed"], discord.Embed)
        self.assertNotIn("view", inter.followup.sent[-1][1], "the command has no card")
        inter = fakes.Interaction()
        await self.cog.egg_create.callback(self.cog, inter, "Gold Egg", "Gems", 5, "Cat:1",
                                           color=app_commands.Choice(name="Gold", value="gold"),
                                           duration=app_commands.Choice(name="7 days", value="7d"), spot="Spawn", template="Default")
        gold = next(r for r in await database.get_active_eggs() if r["name"] == "Gold Egg")
        self.assertEqual((gold["color"], gold["spot"], gold["template"]), (self.live.EGG_COLORS["gold"], "Spawn", "Default"))
        self.assertGreater(gold["ends_at"], time.time() + 6 * 86400)

    async def test_egg_create_refusals_stay_private(self):
        await self.live.create_egg("Taken", "Coins", 5, "Cat:1", author_id=7)
        for args, why in ((("taken", "Coins", 5, "Cat:1"), "name taken"), (("Bad", "Coins", 5, "Cat"), "pets without a chance"),
                          (("Bad", "Coins", 5, "Cat:1, Cat:2"), "double pet")):
            inter = fakes.Interaction()
            await self.cog.egg_create.callback(self.cog, inter, *args)
            self.assertTrue(inter.response.sent and inter.response.sent[-1][1]["ephemeral"], why)
        self.assertEqual([r["name"] for r in await database.get_active_eggs()], ["Taken"])
        for i in range(self.live.MAX_EGGS - 1):
            await self.live.create_egg(f"Filler {i}", "Coins", 5, "Cat:1", author_id=7)
        inter = fakes.Interaction()
        await self.cog.egg_create.callback(self.cog, inter, "Twenty first", "Coins", 5, "Cat:1")
        self.assertIn(str(self.live.MAX_EGGS), inter.response.sent[-1][0])

    async def test_egg_edit_every_field(self):
        await self.live.create_egg("Edit me", "Coins", 5, "Cat:1", spot="Spawn", author_id=7)
        egg = (await database.get_active_eggs())[0]
        steps = (({"name": "Edited"}, "name", "Edited"), ({"currency": "Gems"}, "currency", "Gems"), ({"price": 77}, "price", 77),
                 ({"pets": "Fox:1, Bird:3"}, "pets", None), ({"color": app_commands.Choice(name="Red", value="red")}, "color",
                                                              self.live.EGG_COLORS["red"]),
                 ({"spot": ""}, "spot", ""), ({"template": "Default"}, "template", "Default"))
        for kwargs, column, expected in steps:
            inter = fakes.Interaction()
            await self.cog.egg_edit.callback(self.cog, inter, str(egg["id"]), **kwargs)
            self.assertTrue(inter.followup.sent, f"{column}: {self.said(inter)}")
            row = await database.get_egg(egg["id"])
            if expected is not None:
                self.assertEqual(row[column], expected, column)
        self.assertEqual([p["name"] for p in json.loads(row["pets"])], ["Fox", "Bird"])
        for bad in ("abc", "999999", ""):
            inter = fakes.Interaction()
            await self.cog.egg_edit.callback(self.cog, inter, bad, price=5)
            self.assertEqual(inter.response.sent[-1][0], self.live.t("eggs.not_found"), repr(bad))
        inter = fakes.Interaction()
        await self.cog.egg_edit.callback(self.cog, inter, str(egg["id"]), currency="   ")
        self.assertTrue(inter.response.sent[-1][1]["ephemeral"], "a blank currency is refused, not saved")
        self.assertEqual((await database.get_egg(egg["id"]))["currency"], "Gems")

    async def test_egg_remove(self):
        await self.live.create_egg("Gone soon", "Coins", 5, "Cat:1", author_id=7)
        egg = (await database.get_active_eggs())[0]
        inter = fakes.Interaction()
        await self.cog.egg_remove.callback(self.cog, inter, str(egg["id"]))
        self.assertFalse((await database.get_egg(egg["id"]))["active"])
        inter = fakes.Interaction()
        await self.cog.egg_remove.callback(self.cog, inter, str(egg["id"]))
        self.assertEqual(inter.response.sent[-1][0], self.live.t("eggs.not_found"))

    async def test_eggs_and_events_lists(self):
        await self.live.create_egg("Listed", "Coins", 5, "Cat:1", author_id=7)
        inter = fakes.Interaction()
        await self.cog.eggs.callback(self.cog, inter)
        self.assertTrue(inter.response.sent)
        await self.live.start_event("Listed", "1h", {"exp": 2.0})
        inter = fakes.Interaction()
        await self.cog.events.callback(self.cog, inter)
        self.assertTrue(inter.response.sent)


class EndThisEvent(Base):
    async def started(self, **kwargs):
        inter = await self.send(self.form(["exp"], **kwargs))
        return inter.followup.sent[-1][1]["view"]

    async def test_ending_twice_the_second_says_not_found(self):
        done = await self.started()
        a, b = fakes.Interaction(), fakes.Interaction()
        await asyncio.gather(done.end.callback(a), done.end.callback(b))
        contents = sorted(i.edited[-1]["content"] for i in (a, b))
        self.assertEqual(sum(self.live.t("events.stopped") in c for c in contents), 1, contents)
        self.assertEqual(sum(self.live.t("events.not_found") in c for c in contents), 1, contents)
        self.assertEqual(await database.get_active_live_events(), [])

    async def test_ended_in_another_window_first(self):
        done = await self.started()
        row = (await database.get_active_live_events())[0]
        await database.stop_live_event(row["id"])  # "Stop an event" in the list, or /event-stop
        inter = fakes.Interaction()
        await done.end.callback(inter)
        self.assertIn(self.live.t("events.not_found"), inter.edited[-1]["content"])

    async def test_only_the_event_of_this_card_ends(self):
        first = await self.started(name="First")
        await self.started(name="Second")
        inter = fakes.Interaction()
        await first.end.callback(inter)
        self.assertEqual([r["name"] for r in await database.get_active_live_events()], ["Second"])
        self.assertEqual(self.pushed.count("events"), 3, "two starts and one end were sent to the game")

    async def test_after_the_event_ran_out_the_card_does_not_break(self):
        done = await self.started()
        row = (await database.get_active_live_events())[0]
        with mock.patch("utils.database._now", return_value=row["ends_at"] + 10):
            self.assertEqual(await database.get_active_live_events(), [], "the event is over")
            inter = fakes.Interaction()
            await done.end.callback(inter)
        self.assertTrue(inter.edited[-1]["content"])
        self.assertIsInstance(inter.edited[-1]["view"], self.panel.CloseView)

    async def test_after_the_event_ran_out_the_card_says_not_found_not_stopped(self):
        # DEFECT (cosmetic): database.stop_live_event() only checks `active = 1`, so an event that already ran out
        # by time is "stopped" again: the admin reads "⏹️ Event stopped" and the bot sends the events to the game for
        # nothing. Eggs treat an expired egg as gone (egg_changes); events should too (AND ends_at > now).
        done = await self.started()
        row = (await database.get_active_live_events())[0]
        with mock.patch("utils.database._now", return_value=row["ends_at"] + 10):
            inter = fakes.Interaction()
            await done.end.callback(inter)
        self.assertIn(self.live.t("events.not_found"), inter.edited[-1]["content"])

    async def test_the_card_fits_in_every_language(self):
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                fakes.check_view(self.panel.EventDoneView(1), f"EventDoneView [{lang}]")


if __name__ == "__main__":
    unittest.main()
