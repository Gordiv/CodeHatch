"""The gift form makes a draft: the exact account is shown first, ⚙️ adds EXP and the item's time, and nothing is written
to the game's DataStore before ✅ Send. /give also takes a Roblox user ID. The names panel marks an item the game has
only as <Name>_ExpiresAt as working for a time only.
Uses tests/fakes.py (strict answers, limits checked on every message)."""
import time
import unittest
from unittest import mock

from tests.fakes import Interaction, check_embed, check_modal, check_view
from tests.helpers import TempBot
from utils import config_store, database, i18n, open_cloud, roblox_api, roblox_kit

USER_ID, USERNAME = 7000000001, "BuilderBob"
LANGS = ("en", "pl", "es")


class GiftDraft(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import live_game, setup_roblox
        self.live, self.panel = live_game, setup_roblox
        config_store.write_json("game_economy.json", {"configured": True, "currencies": ["Coins"], "items": ["VIP"]})
        self.written = []  # (key, value) written to the gifts DataStore

        async def write_entry(datastore, key, value):
            self.written.append((key, value))

        async def publish(message):
            pass

        self.found = [(USER_ID, USERNAME, "id")]
        self.find = mock.AsyncMock(side_effect=lambda text: self.found)
        self.patches = [mock.patch.object(open_cloud, "write_entry", write_entry), mock.patch.object(open_cloud, "publish", publish),
                        mock.patch.object(open_cloud, "live_settings", return_value={"gifts": "Gifts"}),
                        mock.patch.object(roblox_api, "find_users", self.find),
                        mock.patch.object(roblox_api, "resolve_user", mock.AsyncMock(return_value=None))]
        for patch in self.patches:
            patch.start()

    async def asyncTearDown(self):
        for patch in self.patches:
            patch.stop()
        await database.close_db()
        self.temp.__exit__(None, None, None)

    def form(self, player=str(USER_ID), currency="none", amount="", item="VIP", message="see https://example.com", target=None):
        modal = self.panel.GiftModal(target=target)
        check_modal(modal)
        modal.player._value = player
        modal.currency._values = [currency]
        modal.amount._value = amount
        modal.item._values = [item]
        modal.message._value = message
        return modal

    async def draft_from(self, modal):
        inter = Interaction()
        await modal.on_submit(inter)
        self.assertTrue(inter.followup.sent, inter.messages())
        content, kwargs = inter.followup.sent[-1]
        self.assertIsInstance(kwargs.get("view"), self.panel.GiftDraftView, content)
        check_embed(kwargs["embed"])
        check_view(kwargs["view"])
        return kwargs["view"], kwargs["embed"]

    async def extras(self, draft, exp, duration=None):
        modal = self.panel.GiftExtrasModal(draft)
        check_modal(modal)
        modal.exp._value = exp
        if duration and modal.duration is not None:
            modal.duration._values = [duration]
        inter = Interaction()
        await modal.on_submit(inter)
        return inter

    async def test_a_message_with_a_link_is_warned_about_in_the_draft_and_the_gift_still_goes(self):
        """Roblox shows a whole message with a link as #### (published game, 2026-10-17): the draft and the "Gift sent"
        card say so; the reward is not stopped."""
        warning = self.live.t("give.link_warning")
        draft, embed = await self.draft_from(self.form(message="see https://example.com"))
        self.assertIn(warning, " ".join(f.value for f in embed.fields))
        inter = Interaction()
        await draft.confirm.callback(inter)
        self.assertTrue(self.written, "the gift is sent anyway")
        self.assertIn(warning, " ".join(f.value for f in inter.edited[-1]["embed"].fields), "the sent card says it too")
        _, plain = await self.draft_from(self.form(message="Thanks for playing!"))
        self.assertNotIn(warning, " ".join(f.value for f in plain.fields))

    async def test_the_draft_writes_nothing_before_send(self):
        draft, embed = await self.draft_from(self.form())
        self.assertEqual(self.written, [], "the form only makes a draft")
        self.assertEqual(draft.draft["user"], (USER_ID, USERNAME), "the exact account is found at once")
        self.assertIn(USERNAME, embed.description)
        self.assertIn(str(USER_ID), embed.description)
        self.assertEqual((draft.draft["exp"], draft.draft["item_key"]), (0, "permanent"), "the defaults")
        await self.extras(draft, "1000", "24h")
        self.assertEqual(self.written, [], "⚙️ changes only the draft")
        inter = Interaction()
        await draft.cancel.callback(inter)
        self.assertTrue(draft.closed and draft.is_finished())
        self.assertEqual(self.written, [], "Cancel sends nothing")
        self.assertEqual(await database.get_recent_gifts(USER_ID, 5), [])

    async def test_exp_and_item_time_reach_the_gift(self):
        draft, _ = await self.draft_from(self.form())
        inter = await self.extras(draft, "1 000", "24h")
        embed = inter.edited[-1]["embed"]
        check_embed(embed)
        self.assertIn("1,000", embed.fields[0].value)
        inter = Interaction()
        await draft.confirm.callback(inter)
        self.assertEqual(len(self.written), 1)
        key, value = self.written[0]
        self.assertTrue(key.startswith(f"gift_{USER_ID}_"))
        self.assertEqual(value["reward"]["exp"], 1000)
        self.assertEqual(value["reward"]["item"], {"name": "VIP", "is_temporary": True, "duration_seconds": 86400})
        self.assertEqual(value["message"], "see https://example.com", "the game's text filter handles the link")
        sent = inter.edited[-1]
        self.assertEqual(sent["embed"].title, i18n.t("give.title"), "the draft turns into the Gift sent card")
        self.assertNotIsInstance(sent["view"], self.panel.GiftDraftView)

    async def test_bad_exp_is_refused_and_the_draft_stays(self):
        draft, _ = await self.draft_from(self.form())
        for exp in ("abc", "-5", "²", "9" * 30):
            inter = await self.extras(draft, exp, "3d")
            self.assertTrue(inter.response.sent[-1][0].startswith("❌"), exp)
            self.assertEqual((draft.draft["exp"], draft.draft["item_key"]), (0, "permanent"), exp)

    async def test_double_send_sends_once(self):
        draft, _ = await self.draft_from(self.form(currency="Coins", amount="50", item="none"))
        first, second = Interaction(), Interaction()
        await draft.confirm.callback(first)
        await draft.confirm.callback(second)
        self.assertEqual(len(self.written), 1, "a double click sends the gift once")
        self.assertEqual(second.response.sent[-1][0], i18n.t("give.draft_closed"))
        inter = await self.extras(draft, "5")
        self.assertEqual(inter.response.sent[-1][0], i18n.t("give.draft_closed"), "⚙️ after sending changes nothing")
        self.assertEqual(len(self.written), 1)

    async def test_a_failed_save_brings_the_draft_back(self):
        draft, _ = await self.draft_from(self.form())
        with mock.patch.object(open_cloud, "write_entry", mock.AsyncMock(side_effect=open_cloud.OpenCloudError("busy"))):
            inter = Interaction()
            await draft.confirm.callback(inter)
        again = inter.edited[-1]["view"]
        self.assertIsInstance(again, self.panel.GiftDraftView, "nothing reached the game: ✅ can be tried again")
        self.assertTrue(inter.edited[-1]["content"].startswith("❌"))
        self.assertEqual(again.draft, draft.draft)
        await again.confirm.callback(Interaction())
        self.assertEqual(len(self.written), 1)

    async def test_a_failed_notice_still_counts_as_sent(self):
        draft, _ = await self.draft_from(self.form())
        with mock.patch.object(open_cloud, "publish", mock.AsyncMock(side_effect=open_cloud.OpenCloudError("429"))):
            inter = Interaction()
            await draft.confirm.callback(inter)
        self.assertEqual(len(self.written), 1)
        embed = inter.edited[-1]["embed"]
        self.assertEqual(embed.title, i18n.t("give.title"))
        self.assertIn("429", " ".join(f.value for f in embed.fields), "the admin is told not to send it again")
        self.assertNotIsInstance(inter.edited[-1]["view"], self.panel.GiftDraftView)
        self.assertEqual(len(await database.get_recent_gifts(USER_ID, 5)), 1, "written to the history too")

    async def test_an_empty_reward_is_refused_only_at_send(self):
        draft, embed = await self.draft_from(self.form(item="none"))
        self.assertEqual(embed.fields[0].value, i18n.t("give.draft_no_reward"))
        inter = Interaction()
        await draft.confirm.callback(inter)
        self.assertEqual(inter.response.sent[-1][0], i18n.t("give.no_reward"))
        self.assertFalse(draft.closed, "the draft stays: EXP can still be added")
        await self.extras(draft, "250")
        await draft.confirm.callback(Interaction())
        self.assertEqual(self.written[-1][1]["reward"], {"exp": 250})

    async def test_the_extras_form_hides_the_time_without_an_item(self):
        draft, _ = await self.draft_from(self.form(currency="Coins", amount="5", item="none"))
        self.assertIsNone(self.panel.GiftExtrasModal(draft).duration)
        draft, _ = await self.draft_from(self.form())
        self.assertIsNotNone(self.panel.GiftExtrasModal(draft).duration)

    async def test_a_gift_from_the_player_card_goes_to_the_card_account(self):
        draft, _ = await self.draft_from(self.form(player="Builderman", target=(4242, "Builderman")))
        self.find.assert_not_called()
        self.assertEqual(draft.draft["user"], (4242, "Builderman"))
        await draft.confirm.callback(Interaction())
        self.assertTrue(self.written[-1][0].startswith("gift_4242_"))
        self.find.assert_not_called()

    async def test_a_number_of_two_accounts_is_refused(self):
        self.found = [(1, "7000000001", "name"), (USER_ID, USERNAME, "id")]
        inter = Interaction()
        await self.form().on_submit(inter)
        self.assertTrue(inter.followup.sent[-1][0].startswith("❌"))
        self.assertNotIsInstance(inter.followup.sent[-1][1].get("view"), self.panel.GiftDraftView)
        self.assertEqual(self.written, [])

    async def test_only_the_admin_who_started_may_click(self):
        draft, _ = await self.draft_from(self.form())
        other = Interaction()
        other.user = type("Other", (), {"id": 99, "display_name": "Other"})()
        self.assertFalse(await draft.interaction_check(other))
        self.assertTrue(await draft.interaction_check(Interaction()))

    async def test_the_draft_fits_in_every_language(self):
        long = {"user": (10 ** 11, "N" * 20), "currency": "C" * 100, "amount": 10 ** 9, "exp": 10 ** 9, "item": "I" * 100,
                "item_key": "30d", "message": "M" * 150}
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                check_embed(self.panel.gift_draft_embed(long))
                draft = self.panel.GiftDraftView(7, long)
                check_view(draft)
                check_modal(self.panel.GiftExtrasModal(draft))


class GiveById(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import live_game
        self.live = live_game
        self.written = []

        async def write_entry(datastore, key, value):
            self.written.append((key, value))

        self.found = [(USER_ID, USERNAME, "id")]
        self.patches = [mock.patch.object(open_cloud, "write_entry", write_entry),
                        mock.patch.object(open_cloud, "publish", mock.AsyncMock()),
                        mock.patch.object(open_cloud, "live_settings", return_value={"gifts": "Gifts"}),
                        mock.patch.object(roblox_api, "find_users", mock.AsyncMock(side_effect=lambda text: self.found)),
                        mock.patch.object(roblox_api, "resolve_user", mock.AsyncMock(return_value=None))]
        for patch in self.patches:
            patch.start()
        self.cog = live_game.LiveGame.__new__(live_game.LiveGame)  # no loop: only the command is called

    async def asyncTearDown(self):
        for patch in self.patches:
            patch.stop()
        await database.close_db()
        self.temp.__exit__(None, None, None)

    async def give(self, player):
        inter = Interaction()
        await self.live.LiveGame.give.callback(self.cog, inter, player, exp=1000)
        return inter

    async def test_give_finds_the_account_by_id(self):
        inter = await self.give(str(USER_ID))
        self.assertTrue(self.written and self.written[-1][0].startswith(f"gift_{USER_ID}_"), inter.messages())
        self.assertEqual(self.written[-1][1]["reward"], {"exp": 1000})

    async def test_give_with_a_link_in_the_message_sends_and_warns(self):
        inter = Interaction()
        await self.live.LiveGame.give.callback(self.cog, inter, str(USER_ID), exp=10, message="join discord.gg/abc")
        self.assertTrue(self.written, "the reward still goes")
        fields = " ".join(f.value for f in inter.followup.sent[-1][1]["embed"].fields)
        self.assertIn(self.live.t("give.link_warning"), fields)

    async def test_give_refuses_a_number_of_two_accounts(self):
        self.found = [(1, "7000000001", "name"), (USER_ID, USERNAME, "id")]
        inter = await self.give(str(USER_ID))
        self.assertEqual(self.written, [])
        self.assertTrue(inter.followup.sent[-1][0].startswith("❌"))

    def test_the_player_option_says_id(self):
        for lang in LANGS:
            self.assertIn("ID", i18n.t("cmd.give.player", lang=lang), lang)


class TimedOnlyItem(unittest.TestCase):
    def test_an_item_with_only_expires_at_is_marked_timed_only(self):
        from cogs import setup_roblox
        scan = {"values": [("Data.Boost_ExpiresAt", "NumberValue"), ("Data.VIP", "BoolValue")], "attributes": [],
                "spots": [], "templates": [], "multipliers": [], "hooks": [], "at": int(time.time()), "studio": True,
                "players": 1}
        with TempBot():
            config_store.write_json("game_economy.json", {"configured": True, "currencies": [], "items": ["Boost", "VIP", "Sword"]})
            with mock.patch.object(roblox_kit, "game_scan", return_value=scan):
                view = setup_roblox.GameNamesView()
                embed = view.embed()
            check_embed(embed)
            field = next((f.value for f in embed.fields if f.name == i18n.t("rbx.names_in_bot")), "")
            timed = i18n.t("rbx.names_timed_only", name="Boost")
        self.assertIn("✅ " + timed, field, [f.name for f in embed.fields])
        self.assertIn("✅ VIP", field)
        self.assertIn("⚠️ Sword", field)
        warnings = roblox_kit.reward_warnings(scan, {"item": {"name": "Boost", "is_temporary": False, "duration_seconds": 0}})
        self.assertTrue(warnings, "a permanent Boost still gets a warning: only the timed one works")
        self.assertEqual(roblox_kit.reward_warnings(scan, {"item": {"name": "Boost", "is_temporary": True,
                                                                    "duration_seconds": 86400}}), [])
