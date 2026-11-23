"""Edge cases of the player card, find_users and send_gift: empty or strange input, Roblox and Open Cloud errors, the
buttons for every ban state, and Discord's limits with the longest names and reasons in all three languages.
Uses tests/fakes.py (strict answers, limits checked on every message)."""
import json
import time
import unittest
from unittest import mock

import discord

from tests.fakes import Admin, Interaction, check_embed, check_modal, check_view
from tests.helpers import TempBot
from utils import config_store, database, i18n, open_cloud, roblox_api
from utils.ui import CloseView

LANGS = ("en", "pl", "es")
USER_ID, USERNAME = 4242, "Builderman"
LONG = "L" * 5000


def iso(seconds_ago: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.123Z", time.gmtime(time.time() - seconds_ago))


class FindUsers(unittest.IsolatedAsyncioTestCase):
    def patches(self, names=None, ids=None, name_error=None, id_error=None):
        names, ids = names or {}, ids or {}
        self.name_calls, self.id_calls = [], []

        async def resolve(name, exclude_banned=False):
            self.name_calls.append(name)
            if name_error:
                raise name_error
            return names.get(name.lower())

        async def get_user(user_id):
            self.id_calls.append(user_id)
            if id_error:
                raise id_error
            return ids.get(user_id)

        return mock.patch.object(roblox_api, "resolve_user", resolve), mock.patch.object(roblox_api, "get_user", get_user)

    async def test_empty_and_only_at_signs_ask_nobody(self):
        a, b = self.patches()
        with a, b:
            for text in ("", "   ", "@", "@@", " @ ", None):
                self.assertEqual(await roblox_api.find_users(text), [], repr(text))
        self.assertEqual((self.name_calls, self.id_calls), ([], []), "no request for an empty name")

    async def test_unicode_digits_and_huge_numbers_never_crash(self):
        a, b = self.patches()
        with a, b:
            for text in ("٣٤٥", "²", "①", "１２３", "०१"):
                self.assertEqual(await roblox_api.find_users(text), [], repr(text))
            self.assertEqual(self.id_calls, [], "only ASCII digits are an ID")
            for text in ("9" * 20, "1" * 100, "9" * 5000, "0" * 25):
                self.assertEqual(await roblox_api.find_users(text), [], text[:10])
            self.assertEqual(self.id_calls, [], "20 digits or more can't be a user ID: not even asked")
            await roblox_api.find_users("9" * 19)
            await roblox_api.find_users("007")
            self.assertEqual(self.id_calls, [int("9" * 19), 7])

    async def test_name_and_id_pointing_at_one_account_is_one_result(self):
        a, b = self.patches({"123": (123, "123")}, {123: {"name": "123"}})
        with a, b:
            self.assertEqual(await roblox_api.find_users("123"), [(123, "123", "name")])

    async def test_errors_are_not_hidden(self):
        error = roblox_api.RobloxApiError("429")
        a, b = self.patches(name_error=error)
        with a, b, self.assertRaises(roblox_api.RobloxApiError):
            await roblox_api.find_users("Roblox")
        # the name was found, the ID check failed: never answer "just the name" (the ID might be another account)
        a, b = self.patches({"123": (777, "123")}, id_error=error)
        with a, b, self.assertRaises(roblox_api.RobloxApiError):
            await roblox_api.find_users("123")
        # a name that is not a number does not need the ID check at all
        a, b = self.patches({"roblox": (1, "Roblox")}, id_error=error)
        with a, b:
            self.assertEqual(await roblox_api.find_users("@Roblox"), [(1, "Roblox", "name")])

    async def test_at_sign_and_spaces_around_the_name(self):
        a, b = self.patches({"roblox": (1, "Roblox")})
        with a, b:
            for text in ("Roblox", "@Roblox", "  @Roblox  ", "@ Roblox", "@@Roblox"):
                self.assertEqual(await roblox_api.find_users(text), [(1, "Roblox", "name")], text)
            self.assertEqual(set(self.name_calls), {"Roblox"})


class SendGift(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import live_game
        self.live = live_game
        self.written = []

        async def write_entry(datastore, key, value):
            if self.cloud_fails:
                raise open_cloud.OpenCloudError("Roblox said no")
            self.written.append(key)

        async def publish(message):
            pass

        self.cloud_fails = False
        self.found = []
        self.find = mock.AsyncMock(side_effect=lambda text: self.found)
        self.resolve = mock.AsyncMock(return_value=(55, "Fiftyfive"))
        self.patches = [mock.patch.object(open_cloud, "write_entry", write_entry), mock.patch.object(open_cloud, "publish", publish),
                        mock.patch.object(open_cloud, "live_settings", return_value={"gifts": "Gifts"}),
                        mock.patch.object(roblox_api, "find_users", self.find), mock.patch.object(roblox_api, "resolve_user", self.resolve)]
        for patch in self.patches:
            patch.start()
        self.reward = {"currency": {"name": "Coins", "amount": 5}}

    async def asyncTearDown(self):
        for patch in self.patches:
            patch.stop()
        await database.close_db()
        self.temp.__exit__(None, None, None)

    async def gift(self, player, by_id=True, reward=None):
        return await self.live.send_gift(player, self.reward if reward is None else reward, "hi", "Admin", 7, by_id=by_id)

    async def test_empty_or_unknown_players_are_an_error_message(self):
        for text in ("", "   ", "@", "٣٤", "9" * 40):
            with self.assertRaises(self.live.RuleError, msg=repr(text)) as caught:
                await self.gift(text)
            self.assertTrue(str(caught.exception).startswith("❌"), text)
        self.assertEqual(self.written, [])

    async def test_a_name_with_markdown_cannot_break_the_message(self):
        with self.assertRaises(self.live.RuleError) as caught:
            await self.gift("**@everyone** _x_ `y`")
        self.assertLess(len(str(caught.exception)), 2000)
        self.assertNotIn("**@everyone**", str(caught.exception).replace("\\*", ""), "markdown is escaped")

    async def test_roblox_api_error_becomes_a_rule_error(self):
        self.find.side_effect = roblox_api.RobloxApiError("Roblox is busy")
        with self.assertRaises(self.live.RuleError) as caught:
            await self.gift("Someone")
        self.assertIn("Roblox is busy", str(caught.exception))
        self.resolve.side_effect = roblox_api.RobloxApiError("Roblox is busy 2")
        with self.assertRaises(self.live.RuleError) as caught:
            await self.gift("Someone", by_id=False)
        self.assertIn("busy 2", str(caught.exception))

    async def test_two_accounts_are_refused_one_account_is_used(self):
        self.found = [(1, "A", "name"), (2, "B", "id")]
        with self.assertRaises(self.live.RuleError):
            await self.gift("12345")
        self.assertEqual(self.written, [])
        self.found = [(2, "B", "id")]
        embed = await self.gift("12345")
        self.assertTrue(self.written[-1].startswith("gift_2_"))
        self.assertIn("B", embed.description)
        rows = await database.get_recent_gifts(2, 5)
        self.assertEqual([r["roblox_username"] for r in rows], ["B"])

    async def test_from_the_card_the_exact_account_is_used_without_asking_roblox(self):
        await self.gift((USER_ID, USERNAME), by_id=False)
        await self.gift((USER_ID, USERNAME), by_id=True)
        self.find.assert_not_called()
        self.resolve.assert_not_called()
        self.assertTrue(all(k.startswith(f"gift_{USER_ID}_") for k in self.written))
        self.assertEqual(len(self.written), 2)

    async def test_open_cloud_error_and_empty_reward(self):
        self.cloud_fails = True
        with self.assertRaises(self.live.RuleError) as caught:
            await self.gift((USER_ID, USERNAME))
        self.assertIn("Roblox said no", str(caught.exception))
        self.assertEqual(await database.get_recent_gifts(USER_ID, 5), [], "a failed gift is not written to the history")
        self.cloud_fails = False
        for reward in ({}, None):
            with self.assertRaises(self.live.RuleError):
                await self.live.send_gift((USER_ID, USERNAME), reward, "", "Admin", 7)

    async def test_the_gift_form_from_the_card(self):
        from cogs import setup_roblox
        config_store.write_json("game_economy.json", {"configured": True, "currencies": ["Coins"], "items": []})
        modal = setup_roblox.GiftModal(target=(USER_ID, USERNAME))
        check_modal(modal)
        self.assertEqual(modal.player.default, USERNAME)

        def fill(text, amount="50"):
            modal.player._value = text
            modal.currency._values = ["Coins"]
            modal.amount._value = amount
            modal.item._values = [setup_roblox.NONE]
            modal.message._value = " thanks "
            return Interaction()

        inter = fill(USERNAME)
        await modal.on_submit(inter)
        self.assertEqual(self.written, [], "the form only makes a draft")
        self.assertFalse(inter.followup.sent[-1][0] and inter.followup.sent[-1][0].startswith("❌"))
        await inter.followup.sent[-1][1]["view"].confirm.callback(Interaction())
        self.assertTrue(self.written[-1].startswith(f"gift_{USER_ID}_"), "the name on the card: the card's account")
        self.find.assert_not_called()

        self.found = [(99, "Other", "name")]
        inter = fill("Other")
        await modal.on_submit(inter)
        await inter.followup.sent[-1][1]["view"].confirm.callback(Interaction())
        self.assertTrue(self.written[-1].startswith("gift_99_"), "another player typed over the name")
        self.find.assert_awaited_once()

        for amount in ("0", "", "-3", "9" * 30):
            inter = fill(USERNAME, amount)
            before = len(self.written)
            await modal.on_submit(inter)
            self.assertEqual(len(self.written), before, amount)
            self.assertTrue(inter.response.sent and inter.response.sent[-1][0].startswith("❌"), amount)

    async def test_the_gift_amount_field_never_crashes_on_odd_digits(self):
        from cogs import setup_roblox
        config_store.write_json("game_economy.json", {"configured": True, "currencies": ["Coins"], "items": []})
        for amount in ("²", "①", "٣", "1²"):
            modal = setup_roblox.GiftModal(target=(USER_ID, USERNAME))
            modal.player._value = USERNAME
            modal.currency._values = ["Coins"]
            modal.amount._value = amount
            modal.item._values = [setup_roblox.NONE]
            inter = Interaction()
            try:
                await modal.on_submit(inter)
            except ValueError as e:
                self.fail(f"amount {amount!r}: the form raised {e!r} instead of answering")


class CardBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import roblox_admin, setup_roblox
        self.admin, self.panel = roblox_admin, setup_roblox
        self.ban, self.ban_error, self.unban_error = {}, None, None
        self.profile = {"name": USERNAME, "displayName": "Bob", "created": iso(3 * 86400)}
        self.get_ban_error = None
        self.set_ban_calls = []

        async def set_ban(user_id, active, seconds=0, display_reason="", private_reason=""):
            self.set_ban_calls.append((user_id, active, seconds, display_reason, private_reason))
            error = self.ban_error if active else self.unban_error
            if error:
                raise error
            self.ban = {"active": True, "displayReason": display_reason, "privateReason": private_reason,
                        "startTime": iso(0)[:19] + "Z", "duration": f"{seconds}s" if seconds else ""} if active else {}

        async def get_ban(user_id):
            if self.get_ban_error:
                raise self.get_ban_error
            return dict(self.ban)

        async def get_user(user_id):
            return self.profile

        async def avatar(user_id, size="352x352"):
            return "https://tr.rbxcdn.com/avatar.png"

        self.patches = [mock.patch.object(open_cloud, "set_ban", set_ban), mock.patch.object(open_cloud, "get_ban", get_ban),
                        mock.patch.object(roblox_api, "get_user", get_user), mock.patch.object(roblox_api, "avatar_url", avatar),
                        mock.patch.object(config_store, "guild_section", return_value={"log_channel_id": 500})]
        for patch in self.patches:
            patch.start()

    async def asyncTearDown(self):
        for patch in self.patches:
            patch.stop()
        await database.close_db()
        self.temp.__exit__(None, None, None)

    def ban_modal(self, card, duration="24h", reason="Exploiting", note=""):
        modal = self.admin.BanModal(card)
        if duration:
            modal.duration._values = [duration]
        modal.reason._value = reason
        modal.note._value = note
        return modal


class CardButtons(CardBase):
    async def test_buttons_for_every_ban_state(self):
        for banned in (True, False, None):
            view = self.admin.PlayerCardView(USER_ID, USERNAME, banned)
            shown = {name for name in ("ban", "unban", "gift") if getattr(view, name) in view.children}
            expected = {"gift"} | ({"unban"} if banned is True else {"ban"} if banned is False else {"ban", "unban"})
            self.assertEqual(shown, expected, banned)
            self.assertIn(view.refresh, view.children)
            self.assertIn(view.other, view.children)
            check_view(view)

    async def test_banned_state_from_roblox_answers(self):
        for ban, expected in (({}, False), ({"active": False}, False), ({"active": True, "duration": "60s"}, True),
                              ({"active": True}, True), ({"active": 1}, True), ({"active": None}, False)):
            self.ban = ban
            embed, banned = await self.admin.player_card(USER_ID, USERNAME)
            self.assertEqual(banned, expected, ban)
        self.get_ban_error = open_cloud.OpenCloudError("no permission")
        embed, banned = await self.admin.player_card(USER_ID, USERNAME)
        self.assertIsNone(banned)

    async def test_buttons_of_the_card_are_for_admins_only(self):
        view = self.admin.PlayerCardView(USER_ID, USERNAME, False)
        stranger = Interaction()
        stranger.user = type("Member", (), {"id": 5, "guild_permissions": discord.Permissions(send_messages=True)})()
        self.assertFalse(await view.interaction_check(stranger))
        self.assertTrue(stranger.response.sent[-1][1]["ephemeral"])
        self.assertTrue(await view.interaction_check(Interaction()))


class CardActions(CardBase):
    async def test_ban_modal_without_time_without_reason_and_with_both(self):
        card = self.admin.PlayerCardView(USER_ID, USERNAME, False)
        for duration, reason in ((None, "Reason"), ("24h", ""), ("24h", "   \n "), (None, "")):
            inter = Interaction()
            await self.ban_modal(card, duration, reason).on_submit(inter)
            self.assertTrue(inter.response.sent and inter.response.sent[-1][0].startswith("❌"), (duration, reason))
            self.assertTrue(inter.response.sent[-1][1]["ephemeral"])
        self.assertEqual(self.set_ban_calls, [], "nothing was sent to Roblox")
        for key, seconds in self.admin.BAN_DURATIONS.items():
            inter = Interaction()
            await self.ban_modal(card, key, " reason ").on_submit(inter)
            self.assertEqual(self.set_ban_calls[-1][:4], (USER_ID, True, seconds, "reason"), key)

    async def test_ban_without_a_note_keeps_the_admin_in_the_private_reason(self):
        card = self.admin.PlayerCardView(USER_ID, USERNAME, False)
        await self.ban_modal(card, "permanent", "x", "").on_submit(Interaction())
        private = self.set_ban_calls[-1][4]
        self.assertTrue(private.startswith("by admin#0 (7) via Discord"), private)
        self.assertEqual(self.set_ban_calls[-1][2], 0, "permanent")

    async def test_open_cloud_error_when_banning_shows_the_error_and_keeps_the_card(self):
        self.ban_error = open_cloud.OpenCloudError("The API key has no user-restrictions permission.")
        card = self.admin.PlayerCardView(USER_ID, USERNAME, False)
        inter = Interaction()
        await self.ban_modal(card).on_submit(inter)
        self.assertFalse(inter.followup.sent, "no extra message under the card")
        self.assertEqual(list(inter.edited[-1]), ["content"], "only a note above the card: its state stays")
        self.assertIn("user-restrictions", inter.edited[-1]["content"])
        self.assertFalse(card.is_finished(), "the card still works")
        self.assertFalse(inter.guild.log.sent, "a failed ban is not written to the log channel")

    async def test_open_cloud_error_when_unbanning_puts_the_card_back(self):
        self.ban = {"active": True, "displayReason": "x", "duration": ""}
        self.unban_error = open_cloud.OpenCloudError("Roblox is down")
        card = self.admin.PlayerCardView(USER_ID, USERNAME, True)
        confirm = self.admin.UnbanConfirmView(card)
        inter = Interaction()
        await confirm.yes.callback(inter)
        back = inter.edited[-1]["view"]
        self.assertIsInstance(back, self.admin.PlayerCardView, "the card comes back, drawn again")
        self.assertTrue(back.banned, "still banned: the unban failed")
        self.assertIn("Roblox is down", inter.edited[-1]["content"], "with the error written above the card")
        self.assertFalse(inter.followup.sent)
        self.assertFalse(inter.guild.log.sent)
        self.assertTrue(self.ban["active"])

    async def test_a_ban_then_the_card_shows_the_unban_button_and_back(self):
        card = self.admin.PlayerCardView(USER_ID, USERNAME, False)
        inter = Interaction()
        await self.ban_modal(card, "7d", "Spam", "note").on_submit(inter)
        banned_card = inter.edited[-1]["view"]
        self.assertTrue(banned_card.banned and banned_card.unban in banned_card.children and banned_card.ban not in banned_card.children)
        shown = json.dumps(inter.edited[-1]["embed"].to_dict(), ensure_ascii=False)
        self.assertIn("Spam", shown)
        confirm = self.admin.UnbanConfirmView(banned_card)
        inter = Interaction()
        await confirm.yes.callback(inter)
        free_card = inter.edited[-1]["view"]
        self.assertIs(free_card.banned, False)
        self.assertIn(free_card.ban, free_card.children)

    async def test_ban_succeeds_but_reading_it_back_fails(self):
        card = self.admin.PlayerCardView(USER_ID, USERNAME, False)
        inter = Interaction()
        self.get_ban_error = open_cloud.OpenCloudError("flaky")
        await self.ban_modal(card).on_submit(inter)
        self.assertTrue(self.set_ban_calls and self.set_ban_calls[-1][1])
        view = inter.edited[-1]["view"]
        self.assertIsNone(view.banned)
        self.assertIn(view.ban, view.children)
        self.assertIn(view.unban, view.children)

    async def test_refresh_and_another_player(self):
        card = self.admin.PlayerCardView(USER_ID, USERNAME, False)
        inter = Interaction()
        await card.refresh.callback(inter)
        self.assertTrue(inter.edited and isinstance(inter.edited[-1]["view"], self.admin.PlayerCardView))
        self.assertTrue(card.is_finished(), "the old card stops when it is replaced")
        inter = Interaction()
        await card.other.callback(inter)
        self.assertIsInstance(inter.response.modals[-1], self.admin.PlayerLookupModal)

    async def test_lookup_errors_and_odd_input(self):
        async def find_users(text):
            if text == "boom":
                raise roblox_api.RobloxApiError("Roblox did not answer")
            return []

        with mock.patch.object(roblox_api, "find_users", find_users):
            for text, expected in (("boom", "did not answer"), ("nobody", "nobody"), ("**bold**", "bold"), ("<@&1>", "")):
                modal = self.admin.PlayerLookupModal()
                modal.player._value = text
                inter = Interaction()
                await modal.on_submit(inter)
                self.assertTrue(inter.followup.sent, text)
                self.assertIn(expected, inter.followup.sent[-1][0])
                self.assertIsInstance(inter.followup.sent[-1][1]["view"], CloseView, "an answer with ✖️ Close")

    async def test_commands_use_the_same_code(self):
        from cogs import roblox_admin
        cog = roblox_admin.RobloxAdmin(None)
        resolve = mock.AsyncMock(return_value=(USER_ID, USERNAME))
        with mock.patch.object(roblox_api, "resolve_user", resolve):
            inter = Interaction()
            await cog.roblox_unban.callback(cog, inter, USERNAME)
            self.assertEqual(self.set_ban_calls[-1][:2], (USER_ID, False))
            self.assertIn(USERNAME, inter.followup.sent[-1][0])
            self.assertTrue(inter.guild.log.sent)

            self.unban_error = open_cloud.OpenCloudError("nope")
            inter = Interaction()
            await cog.roblox_unban.callback(cog, inter, USERNAME)
            self.assertIn("nope", inter.followup.sent[-1][0])

            inter = Interaction()
            await cog.roblox_ban_check.callback(cog, inter, USERNAME)
            self.assertIn(USERNAME, inter.followup.sent[-1][0])  # not banned
            self.ban = {"active": True, "displayReason": "x", "duration": "3600s", "startTime": "2026-10-01T10:00:00Z"}
            inter = Interaction()
            await cog.roblox_ban_check.callback(cog, inter, USERNAME)
            self.assertIn("<t:", inter.followup.sent[-1][0])
            self.ban = {"active": True, "displayReason": "x", "duration": ""}
            inter = Interaction()
            await cog.roblox_ban_check.callback(cog, inter, USERNAME)
            self.assertNotIn("<t:", inter.followup.sent[-1][0], "permanent")


class CardLimits(CardBase):
    async def test_long_names_reasons_and_errors_fit_in_every_language(self):
        for index in range(5):
            reward = {"currency": {"name": "C" * 100, "amount": 10 ** 9}, "exp": 10 ** 9, "item": {"name": "I" * 100,
                      "is_temporary": True, "duration_seconds": 3600}}
            await database.add_gift(f"g{index}", USER_ID, USERNAME, json.dumps(reward), "m" * 150, 7)
        self.profile = {"name": USERNAME, "displayName": LONG, "created": iso(86400)}
        self.ban = {"active": True, "displayReason": LONG, "privateReason": LONG, "duration": "99999999999s",
                    "startTime": iso(0)[:19] + "Z"}
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                embed, banned = await self.admin.player_card(USER_ID, "N" * 20)
                check_embed(embed, lang)
                self.assertEqual(len(embed.fields), 2)
                self.get_ban_error = open_cloud.OpenCloudError(LONG)
                embed, banned = await self.admin.player_card(USER_ID, "N" * 20)
                check_embed(embed, lang + " ban error")
                self.get_ban_error = None
                for state in (True, False, None):
                    card = self.admin.PlayerCardView(USER_ID, "N" * 20, state)
                    check_view(card)
                    check_modal(self.admin.BanModal(card))
                    check_view(self.admin.UnbanConfirmView(card))
                check_modal(self.admin.PlayerLookupModal())
                check_view(self.admin.PlayerChoiceView([(1, "N" * 20, "name"), (10 ** 18, "M" * 20, "id")]))
                check_modal(self.panel.GiftModal(target=(USER_ID, "N" * 20)))

    async def test_answers_of_ban_and_unban_fit_in_every_language(self):
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                card = self.admin.PlayerCardView(USER_ID, "N" * 20, False)
                inter = Interaction()
                await self.ban_modal(card, "permanent", "r" * 300, "n" * 300).on_submit(inter)  # fakes check the limits
                self.assertTrue(inter.edited and inter.edited[-1]["content"])
                self.assertLessEqual(len(inter.guild.log.sent[-1]), 2000)
                confirm = self.admin.UnbanConfirmView(self.admin.PlayerCardView(USER_ID, "N" * 20, True))
                inter = Interaction()
                await confirm.yes.callback(inter)
                self.assertTrue(inter.edited and inter.edited[-1]["content"])

    async def test_the_modal_title_is_cut_for_long_names_not_broken(self):
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                modal = self.admin.BanModal(self.admin.PlayerCardView(USER_ID, "N" * 20, False))
                self.assertLessEqual(len(modal.title), 45)

    async def test_log_without_a_channel_or_with_a_failing_channel(self):
        guild = Interaction().guild
        await self.admin.log_action(None, "x")
        with mock.patch.object(config_store, "guild_section", return_value={}):
            await self.admin.log_action(guild, "x")
        self.assertEqual(guild.log.sent, [])

        class Broken:
            async def send(self, *a, **k):
                raise discord.HTTPException(mock.Mock(status=500, reason="x"), "boom")

        guild.get_channel = lambda channel_id: Broken()
        await self.admin.log_action(guild, "x")  # must not raise

    async def test_player_choice_buttons_open_the_right_card(self):
        view = self.admin.PlayerChoiceView([(11, "Alpha", "name"), (22, "Beta", "id")])
        buttons = [b for b in view.children]
        self.assertEqual(len(buttons), 2)
        labels = [b.label for b in buttons]
        self.assertTrue("Alpha" in labels[0] and "Beta" in labels[1] and "22" in labels[1], labels)
        inter = Interaction()
        await buttons[1].callback(inter)
        card = inter.edited[-1]["view"]  # the card replaces the choice
        self.assertEqual((card.user_id, card.username), (22, "Beta"))


if __name__ == "__main__":
    unittest.main()
