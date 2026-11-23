"""Permissions per feature (utils/access.py): a role gets only what an administrator ticked for it, commands and windows
check the same permission, the old staff_role_ids keep everything, and the list for the game's Manager has the shape the
game reads. No network: Open Cloud is replaced."""
import unittest
from unittest import mock

from tests import test_access as ta
from tests.helpers import TempBot
from tests.panel_fakes import OTHER, STAFF, interaction_for, make_guild
from utils import access, config_store

import main  # noqa: E402


class Roles(unittest.TestCase):
    def setUp(self):
        self.env = TempBot({"bot_settings": {"home_guild_ids": [ta.HOME]}})
        self.env.__enter__()
        self.addCleanup(self.env.__exit__, None, None, None)

    def test_the_lists_are_what_the_panels_show(self):
        self.assertEqual(access.PERMISSIONS, ["codes", "events", "eggs", "gifts", "announce", "players", "bans"])
        self.assertEqual(access.GAME_PERMISSIONS, [p for p in access.PERMISSIONS if p != "players"] + ["settings"],
                         "the Manager shows players to everyone allowed: no player card permission there")
        self.assertTrue(set(access.COMMAND_PERMISSIONS.values()) <= set(access.PERMISSIONS))

    def test_old_staff_role_ids_have_every_permission(self):
        config_store.set_guild_values(ta.HOME, access.GAME_PANEL, {"staff_role_ids": [STAFF, "302"]})
        self.assertEqual(access.role_permissions(ta.HOME), {STAFF: access.PERMISSIONS, 302: access.PERMISSIONS})
        self.assertEqual(sorted(access.staff_role_ids(ta.HOME)), [STAFF, 302])

    def test_everyone_is_never_a_role_even_saved_by_hand(self):
        config_store.set_guild_values(ta.HOME, access.GAME_PANEL, {
            "staff_role_ids": [ta.HOME], "role_permissions": {str(ta.HOME): ["codes", "bans"], str(STAFF): ["codes"]}})
        self.assertEqual(access.role_permissions(ta.HOME), {STAFF: ["codes"]})
        saved = access.set_role_permissions(ta.HOME, {ta.HOME: ["codes"], STAFF: ["eggs"]})
        self.assertEqual(saved, {STAFF: ["eggs"]})

    def test_the_everyone_role_does_not_open_anything_for_a_player(self):
        guild = make_guild()
        config_store.set_guild_values(guild.id, access.GAME_PANEL, {"role_permissions": {str(guild.id): list(access.PERMISSIONS)}})
        for perm in access.PERMISSIONS:
            self.assertFalse(access.can(interaction_for(guild, "player"), perm), perm)

    def test_saving_clears_the_old_list_and_drops_unknown_permissions(self):
        config_store.set_guild_values(ta.HOME, access.GAME_PANEL, {"staff_role_ids": [STAFF]})
        saved = access.set_role_permissions(ta.HOME, {STAFF: ["codes", "root", "settings"], OTHER: []})
        self.assertEqual(saved, {STAFF: ["codes"], OTHER: []})
        self.assertEqual(config_store.guild_section(ta.HOME, access.GAME_PANEL)["staff_role_ids"], [])
        self.assertEqual(access.staff_role_ids(ta.HOME), [STAFF], "a role with nothing ticked is not staff")

    def test_a_role_with_one_permission_can_only_do_that(self):
        guild = make_guild()
        access.set_role_permissions(guild.id, {STAFF: ["codes"]})
        staff, player, admin = (interaction_for(guild, w) for w in ("staff", "player", "admin"))
        self.assertTrue(access.is_game_staff(staff))
        for perm in access.PERMISSIONS:
            self.assertEqual(access.can(staff, perm), perm == "codes", perm)
            self.assertFalse(access.can(player, perm), perm)
            self.assertTrue(access.can(admin, perm), perm)
        self.assertFalse(access.is_game_staff(player))

    def test_permissions_of_several_roles_add_up(self):
        guild = make_guild()
        access.set_role_permissions(guild.id, {STAFF: ["codes"], OTHER: ["bans"]})
        inter = interaction_for(guild, "staff")
        inter.user.roles = [guild.roles[STAFF], guild.roles[OTHER]]
        self.assertEqual(access.member_permissions(inter), {"codes", "bans"})


