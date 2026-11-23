"""Point 5: one event form can multiply several things at once (one multiplier for all of them), never "all
currencies" together with a single currency (the game would multiply it twice), and ⏹️ under a started event."""
import json
import unittest
from unittest import mock

import discord

from tests import fakes
from tests.helpers import TempBot
from utils import config_store, database, i18n, roblox_kit

LANGS = ("en", "pl", "es")


class EventPanel(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import live_game, setup_roblox
        self.live, self.panel = live_game, setup_roblox
        config_store.write_json("game_economy.json", {"configured": True, "currencies": ["Coins", "Gems"]})

        async def push(kind, force=True):
            return True, ""

        self.patches = [mock.patch.object(live_game, "push_live", push),
                        mock.patch.object(roblox_kit, "game_scan", return_value=None)]
        for patch in self.patches:
            patch.start()

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
        modal.value._values = [value]
        return modal

    async def test_several_things_with_one_multiplier(self):
        modal = self.form(["currency:Coins", "exp", "luck"], "3")
        self.assertEqual(modal.kind.max_values, len(modal.kind.options), "the menu takes several")
        inter = fakes.Interaction()
        await modal.on_submit(inter)
        rows = await database.get_active_live_events()
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0]["multipliers"]), {"currency:Coins": 3.0, "exp": 3.0, "luck": 3.0})
        content, kwargs = inter.followup.sent[-1]
        self.assertIsInstance(kwargs["view"], self.panel.EventDoneView)
        self.assertEqual(kwargs["view"].event_id, rows[0]["id"])
        self.assertIn("/event-start", kwargs["embed"].footer.text, "different multipliers: the command")

    async def test_all_currencies_never_together_with_one_currency(self):
        inter = fakes.Interaction()
        await self.form([f"currency:{self.live.ALL_CURRENCIES}", "currency:Coins"]).on_submit(inter)
        self.assertIn("❌", inter.followup.sent[-1][0])
        self.assertEqual(await database.get_active_live_events(), [], "nothing started")
        with self.assertRaises(self.live.RuleError):
            await self.live.start_event("x", "1h", {"currency:*": 2.0, "currency:Gems": 2.0})
        inter = fakes.Interaction()
        await self.form([f"currency:{self.live.ALL_CURRENCIES}", "exp"]).on_submit(inter)
        self.assertEqual(len(await database.get_active_live_events()), 1, "all currencies with EXP is fine")

    async def test_end_the_event_under_it(self):
        inter = fakes.Interaction()
        await self.form(["exp"]).on_submit(inter)
        done = inter.followup.sent[-1][1]["view"]
        inter = fakes.Interaction()
        await done.end.callback(inter)
        self.assertEqual(await database.get_active_live_events(), [])
        self.assertIn(self.live.t("events.stopped"), inter.edited[-1]["content"])
        inter = fakes.Interaction()
        await self.panel.EventDoneView(done.event_id).end.callback(inter)
        self.assertIn(self.live.t("events.not_found"), inter.edited[-1]["content"], "ended already: said so")

    async def test_nothing_is_picked_in_advance(self):
        # a preselected currency stayed picked next to what the admin chose (luck x10 also gave Coins x10)
        self.assertFalse([o for o in self.panel.EventModal().kind.options if o.default])
        self.assertEqual(self.panel.EventModal().kind.min_values, 1, "Discord still asks for at least one")

    async def test_the_command_still_gets_only_the_answer(self):
        embed = await self.live.start_event("Cmd", "1h", {"exp": 2.0})
        self.assertIsInstance(embed, discord.Embed, "/event-start keeps its old answer")

    async def test_the_form_fits_in_every_language(self):
        config_store.write_json("game_economy.json", {"configured": True, "currencies": [f"Coin{i}" for i in range(30)]})
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                modal = self.panel.EventModal()
                fakes.check_modal(modal, f"EventModal [{lang}]")
                self.assertLessEqual(modal.kind.max_values, 25)
                fakes.check_view(self.panel.EventDoneView(1), f"EventDoneView [{lang}]")


