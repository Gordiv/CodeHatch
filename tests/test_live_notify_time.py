"""The bot's notification about events and eggs carries the time it saved them ("at", the same number as updated_at
in the saved data). The game compares the two and reads again when Roblox still serves an older copy (two changes a
moment apart: an event, then ⏹️ right after it). The game side: tests/test_kit_server_scripts.py FreshReadsAfterANotification."""
import json
import time
import unittest
from contextlib import ExitStack

from tests.game_cloud import LIVE, FakeCloud
from tests.helpers import TempBot
from utils import database


class NotificationCarriesTheSaveTime(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import live_game
        self.live = live_game

    async def asyncTearDown(self):
        await database.close_db()
        self.temp.__exit__(None, None, None)

    async def test_events_and_eggs(self):
        cloud = FakeCloud()
        now = int(time.time())
        await database.add_live_event("Double", json.dumps({"exp": 2}), now, now + 600, 1)
        await database.add_egg("Basic", "Coins", 10, json.dumps([{"name": "Cat", "chance": 100}]), "", "", "", 0, 1)
        before = int(time.time())
        with ExitStack() as stack:
            for patch in cloud.patches():
                stack.enter_context(patch)
            for kind in ("events", "eggs"):
                ok, error = await self.live.push_live(kind)
                self.assertTrue(ok, error)
        self.assertEqual([m["type"] for _, m in cloud.published], ["events", "eggs"])
        for (_, message), key in zip(cloud.published, ("Events", "Eggs")):
            self.assertEqual(message["at"], cloud.value(LIVE, key)["updated_at"], f"{key}: the game compares these two numbers")
            self.assertGreaterEqual(message["at"], before)

    async def test_the_save_time_never_goes_back(self):
        """The game's clock may be ahead of the PC's: a save after the game's never gets an older updated_at."""
        cloud = FakeCloud()
        ahead = time.time() + 120
        cloud.game_saves(LIVE, "Events", lambda _: {"events": [], "updated_at": ahead})
        now = int(time.time())
        await database.add_live_event("Double", json.dumps({"exp": 2}), now, now + 600, 1)
        with ExitStack() as stack:
            for patch in cloud.patches():
                stack.enter_context(patch)
            await self.live.push_live("events")
        self.assertGreater(cloud.value(LIVE, "Events")["updated_at"], ahead)


if __name__ == "__main__":
    unittest.main()
