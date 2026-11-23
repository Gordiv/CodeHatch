"""The game control panel: administrators and the roles an administrator chose may use it (also bans), only
administrators choose the roles and post it; the posted panel survives restarts and follows the language."""
import unittest
from unittest import mock

import discord

from tests import fakes
from tests.helpers import TempBot
from utils import access, config_store, database, i18n, open_cloud

LANGS = ("en", "pl", "es")
STAFF, OTHER = 300, 301


class Role:
    def __init__(self, role_id, name, default=False, managed=False, members=0):
        self.id, self.name, self.position = role_id, name, role_id
        self.mention = "@everyone" if default else f"<@&{role_id}>"
        self.managed, self._default, self.members = managed, default, [object()] * members

    def is_default(self):
        return self._default


class Message:
    def __init__(self, message_id):
        self.id = message_id


class PartialMessage:
    def __init__(self, channel, message_id):
        self.channel, self.id = channel, message_id

    async def edit(self, **kwargs):
        if self.id in self.channel.deleted:
            raise discord.NotFound(type("R", (), {"status": 404, "reason": "Not Found"})(), "Unknown Message")
        fakes.check_payload(kwargs.get("content"), kwargs.get("embed"), None, kwargs.get("view"), "panel edit")
        self.channel.edits.append((self.id, kwargs))

    async def delete(self):
        self.channel.deleted.add(self.id)


class TextChannel:
    def __init__(self, channel_id, can_send=True):
        self.id, self.mention, self.can_send = channel_id, f"<#{channel_id}>", can_send
        self.sent, self.edits, self.deleted, self.next_id = [], [], set(), channel_id * 1000

    def permissions_for(self, member):
        return discord.Permissions(view_channel=self.can_send, send_messages=self.can_send, embed_links=self.can_send)

    async def send(self, **kwargs):
        fakes.check_payload(kwargs.get("content"), kwargs.get("embed"), None, kwargs.get("view"), "panel post")
        self.next_id += 1
        self.sent.append(kwargs)
        return Message(self.next_id)

    def get_partial_message(self, message_id):
        return PartialMessage(self, message_id)


class PanelGuild:
    id, owner_id = 4242, 1

    def __init__(self, roles, channels):
        self.roles = {r.id: r for r in roles}
        self.channels = {c.id: c for c in channels}
        self.me = object()

    def get_role(self, role_id):
        return self.roles.get(role_id)

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)


class Member:
    id, mention, display_name = 50, "<@50>", "Mod"
    guild_permissions = discord.Permissions.none()

    def __init__(self, roles):
        self.roles = roles

    def __str__(self):
        return "mod#0"


class GamePanelTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import game_panel, roblox_admin, setup_roblox
        self.gp, self.admin_cog, self.panel = game_panel, roblox_admin, setup_roblox
        self.staff_role, self.other_role = Role(STAFF, "Game moderator", members=3), Role(OTHER, "Player", members=900)
        self.everyone, self.app = Role(4242, "@everyone", default=True), Role(302, "SomeBot", managed=True)
        self.team, self.other_channel = TextChannel(700), TextChannel(701)
        self.guild = PanelGuild([self.staff_role, self.other_role, self.everyone, self.app], [self.team, self.other_channel])

    async def asyncTearDown(self):
        await database.close_db()
        self.temp.__exit__(None, None, None)

    def inter(self, who="staff", channel=None):
        inter = fakes.Interaction(GameCodes=None)
        inter.guild, inter.guild_id = self.guild, self.guild.id
        inter.channel = channel or self.team
        if who == "staff":
            inter.user = Member([self.everyone, self.staff_role])
        elif who == "other":
            inter.user = Member([self.everyone, self.other_role])
        else:
            inter.user = fakes.Admin()
        return inter

    def choose_staff(self, *role_ids):
        config_store.set_guild_values(self.guild.id, access.GAME_PANEL, {"staff_role_ids": list(role_ids)})

    async def test_who_may_use_it(self):
        self.assertFalse(access.is_game_staff(self.inter("staff")), "no role chosen yet: only administrators")
        self.assertTrue(access.is_game_staff(self.inter("admin")))
        self.choose_staff(STAFF)
        self.assertTrue(access.is_game_staff(self.inter("staff")))
        self.assertFalse(access.is_game_staff(self.inter("other")))
        self.assertFalse(access.is_admin(self.inter("staff")), "the staff role is not an administrator")
        self.choose_staff()
        self.assertFalse(access.is_game_staff(self.inter("staff")), "taking the role off the list works at once")

    async def test_the_posted_panel_lets_staff_in_and_others_out(self):
        self.choose_staff(STAFF)
        view = self.gp.GamePanelView()
        self.assertTrue(view.is_persistent(), "works after a restart")
        self.assertTrue(await view.interaction_check(self.inter("staff")))
        refused = self.inter("other")
        self.assertFalse(await view.interaction_check(refused))
        self.assertTrue(refused.response.sent[-1][1]["ephemeral"])

    async def test_buttons_fit_in_every_language(self):
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                view = self.gp.GamePanelView()
                fakes.check_view(view, f"panel {lang}")
                fakes.check_embed(self.gp.panel_embed(self.guild), f"panel embed {lang}")
                manager = self.gp.GamePanelManager(self.guild)
                fakes.check_view(manager, f"manager {lang}")
                fakes.check_embed(manager.embed(), f"manager embed {lang}")
        ids = [c.custom_id for c in view.children]
        self.assertEqual(ids, ["gpanel:codes", "gpanel:player", "gpanel:gift", "gpanel:announce", "gpanel:events", "gpanel:eggs"])
        text = str(self.gp.GamePanelManager(self.guild).embed().to_dict()).lower()
        self.assertIn("ban", text, "the warning about bans")

    async def test_each_button_opens_its_window_for_staff(self):
        self.choose_staff(STAFF)
        expected = {"codes": self.panel.CodesView, "events": self.panel.EventsView, "eggs": self.panel.EggsView}
        for key, view_class in expected.items():
            inter = self.inter("staff")
            await self.gp.open_action(key, inter)
            view = inter.followup.sent[-1][1]["view"]
            self.assertIsInstance(view, view_class)
            self.assertTrue(await view.interaction_check(self.inter("staff")), f"{key}: the staff can click inside")
            self.assertFalse(await view.interaction_check(self.inter("other")))
        modals = {"gift": self.panel.GiftModal, "announce": self.panel.AnnounceModal,
                  "player": self.admin_cog.PlayerLookupModal}
        for key, modal_class in modals.items():
            inter = self.inter("staff")
            await self.gp.open_action(key, inter)
            self.assertIsInstance(inter.response.modals[-1], modal_class)

    async def test_the_player_card_and_a_ban_by_the_staff_role(self):
        self.choose_staff(STAFF)
        card = self.admin_cog.PlayerCardView(4242, "Builderman", False)
        self.assertTrue(await card.interaction_check(self.inter("staff")))
        set_ban = mock.AsyncMock()
        with mock.patch.object(open_cloud, "set_ban", set_ban):
            modal = self.admin_cog.BanModal(card)
            modal.duration._values = ["24h"]
            modal.reason._value = "Exploiting"
            modal.note._value = ""
            self.choose_staff()  # the role was taken away while the form was open
            inter = self.inter("staff")
            await modal.on_submit(inter)
            set_ban.assert_not_called()
            self.assertTrue(inter.response.sent and "❌" in inter.response.sent[-1][0])

    async def test_only_administrators_choose_the_roles(self):
        self.choose_staff(STAFF)
        manager = self.gp.GamePanelManager(self.guild)
        self.assertFalse(await manager.interaction_check(self.inter("staff")), "the staff role can't change who has access")
        self.assertTrue(await manager.interaction_check(self.inter("admin")))

    async def test_choosing_roles_skips_everyone_and_apps_and_redraws_the_panel(self):
        await self.gp.post_panel(self.inter("admin"))
        manager = self.gp.GamePanelManager(self.guild)
        select = next(c for c in manager.children if isinstance(c, discord.ui.RoleSelect))
        select._values = [self.staff_role, self.everyone, self.app]
        with mock.patch.object(discord.ui.RoleSelect, "values", property(lambda s: s._values)):
            inter = self.inter("admin")
            await select.callback(inter)
        self.assertEqual(access.staff_role_ids(self.guild.id), [STAFF])
        self.assertIn("@everyone", inter.followup.sent[-1][0], "the admin is told why two roles were left out")
        self.assertTrue(self.team.edits, "the posted panel shows the new roles")
        self.assertIn(self.staff_role.mention, self.team.edits[-1][1]["embed"].description)
        self.assertIn("3", str(inter.response.edits[-1]["embed"].to_dict()), "member count next to the role")

    async def test_posting_moves_the_panel_and_checks_permissions(self):
        text = await self.gp.post_panel(self.inter("admin", self.team))
        self.assertIn(self.team.mention, text)
        first = self.gp.settings(self.guild.id)
        self.assertEqual(first["channel_id"], self.team.id)
        text = await self.gp.post_panel(self.inter("admin", self.other_channel))
        self.assertIn(first["message_id"], self.team.deleted, "one panel per server: the old one is removed")
        self.assertIn(self.team.mention, text)
        self.assertEqual(self.gp.settings(self.guild.id)["channel_id"], self.other_channel.id)
        closed = TextChannel(702, can_send=False)
        self.guild.channels[702] = closed
        text = await self.gp.post_panel(self.inter("admin", closed))
        self.assertIn("❌", text)
        self.assertEqual(self.gp.settings(self.guild.id)["channel_id"], self.other_channel.id, "nothing saved")

    async def test_redraw_at_start_only_when_something_changed(self):
        await self.gp.post_panel(self.inter("admin"))
        self.assertTrue(await self.gp.redraw_posted(self.guild, force=False))
        self.assertEqual(self.team.edits, [], "nothing changed: no edit at start")
        with mock.patch.object(i18n, "language", return_value="pl"):
            await self.gp.redraw_posted(self.guild, force=False)
        self.assertEqual(len(self.team.edits), 1, "another language: the panel is redrawn")
        self.team.deleted.add(self.gp.settings(self.guild.id)["message_id"])
        self.assertFalse(await self.gp.redraw_posted(self.guild))
        self.assertEqual(self.gp.settings(self.guild.id)["message_id"], 0, "deleted by someone: not posted any more")

    async def test_the_cog_registers_the_panel_for_restarts(self):
        bot = mock.MagicMock()
        bot.add_cog = mock.AsyncMock()
        await self.gp.setup(bot)
        registered = bot.add_view.call_args.args[0]
        self.assertIsInstance(registered, self.gp.GamePanelView)
        self.assertTrue(registered.is_persistent())

    async def test_setup_roblox_and_tutorial_open_the_settings(self):
        view = self.panel.RobloxPanelView()
        self.assertIn(view.control, view.children)
        fakes.check_view(view, "setup-roblox")
        inter = self.inter("admin")
        await view.control.callback(inter)
        self.assertIsInstance(inter.response.sent[-1][1]["view"], self.gp.GamePanelManager)
        from cogs import tutorial
        inter = self.inter("admin")
        await tutorial.run_action("control_panel", inter)
        self.assertIsInstance(inter.response.sent[-1][1]["view"], self.gp.GamePanelManager)
        lines = await tutorial.check_lines("control_panel", self.guild)
        self.assertTrue(lines[0].startswith("⚠️"), "not posted yet")
        await self.gp.post_panel(self.inter("admin"))
        self.choose_staff(STAFF)
        lines = await tutorial.check_lines("control_panel", self.guild)
        self.assertTrue(lines[0].startswith("✅") and self.staff_role.mention in lines[1])


if __name__ == "__main__":
    unittest.main()
