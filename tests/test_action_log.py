"""The log channel: changes to the game made on Discord (codes, eggs, events, gifts, announcements) are written there,
like the requests from the game's ⚙️ Manager and the bans. A refused change is not written; a broken log channel never
breaks the change itself."""
from unittest import mock

from tests import fakes
from tests.test_egg_panel import EggSetup
from utils import action_log, config_store, database


class ActionLog(EggSetup):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        patch = mock.patch.object(config_store, "guild_section", return_value={"log_channel_id": 500})
        patch.start()
        self.patches.append(patch)

    def logged(self, inter) -> str:
        self.assertEqual(len(inter.guild.log.sent), 1, inter.guild.log.sent)
        line = inter.guild.log.sent[0]
        self.assertIn(inter.user.mention, line, "who did it")
        return line

    async def test_a_new_egg_from_the_panel(self):
        modal = self.fill(self.panel.EggModal(), "Ice Egg", "250", "Cat:1, Dog:1", "Coins", "0")
        inter = fakes.Interaction()
        await modal.on_submit(inter)
        line = self.logged(inter)
        self.assertIn(action_log.kind_label("egg_create"), line)
        self.assertIn("Ice Egg", line)

    async def test_a_refused_egg_is_not_written(self):
        modal = self.fill(self.panel.EggModal(), "Ice Egg", "250", "not a pet list", "Coins", "0")
        inter = fakes.Interaction()
        await modal.on_submit(inter)
        self.assertEqual(inter.guild.log.sent, [])

    async def test_egg_menus_command_and_removal(self):
        egg = await self.make_egg()
        done = self.panel.EggDoneView(egg["id"])
        done.color._values = ["gold"]
        inter = fakes.Interaction()
        await done.color.callback(inter)
        self.assertIn(action_log.kind_label("egg_edit"), self.logged(inter))

        cog = self.live.LiveGame.__new__(self.live.LiveGame)
        inter = fakes.Interaction()
        await cog.egg_edit.callback(cog, inter, str(egg["id"]), price=900)
        self.assertIn(action_log.kind_label("egg_edit"), self.logged(inter))

        inter = fakes.Interaction()
        await self.panel.EggDoneView(egg["id"]).remove.callback(inter)
        line = self.logged(inter)
        self.assertIn(action_log.kind_label("egg_remove"), line)
        self.assertIn("Dragon Egg", line)
        inter = fakes.Interaction()
        await self.panel.EggDoneView(egg["id"]).remove.callback(inter)  # already gone: nothing new happened
        self.assertEqual(inter.guild.log.sent, [])

    async def test_event_start_and_stop(self):
        modal = self.panel.EventModal()
        modal.event_name._value, modal.duration._values = "Weekend", ["3h"]
        modal.kind._values, modal.value._values = ["exp"], ["2"]
        inter = fakes.Interaction()
        await modal.on_submit(inter)
        line = self.logged(inter)
        self.assertIn(action_log.kind_label("event_start"), line)
        self.assertIn("Weekend", line)
        done = inter.followup.sent[-1][1]["view"]
        inter = fakes.Interaction()
        await done.end.callback(inter)
        self.assertIn(action_log.kind_label("event_stop"), self.logged(inter))

    async def test_codes_from_the_panel(self):
        from cogs import game_codes
        cog = game_codes.GameCodes.__new__(game_codes.GameCodes)
        cog.bot = fakes.Client()
        inter = fakes.Interaction()
        await inter.response.defer()
        await cog.save_code(inter, "SPRING", "unlimited", "Coins", 50, 0, game_codes.NONE, "permanent", panel=True)
        line = self.logged(inter)
        self.assertIn(action_log.kind_label("code_add"), line)
        self.assertIn("SPRING", line)
        inter = fakes.Interaction()
        await cog.code_remove.callback(cog, inter, "spring")
        self.assertIn(action_log.kind_label("code_remove"), self.logged(inter))

    async def test_announcement_command(self):
        cog = self.live.LiveGame.__new__(self.live.LiveGame)
        inter = fakes.Interaction()
        with mock.patch.object(self.live, "announce", mock.AsyncMock(return_value="📢 Sent: Hello")):
            await cog.announce_game.callback(cog, inter, "Hello")
        line = self.logged(inter)
        self.assertIn(action_log.kind_label("announce"), line)
        self.assertIn("Hello", line)

    async def test_no_channel_or_a_broken_one_never_breaks_the_change(self):
        egg = await self.make_egg()
        inter = fakes.Interaction()
        with mock.patch.object(config_store, "guild_section", return_value={}):
            await self.panel.EggDoneView(egg["id"]).remove.callback(inter)
        self.assertEqual(inter.guild.log.sent, [])
        self.assertFalse((await database.get_egg(egg["id"]))["active"])

        egg = await self.make_egg("Second Egg")
        inter = fakes.Interaction()

        async def broken(*args, **kwargs):
            raise RuntimeError("boom")

        inter.guild.log.send = broken
        await self.panel.EggDoneView(egg["id"]).remove.callback(inter)
        self.assertIn("Second Egg", inter.edited[-1]["content"], "the admin still gets the answer")

    async def test_codes_that_had_already_ended_are_not_a_change(self):
        from cogs import game_codes
        cog = game_codes.GameCodes.__new__(game_codes.GameCodes)
        cog.bot = fakes.Client()
        message, removed = await cog.remove_codes_counted(["NOPE"])
        self.assertEqual(removed, 0)
        self.assertIn("NOPE", message)
        self.assertEqual(await cog.remove_codes(["NOPE"]), message, "the old call gives the same text")

    async def test_the_log_never_pings_anyone(self):
        sent = []

        class Channel:
            async def send(self, text, **kwargs):
                sent.append(kwargs)

        inter = fakes.Interaction()
        inter.guild.get_channel = lambda channel_id: Channel()
        await action_log.discord_action(inter, "announce", "@everyone <@&1> hi")
        self.assertEqual(sent[0]["allowed_mentions"].to_dict()["parse"], [])

    def test_every_kind_has_a_label_in_every_language(self):
        from cogs import game_requests
        from utils import i18n
        self.assertLessEqual(set(game_requests.GameRequests.HANDLERS), set(action_log.KINDS), "the Manager's too")
        for lang in ("en", "pl", "es"):
            for kind in action_log.KINDS:
                self.assertTrue(i18n.has_key(f"actionlog.kind.{kind}", lang), (lang, kind))
        self.assertEqual(action_log.kind_label("something_new"), "something_new")

    async def test_long_answers_fit_in_one_message(self):
        inter = fakes.Interaction()
        await action_log.discord_action(inter, "gift", "x" * 5000)
        self.assertLessEqual(len(self.logged(inter)), 1900)