class EventFromTheAnimationList(unittest.IsolatedAsyncioTestCase):
    """⚡ Eventy -> New event: a panel with the animation list first, then the form that answers in place of the list."""

    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import live_game, setup_roblox
        from utils import ui
        self.live, self.panel, self.ui = live_game, setup_roblox, ui
        config_store.write_json("game_economy.json", {"configured": True, "currencies": ["Coins", "Gems"]})

        async def push(kind, force=True):
            return True, ""

        self.patches = [mock.patch.object(live_game, "push_live", push),
                        mock.patch.object(roblox_kit, "game_scan", return_value=None)]
        for patch in self.patches:
            patch.start()

    async def asyncTearDown(self):
        for patch in self.patches:
            patch.stop()
        await database.close_db()
        self.temp.__exit__(None, None, None)

    async def click_new_event(self):
        """The click on 'New event': returns the panel that was sent and its animation list."""
        inter = fakes.Interaction()
        await self.panel.EventsView().new.callback(inter)
        self.assertEqual(len(inter.response.sent), 1, "one message, no form yet")
        self.assertEqual(inter.response.modals, [])
        content, kwargs = inter.response.sent[-1]
        self.assertTrue(kwargs["ephemeral"])
        self.assertEqual(content, self.live.t("rbx.event_pick_animation"))
        view = kwargs["view"]
        self.assertIsInstance(view, self.panel.StaffView)
        selects = [i for i in view.children if isinstance(i, self.panel.EventAnimationSelect)]
        self.assertEqual(len(selects), 1)
        return view, selects[0]

    async def pick(self, view, select, value):
        """Picks an animation in the list; returns the form that Discord opens."""
        select._values = [value]
        inter = fakes.Interaction()
        await select.callback(inter)
        self.assertEqual(len(inter.response.modals), 1, "the pick opens exactly one form")
        modal = inter.response.modals[0]
        self.assertIsInstance(modal, self.panel.EventModal)
        return modal

    @staticmethod
    def fill(modal, name="Petals", duration="1h", custom="", kinds=("exp",), value="2"):
        modal.event_name._value = name
        modal.duration._values = [duration]
        modal.custom_duration._value = custom
        modal.kind._values = list(kinds)
        modal.value._values = [value]

    async def test_new_event_sends_the_animation_list(self):
        view, select = await self.click_new_event()
        self.assertEqual(select.options[0].value, "none")
        self.assertEqual([o.value for o in select.options[1:]], list(self.live.ANIMATIONS))
        self.assertIn("sakura_festival", [o.value for o in select.options])
        fakes.check_view(view, "animation list")

    async def test_picking_sakura_festival_saves_the_event_and_answers_in_place_of_the_list(self):
        view, select = await self.click_new_event()
        modal = await self.pick(view, select, "sakura_festival")
        self.assertEqual(modal.animation, "sakura_festival")
        self.assertIs(modal.source, view, "the form knows the list it came from")
        self.assertEqual(view.timeout, self.ui.PANEL_TIMEOUT, "hold_for_form: time to fill the form in")
        self.assertIn("Sakura Festival", modal.title)
        self.fill(modal)
        inter = fakes.Interaction()
        await modal.on_submit(inter)
        rows = await database.get_active_live_events()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["animation"], "sakura_festival")
        self.assertEqual(rows[0]["name"], "Petals")
        self.assertEqual(json.loads(rows[0]["multipliers"]), {"exp": 2.0})
        # the answer replaces the list: a plain defer, then edit_original_response; no new message
        self.assertEqual(inter.response.defers, [{}])
        self.assertEqual(inter.response.sent, [])
        self.assertEqual(inter.followup.sent, [])
        self.assertEqual(len(inter.edited), 1)
        edit = inter.edited[-1]
        self.assertIsInstance(edit["view"], self.panel.EventDoneView)
        self.assertEqual(edit["view"].event_id, rows[0]["id"])
        self.assertIn(self.live.animation_name("sakura_festival"), [f.value for f in edit["embed"].fields])

    async def test_none_gives_an_event_without_animation(self):
        view, select = await self.click_new_event()
        modal = await self.pick(view, select, "none")
        self.assertEqual(modal.animation, "")
        self.assertIs(modal.source, view)
        self.assertNotIn("·", modal.title, "no animation name in the title")
        self.fill(modal, name="Plain")
        inter = fakes.Interaction()
        await modal.on_submit(inter)
        rows = await database.get_active_live_events()
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["animation"], "no animation saved")
        self.assertEqual(self.live.animation_name(rows[0]["animation"]), "")
        self.assertEqual(inter.followup.sent + inter.response.sent, [])
        self.assertIsInstance(inter.edited[-1]["view"], self.panel.EventDoneView)

    async def test_every_animation_of_the_list_is_saved_with_the_event(self):
        for key in self.live.ANIMATIONS:
            view, select = await self.click_new_event()
            modal = await self.pick(view, select, key)
            self.fill(modal, name=f"Event {key}")
            await modal.on_submit(fakes.Interaction())
        saved = {r["name"]: r["animation"] for r in await database.get_active_live_events()}
        self.assertEqual(saved, {f"Event {key}": key for key in self.live.ANIMATIONS})

    async def test_a_rule_error_is_said_in_place_of_the_list(self):
        view, select = await self.click_new_event()
        modal = await self.pick(view, select, "sakura_festival")
        self.fill(modal, custom="31d")  # longer than an event may last
        inter = fakes.Interaction()
        await modal.on_submit(inter)
        self.assertEqual(await database.get_active_live_events(), [], "nothing saved")
        self.assertEqual(inter.response.sent + inter.followup.sent, [], "no new message")
        self.assertEqual(len(inter.edited), 1)
        self.assertIn("❌", inter.edited[-1]["content"])
        self.assertIsInstance(inter.edited[-1]["view"], self.ui.CloseView)

    async def test_a_blank_name_is_also_said_in_place_of_the_list(self):
        view, select = await self.click_new_event()
        modal = await self.pick(view, select, "none")
        self.fill(modal, name="   ")
        inter = fakes.Interaction()
        await modal.on_submit(inter)
        self.assertIn(self.live.t("events.err_name"), inter.edited[-1]["content"])
        self.assertEqual(inter.response.sent + inter.followup.sent, [])

    async def test_when_the_list_is_gone_the_answer_is_a_new_private_message(self):
        view, select = await self.click_new_event()
        modal = await self.pick(view, select, "aurora")
        self.fill(modal)
        view.stop()  # closed or removed while the form was open
        inter = fakes.Interaction()
        await modal.on_submit(inter)
        self.assertEqual(inter.response.defers, [{"ephemeral": True, "thinking": True}])
        self.assertEqual((await database.get_active_live_events())[0]["animation"], "aurora", "the event is saved anyway")
        self.assertIsInstance(inter.edited[-1]["view"], self.panel.EventDoneView)

    async def test_the_form_without_the_list_still_answers_with_a_new_message(self):
        # EventModal() without a source (nothing else opens it now, but it must not break)
        modal = self.panel.EventModal()
        self.fill(modal, name="Direct")
        inter = fakes.Interaction()
        await modal.on_submit(inter)
        self.assertEqual(inter.response.defers, [{"ephemeral": True, "thinking": True}])
        self.assertIsInstance(inter.followup.sent[-1][1]["view"], self.panel.EventDoneView)
        self.assertEqual(inter.edited, [])

    async def test_the_events_window_shows_the_animation_of_an_active_event(self):
        await self.live.start_event("Blossoms", "1h", {"exp": 2.0}, animation="sakura_festival")
        await self.live.start_event("Quiet", "1h", {"luck": 2.0})
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                embed = await self.panel.EventsView().embed()
                fakes.check_embed(embed, f"EventsView [{lang}]")
                field = next(f for f in embed.fields if "Blossoms" in f.value)
                lines = {("Blossoms" in line): line for line in field.value.split("\n")}
                animation = self.live.animation_name("sakura_festival")
                self.assertTrue(animation)
                self.assertIn(f"• ✨ {animation}", lines[True], lang)
                self.assertNotIn("✨", lines[False], f"an event without animation shows none [{lang}]")

    async def test_the_events_window_with_ten_animated_events_stays_within_the_field_limit(self):
        for i in range(self.live.MAX_EVENTS):
            await self.live.start_event(f"A long event name number {i} " + "x" * 20, "1h", {"exp": 2.0},
                                        animation=self.live.ANIMATIONS[i % len(self.live.ANIMATIONS)])
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                fakes.check_embed(await self.panel.EventsView().embed(), f"EventsView full [{lang}]")

    async def test_the_list_fits_in_every_language(self):
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                view, select = await self.click_new_event()
                fakes.check_view(view, f"animation list [{lang}]")
                self.assertGreater(len(self.live.t("rbx.event_pick_animation")), 5)
                for key in self.live.ANIMATIONS:
                    self.assertTrue(self.live.t(f"rbx.event_anim_desc.{key}"), f"{key} [{lang}]")
                    fakes.check_modal(self.panel.EventModal(key, source=view), f"EventModal {key} [{lang}]")


if __name__ == "__main__":
    unittest.main()
