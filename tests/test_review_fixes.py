"""Fixes after the review of the control panel and the closing windows: a replaced window never removes the new one,
a window removes itself before Discord stops letting the bot do it, the game-staff check also on forms, roles members
get by themselves or automatically can't open the panel, and a few smaller things."""
import asyncio
import time
import unittest
from unittest import mock

import discord

from tests import fakes
from tests.helpers import TempBot
from tests.test_game_panel import STAFF, Member, PanelGuild, Role, TextChannel
from utils import access, config_store, database, ui


class Message:
    def __init__(self, message_id=1):
        self.id, self.deleted, self.edits = message_id, False, []

    async def delete(self):
        self.deleted = True

    async def edit(self, **kwargs):
        self.edits.append(kwargs)


class WindowLifetime(unittest.IsolatedAsyncioTestCase):
    async def test_a_replaced_window_stops_and_never_removes_the_new_one(self):
        message = Message(101)
        old, new = ui.Panel(), ui.Panel()
        old.message = message
        new.message = message  # an answer in place: the same message shows another window now
        self.assertTrue(old.is_finished(), "the old window stops")
        await old.on_timeout()
        self.assertFalse(message.deleted, "its timer can't remove the new content")
        await new.on_timeout()
        self.assertTrue(message.deleted)

    async def test_the_window_removes_itself_before_the_bot_loses_the_right_to(self):
        with mock.patch.object(ui, "PANEL_TIMEOUT", 0.05):
            view, message = ui.Panel(), Message(102)
            ui._remember_token(message, fresh=True)
            view.message = message
            await asyncio.sleep(0.2)
        self.assertTrue(message.deleted, "removed at the token's end even though it was still in use")
        self.assertTrue(view.is_finished())

    async def test_a_fresh_answer_in_place_starts_the_time_again(self):
        inter = fakes.Interaction()
        await inter.response.defer()
        fresh = Message(103)

        async def edit(**kwargs):
            return fresh
        inter.edit_original_response = edit
        with mock.patch.object(ui, "PANEL_TIMEOUT", 0.3):
            ui._token_ends[103] = time.monotonic() + 0.01  # the old token is about to end
            view = ui.Panel()
            await ui.show_in_place(inter, view=view, content="x")
            await asyncio.sleep(0.1)
            self.assertFalse(fresh.deleted, "a new token: the window still lives")
            view.stop()

    async def test_an_open_form_gets_more_time(self):
        view = ui.Panel()
        view.hold_for_form()
        self.assertEqual(view.timeout, ui.PANEL_TIMEOUT)


