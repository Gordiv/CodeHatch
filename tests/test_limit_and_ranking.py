"""The game's currency limit (Settings -> MaxCurrencyPerCode, reported since file version 15) gives a warning for codes
and gifts above it, also when the game uses Core.OnReward. The leaderboard turns keys made only of digits (also "1")
into usernames, in /leaderboard and in the sample shown when it is connected."""
import time
import unittest
from unittest import mock

from tests.fakes import Interaction, check_embed
from tests.helpers import TempBot
from utils import cloud_sync, config_store, i18n, open_cloud, roblox_api, roblox_kit

LANGS = ("en", "pl", "es")


def report(limit=None, at=None, **fields) -> dict:
    now = int(time.time()) if at is None else at
    entry = {"at": now, "saved": now, "values": ["leaderstats.Gems:IntValue"], "attributes": [], "spots": [],
             "templates": [], "multipliers": [], "hooks": [], "players": 1}
    if limit is not None:
        entry["maxCurrency"] = limit
    entry.update(fields)
    return entry


def scan_of(places: dict) -> dict:
    with mock.patch.object(cloud_sync, "status", return_value="ready"), \
            mock.patch.object(cloud_sync, "universe_id", return_value=1):
        return roblox_kit.game_scan({"universe": 1, "scan": places})


GEMS_5000 = {"currency": {"name": "Gems", "amount": 5000}}


class CurrencyLimit(unittest.TestCase):
    def test_the_scan_has_the_lowest_limit_of_the_places(self):
        self.assertEqual(scan_of({"1": {"live": report(1000)}, "2": {"studio": report(500)}, "3": {"live": report(0)}})
                         ["max_currency"], 500)
        self.assertEqual(scan_of({"1": {"live": report()}})["max_currency"], 0, "a file older than 15 says nothing")
        for odd in ("x", None, float("inf"), -5, 1e30):
            self.assertEqual(scan_of({"1": {"live": report(odd)}})["max_currency"], 0, repr(odd))

    def test_the_published_game_and_studio_both_count(self):
        now = int(time.time())
        place = {"live": report(1000, at=now - 500), "studio": report(0, at=now)}
        self.assertEqual(scan_of({"1": place})["max_currency"], 1000, "a newer Studio test without a limit: the game still has it")
        place = {"live": report(0, at=now - 500), "studio": report(700, at=now - 900)}
        self.assertEqual(scan_of({"1": place})["max_currency"], 700, "a gift tried in Studio fails there too")
        place = {"live": report(1000, at=now - 31 * 86400)}
        self.assertEqual(scan_of({"1": place, "2": {"live": report()}})["max_currency"], 0, "a report older than 30 days")

    def test_an_amount_above_the_limit_is_warned_about(self):
        scan = scan_of({"1": {"live": report(1000)}})
        with TempBot():
            warnings = roblox_kit.reward_warnings(scan, GEMS_5000)
            self.assertEqual(warnings, [i18n.t("scan.warn_reward_limit", amount="5,000", currency="Gems", limit="1,000")])
            self.assertEqual(roblox_kit.reward_warnings(scan, {"currency": {"name": "Gems", "amount": 1000}}), [],
                             "exactly the limit is fine")
            hooked = scan_of({"1": {"live": report(1000, hooks=["OnReward"])}})
            self.assertEqual(len(roblox_kit.reward_warnings(hooked, GEMS_5000)), 1, "the limit applies before OnReward")
            self.assertEqual(roblox_kit.reward_warnings(scan_of({"1": {"live": report()}}), GEMS_5000), [])
            for lang in LANGS:
                text = i18n.t("scan.warn_reward_limit", lang=lang, amount="5,000", currency="Gems", limit="1,000")
                self.assertIn("1,000", text)
                self.assertIn("MaxCurrencyPerCode", text)

    def test_the_gift_and_code_drafts_show_the_warning(self):
        from cogs import game_codes, setup_roblox
        scan = scan_of({"1": {"live": report(1000)}})
        with TempBot(), mock.patch.object(roblox_kit, "game_scan", return_value=scan):
            expected = "⚠️ " + i18n.t("scan.warn_reward_limit", amount="5,000", currency="Gems", limit="1,000")
            gift = setup_roblox.gift_draft_embed({"user": (1, "Roblox"), "currency": "Gems", "amount": 5000, "exp": 0,
                                                  "item": "none", "item_key": "permanent", "message": ""})
            check_embed(gift)
            self.assertIn(expected, "\n".join(f.value for f in gift.fields))
            code = game_codes.draft_embed(game_codes.code_params("BIG", "7d", "Gems", 5000, allow_empty=True))
            check_embed(code)
            self.assertIn(expected, "\n".join(f.value for f in code.fields))



