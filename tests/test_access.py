"""K1/K2: commands work only on the owner's servers, never in DMs, and admin commands check the permission in code."""
import unittest
from unittest import mock

import discord

from tests.helpers import TempBot

import main  # noqa: E402  (creates the bot object, does not start it)
from utils import access  # noqa: E402

HOME, STRANGER = 111111111111111111, 222222222222222222


class Response:
    def __init__(self):
        self.sent = []

    def is_done(self):
        return bool(self.sent)

    async def send_message(self, text=None, **kwargs):
        self.sent.append(text)


class Followup:
    def __init__(self):
        self.sent = []

    async def send(self, text=None, **kwargs):
        self.sent.append(text)


class Interaction:
    def __init__(self, command, guild_id=HOME, permissions=None, owner=False):
        self.command = command
        self.guild_id = guild_id
        self.user = type("User", (), {"id": 5, "guild_permissions": permissions or discord.Permissions.none()})()
        self.guild = type("Guild", (), {"id": guild_id, "owner_id": 5 if owner else 9})() if guild_id else None
        self.permissions = permissions or discord.Permissions.none()
        self.response, self.followup = Response(), Followup()


class CommandAccess(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = TempBot({"bot_settings": {"home_guild_ids": [HOME]}})
        self.env.__enter__()
        if not main.bot.cogs:
            await main.load_extensions()
        self.assertEqual(main.bot.failed_extensions, [], "every module loads")

    async def asyncTearDown(self):
        self.env.__exit__(None, None, None)

    def command(self, name):
        parts = name.split()
        command = main.bot.tree.get_command(parts[0])
        for part in parts[1:]:
            command = command.get_command(part)
        return command

    async def check(self, name, **kwargs):
        interaction = Interaction(self.command(name), **kwargs)
        with mock.patch.object(main.bot, "get_guild", lambda guild_id: object()):
            return await main.global_command_check(interaction), interaction

    async def test_dm_is_refused(self):
        ok, interaction = await self.check("codes", guild_id=None)
        self.assertFalse(ok)
        self.assertTrue(interaction.response.sent)

    async def test_stranger_server_is_refused(self):
        ok, _ = await self.check("codes", guild_id=STRANGER, permissions=discord.Permissions.all())
        self.assertFalse(ok)

    async def test_admin_commands_need_admin_in_code(self):
        admin_commands = [c for c in main.bot.tree.walk_commands()
                          if isinstance(c, discord.app_commands.Command)
                          and ((c.root_parent or c).default_permissions or c.default_permissions)]
        names = {c.qualified_name for c in admin_commands}
        self.assertTrue(names.isdisjoint(access.COMMAND_PERMISSIONS), "permission commands are not admin-only any more")
        self.assertGreaterEqual(len(admin_commands), 6, "the setup, sync and leaderboard commands are admin commands")
        for command in admin_commands:
            ok, _ = await self.check(command.qualified_name)
            self.assertFalse(ok, f"/{command.qualified_name} runs for a member without permissions")
            ok, _ = await self.check(command.qualified_name, permissions=discord.Permissions(administrator=True))
            self.assertTrue(ok, f"/{command.qualified_name} refused for an administrator")

    async def test_permission_commands_need_their_permission_in_code(self):
        self.assertGreaterEqual(len(access.COMMAND_PERMISSIONS), 12)
        for name, perm in access.COMMAND_PERMISSIONS.items():
            command = self.command(name)
            self.assertFalse((command.root_parent or command).default_permissions or command.default_permissions, name)
            ok, interaction = await self.check(name)
            self.assertFalse(ok, f"/{name} runs for a member without a role")
            self.assertEqual(interaction.response.sent[0], main.t("perm.no_access", what=main.t(f"perm.{perm}")), name)
            ok, _ = await self.check(name, permissions=discord.Permissions(administrator=True))
            self.assertTrue(ok, f"/{name} refused for an administrator")

    async def test_player_commands(self):
        for name in ("codes", "help"):
            ok, _ = await self.check(name)
            self.assertTrue(ok, name)

    async def test_the_commands_of_the_game_bot_are_exactly_these(self):
        names = {c.qualified_name for c in main.bot.tree.walk_commands() if isinstance(c, discord.app_commands.Command)}
        self.assertEqual(names, {
            "help", "setup", "setup-guide", "setup-roblox", "tutorial", "sync-codes", "code-add", "code-remove", "codes",
            "give", "announce-game", "event-start", "event-stop", "events", "egg-create", "egg-edit", "egg-remove", "eggs",
            "roblox-ban", "roblox-unban", "roblox-ban-check", "leaderboard", "leaderboard-setup"})

    async def test_every_command_is_server_only(self):
        tree = main.bot.tree
        self.assertTrue(tree.allowed_contexts.guild and not tree.allowed_contexts.dm_channel
                        and not tree.allowed_contexts.private_channel)
        self.assertTrue(tree.allowed_installs.guild and not tree.allowed_installs.user)
        for command in tree.get_commands():
            payload = command.to_dict(tree)
            self.assertEqual(payload.get("contexts"), [0], f"/{command.name} must be a server-only command")
            self.assertEqual(payload.get("integration_types"), [0], f"/{command.name} must not be a user app")


class HomeServers(unittest.IsolatedAsyncioTestCase):
    async def test_list_and_migration(self):
        with TempBot():
            self.assertFalse(access.home_list_exists())
            self.assertFalse(access.is_home_guild(HOME))
            access.add_home_guild(HOME)
            self.assertTrue(access.home_list_exists() and access.is_home_guild(HOME))
            access.remove_home_guild(HOME)
            self.assertFalse(access.is_home_guild(HOME))

    async def test_trust_rules(self):
        owner = 42

        class Member:
            def __init__(self, perms):
                self.guild_permissions = perms

        class Guild:
            def __init__(self, owner_id, member=None):
                self.owner_id, self._member, self.id, self.name = owner_id, member, 7, "g"

            def get_member(self, user_id):
                return self._member

        with mock.patch.object(access, "bot_owner_ids", mock.AsyncMock(return_value={owner})):
            self.assertTrue(await access.owner_trusts(None, Guild(owner)))
            self.assertTrue(await access.owner_trusts(None, Guild(1, Member(discord.Permissions(manage_guild=True)))))
            self.assertFalse(await access.owner_trusts(None, Guild(1, Member(discord.Permissions.none()))))
            self.assertTrue(await access.owner_trusts(None, Guild(1, Member(discord.Permissions.none())), membership_enough=True))


if __name__ == "__main__":
    unittest.main()
