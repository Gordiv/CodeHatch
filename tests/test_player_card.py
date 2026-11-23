"""/setup-roblox -> Player card: one player's profile, ban and gifts on one screen, with Ban / Unban / Gift buttons
that use the same code as /roblox-ban and /roblox-unban ."""
import calendar
import json
import time
import unittest
from unittest import mock

import discord

from tests.helpers import TempBot
from utils import config_store, database, i18n, open_cloud, roblox_api

LANGS = ("en", "pl", "es")
USER_ID, USERNAME = 4242, "Builderman"


class Admin:
    id, mention, display_name = 7, "<@7>", "Admin"
    guild_permissions = discord.Permissions(administrator=True)

    def __str__(self):
        return "admin#0"


class Channel:
    def __init__(self):
        self.sent = []

    async def send(self, text=None, **kwargs):
        self.sent.append(text)


class Guild:
    id = 4242

    def __init__(self):
        self.log = Channel()

    def get_channel(self, channel_id):
        return self.log if channel_id == 500 else None


class Response:
    def __init__(self):
        self.sent, self.modals, self.deferred = [], [], False

    def is_done(self):
        return bool(self.sent or self.modals or self.deferred)

    async def send_message(self, content=None, **kwargs):
        self.sent.append((content, kwargs))

    async def send_modal(self, modal):
        self.modals.append(modal)

    async def edit_message(self, **kwargs):
        self.deferred = True

    async def defer(self, **kwargs):
        self.deferred = True


class Followup:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, **kwargs):
        kwargs.pop("wait", None)
        self.sent.append((content, kwargs))


class Interaction:
    def __init__(self):
        self.user, self.guild = Admin(), Guild()
        self.guild_id = self.guild.id
        self.response, self.followup, self.edited = Response(), Followup(), []
        self.deleted = False

    async def edit_original_response(self, **kwargs):
        self.edited.append(kwargs)

    async def delete_original_response(self):
        self.deleted = True

    async def original_response(self):
        return None


