"""More of the control panel's settings and posting (cogs/game_panel.py): two administrators at the same moment, many
roles, the redraw at start for every server, the language or the roles changing, an old panel that can't be removed."""
import asyncio
import unittest
from unittest import mock

import discord

from tests import fakes
from tests.helpers import TempBot
from tests.panel_fakes import STAFF, Guild, Role, TextChannel, interaction_for, make_guild, not_found
from utils import access, config_store, database, i18n


class Choosing:
    """Lets a role menu answer with the given roles, like an administrator choosing them."""

    def __enter__(self):
        self.patch = mock.patch.object(discord.ui.RoleSelect, "values", property(lambda s: s._values))
        self.patch.start()
        return self

    def __exit__(self, *exc):
        self.patch.stop()


def slow_role_problem(original):
    """A role check that takes a moment, so two callbacks really run at the same time."""
    async def slow(guild, role):
        await asyncio.sleep(0.01)
        return await original(guild, role)
    return slow


def menu(manager):
    return next(item for item in manager.children if isinstance(item, discord.ui.RoleSelect))


class Settings(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import game_panel
        self.gp = game_panel
        self.roles = [Role(300 + i, f"Role {i}", members=2) for i in range(30)]
        self.guild = Guild(self.roles, [TextChannel(700), TextChannel(701)])
        self.guild.default_role = Role(4242, "@everyone", default=True)

    async def asyncTearDown(self):
        await database.close_db()
        self.temp.__exit__(None, None, None)

    def staff(self, *ids):
        config_store.set_guild_values(self.guild.id, access.GAME_PANEL, {"staff_role_ids": list(ids)})

    async def choose(self, manager, ids, slow=False):
        select = menu(manager)
        select._values = [self.guild.get_role(i) for i in ids]
        inter = interaction_for(self.guild, "admin")
        await select.callback(inter)
        return inter

    async def test_two_administrators_choosing_at_the_same_moment_keep_both_choices(self):
        self.staff(300)
        with Choosing(), mock.patch.object(self.gp, "role_problem", slow_role_problem(self.gp.role_problem)):
            a, b = self.gp.GamePanelManager(self.guild), self.gp.GamePanelManager(self.guild)
            await asyncio.gather(self.choose(a, [300, 301]), self.choose(b, [300, 302]))
        self.assertEqual(access.staff_role_ids(self.guild.id), [300, 301, 302])

    async def test_a_removal_and_an_addition_at_the_same_moment(self):
        self.staff(300)
        with Choosing(), mock.patch.object(self.gp, "role_problem", slow_role_problem(self.gp.role_problem)):
            a, b = self.gp.GamePanelManager(self.guild), self.gp.GamePanelManager(self.guild)
            await asyncio.gather(self.choose(a, []), self.choose(b, [300, 303]))
        self.assertEqual(access.staff_role_ids(self.guild.id), [303], "A removed 300, B added 303: both stay")

    async def test_choosing_nothing_empties_the_list_and_the_panel_text_follows(self):
        self.staff(300, 301)
        with Choosing():
            manager = self.gp.GamePanelManager(self.guild)
            inter = await self.choose(manager, [])
        self.assertEqual(access.staff_role_ids(self.guild.id), [])
        self.assertIn(i18n.t("gpanel.roles_none"), str(inter.response.edits[-1]["embed"].to_dict()))
        self.assertIn(i18n.t("gpanel.who_admins_only"), self.gp.panel_embed(self.guild).description)

    async def test_more_than_25_saved_roles_still_open_the_settings(self):
        # LOW: the menu takes at most 25 roles (max_values), but the list can hold more (edited by hand, or two
        # administrators adding at the same moment while it has 24), and Discord refuses a menu with more default
        # values than max_values: the settings window could then not be opened any more
        self.staff(*[300 + i for i in range(26)])
        manager = self.gp.GamePanelManager(self.guild)
        select = menu(manager)
        self.assertLessEqual(len(select.default_values), select.max_values)


class PostingAndRedrawing(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import game_panel
        self.gp = game_panel
        self.guild = make_guild()
        self.team, self.other = self.guild.get_channel(700), TextChannel(701)
        self.guild.channels[701] = self.other

    async def asyncTearDown(self):
        await database.close_db()
        self.temp.__exit__(None, None, None)

    def inter(self, channel):
        inter = interaction_for(self.guild, "admin")
        inter.channel = channel
        return inter

    async def test_the_posted_panel_is_redrawn_when_the_language_or_the_roles_change(self):
        await self.gp.post_panel(self.inter(self.team))
        self.assertTrue(await self.gp.redraw_posted(self.guild, force=False))
        self.assertEqual(self.team.edits, [], "nothing changed: left alone")
        with mock.patch.object(i18n, "language", return_value="pl"):
            await self.gp.redraw_posted(self.guild, force=False)
        self.assertEqual(len(self.team.edits), 1, "another language: the texts changed")
        self.assertFalse(self.gp.settings(self.guild.id)["drawn"] == "")
        config_store.set_guild_values(self.guild.id, access.GAME_PANEL, {"staff_role_ids": [STAFF]})
        await self.gp.redraw_posted(self.guild, force=False)  # back in the first language and with a role
        self.assertEqual(len(self.team.edits), 2)
        await self.gp.redraw_posted(self.guild, force=False)
        self.assertEqual(len(self.team.edits), 2, "and then left alone again")

    async def test_start_redraws_every_server_once_and_one_failure_does_not_stop_the_others(self):
        calls = []

        async def redraw(guild, force=True):
            calls.append(guild.id)
            if guild.id == 2:
                raise RuntimeError("one server is broken")
            return True
        bot = mock.MagicMock()
        bot.guilds = [type("G", (), {"id": i})() for i in (1, 2, 3)]
        cog = self.gp.GamePanel(bot)
        with mock.patch.object(self.gp, "redraw_posted", redraw):
            await cog.redraw_all()
            await cog.redraw_all()  # the second ready event does nothing
        self.assertEqual(calls, [1, 2, 3])

    async def test_an_old_panel_that_cannot_be_removed_is_reported_and_the_new_one_works(self):
        await self.gp.post_panel(self.inter(self.team))
        old = self.gp.settings(self.guild.id)

        async def forbidden():
            raise discord.Forbidden(type("R", (), {"status": 403, "reason": "Forbidden"})(), "Missing Access")
        original = self.team.get_partial_message

        def locked(message_id):
            message = original(message_id)
            message.delete = forbidden
            return message
        self.team.get_partial_message = locked
        text = await self.gp.post_panel(self.inter(self.other))
        self.assertIn(f"https://discord.com/channels/{self.guild.id}/700/{old['message_id']}", text, "a link to the old one")
        settings = self.gp.settings(self.guild.id)
        self.assertEqual(settings["channel_id"], 701)
        self.assertNotEqual(settings["message_id"], old["message_id"])

    async def test_the_old_channel_is_gone_and_discord_cannot_find_it(self):
        await self.gp.post_panel(self.inter(self.team))
        del self.guild.channels[700]  # deleted since
        inter = self.inter(self.other)

        async def fetch(channel_id):
            raise not_found("Unknown Channel")
        inter.client.fetch_channel = fetch
        text = await self.gp.post_panel(inter)
        self.assertIn("701", text)
        self.assertEqual(self.gp.settings(self.guild.id)["channel_id"], 701)

    async def test_a_channel_the_bot_cannot_write_in_saves_nothing_and_says_so(self):
        closed = TextChannel(702, can_send=False)
        text = await self.gp.post_panel(self.inter(closed))
        self.assertTrue(text.startswith("❌"))
        self.assertEqual(self.gp.settings(self.guild.id)["message_id"], 0)

    async def test_a_message_deleted_by_hand_is_forgotten_at_the_next_redraw(self):
        await self.gp.post_panel(self.inter(self.team))
        self.team.deleted.add(self.gp.settings(self.guild.id)["message_id"])
        self.assertFalse(await self.gp.redraw_posted(self.guild))
        self.assertEqual(self.gp.settings(self.guild.id)["message_id"], 0)
        # and the settings window then says it isn't posted
        manager = self.gp.GamePanelManager(self.guild)
        fakes.check_embed(manager.embed())
        self.assertIn(i18n.t("gpanel.where_none"), str(manager.embed().to_dict()))


if __name__ == "__main__":
    unittest.main()
