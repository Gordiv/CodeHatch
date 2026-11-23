"""Who may do what: a person with a staff role (chosen in /setup-roblox -> Control panel) may use the game actions and
never a configuration window; a player may use nothing; the check is made at every click (also in a window that was
opened before the role was taken away), by discord.py's own dispatch, not only by calling interaction_check.

Windows come from tests/panel_catalog.py, so a new window must be classified here before the tests pass."""
import ast
import glob
import os
import unittest
from unittest import mock

import discord

from tests import fakes
from tests.helpers import ROOT, TempBot
from tests.panel_catalog import all_modal_classes, build_windows, import_every_module
from tests.panel_fakes import OTHER, STAFF, Member, interaction_for, make_guild
from utils import access, config_store, database, ui

# Windows for game actions: administrators and the staff roles (windows of one person: that person only)
GAME = {"CodesView", "EggsView", "EventsView", "GiftsView", "PlayerChoiceView", "PlayerCardView", "UnbanConfirmView",
        "CodeRemoveView", "OverwriteView", "CodeDraftView", "GiftDraftView", "StaffView", "EggDoneView", "EventDoneView",
        "AnnounceFixView"}
# Not checked on purpose: a close button / text to read (ephemeral, only the person who got it sees it), a ban
# confirmation only the administrator who ran the admin command can click
NOT_FOR_STAFF_TEST = {"CloseView", "GuideView", "BanConfirmView"}

# Forms for game actions must check the role again when they are sent (the role may be taken away while one is open)
GAME_FORMS = {"CodeModal", "EggModal", "EventModal", "GiftModal", "AnnounceModal", "PlayerLookupModal", "BanModal",
              "CodeExtrasModal", "GiftExtrasModal"}
# Forms of the configuration are reachable only from administrator windows (checked at every click there); a window
# can't be opened by a staff role.
CONFIG_FORMS = {"GameModal", "EconomyModal", "ApiKeyModal", "AddServerModal", "LeaderboardModal",
                "AddManagerUserModal"}  # AddManagerUserModal: a configuration form (a Roblox player for the Manager), not a game action


async def dispatch(view, item, interaction):
    """What discord.py does for a click: refresh the item, run the checks, then the callback. The callback is replaced
    by a mock, so the result says whether it would have run."""
    item.callback = mock.AsyncMock()
    data = {"custom_id": getattr(item, "custom_id", None)}
    if isinstance(item, discord.ui.Select):
        data["values"] = [item.options[0].value] if getattr(item, "options", None) else []
    interaction.data = data
    await view._scheduled_task(item, interaction)
    return item.callback