def iso(seconds_ago: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.123Z", time.gmtime(time.time() - seconds_ago))


class FindUser(unittest.IsolatedAsyncioTestCase):
    async def test_name_and_id_never_guessed(self):
        async def by_name(name, exclude_banned=False):
            return {"roblox": (1, "Roblox"), "156": (777, "156")}.get(name.lower())

        async def by_id(user_id):
            return {156: {"name": "Builderman"}, 1: {"name": "Roblox"}}.get(user_id)

        with mock.patch.object(roblox_api, "resolve_user", by_name), mock.patch.object(roblox_api, "get_user", by_id):
            self.assertEqual(await roblox_api.find_users(" @Roblox "), [(1, "Roblox", "name")])
            self.assertEqual(await roblox_api.find_users("1"), [(1, "Roblox", "id")])
            self.assertEqual(await roblox_api.find_users("156"), [(777, "156", "name"), (156, "Builderman", "id")],
                             "a name made of digits and another account's ID: both, the admin picks")
            self.assertEqual(await roblox_api.find_users("157"), [])
            self.assertEqual(await roblox_api.find_users("\u00b2"), [], "not a number for Python's int()")
            self.assertEqual(await roblox_api.find_users("  "), [])


class PlayerCard(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import roblox_admin, setup_roblox
        from utils import ui
        self.admin, self.panel, self.ui = roblox_admin, setup_roblox, ui
        self.ban = {}
        self.set_ban = mock.AsyncMock(side_effect=self.fake_set_ban)
        self.profile = {"name": USERNAME, "displayName": "Bob", "created": iso(3 * 86400)}

        async def get_user(user_id):
            return self.profile

        async def avatar(user_id, size="352x352"):
            return "https://tr.rbxcdn.com/avatar.png"

        async def get_ban(user_id):
            return dict(self.ban)

        async def find_users(text):
            text = text.strip().lstrip("@").lower()
            if text == "12345":
                return [(USER_ID, USERNAME, "id"), (999, "12345", "name")]
            return [(USER_ID, USERNAME, "id" if text.isdigit() else "name")] if text in ("builderman", str(USER_ID)) else []

        self.patches = [mock.patch.object(roblox_api, "get_user", get_user), mock.patch.object(roblox_api, "avatar_url", avatar),
                        mock.patch.object(roblox_api, "find_users", find_users), mock.patch.object(open_cloud, "get_ban", get_ban),
                        mock.patch.object(open_cloud, "set_ban", self.set_ban),
                        mock.patch.object(config_store, "guild_section", return_value={"log_channel_id": 500})]
        for patch in self.patches:
            patch.start()

    async def fake_set_ban(self, user_id, active, seconds=0, display_reason="", private_reason=""):
        self.ban = {"active": active, "displayReason": display_reason, "privateReason": private_reason,
                    "startTime": iso(0)[:19] + "Z", "duration": f"{seconds}s" if seconds else ""} if active else {}

    async def asyncTearDown(self):
        for patch in self.patches:
            patch.stop()
        await database.close_db()
        self.temp.__exit__(None, None, None)

    async def open_card(self, text="Builderman"):
        modal = self.admin.PlayerLookupModal()
        modal.player._value = text
        inter = Interaction()
        await modal.on_submit(inter)
        return inter

    async def test_card_shows_profile_link_ban_and_gifts(self):
        await database.add_gift("g1", USER_ID, USERNAME, json.dumps({"currency": {"name": "Coins", "amount": 500}}), "", 7)
        self.ban = {"active": True, "displayReason": "Exploiting", "privateReason": "seen on video", "duration": ""}
        embed, banned = await self.admin.player_card(USER_ID, USERNAME)
        self.assertTrue(banned)
        text = str(embed.to_dict())
        for part in ("Bob", "@Builderman", str(USER_ID), "Exploiting", "seen on video", "500", "Coins", "⚠️"):
            self.assertIn(part, text)
        self.assertEqual(embed.url, f"https://www.roblox.com/users/{USER_ID}/profile")

    async def test_card_fits_and_explains_in_every_language(self):
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                embed, _ = await self.admin.player_card(USER_ID, USERNAME)
                self.assertLess(len(embed), 6000)
                self.assertEqual(len(embed.fields), 2, lang)  # ban, gifts
                for modal in (self.admin.PlayerLookupModal(), self.admin.BanModal(self.admin.PlayerCardView(USER_ID, USERNAME, False))):
                    data = modal.to_dict()
                    self.assertLessEqual(len(data["title"]), 45)
                    labels = [c.get("label", "") for row in data["components"] for c in [row, *row.get("components", [])]
                              if c.get("type") in (4, 18)]
                    self.assertTrue(labels and all(0 < len(label) <= 45 for label in labels), (lang, labels))

    async def test_roblox_times_with_short_fractions_and_a_broken_avatar_service(self):
        self.profile["created"] = "2026-10-12T21:06:40.3Z"

        async def busy(user_id, size="352x352"):
            raise roblox_api.RobloxApiError("429")

        with mock.patch.object(roblox_api, "avatar_url", busy):
            embed, _ = await self.admin.player_card(USER_ID, USERNAME)
        self.assertIn(f"<t:{calendar.timegm((2026, 10, 12, 21, 6, 40))}:D>", embed.description)
        self.assertIn("Bob", embed.title, "the profile stays when only the avatar fails")
        self.assertIsNone(embed.thumbnail.url)
        self.assertEqual(self.admin.utc_timestamp("nonsense"), 0)

    async def test_an_old_account_and_a_missing_ban_permission(self):
        self.profile["created"] = iso(400 * 86400)

        async def no_permission(user_id):
            raise open_cloud.OpenCloudError("no user-restrictions permission")

        with mock.patch.object(open_cloud, "get_ban", no_permission):
            embed, banned = await self.admin.player_card(USER_ID, USERNAME)
        self.assertIsNone(banned)
        self.assertNotIn("⚠️ ", embed.description)
        self.assertIn("user-restrictions", str(embed.to_dict()))
        view = self.admin.PlayerCardView(USER_ID, USERNAME, None)
        self.assertIn(view.ban, view.children)
        self.assertIn(view.unban, view.children, "unknown state: both, the click explains the error")

    async def test_buttons_follow_the_ban(self):
        free = self.admin.PlayerCardView(USER_ID, USERNAME, False)
        self.assertIn(free.ban, free.children)
        self.assertNotIn(free.unban, free.children)
        self.assertIn(free.gift, free.children)
        banned = self.admin.PlayerCardView(USER_ID, USERNAME, True)
        self.assertNotIn(banned.ban, banned.children)
        self.assertIn(banned.unban, banned.children)

    async def test_lookup_by_name_or_id(self):
        inter = await self.open_card("builderman")
        content, kwargs = inter.followup.sent[-1]
        self.assertIsInstance(kwargs["view"], self.admin.PlayerCardView)
        self.assertTrue(kwargs["ephemeral"])
        inter = await self.open_card(str(USER_ID))
        self.assertIsInstance(inter.followup.sent[-1][1]["view"], self.admin.PlayerCardView)
        inter = await self.open_card("@Builderman")
        self.assertIsInstance(inter.followup.sent[-1][1]["view"], self.admin.PlayerCardView)
        inter = await self.open_card("nobody_here")
        self.assertIn("nobody", inter.followup.sent[-1][0])
        self.assertIsInstance(inter.followup.sent[-1][1]["view"], self.ui.CloseView, "an answer with ✖️ Close")

    async def test_two_matching_accounts_the_admin_chooses(self):
        inter = await self.open_card("12345")
        content, kwargs = inter.followup.sent[-1]
        choice = kwargs["view"]
        self.assertIsInstance(choice, self.admin.PlayerChoiceView)
        self.assertIn("12345", content)
        buttons = [b for b in choice.children if isinstance(b, discord.ui.Button)]
        self.assertEqual(len(buttons), 2)
        self.assertTrue(any(str(USER_ID) in b.label for b in buttons) and any("12345" in b.label for b in buttons))
        inter = Interaction()
        await buttons[0].callback(inter)
        card = inter.edited[-1]["view"]
        self.assertIsInstance(card, self.admin.PlayerCardView, "the card replaces the choice")
        self.assertEqual(card.user_id, USER_ID)
        self.assertFalse(inter.followup.sent)

    async def test_ban_from_the_card(self):
        card = self.admin.PlayerCardView(USER_ID, USERNAME, False)
        modal = self.admin.BanModal(card)
        modal.reason._value = " "
        modal.note._value = ""
        inter = Interaction()
        await modal.on_submit(inter)
        self.assertTrue(inter.response.sent and "❌" in inter.response.sent[-1][0], "no duration and no reason")
        self.set_ban.assert_not_called()

        modal.duration._values = ["24h"]
        modal.reason._value = "Exploiting"
        modal.note._value = "seen on video"
        inter = Interaction()
        await modal.on_submit(inter)
        self.set_ban.assert_awaited_once()
        args = self.set_ban.await_args.args
        self.assertEqual(args[:4], (USER_ID, True, 86400, "Exploiting"))
        self.assertIn("seen on video", args[4])
        self.assertIn("admin#0", args[4])
        self.assertTrue(inter.guild.log.sent and "Builderman" in inter.guild.log.sent[-1], "written to the log channel")
        new_view = inter.edited[-1]["view"]
        self.assertTrue(new_view.banned and new_view.unban in new_view.children, "the card now shows the ban")
        self.assertIn("Builderman", inter.edited[-1]["content"], "what happened is written above the card")
        self.assertFalse(inter.followup.sent, "no extra message under the card")

    async def test_unban_from_the_card(self):
        self.ban = {"active": True, "displayReason": "x", "duration": ""}
        card = self.admin.PlayerCardView(USER_ID, USERNAME, True)
        inter = Interaction()
        edits = []

        async def edit_message(**kwargs):
            edits.append(kwargs)
        inter.response.edit_message = edit_message
        await card.unban.callback(inter)
        self.set_ban.assert_not_called()
        confirm = edits[-1]["view"]
        self.assertIsInstance(confirm, self.admin.UnbanConfirmView, "a second click is needed")
        self.assertTrue(card.is_finished(), "the question took the card's place")
        inter = Interaction()
        await confirm.no.callback(inter)
        back = inter.edited[-1]["view"]
        self.assertIsInstance(back, self.admin.PlayerCardView, "Cancel draws the card again")
        self.assertTrue(back.banned and not back.is_finished())
        self.set_ban.assert_not_called()
        inter = Interaction()
        await confirm.yes.callback(inter)
        self.assertEqual(self.set_ban.await_args.args[:2], (USER_ID, False))
        self.assertFalse(inter.edited[-1]["view"].banned)
        self.assertTrue(inter.guild.log.sent)

    async def test_gift_form_has_the_player_filled_in(self):
        card = self.admin.PlayerCardView(USER_ID, USERNAME, False)
        inter = Interaction()
        await card.gift.callback(inter)
        modal = inter.response.modals[-1]
        self.assertIsInstance(modal, self.panel.GiftModal)
        self.assertEqual(modal.player.default, USERNAME)
        self.assertEqual(modal.target, (USER_ID, USERNAME))

    async def test_gifts_go_to_the_exact_account(self):
        from cogs import live_game
        sent = []

        async def write_entry(datastore, key, value):
            sent.append(key)

        async def publish(message):
            pass

        resolve = mock.AsyncMock(return_value=(55, "Fiftyfive"))
        with mock.patch.object(open_cloud, "write_entry", write_entry), mock.patch.object(open_cloud, "publish", publish), \
                mock.patch.object(open_cloud, "live_settings", return_value={"gifts": "Gifts"}), \
                mock.patch.object(roblox_api, "resolve_user", resolve):
            reward = {"currency": {"name": "Coins", "amount": 5}}
            embed = await live_game.send_gift((USER_ID, USERNAME), reward, "", "Admin", 7)
            self.assertTrue(sent[-1].startswith(f"gift_{USER_ID}_") and "Builderman" in embed.description,
                            "from the card: the account on the card, no new search")
            resolve.assert_not_called()
            with self.assertRaises(live_game.RuleError):
                await live_game.send_gift("12345", reward, "", "Admin", 7, by_id=True)  # two accounts: refused
            await live_game.send_gift("12345", reward, "", "Admin", 7)  # by_id=False: names only (/give and the form use by_id=True)
            resolve.assert_awaited_once()
            self.assertTrue(sent[-1].startswith("gift_55_"))

    async def test_the_command_still_bans_after_a_confirmation(self):
        view = self.admin.BanConfirmView(None, Admin(), USER_ID, USERNAME, 3600, "Spam", "")
        inter = Interaction()

        async def edit_message(**kwargs):
            inter.response.deferred = True
        inter.response.edit_message = edit_message
        await view.confirm.callback(inter)
        self.assertEqual(self.set_ban.await_args.args[:4], (USER_ID, True, 3600, "Spam"))
        self.assertIn("Builderman", inter.followup.sent[-1][0])

    async def test_ban_end_from_roblox(self):
        until = self.admin.ban_until({"startTime": "2026-10-01T10:00:00Z", "duration": "86400s"})
        self.assertEqual(until, f"<t:{calendar.timegm((2026, 10, 1, 10, 0, 0)) + 86400}:f>")
        self.assertNotIn("<t:", self.admin.ban_until({"duration": ""}))

    async def test_where_the_card_opens(self):
        view = self.panel.RobloxPanelView()
        self.assertIn(view.player, view.children)
        rows = view.to_components()
        self.assertTrue(len(rows) <= 5 and all(len(r["components"]) <= 5 for r in rows))
        for opener in (self.panel.RobloxPanelView().player, self.panel.BansView().find):
            inter = Interaction()
            await opener.callback(inter)
            self.assertIsInstance(inter.response.modals[-1], self.admin.PlayerLookupModal)
        from cogs import tutorial
        inter = Interaction()
        await tutorial.run_action("player", inter)
        self.assertIsInstance(inter.response.modals[-1], self.admin.PlayerLookupModal)


if __name__ == "__main__":
    unittest.main()
