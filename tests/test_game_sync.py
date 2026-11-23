"""utils/game_sync.py: the game's ⚙️ Manager makes and removes codes, events and eggs in the game's DataStore by itself
(also while the bot is off), and Discord changes the same entries. One sync makes the game and the bot's database agree:
what the game did is copied here, what Discord did goes there, and a save never overwrites what a game server saved in
that very moment (Open Cloud matchVersion; the fake answers like Roblox: 412 with the entry as it is now)."""
import json
import time
import unittest
from contextlib import ExitStack
from unittest import mock

from tests.game_cloud import CODES, LIVE, FakeCloud
from tests.helpers import TempBot
from utils import cloud_sync, database, game_sync


def game_egg(uid: str, **fields) -> dict:
    egg = {"id": uid, "name": f"Egg {uid}", "currency": "Coins", "price": 100, "pets": [{"name": "Cat", "chance": 100}],
           "color": "#F5F5F5", "spot": "", "template": "", "ends_at": 0, "origin": "game", "by": "Builder", "by_id": 77}
    egg.update(fields)
    return egg


class Sync(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import live_game
        self.live = live_game
        self.cloud = FakeCloud()
        self.stack = ExitStack()
        for patch in self.cloud.patches():
            self.stack.enter_context(patch)

    async def asyncTearDown(self):
        self.stack.close()
        await database.close_db()
        self.temp.__exit__(None, None, None)

    def eggs(self) -> list:
        return (self.cloud.value(LIVE, "Eggs") or {}).get("eggs", [])

    async def add_event(self, name="Double", seconds=3600) -> int:
        now = int(time.time())
        return await database.add_live_event(name, json.dumps({"currency:*": 2}), now, now + seconds, 5)

    # ---------- Discord -> game ----------

    async def test_an_event_made_on_discord_goes_to_the_game_once(self):
        event_id = await self.add_event()
        ok, error = await self.live.push_live("events")
        self.assertTrue(ok, error)
        events = self.cloud.value(LIVE, "Events")["events"]
        self.assertEqual([(e["id"], e["name"], e["origin"]) for e in events], [(event_id, "Double", "discord")])
        self.assertEqual(self.cloud.published, [("DiscordLive", {"type": "events", "at": self.cloud.value(LIVE, "Events")["updated_at"]})],
                         "the game compares 'at' with updated_at")
        self.assertEqual((await database.get_live_event(event_id))["pending"], 0, "the game has it now")
        await self.live.push_live("events")
        self.assertEqual(len(self.cloud.writes), 1, "nothing changed: nothing saved again")

    async def test_a_code_from_discord_keeps_the_codes_the_game_made(self):
        self.cloud.game_saves(CODES, "ActiveCodes", lambda _: {"version": 2, "codes": {"PANEL": {"expires_at": 0, "exp": 50}},
                                                                 "meta": {"PANEL": {"origin": "game", "by": "Builder"}}})
        await database.add_game_code("SUMMER", "Coins", 500, 0, None, "permanent", 0, 0, 0, 5)
        result = await cloud_sync.push_codes(force=False)
        self.assertTrue(result.ok, result.message)
        saved = self.cloud.value(CODES, "ActiveCodes")
        self.assertEqual(sorted(saved["codes"]), ["PANEL", "SUMMER"], "the code made in the game stays")
        self.assertEqual(saved["meta"]["PANEL"], {"origin": "game", "by": "Builder"})
        self.assertEqual(saved["meta"]["SUMMER"], {"origin": "discord"})
        panel = await database.get_game_code("PANEL")
        self.assertEqual((panel["origin"], panel["author"], panel["exp_amount"], panel["is_active"]), ("game", "Builder", 50, 1),
                         "and is copied into the database")
        self.assertIn("2", result.message, "the answer counts both codes")

    async def test_a_save_that_meets_a_game_save_tries_again_and_keeps_both(self):
        event_id = await self.add_event("From Discord")

        def game_starts_an_event(cloud):  # in the moment between the bot's read and its save
            cloud.game_saves(LIVE, "Events", lambda v: {"events": [{"id": "g1", "name": "From the game", "ends_at": int(time.time()) + 600,
                                                                     "multipliers": {"exp": 2}, "origin": "game", "by": "Builder"}],
                                                         "next_id": 2})
        self.cloud.before_write.append(game_starts_an_event)
        ok, error = await self.live.push_live("events")
        self.assertTrue(ok, error)
        self.assertEqual(self.cloud.conflicts, 1, "the first save was refused (the entry changed)")
        saved = self.cloud.value(LIVE, "Events")
        self.assertEqual(sorted(str(e["id"]) for e in saved["events"]), sorted([str(event_id), "g1"]))
        self.assertEqual(saved["next_id"], 2, "the game's own fields stay")
        rows = await database.get_active_live_events()
        self.assertEqual(sorted(r["name"] for r in rows), ["From Discord", "From the game"])

    async def test_the_game_changing_it_every_time_gives_up_with_a_message_and_changes_nothing_here(self):
        await self.add_event()
        for n in range(game_sync.MAX_TRIES):
            self.cloud.before_write.append(lambda cloud, n=n: cloud.game_saves(LIVE, "Events", lambda v: {"events": [], "n": n}))
        ok, error = await self.live.push_live("events")
        self.assertFalse(ok)
        self.assertIn(self.live.t("sync.busy"), error)
        self.assertGreater((await database.get_active_live_events())[0]["pending"], 0, "still waits for the next sync")

    async def test_removed_on_discord_leaves_the_game_and_other_things_stay(self):
        self.cloud.game_saves(LIVE, "Eggs", lambda _: {"eggs": [game_egg("g1"), game_egg("g2")], "next_id": 3})
        await self.live.push_live("eggs")
        rows = {r["uid"]: r for r in await database.get_active_eggs()}
        self.assertEqual(sorted(rows), ["g1", "g2"])
        self.assertTrue(await database.remove_egg(rows["g1"]["id"]))
        ok, error = await self.live.push_live("eggs")
        self.assertTrue(ok, error)
        self.assertEqual([e["id"] for e in self.eggs()], ["g2"])
        self.assertEqual(self.eggs()[0]["by_id"], 77, "the game's own fields of the other egg stay")
        self.assertEqual(self.cloud.value(LIVE, "Eggs")["next_id"], 3)

    async def test_an_egg_from_the_game_edited_on_discord_keeps_its_id(self):
        self.cloud.game_saves(LIVE, "Eggs", lambda _: {"eggs": [game_egg("g7", spot="Spot1")]})
        await self.live.push_live("eggs")
        row = (await database.get_active_eggs())[0]
        self.assertEqual((row["origin"], row["author"], row["spot"], row["pending"]), ("game", "Builder", "Spot1", 0))
        self.assertTrue(await database.update_egg(row["id"], price=250))
        await self.live.push_live("eggs")
        egg = self.eggs()[0]
        self.assertEqual((egg["id"], egg["price"], egg["by_id"], egg["origin"]), ("g7", 250, 77, "game"))

    # ---------- game -> Discord ----------

    async def test_what_the_game_removed_or_changed_comes_here(self):
        event_id = await self.add_event()
        await database.add_game_code("GONE", None, 0, 10, None, "permanent", 0, 0, 0, 5)
        egg_id = await database.add_egg("Basic", "Coins", 10, json.dumps([{"name": "Cat", "chance": 100}]), "", "", "", 0, 5)
        for kind in ("events", "eggs"):
            await self.live.push_live(kind)
        await cloud_sync.push_codes(force=False)
        # the game's Manager: the event stopped, the code removed, the egg moved
        self.cloud.game_saves(LIVE, "Events", lambda v: dict(v, events=[]))
        self.cloud.game_saves(CODES, "ActiveCodes", lambda v: dict(v, codes={}, meta={}))
        self.cloud.game_saves(LIVE, "Eggs", lambda v: dict(v, eggs=[dict(v["eggs"][0], spot="Spot2")]))
        await self.live.push_live("events")
        await self.live.push_live("eggs")
        await cloud_sync.push_codes(force=False)
        self.assertEqual(await database.get_active_live_events(), [])
        self.assertFalse((await database.get_live_event(event_id))["active"])
        self.assertEqual(await database.get_active_game_codes(), [])
        egg = await database.get_egg(egg_id)
        self.assertEqual((egg["spot"], egg["active"], egg["origin"]), ("Spot2", 1, "discord"))

    async def test_a_change_made_on_discord_during_a_sync_is_not_lost(self):
        self.cloud.game_saves(LIVE, "Eggs", lambda _: {"eggs": [game_egg("g1")]})
        await self.live.push_live("eggs")
        row = (await database.get_active_eggs())[0]
        # the sync sees pending P; an edit on Discord makes it P2 before the sync marks the row done
        await database.update_egg(row["id"], price=300)
        pending = (await database.get_egg(row["id"]))["pending"]
        real_apply = database.apply_sync

        async def apply_after_an_edit(kind, *args, **kwargs):
            await database.update_egg(row["id"], price=400)  # the admin clicked again in that moment
            await real_apply(kind, *args, **kwargs)
        with mock.patch.object(database, "apply_sync", apply_after_an_edit):
            await self.live.push_live("eggs")
        after = await database.get_egg(row["id"])
        self.assertNotEqual(after["pending"], 0, "the newer change still waits")
        self.assertNotEqual(after["pending"], pending)
        await self.live.push_live("eggs")
        self.assertEqual(self.eggs()[0]["price"], 400)
        self.assertEqual((await database.get_egg(row["id"]))["pending"], 0)

    async def test_ended_things_leave_the_entry_and_are_never_copied(self):
        past = int(time.time()) - 5
        self.cloud.game_saves(LIVE, "Eggs", lambda _: {"eggs": [game_egg("g1", ends_at=past), game_egg("g2")]})
        self.cloud.game_saves(LIVE, "Events", lambda _: {"events": [{"id": "g3", "name": "Old", "ends_at": past, "multipliers": {"exp": 2}}]})
        await self.live.push_live("eggs")
        await self.live.push_live("events")
        self.assertEqual([e["id"] for e in self.eggs()], ["g2"])
        self.assertEqual(self.cloud.value(LIVE, "Events")["events"], [])
        self.assertEqual([r["uid"] for r in await database.get_active_eggs()], ["g2"])
        self.assertEqual(await database.get_active_live_events(), [])

    async def test_a_game_without_the_entry_gets_everything_again(self):
        """A missing entry (a new game, or removed in Creator Hub) never means "everything was removed in the game"."""
        await database.add_game_code("KEEP", None, 0, 10, None, "permanent", 0, 0, 0, 5)
        await cloud_sync.push_codes(force=False)
        self.cloud.entries.clear()
        result = await cloud_sync.push_codes(force=False)
        self.assertTrue(result.ok, result.message)
        self.assertEqual(list(self.cloud.value(CODES, "ActiveCodes")["codes"]), ["KEEP"])
        self.assertEqual(len(await database.get_active_game_codes()), 1)

    async def test_another_game_gets_everything_and_takes_nothing_as_removed(self):
        await self.add_event("Kept")
        await self.live.push_live("events")
        await cloud_sync.reset_game_state()
        self.cloud.game_saves(LIVE, "Events", lambda _: {"events": []})  # the new game has its own (empty) entry
        await self.live.push_live("events")
        self.assertEqual([e["name"] for e in self.cloud.value(LIVE, "Events")["events"]], ["Kept"])
        self.assertEqual(len(await database.get_active_live_events()), 1)

    async def test_another_game_never_loses_its_own_things_to_the_old_game(self):
        """Game A: a code removed on Discord, an egg made in A's Manager. Game B already has its own WELCOME and g1."""
        await database.add_game_code("WELCOME", None, 0, 5, None, "permanent", 0, 0, 0, 5)
        await database.add_game_code("KEEP", None, 0, 7, None, "permanent", 0, 0, 0, 5)
        self.cloud.game_saves(LIVE, "Eggs", lambda _: {"eggs": [game_egg("g1", name="A egg")], "next_id": 2})
        await cloud_sync.push_codes(force=False)
        await self.live.push_live("eggs")
        await database.delete_game_code("WELCOME")
        await cloud_sync.push_codes(force=False)
        await cloud_sync.reset_game_state()  # game B is connected
        self.cloud.entries.clear()
        self.cloud.game_saves(CODES, "ActiveCodes", lambda _: {"codes": {"WELCOME": {"expires_at": 0, "exp": 99}},
                                                                 "meta": {"WELCOME": {"origin": "game", "by": "B owner"}}})
        self.cloud.game_saves(LIVE, "Eggs", lambda _: {"eggs": [game_egg("g1", name="B egg")], "next_id": 2})
        await cloud_sync.push_codes(force=False)
        await self.live.push_live("eggs")
        codes = self.cloud.value(CODES, "ActiveCodes")["codes"]
        self.assertEqual(codes["WELCOME"]["exp"], 99, "B's own code stays as B made it")
        self.assertEqual(codes["KEEP"]["exp"], 7, "a running code from Discord goes to B")
        self.assertEqual([e["name"] for e in self.eggs()], ["B egg"], "A's egg never goes to B")
        self.assertEqual(sorted(r["name"] for r in await database.get_active_eggs()), ["B egg"])

    async def test_an_egg_sent_back_keeps_the_games_counter_above_its_id(self):
        self.cloud.game_saves(LIVE, "Eggs", lambda _: {"eggs": [game_egg("g4")]})  # remade without next_id
        await self.live.push_live("eggs")
        row = (await database.get_active_eggs())[0]
        await database.update_egg(row["id"], price=11)
        await self.live.push_live("eggs")
        self.assertEqual(self.cloud.value(LIVE, "Eggs")["next_id"], 5, "the game's next egg can't get g4 again")

    async def test_an_id_the_bot_gave_comes_back_as_the_same_row_after_the_database_was_lost(self):
        self.cloud.game_saves(LIVE, "Eggs", lambda _: {"eggs": [game_egg(12, origin="discord", by="")]})
        await self.live.push_live("eggs")
        row = await database.get_egg(12)
        self.assertIsNotNone(row, "the same id")
        self.assertIsNone(row["uid"])
        egg_id = await database.add_egg("New", "Coins", 10, json.dumps([{"name": "Cat", "chance": 100}]), "", "", "", 0, 5)
        self.assertGreater(egg_id, 12, "a new egg never gets an id the game already has")

    async def test_old_entries_without_versions_or_meta_work(self):
        self.cloud.game_saves(CODES, "ActiveCodes", lambda _: {"version": 1, "codes": {"OLD": {"expires_at": 0, "currency": {"name": "Coins", "amount": 5}}}})
        await cloud_sync.push_codes(force=False)
        row = await database.get_game_code("OLD")
        self.assertEqual((row["origin"], row["reward_currency"], row["currency_amount"]), ("discord", "Coins", 5))
        self.assertEqual(len(self.cloud.writes), 0, "nothing to send: the entry is left as it is")

    async def test_the_game_removing_its_last_code_is_not_a_missing_entry(self):
        """Roblox saves an empty Lua table as [], so the game's last code removed leaves "codes": []."""
        await database.add_game_code("LAST", None, 0, 10, None, "permanent", 0, 0, 0, 5)
        await cloud_sync.push_codes(force=False)
        self.cloud.game_saves(CODES, "ActiveCodes", lambda v: dict(v, codes=[], meta=[]))
        result = await cloud_sync.push_codes(force=False)
        self.assertTrue(result.ok, result.message)
        self.assertEqual(await database.get_active_game_codes(), [], "removed in the game, not sent back")
        self.assertEqual(self.cloud.value(CODES, "ActiveCodes")["codes"], [])

    async def test_force_tells_the_servers_even_without_a_change(self):
        result = await cloud_sync.push_codes(force=True)
        self.assertTrue(result.ok, result.message)
        self.assertEqual([topic for topic, _ in self.cloud.published], ["DiscordCodes"])

    async def test_an_events_animation_goes_both_ways(self):
        now = int(time.time())
        await database.add_live_event("Storm", json.dumps({"currency:*": 2}), now, now + 600, 5, "coin_storm")
        await self.live.push_live("events")
        self.assertEqual(self.cloud.value(LIVE, "Events")["events"][0]["animation"], "coin_storm")
        self.cloud.game_saves(LIVE, "Events", lambda v: dict(v, events=v["events"] + [
            {"id": "g1", "name": "From the game", "ends_at": now + 300, "multipliers": {"exp": 2}, "animation": "coin_storm",
             "origin": "game", "by": "Builder"}]))
        await self.live.push_live("events")
        imported = [r for r in await database.get_active_live_events() if r["uid"] == "g1"][0]
        self.assertEqual(imported["animation"], "coin_storm")
        self.assertEqual(len(self.cloud.writes), 1, "nothing to send back")

    async def test_the_durations_match_the_codes_command(self):
        from cogs.game_codes import ITEM_DURATIONS
        self.assertEqual(game_sync.ITEM_DURATION_LABELS,
                         {seconds: key for key, (seconds, temporary) in ITEM_DURATIONS.items() if temporary})

    async def test_odd_values_from_the_game_are_cleaned(self):
        self.cloud.game_saves(LIVE, "Eggs", lambda _: {"eggs": [game_egg("g1", price="lots", pets=[{"name": 5}, "x"], name=None),
                                                                 "not an egg", {"no": "id"}]})
        self.cloud.game_saves(LIVE, "Events", lambda _: {"events": [{"id": "g2", "name": "E", "ends_at": int(time.time()) + 60,
                                                                     "multipliers": {"exp": "2", "luck": 3, "bad": True}}]})
        await self.live.push_live("eggs")
        await self.live.push_live("events")
        egg = (await database.get_active_eggs())[0]
        self.assertEqual((egg["name"], egg["price"], json.loads(egg["pets"])), ("?", 1, []))
        event = (await database.get_active_live_events())[0]
        self.assertEqual(json.loads(event["multipliers"]), {"luck": 3.0})


if __name__ == "__main__":
    unittest.main()