class Commands(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = TempBot({"bot_settings": {"home_guild_ids": [ta.HOME]}})
        self.env.__enter__()
        if not main.bot.cogs:
            await main.load_extensions()

    async def asyncTearDown(self):
        self.env.__exit__(None, None, None)

    async def run_command(self, name, roles=()):
        command = main.bot.tree.get_command(name)
        inter = ta.Interaction(command)
        inter.user.roles = [type("R", (), {"id": r})() for r in roles]
        with mock.patch.object(main.bot, "get_guild", lambda guild_id: object()):
            return await main.global_command_check(inter), inter

    async def test_a_role_with_codes_may_add_a_code_but_not_ban(self):
        access.set_role_permissions(ta.HOME, {STAFF: ["codes"]})
        for name in ("code-add", "code-remove"):
            ok, _ = await self.run_command(name, [STAFF])
            self.assertTrue(ok, name)
        ok, inter = await self.run_command("roblox-ban", [STAFF])
        self.assertFalse(ok)
        self.assertEqual(inter.response.sent[0], main.t("perm.no_access", what=main.t("perm.bans")))
        for name in ("give", "announce-game", "event-start", "egg-create", "roblox-ban-check", "roblox-unban"):
            ok, _ = await self.run_command(name, [STAFF])
            self.assertFalse(ok, name)

    async def test_a_player_without_the_role_and_the_admin_only_commands(self):
        access.set_role_permissions(ta.HOME, {STAFF: list(access.PERMISSIONS)})
        ok, _ = await self.run_command("code-add", [OTHER])
        self.assertFalse(ok)
        for name in ("setup", "setup-roblox", "sync-codes"):  # every game permission is still not an administrator
            ok, _ = await self.run_command(name, [STAFF])
            self.assertFalse(ok, name)

    async def test_the_old_staff_roles_may_use_every_game_command(self):
        config_store.set_guild_values(ta.HOME, access.GAME_PANEL, {"staff_role_ids": [STAFF]})
        for name in access.COMMAND_PERMISSIONS:
            ok, _ = await self.run_command(name, [STAFF])
            self.assertTrue(ok, name)

    async def test_the_public_commands_stay_public(self):
        for name in ("codes", "events", "eggs"):
            ok, _ = await self.run_command(name)
            self.assertTrue(ok, name)


class Windows(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = TempBot()
        self.env.__enter__()
        from cogs import setup_roblox
        self.panel = setup_roblox
        self.guild = make_guild()
        access.set_role_permissions(self.guild.id, {STAFF: ["codes"]})

    async def asyncTearDown(self):
        self.env.__exit__(None, None, None)

    async def test_codes_opens_and_eggs_does_not_for_a_role_with_codes(self):
        self.assertTrue(await self.panel.CodesView().interaction_check(interaction_for(self.guild, "staff")))
        inter = interaction_for(self.guild, "staff")
        self.assertFalse(await self.panel.EggsView().interaction_check(inter))
        self.assertEqual(inter.response.sent[0][0], main.t("perm.no_access", what=main.t("perm.eggs")))

    async def test_a_player_opens_nothing_and_an_admin_everything(self):
        for who, expected in (("player", False), ("admin", True)):
            for view in (self.panel.CodesView(), self.panel.EggsView(), self.panel.EventsView(), self.panel.GiftsView()):
                self.assertEqual(await view.interaction_check(interaction_for(self.guild, who)), expected, (who, type(view)))

    async def test_each_window_names_its_permission(self):
        expected = {self.panel.CodesView: "codes", self.panel.EggsView: "eggs", self.panel.EventsView: "events",
                    self.panel.GiftsView: "gifts"}
        for cls, perm in expected.items():
            self.assertEqual(cls().permission, perm, cls.__name__)


class ManagerList(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = TempBot()
        self.env.__enter__()

    async def asyncTearDown(self):
        self.env.__exit__(None, None, None)

    def test_the_entry_has_the_shape_the_game_reads(self):
        access.set_manager_users([{"user_id": 123, "name": "Builderman", "permissions": ["codes", "settings", "root"]},
                                  {"user_id": "456", "name": "Roblox", "permissions": []},
                                  {"user_id": 123, "name": "Duplicate", "permissions": ["bans"]}])
        entry = access.manager_access_entry()
        self.assertGreater(entry.pop("updated_at"), 0, "the game and the bot see which side changed it last")
        self.assertEqual(entry, {"version": 1, "users": {
            "123": {"name": "Builderman", "permissions": ["codes", "settings"]},
            "456": {"name": "Roblox", "permissions": []}}})

    def test_the_list_the_owner_saved_in_the_game_is_taken(self):
        access.set_manager_users([{"user_id": 1, "name": "Old", "permissions": ["codes"]}], updated_at=100)
        game = {"version": 1, "updated_at": 200, "by": "game", "users": {
            "777": {"name": "Builder", "permissions": ["events", "root"]}, "x": {}, "5": "garbage"}}
        self.assertTrue(access.adopt_manager_entry(game))
        self.assertEqual(access.manager_users(), [{"user_id": 777, "name": "Builder", "permissions": ["events"]}])
        self.assertEqual(access.manager_updated_at(), 200, "kept as the game's time: not newer than the game's list")

    def test_an_older_list_from_the_game_does_not_undo_a_change_here(self):
        access.set_manager_users([{"user_id": 1, "name": "New", "permissions": ["codes"]}], updated_at=300)
        self.assertFalse(access.adopt_manager_entry({"version": 1, "updated_at": 200, "users": {}}))
        self.assertFalse(access.adopt_manager_entry(None))
        self.assertFalse(access.adopt_manager_entry({"users": "garbage"}))
        self.assertEqual([u["name"] for u in access.manager_users()], ["New"])

    async def test_opening_the_list_reads_the_game_first(self):
        from cogs import game_panel
        from utils import open_cloud
        access.set_manager_users([], updated_at=1)
        read = mock.AsyncMock(return_value={"version": 1, "updated_at": 50, "users": {"9": {"name": "N", "permissions": ["bans"]}}})
        with mock.patch.object(open_cloud, "live_settings", return_value={"datastore": "Store"}), \
                mock.patch.object(open_cloud, "read_entry", read):
            self.assertTrue(await game_panel.pull_manager_access())
            self.assertFalse(await game_panel.pull_manager_access(), "nothing new the second time")
        read.assert_awaited_with("Store", game_panel.MANAGER_ENTRY)
        self.assertEqual(access.manager_users(), [{"user_id": 9, "name": "N", "permissions": ["bans"]}])

    async def test_reading_the_game_quietly_keeps_the_list_when_it_is_not_connected(self):
        from cogs import game_panel
        from utils import open_cloud
        access.set_manager_users([{"user_id": 3, "name": "K", "permissions": []}])
        with mock.patch.object(open_cloud, "live_settings", side_effect=Exception("not set up")):
            self.assertFalse(await game_panel.pull_manager_access())
        self.assertEqual([u["user_id"] for u in access.manager_users()], [3])

    def test_an_empty_or_broken_list_gives_no_users(self):
        self.assertEqual(access.manager_access_entry(), {"version": 1, "updated_at": 0, "users": {}})
        config_store.set_values([("game_manager", "users", "garbage")])
        self.assertEqual(access.manager_users(), [])
        config_store.set_values([("game_manager", "users", [None, {"user_id": "x"}, {"user_id": 7, "permissions": "codes"}])])
        self.assertEqual(access.manager_users(), [{"user_id": 7, "name": "", "permissions": []}])

    def test_the_list_is_capped(self):
        access.set_manager_users([{"user_id": i + 1, "name": "n", "permissions": []} for i in range(access.MAX_MANAGER_USERS + 5)])
        self.assertEqual(len(access.manager_users()), access.MAX_MANAGER_USERS)

    async def test_push_returns_the_reason_when_open_cloud_fails(self):
        from cogs import game_panel
        from utils import open_cloud
        with mock.patch.object(open_cloud, "live_settings", return_value={"datastore": "Store"}), \
                mock.patch.object(open_cloud, "read_entry_versioned", mock.AsyncMock(return_value=(None, None))), \
                mock.patch.object(open_cloud, "write_entry_if", mock.AsyncMock(side_effect=RuntimeError("HTTP 403 denied"))), \
                mock.patch.object(open_cloud, "publish", mock.AsyncMock()) as publish:
            text = await game_panel.push_manager_access()
        self.assertIn("403", text)
        publish.assert_not_awaited()

    async def test_push_writes_the_entry_and_sends_a_notice(self):
        from cogs import game_panel
        from utils import open_cloud
        access.set_manager_users([{"user_id": 9, "name": "N", "permissions": ["codes"]}])
        write, publish = mock.AsyncMock(), mock.AsyncMock()
        with mock.patch.object(open_cloud, "live_settings", return_value={"datastore": "Store"}), \
                mock.patch.object(open_cloud, "read_entry_versioned", mock.AsyncMock(return_value=(None, None))), \
                mock.patch.object(open_cloud, "write_entry_if", write), mock.patch.object(open_cloud, "publish", publish):
            self.assertEqual(await game_panel.push_manager_access(), "")
        write.assert_awaited_once_with("Store", game_panel.MANAGER_ENTRY, access.manager_access_entry(), None)
        self.assertEqual(publish.await_args.args[0]["type"], "access")

    async def test_a_change_on_discord_never_undoes_one_made_in_the_game(self):
        from cogs import game_panel
        from utils import open_cloud
        access.set_manager_users([{"user_id": 5, "name": "Removed", "permissions": ["codes"]}], updated_at=100)
        # the owner removed player 5 in the game and added 7; then saves again just while the bot writes
        game = {"version": 1, "updated_at": 150, "users": {"7": {"name": "Seven", "permissions": ["events"]}}}
        later = {"version": 1, "updated_at": 160, "users": {"7": {"name": "Seven", "permissions": ["events"]},
                                                             "8": {"name": "Eight", "permissions": []}}}
        read = mock.AsyncMock(side_effect=[(game, "v1"), (later, "v2")])
        write = mock.AsyncMock(side_effect=[open_cloud.VersionConflict(later, "v2"), None])
        with mock.patch.object(open_cloud, "live_settings", return_value={"datastore": "Store"}), \
                mock.patch.object(open_cloud, "read_entry_versioned", read), \
                mock.patch.object(open_cloud, "write_entry_if", write), mock.patch.object(open_cloud, "publish", mock.AsyncMock()):

            def tick(users):
                for user in users:
                    if user["user_id"] == 7:
                        user["permissions"] = ["events", "bans"]
                return users

            self.assertEqual(await game_panel.change_manager_access(tick), "")
        sent = write.await_args.args[2]
        self.assertEqual(write.await_args.args[3], "v2", "saved only over the version it read")
        self.assertEqual(set(sent["users"]), {"7", "8"}, "the removed player stays removed, the game's new one stays")
        self.assertEqual(sent["users"]["7"]["permissions"], ["events", "bans"], "the change from Discord is in")
        self.assertGreater(sent["updated_at"], 160)

    async def test_when_the_game_cant_be_read_nothing_is_changed_or_sent(self):
        from cogs import game_panel
        from utils import open_cloud
        access.set_manager_users([{"user_id": 5, "name": "A", "permissions": []}])
        write = mock.AsyncMock()
        with mock.patch.object(open_cloud, "live_settings", return_value={"datastore": "Store"}), \
                mock.patch.object(open_cloud, "read_entry_versioned", mock.AsyncMock(side_effect=RuntimeError("HTTP 503"))), \
                mock.patch.object(open_cloud, "write_entry_if", write):
            text = await game_panel.change_manager_access(lambda users: [])
        self.assertIn("503", text)
        write.assert_not_awaited()
        self.assertEqual([u["user_id"] for u in access.manager_users()], [5], "the old list could undo the game's")

    async def test_push_without_game_settings_returns_text_not_an_exception(self):
        from cogs import game_panel
        from utils import open_cloud
        with mock.patch.object(open_cloud, "live_settings", side_effect=Exception("")):
            text = await game_panel.push_manager_access()
        self.assertTrue(text)


if __name__ == "__main__":
    unittest.main()


class OwnerProtection(unittest.IsolatedAsyncioTestCase):
    """A role with "bans" can't ban the game's owner from Discord, and the gift draft checks "gifts"."""

    async def asyncSetUp(self):
        self.env = TempBot({"bot_settings": {"home_guild_ids": [ta.HOME]}})
        self.env.__enter__()
        self.addAsyncCleanup(self._close)

    async def _close(self):
        self.env.__exit__(None, None, None)

    async def test_the_games_owner_is_never_banned(self):
        from cogs import roblox_admin
        admin = mock.Mock(id=5, mention="@admin")
        with mock.patch.object(roblox_admin.roblox_api, "game_owner_id", mock.AsyncMock(return_value=42)), \
                mock.patch.object(roblox_admin.open_cloud, "set_ban", mock.AsyncMock()) as ban:
            text = await roblox_admin.ban_player(None, admin, 42, "Owner", 0, "x")
        ban.assert_not_called()
        self.assertEqual(text, roblox_admin.t("rban.owner_protected", username="Owner"))

    async def test_the_gift_draft_checks_gifts(self):
        from cogs import game_codes
        calls = []

        async def fake(interaction, permission=None):
            calls.append(permission)
            return True

        interaction = mock.Mock()
        interaction.user.id = 7
        with mock.patch.object(game_codes, "staff_only", fake):
            await game_codes.owner_and_staff(interaction, 7, "gifts")
            await game_codes.owner_and_staff(interaction, 7)
        self.assertEqual(calls, ["gifts", "codes"])
        import inspect
        from cogs import setup_roblox
        self.assertIn('owner_and_staff(interaction, self.admin_id, "gifts")', inspect.getsource(setup_roblox.GiftDraftView))
