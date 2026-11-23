"""Who may use the egg and event windows of /setup-roblox (the new ones too): administrators and the roles chosen in
/setup-roblox -> Control panel; nobody else. Checked with discord.py's own dispatch (View._scheduled_task) and the REAL
callbacks (not replaced by mocks), so a window that forgot the check would change the database in this test.
Forms are checked when they are SENT: the role may be taken away while one is open."""
import json
import time
import unittest
from unittest import mock

import discord

from tests.helpers import TempBot
from tests.panel_fakes import OTHER, STAFF, interaction_for, make_guild
from utils.ui import CLOSE_ID
from utils import access, catalog, config_store, database, roblox_kit

SCAN = {"values": [], "attributes": [], "spots": ["Spawn"], "templates": ["Default", "Golden"], "multipliers": [],
        "hooks": [], "at": 0, "studio": False}
PRESET = ("Catalog Egg", "Cat:60, Dog:40", "Coins", 100)


class Base(unittest.IsolatedAsyncioTestCase):
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
                        mock.patch.object(roblox_kit, "game_scan", return_value=SCAN),
                        mock.patch.object(catalog, "egg_presets", return_value=[PRESET]),
                        mock.patch("utils.access.is_bot_owner", mock.AsyncMock(return_value=False))]
        for patch in self.patches:
            patch.start()
        self.guild = make_guild([STAFF])
        await live_game.create_egg("Guarded", "Coins", 500, "Cat:60, Dog:40", spot="Spawn", author_id=7)
        self.egg = (await database.get_active_eggs())[0]

    async def asyncTearDown(self):
        for patch in self.patches:
            patch.stop()
        await database.close_db()
        self.temp.__exit__(None, None, None)

    async def state(self):
        eggs = [{k: r[k] for k in r.keys()} for r in await database.get_active_eggs()]
        events = [{k: r[k] for k in r.keys()} for r in await database.get_active_live_events()]
        return json.dumps([eggs, events], sort_keys=True), len(self.pushed)

    def no_access(self, label):
        """The refusal names the permission: events for the event forms and windows, eggs for the rest here."""
        perm = "events" if "event" in label.lower() else "eggs"
        return self.live.t("perm.no_access", what=self.live.t(f"perm.{perm}"))

    def modals(self):
        egg = self.panel.EggModal()
        egg.egg_name._value, egg.price._value, egg.pets._value = "Sneaky", "5", "Cat:1, Dog:1"
        egg.currency._values, egg.spot._values = ["Coins"], ["-"]
        edit = self.panel.EggModal(egg=self.egg)
        edit.egg_name._value, edit.price._value, edit.pets._value = "Hacked", "1", "Fox:1"
        edit.currency._values, edit.spot._values = ["Gems"], ["-"]
        preset = self.panel.EggModal(preset=PRESET)
        preset.egg_name._value, preset.price._value, preset.pets._value = "Catalog Egg", "100", "Cat:60, Dog:40"
        preset.currency._values, preset.spot._values = ["Coins"], ["-"]
        event = self.panel.EventModal()
        event.event_name._value, event.duration._values, event.kind._values, event.value._values = "Sneaky", ["1h"], ["exp"], ["10"]
        return {"new egg": egg, "edit egg": edit, "egg from the catalog": preset, "event": event}

    async def click(self, view, item, who, values=None):
        """discord.py's dispatch with the real callback. Returns (interaction, errors the window met)."""
        inter = interaction_for(self.guild, who)
        inter.data = {"custom_id": getattr(item, "custom_id", None)}
        if isinstance(item, discord.ui.Select):
            inter.data["values"] = values if values is not None else [item.options[0].value]
        errors = []

        async def on_error(interaction, error, item):
            errors.append(error)

        view.on_error = on_error
        await view._scheduled_task(item, inter)
        return inter, errors


class Forms(Base):
    async def test_a_player_sending_a_form_changes_nothing(self):
        before = await self.state()
        for label, modal in self.modals().items():
            inter = interaction_for(self.guild, "player")
            await modal.on_submit(inter)
            self.assertEqual(await self.state(), before, label)
            self.assertEqual(len(inter.response.sent), 1, label)
            self.assertEqual(inter.response.sent[0][0], self.no_access(label), label)
            self.assertTrue(inter.response.sent[0][1]["ephemeral"], label)
            self.assertFalse(inter.response.defers, f"{label}: nothing was started")

    async def test_staff_and_administrators_can_send_them(self):
        for who in ("staff", "admin"):
            modals = self.modals()
            modals["new egg"].egg_name._value = f"New by {who}"
            modals["edit egg"].egg_name._value = f"Edited by {who}"
            modals["egg from the catalog"].egg_name._value = f"Catalog by {who}"
            modals["event"].event_name._value = f"Event {who}"
            for label, modal in modals.items():
                inter = interaction_for(self.guild, who)
                await modal.on_submit(inter)
                self.assertTrue(inter.response.defers, f"{who} / {label}: the form was accepted")
                self.assertNotEqual(inter.response.sent[:1] and inter.response.sent[0][0], self.no_access(label))
                self.assertNotEqual(inter.response.sent[:1] and inter.response.sent[0][0], self.live.t("gpanel.no_access"))
        names = sorted(r["name"] for r in await database.get_active_eggs())
        self.assertEqual(names, ["Catalog by admin", "Catalog by staff", "Edited by admin", "New by admin", "New by staff"])
        self.assertEqual(sorted(r["name"] for r in await database.get_active_live_events()), ["Event admin", "Event staff"])

    async def test_the_role_taken_away_while_the_form_was_open(self):
        modals = self.modals()  # opened while the role still worked
        config_store.set_guild_values(self.guild.id, access.GAME_PANEL, {"staff_role_ids": []})
        before = await self.state()
        for label, modal in modals.items():
            inter = interaction_for(self.guild, "staff")
            await modal.on_submit(inter)
            self.assertEqual(inter.response.sent[0][0], self.no_access(label), label)
        self.assertEqual(await self.state(), before)
        config_store.set_guild_values(self.guild.id, access.GAME_PANEL, {"staff_role_ids": [OTHER]})  # another role: still no
        for label, modal in self.modals().items():
            inter = interaction_for(self.guild, "staff")
            await modal.on_submit(inter)
            self.assertEqual(inter.response.sent[0][0], self.no_access(label), label)
        self.assertEqual(await self.state(), before)


