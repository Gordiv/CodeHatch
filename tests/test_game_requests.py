"""Requests from the game's ⚙️ Manager (cogs/game_requests.py): the bot reads them from the game's DataStore, does each
new one once with the same functions as Discord (so the same checks), answers through ManagerResults and
MessagingService, and never does a request that waited from before the bot knew the game or longer than 10 minutes."""
import time
import unittest
from unittest import mock

from tests.helpers import TempBot
from utils import catalog, cloud_sync, config_store, database, i18n, open_cloud, roblox_api

OWNER_ID = 1
CATALOG = {"currencies": ["Coins"], "items": ["VIP"], "multipliers": [], "robux": [],
           "pets": [{"name": "Cat", "rarity": ""}, {"name": "Dog", "rarity": ""}], "eggs": [], "problems": [],
           "at": int(time.time()), "studio": False, "missing": False, "template": False}


class FakeBot:
    def __init__(self):
        self.guilds = []
        self.cogs = {}

    def get_cog(self, name):
        return self.cogs.get(name)

    async def wait_until_ready(self):  # the loops wait forever: the tests call check_requests themselves
        await __import__("asyncio").Event().wait()


class GameRequestsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import game_codes, game_requests, live_game
        self.module, self.live = game_requests, live_game
        self.bot = FakeBot()
        self.codes = game_codes.GameCodes(self.bot)
        self.bot.cogs["GameCodes"] = self.codes
        self.requests = []
        self.written, self.published = {}, []

        async def read_entry(datastore, key):
            return {"next": len(self.requests) + 1, "requests": list(self.requests)} if key == "ManagerRequests" else None

        async def write_entry(datastore, key, value):
            self.written[key] = value

        async def publish(message):
            self.published.append(message)

        self.ban = mock.AsyncMock(return_value={})
        self.patches = [mock.patch.object(open_cloud, "read_entry", read_entry),
                        mock.patch.object(open_cloud, "write_entry", write_entry),
                        mock.patch.object(open_cloud, "publish", publish),
                        mock.patch.object(open_cloud, "set_ban", self.ban),
                        mock.patch.object(open_cloud, "live_settings",
                                          return_value={"datastore": "Live", "gifts": "Gifts", "topic": "T"}),
                        mock.patch.object(cloud_sync, "universe_id", return_value=99),
                        mock.patch.object(catalog, "game_catalog", return_value=CATALOG),
                        mock.patch.object(live_game, "push_live", mock.AsyncMock(return_value=(True, ""))),
                        mock.patch.object(roblox_api, "find_users", mock.AsyncMock(return_value=[(77, "Cheater")]))]
        for patch in self.patches:
            patch.start()
        self.cog = game_requests.GameRequests(self.bot)

    async def asyncTearDown(self):
        self.cog.cog_unload()
        self.codes.cog_unload()
        for patch in self.patches:
            patch.stop()
        self.temp.__exit__(None, None, None)

    def add(self, kind, data, age=0):
        self.requests.append({"id": len(self.requests) + 1, "at": int(time.time()) - age, "by": OWNER_ID, "name": "Owner",
                              "kind": kind, "data": data})

    def results(self):
        return {r["id"]: r for r in self.published if r.get("type") == "manager_result"}

    async def test_new_requests_are_done_once_and_answered(self):
        await self.cog.check_requests()  # the bot learns the game: nothing waits yet
        self.add("code_add", {"code": "summer24", "currency": "coins", "amount": 100, "validity": "7d"})
        self.add("announce", {"text": "Double coins now!", "seconds": 10})
        self.assertEqual(await self.cog.check_requests(), 2)
        code = await database.get_game_code("SUMMER24")
        self.assertTrue(code and code["is_active"], "the code is saved like from Discord")
        self.assertEqual(code["reward_currency"], "Coins", "the catalog's spelling, as /code-add uses")
        self.assertTrue(all(r["ok"] for r in self.results().values()), self.results())
        self.assertIn({"type": "announce", "text": "Double coins now!", "seconds": 10}, self.published)
        self.assertEqual(self.written["ManagerResults"]["done"], 2)
        self.published.clear()
        self.assertEqual(await self.cog.check_requests(), 0, "a request is never done twice")
        self.assertEqual(self.published, [])

    async def test_what_waited_before_the_bot_knew_the_game_is_never_done(self):
        self.add("announce", {"text": "old"}, age=3600)
        self.assertEqual(await self.cog.check_requests(), 0)
        self.assertEqual(self.published, [])
        self.add("announce", {"text": "new"})
        self.assertEqual(await self.cog.check_requests(), 1, "a fresh one after it is done")

    async def test_a_request_that_waited_too_long_is_answered_not_done(self):
        await self.cog.check_requests()
        self.add("ban", {"player": "Cheater", "duration": "24h"}, age=self.module.REQUEST_MAX_AGE + 60)
        await self.cog.check_requests()
        self.ban.assert_not_awaited()
        self.assertFalse(self.results()[1]["ok"])
        self.assertEqual(self.results()[1]["text"], i18n.t("grequest.too_old"))

    async def test_the_same_checks_as_on_discord_refuse_bad_requests(self):
        await self.cog.check_requests()
        self.add("code_add", {"code": "BAD CODE", "currency": "Coins", "amount": 5})
        self.add("code_add", {"code": "X1", "currency": "Diamonds", "amount": 5})  # not in the game's catalog
        self.add("announce", {"text": "join https://example.com"})
        self.add("event_start", {"name": "Boost", "duration": "1h"})  # no multiplier
        self.add("ban", {"user_id": 77, "duration": "forever"})  # not one of the lengths
        self.add("nothing", {})
        await self.cog.check_requests()
        results = self.results()
        self.assertEqual(len(results), 6)
        self.assertFalse(any(r["ok"] for r in results.values()), results)
        self.assertIsNone(await database.get_game_code("X1"))
        self.assertEqual(results[6]["text"], i18n.t("grequest.unknown"))

    async def test_an_active_code_is_not_replaced(self):
        await self.cog.check_requests()
        self.add("code_add", {"code": "GIFT", "exp": 50})
        self.add("code_add", {"code": "GIFT", "exp": 999})
        await self.cog.check_requests()
        self.assertTrue(self.results()[1]["ok"])
        self.assertFalse(self.results()[2]["ok"])
        self.assertEqual((await database.get_game_code("GIFT"))["exp_amount"], 50)

    async def test_events_eggs_and_gifts(self):
        await self.cog.check_requests()
        self.add("event_start", {"name": "Weekend", "duration": "1h", "currency": "", "currency_x": "2"})
        self.add("egg_create", {"name": "Lava Egg", "currency": "Coins", "price": 100, "pets": "Cat:60, Dog:40", "spot": "Spot1"})
        self.add("gift", {"player": "Cheater", "currency": "Coins", "amount": 50, "message": "sorry", "item": "VIP",
                          "item_duration": "24h"})
        self.add("gift", {"player": "Cheater", "currency": "Coins", "amount": 2_000_000_000})  # above /give's limit
        await self.cog.check_requests()
        results = self.results()
        self.assertTrue(results[1]["ok"], results[1])
        self.assertEqual(len(await database.get_active_live_events()), 1)
        self.assertTrue(results[2]["ok"], results[2])
        self.assertEqual((await database.get_active_eggs())[0]["spot"], "Spot1")
        self.assertTrue(results[3]["ok"], results[3])
        self.assertFalse(results[4]["ok"], "the same limit as on Discord")
        self.assertTrue(all(len(r["text"]) <= self.module.MAX_TEXT for r in results.values()))

    async def test_a_ban_hits_only_the_account_the_owner_saw_and_never_the_owner(self):
        await self.cog.check_requests()
        self.add("find_player", {"player": "Cheater"})
        self.add("ban", {"player": "Cheater", "duration": "7d"})  # no account checked first: refused
        self.add("ban", {"user_id": 77, "duration": "7d", "reason": "Exploiting"})
        self.add("ban", {"user_id": OWNER_ID, "duration": "1h"})
        self.add("ban", {"user_id": 5, "duration": "1h"})  # the game's creator
        game = {"creator": {"id": 5, "type": "User"}}
        with mock.patch.object(roblox_api, "get_user", mock.AsyncMock(return_value={"name": "Someone"})),                 mock.patch.object(roblox_api, "get_game", mock.AsyncMock(return_value=game)):
            await self.cog.check_requests()
        results = self.results()
        self.assertEqual(results[1]["extra"], {"user_id": 77, "username": "Cheater"}, "the panel shows this account")
        self.assertFalse(results[2]["ok"])
        self.assertTrue(results[3]["ok"], results[3])
        self.assertEqual(self.ban.await_args_list[0].args[:3], (77, True, 7 * 86400))
        self.assertFalse(results[4]["ok"], "the owner can't ban themselves")
        self.assertFalse(results[5]["ok"], "nobody bans the game's creator")
        self.assertEqual(self.ban.await_count, 1)

    async def test_a_lost_state_file_never_does_a_request_twice(self):
        await self.cog.check_requests()
        self.add("announce", {"text": "once"})
        await self.cog.check_requests()
        config_store.write_json(self.module.STATE_FILE, {})  # the bot moved to another PC, or the file was deleted

        async def read_entry(datastore, key):
            if key == "ManagerResults":
                return self.written.get("ManagerResults")
            return {"next": len(self.requests) + 1, "requests": list(self.requests)}

        self.published.clear()
        with mock.patch.object(open_cloud, "read_entry", read_entry):
            self.assertEqual(await self.cog.check_requests(), 0)
        self.assertEqual(self.published, [], "done is kept in the game too")

    async def test_a_broken_entry_does_not_stop_the_reading(self):
        for broken in ("text", ["a"], {"requests": "x"}, {"requests": [{"id": "1"}, {"id": 2, "at": "now"}]}):
            with mock.patch.object(open_cloud, "read_entry", mock.AsyncMock(return_value=broken)):
                await self.cog.check_requests()

    def test_answers_are_plain_text(self):
        text = self.module.plain("**Done** `CODE` ends <t:0:R> for <@123>")
        self.assertEqual(text, "Done CODE ends 1970-01-01 00:00 UTC for")


if __name__ == "__main__":
    unittest.main()