class GameStaffOnForms(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import game_codes, roblox_admin, setup_roblox
        self.codes, self.admin, self.panel = game_codes, roblox_admin, setup_roblox
        self.role = Role(STAFF, "Game moderator", members=3)
        self.guild = PanelGuild([self.role], [])
        self.cog = game_codes.GameCodes.__new__(game_codes.GameCodes)
        self.cog.bot = fakes.Client()

    async def asyncTearDown(self):
        await database.close_db()
        self.temp.__exit__(None, None, None)

    def inter(self, staff=True):
        inter = fakes.Interaction(GameCodes=self.cog)
        inter.guild, inter.guild_id = self.guild, self.guild.id
        inter.user = Member([self.role] if staff else [])
        return inter

    def allow_staff(self, on=True):
        config_store.set_guild_values(self.guild.id, access.GAME_PANEL, {"staff_role_ids": [STAFF] if on else []})

    async def test_every_game_form_checks_the_role_again_when_sent(self):
        self.allow_staff()
        forms = [self.panel.CodeModal(), self.panel.GiftModal(), self.panel.AnnounceModal(), self.panel.EventModal(),
                 self.panel.EggModal(), self.admin.PlayerLookupModal()]
        self.allow_staff(False)  # the role is taken away while the forms are open
        for form in forms:
            inter = self.inter()
            await form.on_submit(inter)
            self.assertTrue(inter.response.sent and "❌" in inter.response.sent[-1][0], type(form).__name__)
            self.assertFalse(inter.followup.sent, type(form).__name__)

    async def test_the_code_draft_and_its_questions_check_the_role_too(self):
        self.allow_staff()
        params = self.codes.code_params("SAFE", "7d", "Coins", 5)
        views = [self.codes.CodeDraftView(self.cog, Member.id, params),
                 self.codes.OverwriteView(self.cog, Member.id, params, panel=True)]
        self.assertTrue(all([await v.interaction_check(self.inter()) for v in views]))
        extras = self.codes.CodeExtrasModal(views[0])
        self.allow_staff(False)
        for view in views:
            self.assertFalse(await view.interaction_check(self.inter()), type(view).__name__)
        inter = self.inter()
        await extras.on_submit(inter)
        self.assertTrue(inter.response.sent and "❌" in inter.response.sent[-1][0])

    async def test_a_long_gear_form_brings_the_draft_back(self):
        params = self.codes.code_params("SLOW", "7d", "Coins", 5)
        draft = self.codes.CodeDraftView(self.cog, 7, params)
        modal = self.codes.CodeExtrasModal(draft)
        draft.stop()  # the draft removed itself after 5 minutes while the form was open
        modal.exp._value = "300"
        inter = fakes.Interaction(GameCodes=self.cog)
        await modal.on_submit(inter)
        content, kwargs = inter.response.sent[-1]
        self.assertIsInstance(kwargs["view"], self.codes.CodeDraftView, "a new draft with the typed EXP")
        self.assertEqual(kwargs["view"].params["exp_amount"], 300)
        saved = self.codes.CodeDraftView(self.cog, 7, params)
        modal = self.codes.CodeExtrasModal(saved)
        saved.closed = True
        saved.stop()
        inter = fakes.Interaction(GameCodes=self.cog)
        await modal.on_submit(inter)
        self.assertNotIn("view", inter.response.sent[-1][1], "a saved draft is not brought back")

    async def test_a_ban_sent_after_the_card_closed_still_answers(self):
        card = self.admin.PlayerCardView(4242, "Builderman", False)
        card.stop()
        modal = self.admin.BanModal(card)
        modal.duration._values = ["24h"]
        modal.reason._value = "Exploiting"
        modal.note._value = ""
        inter = fakes.Interaction()
        with mock.patch("utils.open_cloud.set_ban", mock.AsyncMock()), \
                mock.patch("utils.open_cloud.get_ban", mock.AsyncMock(return_value={"active": True, "duration": ""})), \
                mock.patch("utils.roblox_api.get_user", mock.AsyncMock(return_value={})), \
                mock.patch("utils.roblox_api.avatar_url", mock.AsyncMock(return_value="")):
            await modal.on_submit(inter)
        self.assertEqual(inter.response.defers[-1], {"ephemeral": True, "thinking": True}, "a new private message")
        self.assertIn("Builderman", inter.edited[-1]["content"])


class StaffRoleSafety(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import game_panel
        self.gp = game_panel
        self.staff, self.bot_role = Role(300, "Mod", members=3), Role(301, "Some app", managed=True)
        self.everyone, self.other = Role(4242, "@everyone", default=True), Role(304, "Helper", members=2)
        self.team = TextChannel(700)
        self.guild = PanelGuild([self.staff, self.bot_role, self.other], [self.team])

    async def asyncTearDown(self):
        await database.close_db()
        self.temp.__exit__(None, None, None)

    async def test_everyone_and_an_apps_role_are_refused(self):
        self.assertIsNone(await self.gp.role_problem(self.guild, self.staff))
        self.assertIsNone(await self.gp.role_problem(self.guild, self.other))
        self.assertIn(self.everyone.mention, await self.gp.role_problem(self.guild, self.everyone))
        self.assertIn(self.bot_role.mention, await self.gp.role_problem(self.guild, self.bot_role))

    async def test_two_admins_changing_the_list_keep_both_changes(self):
        config_store.set_guild_values(self.guild.id, access.GAME_PANEL, {"staff_role_ids": [300]})
        manager_a = self.gp.GamePanelManager(self.guild)
        select_a = next(c for c in manager_a.children if isinstance(c, discord.ui.RoleSelect))
        config_store.set_guild_values(self.guild.id, access.GAME_PANEL, {"staff_role_ids": [300, 304]})  # admin B adds
        select_a._values = []  # admin A removes 300 in the menu opened before B's change
        with mock.patch.object(discord.ui.RoleSelect, "values", property(lambda s: s._values)):
            inter = fakes.Interaction()
            inter.guild, inter.guild_id = self.guild, self.guild.id
            await select_a.callback(inter)
        self.assertEqual(access.staff_role_ids(self.guild.id), [304], "A's removal and B's addition both stay")

    async def test_warnings_for_a_big_role_and_a_public_channel(self):
        crowd = Role(305, "Everyone-ish", members=500)
        self.guild.roles[305] = crowd
        self.guild.member_count = 600
        config_store.set_guild_values(self.guild.id, access.GAME_PANEL, {"staff_role_ids": [305]})
        embed = self.gp.GamePanelManager(self.guild).embed()
        self.assertIn("⚠️", str(embed.to_dict()))
        self.guild.default_role = Role(4242, "@everyone", default=True)
        inter = fakes.Interaction()
        inter.guild, inter.channel = self.guild, self.team
        text = await self.gp.post_panel(inter)
        self.assertIn("⚠️", text, "everyone can see the channel: the admin is told")

    async def test_an_old_panel_button_without_the_live_module_answers(self):
        from cogs import setup_roblox
        inter = fakes.Interaction()
        with mock.patch.object(setup_roblox, "live_game", None):
            await self.gp.open_action("eggs", inter)
        self.assertTrue(inter.response.sent and "❌" in inter.response.sent[-1][0])
        registered = self.gp.GamePanelView()
        self.assertEqual(len(registered.children), len(self.gp.BUTTONS))


class SmallerThings(unittest.IsolatedAsyncioTestCase):
    async def test_any_admin_may_close_the_servers_window(self):
        from cogs import setup
        with TempBot():
            view = setup.ServersView(mock.MagicMock(), fakes.Guild())
            view.to_components()
            close = next(c for c in view.children if isinstance(c, ui.CloseButton))
            with mock.patch("utils.access.is_bot_owner", mock.AsyncMock(return_value=False)):
                co_admin = fakes.Interaction()
                co_admin.data = {"custom_id": close.custom_id}
                self.assertTrue(await view.interaction_check(co_admin), "a co-admin may close it")
                change = fakes.Interaction()
                change.data = {"custom_id": "servers:add"}
                self.assertFalse(await view.interaction_check(change), "but only the owner may change the list")
                self.assertTrue(change.response.sent)


if __name__ == "__main__":
    unittest.main()