class Windows(Base):
    def windows(self):
        chooser_edit, chooser_copy = self.panel.StaffView(permission="eggs"), self.panel.StaffView(permission="eggs")
        chooser_edit.add_item(self.panel.EggPickSelect("edit", [self.egg, self.egg]))
        chooser_copy.add_item(self.panel.EggPickSelect("preset", [PRESET]))
        return {"egg card": self.panel.EggDoneView(self.egg["id"], self.egg), "pick an egg to edit": chooser_edit,
                "pick a catalog egg": chooser_copy, "event card": self.panel.EventDoneView(1), "eggs": self.panel.EggsView(),
                "events": self.panel.EventsView()}

    async def test_a_player_uses_nothing(self):
        await self.live.start_event("Running", "1h", {"exp": 2.0})
        before = await self.state()
        for label, view in self.windows().items():
            view.to_components()
            for item in view.children:
                if str(getattr(item, "custom_id", "")).startswith(CLOSE_ID):
                    continue  # ✖️ Close works for anyone (it only removes the window, utils/ui.py is_close_click)
                inter, errors = await self.click(view, item, "player")
                where = f"{label} / {getattr(item, 'label', None) or type(item).__name__} / player"
                self.assertEqual(errors, [], where)
                self.assertEqual(len(inter.response.sent), 1, where)
                self.assertEqual(inter.response.sent[0][0], self.no_access(where), where)
                self.assertFalse(inter.response.modals or inter.response.defers or inter.response.edits, where)
        self.assertEqual(await self.state(), before, "no click of a player changed an egg or an event")

    async def test_staff_and_administrators_get_through_the_same_windows(self):
        for who in ("staff", "admin"):
            for label, view in self.windows().items():
                view.to_components()
                for item in view.children:
                    if isinstance(item, discord.ui.Button) and item.emoji and str(item.emoji) in ("🗑️", "⏹️"):
                        continue  # (these change data: checked below)
                    inter, errors = await self.click(view, item, who)
                    where = f"{label} / {getattr(item, 'label', None) or type(item).__name__} / {who}"
                    self.assertEqual(errors, [], where)
                    self.assertNotEqual((inter.response.sent[0][0] if inter.response.sent else None), self.no_access(where), where)

    async def test_the_buttons_that_remove_work_for_staff_and_not_for_a_player(self):
        _, event_id = await self.live.start_event("Running", "1h", {"exp": 2.0}, with_id=True)
        player_ends, _ = await self.click(self.panel.EventDoneView(event_id), self.panel.EventDoneView(event_id).end, "player")
        self.assertEqual(len(await database.get_active_live_events()), 1, "a player can't end the event")
        card = self.panel.EggDoneView(self.egg["id"])
        await self.click(card, card.remove, "player")
        self.assertTrue((await database.get_egg(self.egg["id"]))["active"], "a player can't remove the egg")
        done = self.panel.EventDoneView(event_id)
        _, errors = await self.click(done, done.end, "staff")
        self.assertEqual((errors, await database.get_active_live_events()), ([], []))
        card = self.panel.EggDoneView(self.egg["id"])
        _, errors = await self.click(card, card.remove, "staff")
        self.assertEqual(errors, [])
        self.assertFalse((await database.get_egg(self.egg["id"]))["active"])

    async def test_the_color_time_and_model_menus_work_for_staff_only(self):
        card = self.panel.EggDoneView(self.egg["id"], self.egg)
        for select, value in ((card.color, "gold"), (card.duration, "7d"), (card.template, "1")):
            await self.click(card, select, "player", [value])
        row = await database.get_egg(self.egg["id"])
        self.assertEqual((row["color"], row["ends_at"], row["template"]), (self.egg["color"], 0, self.egg["template"]))
        for select, value in ((card.color, "gold"), (card.duration, "7d"), (card.template, "1")):
            _, errors = await self.click(card, select, "staff", [value])
            self.assertEqual(errors, [])
        row = await database.get_egg(self.egg["id"])
        self.assertEqual((row["color"], row["template"]), (self.live.EGG_COLORS["gold"], "Golden"))
        self.assertGreater(row["ends_at"], time.time() + 6 * 86400)

    async def test_the_role_taken_away_works_in_a_card_opened_before(self):
        card = self.panel.EggDoneView(self.egg["id"], self.egg)
        config_store.set_guild_values(self.guild.id, access.GAME_PANEL, {"staff_role_ids": []})
        before = await self.state()
        for item in card.children:
            inter, _ = await self.click(card, item, "staff", ["gold"] if isinstance(item, discord.ui.Select) else None)
            self.assertEqual(inter.response.sent[0][0], self.no_access("egg card"))
        self.assertEqual(await self.state(), before)

    async def test_the_pickers_open_no_form_for_a_player(self):
        for view in (self.windows()["pick an egg to edit"], self.windows()["pick a catalog egg"]):
            inter, _ = await self.click(view, view.children[0], "player", ["0"])
            self.assertFalse(inter.response.modals)


if __name__ == "__main__":
    unittest.main()