class Staff(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        import_every_module()
        self.guild = make_guild([STAFF])
        self.owner_patch = mock.patch("utils.access.is_bot_owner", mock.AsyncMock(return_value=True))
        self.owner_patch.start()

    async def asyncTearDown(self):
        self.owner_patch.stop()
        await database.close_db()
        self.temp.__exit__(None, None, None)

    def classify(self, windows):
        game, config, rest = [], [], []
        for name, view in windows:
            kind = type(view).__name__
            (game if kind in GAME else rest if kind in NOT_FOR_STAFF_TEST else config).append((name, view))
        return game, config, rest

    async def test_a_staff_role_and_a_player_reach_no_configuration_window(self):
        windows = await build_windows(self.guild, owner_id=7)  # configuration windows belong to an administrator (id 7)
        game, config, rest = self.classify(windows)
        self.assertGreaterEqual(len(config), 11, "the configuration windows are really there")
        for name, view in config:
            view.to_components()  # adds the Close button too
            for item in view.children:
                for who in ("staff", "player"):
                    inter = interaction_for(self.guild, who)
                    callback = await dispatch(view, item, inter)
                    where = f"{name} / {getattr(item, 'label', None) or type(item).__name__} / {who}"
                    self.assertEqual(callback.await_count, 0, where)
                    self.assertTrue(inter.response.sent, f"{where}: the person is told no")
                    self.assertTrue(inter.response.sent[-1][1].get("ephemeral"), where)

    async def test_administrators_still_use_every_configuration_window(self):
        windows = await build_windows(self.guild, owner_id=7)  # fakes.Admin has id 7
        _, config, _ = self.classify(windows)
        for name, view in config:
            view.to_components()
            for item in view.children:
                inter = interaction_for(self.guild, "admin")
                callback = await dispatch(view, item, inter)
                self.assertEqual(callback.await_count, 1, f"{name} / {type(item).__name__} / admin")

    async def test_game_windows_let_the_staff_role_and_administrators_in_and_players_out(self):
        for owner, who in ((50, "staff"), (7, "admin")):
            game, _, _ = self.classify(await build_windows(self.guild, owner_id=owner))
            self.assertGreaterEqual(len(game), 12)
            for name, view in game:
                view.to_components()
                for item in view.children:
                    inter = interaction_for(self.guild, who)
                    callback = await dispatch(view, item, inter)
                    self.assertEqual(callback.await_count, 1, f"{name} / {type(item).__name__} / {who}")
                    self.assertFalse(inter.response.sent, f"{name}: no refusal for {who}")
        game, _, _ = self.classify(await build_windows(self.guild, owner_id=50))
        for name, view in game:
            for item in view.children:
                for who in ("player",):
                    inter = interaction_for(self.guild, who)
                    callback = await dispatch(view, item, inter)
                    self.assertEqual(callback.await_count, 0, name)
                    self.assertTrue(inter.response.sent, name)

    async def test_a_window_of_one_person_is_not_for_another_staff_member(self):
        windows = await build_windows(self.guild, owner_id=50)
        other_staff = Member([self.guild.roles[STAFF]], user_id=52)
        for name, view in windows:
            if type(view).__name__ not in ("CodeRemoveView", "OverwriteView", "CodeDraftView"):
                continue
            for item in view.children:
                inter = interaction_for(self.guild, "staff")
                inter.user = other_staff
                callback = await dispatch(view, item, inter)
                self.assertEqual(callback.await_count, 0, name)
                self.assertTrue(inter.response.sent, name)

    async def test_taking_the_role_away_works_in_a_window_opened_before(self):
        windows = await build_windows(self.guild, owner_id=50)
        game, _, _ = self.classify(windows)
        config_store.set_guild_values(self.guild.id, access.GAME_PANEL, {"staff_role_ids": []})
        for name, view in game:
            for item in view.children:
                inter = interaction_for(self.guild, "staff")
                callback = await dispatch(view, item, inter)
                self.assertEqual(callback.await_count, 0, name)
                self.assertTrue(inter.response.sent and "❌" in inter.response.sent[-1][0], name)
        config_store.set_guild_values(self.guild.id, access.GAME_PANEL, {"staff_role_ids": [OTHER]})  # another role
        for name, view in game:
            inter = interaction_for(self.guild, "staff")
            self.assertFalse(await view.interaction_check(inter), name)

    async def test_the_posted_panel_buttons(self):
        from cogs import game_panel
        view = game_panel.GamePanelView()
        self.assertTrue(view.is_persistent())
        for who, allowed in (("admin", True), ("staff", True), ("player", False)):
            for item in view.children:
                inter = interaction_for(self.guild, who)
                callback = await dispatch(view, item, inter)
                where = f"{item.custom_id} / {who}"
                if allowed:
                    callback.assert_awaited_once()
                else:
                    callback.assert_not_awaited()
                    self.assertTrue(inter.response.sent and "❌" in inter.response.sent[-1][0], where)

    async def test_nobody_without_a_role_gets_through_a_missing_or_broken_list(self):
        for raw in (None, "300", [None, "x", -5, 1.5, True], {"300": 1}):
            config_store.set_guild_values(self.guild.id, access.GAME_PANEL, {"staff_role_ids": raw})
            self.assertFalse(access.is_game_staff(interaction_for(self.guild, "staff")), repr(raw))
            self.assertFalse(access.is_game_staff(interaction_for(self.guild, "player")), repr(raw))
            self.assertTrue(access.is_game_staff(interaction_for(self.guild, "admin")), repr(raw))
        direct = interaction_for(self.guild, "staff")
        direct.guild = None  # a private message
        self.assertFalse(access.is_game_staff(direct))

    async def test_everyone_saved_by_hand_in_the_list_does_not_open_the_panel_to_all_players(self):
        # LOW (defence in depth): the settings window refuses @everyone, but utils/access.py is_game_staff() trusts the
        # saved list: with the server's own ID in it (edited by hand, or saved by an older version) every player has
        # that "role" and gets bans and gifts
        config_store.set_guild_values(self.guild.id, access.GAME_PANEL, {"staff_role_ids": [self.guild.id]})
        self.assertFalse(access.is_game_staff(interaction_for(self.guild, "player")))

    async def test_a_staff_role_is_not_an_administrator_for_commands(self):
        required = discord.Permissions(administrator=True)
        self.assertFalse(access.has_permissions(interaction_for(self.guild, "staff"), required))
        self.assertFalse(access.is_admin(interaction_for(self.guild, "staff")))
        self.assertTrue(access.has_permissions(interaction_for(self.guild, "admin"), required))

    async def test_the_role_check_survives_a_member_without_roles_data(self):
        inter = interaction_for(self.guild, "staff")
        inter.user = type("Bare", (), {"id": 53, "guild_permissions": discord.Permissions.none()})()
        self.assertFalse(access.is_game_staff(inter))


class Forms(unittest.TestCase):
    def test_every_form_is_classified_and_the_game_forms_check_the_role_when_sent(self):
        import_every_module()
        known = GAME_FORMS | CONFIG_FORMS
        found = {cls.__name__: cls for cls in all_modal_classes()}
        self.assertEqual(sorted(set(found) - known), [], "a new form: say whether it is a game action (staff check) or not")
        self.assertEqual(sorted(known - set(found)), [], "a form that no longer exists is still in the list")
        for name in sorted(GAME_FORMS):
            path = os.path.join(ROOT, "cogs", found[name].__module__.split(".")[1] + ".py")
            with open(path, encoding="utf-8") as source:
                tree = ast.parse(source.read())
            cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == name)
            submit = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "on_submit")
            first = ast.unparse(submit.body[0])
            self.assertIn("staff_only(interaction, ", first, f"{name}: the first thing on_submit does is the role check")


if __name__ == "__main__":
    unittest.main()
