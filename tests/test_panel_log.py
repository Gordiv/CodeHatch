"""The bot reads the log of the game's ⚙️ Manager (cogs/game_requests.py check_panel_log): every change made in the game
(also while the bot was off) is written to the Discord log channel once, the codes, events and eggs it made are copied
into the database at once, and a gift is kept for the player card. A bot that lost its own file never writes a change
twice: the game keeps the number of the last change read (PanelLogRead). The game's side: tests/test_kit_panel_changes.py."""
import json
import time
import unittest
from contextlib import ExitStack
from unittest import mock

from tests.game_cloud import CODES, LIVE, FakeCloud
from tests.helpers import TempBot
from tests.test_game_requests import FakeBot
from utils import config_store, database


def change(seq: int, kind: str, **data) -> dict:
    return {"seq": seq, "at": int(time.time()), "by": 42, "name": "Builder", "kind": kind, "data": data}


class PanelLog(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import game_requests, roblox_admin
        self.module = game_requests
        self.cloud = FakeCloud()
        self.posted = []

        async def log_action(guild, text):
            self.posted.append(text)

        self.stack = ExitStack()
        for patch in self.cloud.patches() + [mock.patch.object(roblox_admin, "log_action", log_action)]:
            self.stack.enter_context(patch)
        self.bot = FakeBot()
        self.bot.guilds = ["one server"]
        self.cog = game_requests.GameRequests(self.bot)

    async def asyncTearDown(self):
        self.cog.cog_unload()
        self.stack.close()
        await database.close_db()
        self.temp.__exit__(None, None, None)

    def game_log(self, *changes, next_seq=None):
        last = max((c["seq"] for c in changes if isinstance(c, dict) and isinstance(c.get("seq"), int)), default=0)
        self.cloud.game_saves(LIVE, "PanelLog", lambda _: {"next": next_seq or last + 1, "entries": list(changes)})

    def text(self) -> str:
        return "\n".join(self.posted)

    async def test_each_change_is_written_once_and_what_it_made_is_copied(self):
        reward = {"expires_at": 0, "currency": {"name": "Coins", "amount": 500}}
        self.cloud.game_saves(CODES, "ActiveCodes", lambda _: {"codes": {"PANEL": reward},
                                                                 "meta": {"PANEL": {"origin": "game", "by": "Builder"}}})
        self.game_log(change(1, "code_add", code="PANEL", reward=reward),
                      change(2, "announce", text="Double coins!", seconds=10),
                      change(3, "ban", user_id=77, username="Cheater", seconds=0, reason="Exploiting"))
        self.assertEqual(await self.cog.check_panel_log(), 3)
        text = self.text()
        for part in ("Builder", "`PANEL`", "500", "Double coins!", "Cheater", "Exploiting"):
            self.assertIn(part, text)
        self.assertEqual(len(self.posted), 1, "a burst of changes is one message, not one per line")
        row = await database.get_game_code("PANEL")
        self.assertEqual((row["origin"], row["author"], row["is_active"]), ("game", "Builder", 1),
                         "copied into the database at once (Discord lists it)")
        self.assertEqual(self.cloud.value(LIVE, "PanelLogRead")["seen"], 3, "the game keeps what was read")
        self.assertEqual(config_store.read_json(self.module.PANEL_STATE_FILE, {})["seen"], 3)
        self.assertEqual(await self.cog.check_panel_log(), 0)
        self.assertEqual(len(self.posted), 1, "never written twice")

    async def test_a_bot_that_lost_its_file_goes_on_from_the_game(self):
        self.game_log(change(1, "announce", text="one", seconds=5), change(2, "announce", text="two", seconds=5),
                      change(3, "announce", text="three", seconds=5))
        self.cloud.game_saves(LIVE, "PanelLogRead", lambda _: {"seen": 2})
        self.assertEqual(await self.cog.check_panel_log(), 1)
        self.assertNotIn("two", self.text())
        self.assertIn("three", self.text())

    async def test_the_first_read_ever_writes_only_the_newest_ten(self):
        self.game_log(*[change(n, "announce", text=f"news {n:02d}", seconds=5) for n in range(1, 16)])
        self.assertEqual(await self.cog.check_panel_log(), 10)
        self.assertNotIn("news 05", self.text())
        self.assertIn("news 06", self.text())
        self.assertIn(self.module.t("panellog.skipped", count=5), self.text())

    async def test_a_cleared_log_starts_again(self):
        config_store.write_json(self.module.PANEL_STATE_FILE, {"universe": 123, "seen": 50})
        self.game_log(change(1, "announce", text="after clearing", seconds=5))
        self.assertEqual(await self.cog.check_panel_log(), 1)
        self.assertIn("after clearing", self.text())

    async def test_a_gift_is_kept_for_the_player_card_once(self):
        gift = change(1, "gift", user_id=77, username="Winner", reward={"exp": 100}, message="GG", key="gift_77_1700000000abcd")
        self.game_log(gift)
        await self.cog.check_panel_log()
        rows = await database.get_recent_gifts(77)
        self.assertEqual([(r["gift_key"], r["author"], r["created_by"], json.loads(r["reward"])) for r in rows],
                         [("gift_77_1700000000abcd", "Builder", 0, {"exp": 100})])
        self.assertIn("Winner", self.text())
        self.assertIn("GG", self.text())
        config_store.write_json(self.module.PANEL_STATE_FILE, {})
        self.cloud.entries.pop((LIVE, "PanelLogRead"))
        await self.cog.check_panel_log()  # read again from the start: the gift is not kept twice
        self.assertEqual(len(await database.get_recent_gifts(77)), 1)

    async def test_events_and_eggs_made_in_the_game_are_copied_at_once(self):
        ends = int(time.time()) + 600
        self.cloud.game_saves(LIVE, "Events", lambda _: {"events": [{"id": "g1", "name": "Boost", "ends_at": ends,
                                                                     "multipliers": {"exp": 2}, "origin": "game", "by": "Builder"}]})
        self.cloud.game_saves(LIVE, "Eggs", lambda _: {"eggs": [{"id": "g2", "name": "Lava", "currency": "Coins", "price": 50,
                                                                 "pets": [{"name": "Dog", "chance": 100}], "ends_at": 0,
                                                                 "origin": "game", "by": "Builder"}]})
        self.game_log(change(1, "event_start", id="g1", name="Boost", multipliers={"exp": 2}, ends_at=ends),
                      change(2, "egg_create", id="g2", name="Lava", currency="Coins", price=50,
                             pets=[{"name": "Dog", "chance": 100}], spot=""))
        await self.cog.check_panel_log()
        self.assertEqual([r["uid"] for r in await database.get_active_live_events()], ["g1"])
        self.assertEqual([r["uid"] for r in await database.get_active_eggs()], ["g2"])
        self.assertIn("Dog 100%", self.text())

    async def test_odd_entries_never_stop_the_reading(self):
        self.game_log(change(1, "announce", text="fine", seconds=5),
                      {"seq": "2", "kind": "announce"}, {"kind": "gift"}, "text", {"seq": 3, "kind": "unknown_kind", "data": []},
                      change(4, "egg_create", name="Odd", price="lots", pets="Dog", currency=None),
                      change(5, "gift", user_id="x", reward="nothing", key=5),
                      next_seq=6)
        self.assertEqual(await self.cog.check_panel_log(), 4)
        self.assertIn("fine", self.text())
        self.assertIn("unknown_kind", self.text())
        self.assertEqual(await database.get_recent_gifts(0), [])

    def test_every_kind_is_described(self):
        details = self.module.panel_details
        future = int(time.time()) + 3600
        cases = {
            "code_add": ({"code": "A1", "reward": {"exp": 5, "expires_at": future}}, ["`A1`", "+5", "EXP", f"<t:{future}:R>"]),
            "code_remove": ({"code": "A1"}, ["`A1`"]),
            "event_start": ({"name": "Party", "multipliers": {"currency:*": 2}, "ends_at": future}, ["**Party**", "2×", f"<t:{future}:R>"]),
            "event_stop": ({"name": "Party"}, ["**Party**"]),
            "egg_create": ({"name": "Lava", "currency": "Coins", "price": 1500, "pets": [{"name": "Dog", "chance": 60},
                                                                                     {"name": "Cat", "chance": 40}], "spot": "Spawn"},
                           ["**Lava**", "1,500 Coins", "Dog 60%", "Cat 40%", "Spawn"]),
            "egg_move": ({"name": "Lava", "spot": ""}, ["**Lava**", self.module.t("panellog.any_spot")]),
            "egg_remove": ({"name": "Lava"}, ["**Lava**"]),
            "announce": ({"text": "Hi *all*", "seconds": 15}, ["Hi \\*all\\*", "15"]),
            "ban": ({"user_id": 7, "username": "Bad_Guy", "seconds": 3600, "reason": "x"}, ["Bad\\_Guy", "`7`", "<t:"]),
            "unban": ({"user_id": 7, "username": "Bad_Guy"}, ["Bad\\_Guy"]),
        }
        for kind, (data, parts) in cases.items():
            text = details({"kind": kind, "data": data, "at": int(time.time())})
            for part in parts:
                self.assertIn(part, text, kind)
        permanent = details({"kind": "ban", "data": {"user_id": 7, "username": "B", "seconds": 0, "reason": "r"}})
        self.assertIn(self.module.t("rban.permanent"), permanent)
        mention = details({"kind": "announce", "data": {"text": "@everyone come", "seconds": 5}})
        self.assertNotIn("@everyone", mention.replace("@​everyone", ""), "never a mention")

    def test_long_bursts_are_split_into_messages(self):
        lines = [f"line {n} " + "x" * 300 for n in range(20)]
        messages = self.module.chunks(lines)
        self.assertTrue(all(len(m) <= 1800 for m in messages))
        self.assertEqual("\n".join(messages).count("line "), 20)


if __name__ == "__main__":
    unittest.main()