class LimitRefusals(unittest.IsolatedAsyncioTestCase):
    """Above the limit: /give, /code-add and ✅ in both drafts refuse privately and nothing is saved or sent; the drafts
    themselves still open and show the warning."""

    async def asyncSetUp(self):
        from utils import database
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        config_store.write_json("game_economy.json", {"configured": True, "currencies": ["Gems"], "items": []})
        self.write = mock.AsyncMock()
        self.patches = [mock.patch.object(roblox_kit, "game_scan", return_value=scan_of({"1": {"live": report(1000)}})),
                        mock.patch.object(open_cloud, "write_entry", self.write),
                        mock.patch.object(open_cloud, "publish", mock.AsyncMock()),
                        mock.patch.object(open_cloud, "live_settings", return_value={"gifts": "Gifts"}),
                        mock.patch.object(roblox_api, "find_users", mock.AsyncMock(return_value=[(1, "Roblox", "id")])),
                        mock.patch.object(roblox_api, "resolve_user", mock.AsyncMock(return_value=None))]
        for patch in self.patches:
            patch.start()
        self.refusal = i18n.t("scan.err_reward_limit", amount="5,000", currency="Gems", limit="1,000")

    async def asyncTearDown(self):
        from utils import database
        for patch in self.patches:
            patch.stop()
        await database.close_db()
        self.temp.__exit__(None, None, None)

    def draft(self, amount):
        return {"user": (1, "Roblox"), "currency": "Gems", "amount": amount, "exp": 0, "item": "none",
                "item_key": "permanent", "message": ""}

    async def test_the_text_says_the_limit_and_where_to_change_it(self):
        for lang in LANGS:
            text = i18n.t("scan.err_reward_limit", lang=lang, amount="5,000", currency="Gems", limit="1,000")
            self.assertTrue(text.startswith("❌"), lang)
            for part in ("1,000", "5,000", "Gems", "MaxCurrencyPerCode"):
                self.assertIn(part, text, lang)
            self.assertLessEqual(len(text), 2000, lang)

    async def test_give_refuses_privately(self):
        from cogs import live_game
        cog = live_game.LiveGame.__new__(live_game.LiveGame)
        inter = Interaction()
        await live_game.LiveGame.give.callback(cog, inter, "1", currency="Gems", amount=5000)
        self.assertEqual(inter.response.sent[-1][0], self.refusal)
        self.assertTrue(inter.response.sent[-1][1].get("ephemeral"))
        self.write.assert_not_called()
        inter = Interaction()
        await live_game.LiveGame.give.callback(cog, inter, "1", currency="Gems", amount=1000)
        self.write.assert_awaited_once()
        with self.assertRaises(live_game.RuleError):  # every other way to send a gift too
            await live_game.send_gift((1, "Roblox"), {"currency": {"name": "Gems", "amount": 5000}}, "", "A", 7)
        self.write.assert_awaited_once()

    async def test_the_gift_draft_warns_and_send_refuses(self):
        from cogs import setup_roblox
        embed = setup_roblox.gift_draft_embed(self.draft(5000))
        self.assertIn(i18n.t("scan.warn_reward_limit", amount="5,000", currency="Gems", limit="1,000"),
                      " ".join(f.value for f in embed.fields))
        view = setup_roblox.GiftDraftView(7, self.draft(5000))
        inter = Interaction()
        await view.confirm.callback(inter)
        self.assertEqual(inter.response.sent[-1][0], self.refusal)
        self.assertFalse(view.closed or view.is_finished(), "the draft stays open")
        self.write.assert_not_called()

    async def test_code_add_and_the_code_draft_refuse(self):
        from discord import app_commands
        from cogs import game_codes
        with self.assertRaises(game_codes.CodeError) as caught:
            game_codes.code_params("BIG", "7d", "Gems", 5000)
        self.assertEqual(str(caught.exception), self.refusal)
        game_codes.code_params("OK", "7d", "Gems", 1000)
        cog = game_codes.GameCodes.__new__(game_codes.GameCodes)
        inter = Interaction()
        await game_codes.GameCodes.code_add.callback(cog, inter, "BIG", app_commands.Choice(name="7d", value="7d"),
                                                      "Gems", 5000)
        self.assertEqual(inter.response.sent[-1][0], self.refusal)
        self.assertTrue(inter.response.sent[-1][1].get("ephemeral"))
        draft = game_codes.CodeDraftView(cog, 7, game_codes.code_params("BIG", "7d", "Gems", 5000, allow_empty=True))
        inter = Interaction()
        await draft.save.callback(inter)
        self.assertEqual(inter.response.sent[-1][0], self.refusal)
        self.assertFalse(draft.closed)
        from utils import database
        self.assertIsNone(await database.get_game_code("BIG"))

class Ranking(unittest.IsolatedAsyncioTestCase):
    def test_keys_of_digits_are_user_ids_whatever_their_length(self):
        from cogs.roblox_admin import entry_user_id
        cases = {"1": 1, "2": 2, "156": 156, " 42 ": 42, "7000000001": 7000000001, "Player_12345": 12345,
                 "Slot_2": None, "0": None, "": None, None: None, "9" * 25: None, "abc": None,
                 "9" * 19: None, "Player_" + "9" * 19: None, str(2 ** 63 - 1): 2 ** 63 - 1, "٣٤٥": None}
        for key, expected in cases.items():
            self.assertEqual(entry_user_id(key), expected, repr(key))

    async def test_the_sample_after_connecting_shows_usernames(self):
        from cogs import roblox_admin
        entries = [("1", 50000), ("156", 42000), ("Slot_2", 10)]
        names = mock.AsyncMock(return_value={1: "Roblox", 156: "builder_man"})
        bot = mock.Mock(get_cog=mock.Mock(return_value=None))
        with TempBot(), mock.patch.object(open_cloud, "top_entries", mock.AsyncMock(return_value=entries)), \
                mock.patch.object(roblox_api, "usernames", names):
            text = await roblox_admin.connect_leaderboard(bot, "PlayerCoins", "Coins", "global")
            self.assertEqual(config_store.load()["leaderboard"]["datastore"], "PlayerCoins")
        self.assertIn("Roblox = 50,000", text)
        self.assertIn("builder\\_man = 42,000", text, "a name is escaped for Discord")
        self.assertIn("Slot_2 = 10", text.replace("\\_", "_"), "a key that isn't an account stays as it is")
        self.assertEqual(sorted(names.await_args.args[0]), [1, 156])

    async def test_without_names_from_roblox_the_keys_stay(self):
        from cogs import roblox_admin
        with mock.patch.object(roblox_api, "usernames", mock.AsyncMock(return_value={})):
            self.assertEqual(await roblox_admin.with_names([("1", 5)]), [("1", 5)])
