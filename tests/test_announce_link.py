"""An announcement with a link is not sent: Roblox's filter shows a whole text with a link as #### (published game,
2026-10-17), so every player would see only ####. The admin gets the text back: /announce-game prints it to copy,
the form gets a ✏️ Fix button that opens it again filled in. Gifts with a link: tests/test_gift_draft.py."""
import unittest
from unittest import mock

from tests.fakes import Interaction, check_modal, check_view
from tests.helpers import TempBot
from utils import database, open_cloud


class AnnouncementWithALink(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import live_game, setup_roblox
        self.live, self.panel = live_game, setup_roblox
        self.published = []

        async def publish(message):
            self.published.append(message)

        self.patch = mock.patch.object(open_cloud, "publish", publish)
        self.patch.start()

    async def asyncTearDown(self):
        self.patch.stop()
        await database.close_db()
        self.temp.__exit__(None, None, None)

    def test_what_counts_as_a_link(self):
        for text in ("https://example.com", "see http://a.b", "www.roblox.com", "discord.gg/abc", "Join our DISCORD.GG/x",
                     "roblox.com/groups/1", "my-game.xyz", "shop at example.pl!", "youtu.be/abc", "linktr.ee/me",
                     "discord . gg/abc", "game.mx"):
            self.assertTrue(self.live.has_link(text), text)
        for text in ("Update 1.2 is out", "2x coins this weekend!", "lvl.5 players", "", None, "v2.0.1", "Mr.Bean",
                     "Awww. Thanks for 1000 players!", "Owww. Server restart in 5 min", "and/or",
                     "Super.To nowy event", "Wow.Co nowego?", "New event.Fun for all", "km/h"):
            self.assertFalse(self.live.has_link(text), text)

    async def test_the_command_refuses_and_gives_the_text_back(self):
        inter = Interaction()
        cog = self.live.LiveGame.__new__(self.live.LiveGame)
        await self.live.LiveGame.announce_game.callback(cog, inter, "Codes on `discord.gg/abc`!")
        self.assertEqual(self.published, [], "nothing reaches the game")
        said = inter.followup.sent[-1][0]
        self.assertTrue(said.startswith("❌"), said)
        self.assertIn("Codes on 'discord.gg/abc'!", said, "the text to copy, without backticks that would break the block")
        self.assertTrue(inter.followup.sent[-1][1]["ephemeral"])
        self.assertIn(self.live.t("announce.link_hint_command"), said, "where to send it anyway if it is not a link")

    async def test_without_a_link_it_is_sent(self):
        self.assertTrue(await self.live.announce("2x coins this weekend!", 15))
        self.assertEqual(self.published, [{"type": "announce", "text": "2x coins this weekend!", "seconds": 15}])

    def link_form(self, text="Join us: discord.gg/abc", seconds="30"):
        modal = self.panel.AnnounceModal()
        check_modal(modal)
        modal.text._value = text
        modal.seconds._values = [seconds]
        return modal

    async def refused(self):
        inter = Interaction()
        await self.link_form().on_submit(inter)
        self.assertEqual(self.published, [])
        content, kwargs = inter.followup.sent[-1]
        self.assertTrue(content.startswith("❌"), content)
        self.assertIsInstance(kwargs["view"], self.panel.AnnounceFixView)
        check_view(kwargs["view"])
        return kwargs["view"]

    async def test_fix_opens_the_form_filled_in_and_answers_in_the_same_message(self):
        view = await self.refused()
        click = Interaction()
        await view.fix.callback(click)
        again = click.response.modals[-1]
        check_modal(again)
        self.assertEqual(again.text.default, "Join us: discord.gg/abc")
        self.assertEqual([o.value for o in again.seconds.options if o.default], ["30"])
        again.text._value = "2x coins this weekend!"
        again.seconds._values = ["30"]
        done = Interaction()
        await again.on_submit(done)
        self.assertEqual(self.published[-1]["text"], "2x coins this weekend!")
        self.assertEqual(done.followup.sent, [], "no new message: the refused one turns into the answer")
        self.assertIn("2x coins this weekend!", done.edited[-1]["content"])

    async def test_send_anyway_sends_it_once(self):
        view = await self.refused()
        click = Interaction()
        await view.send_anyway.callback(click)
        self.assertEqual(self.published, [{"type": "announce", "text": "Join us: discord.gg/abc", "seconds": 30}])
        again = Interaction()
        await view.send_anyway.callback(again)
        self.assertEqual(len(self.published), 1, "a double click sends it once")

    async def test_send_anyway_that_fails_keeps_the_text(self):
        view = await self.refused()

        async def broken(message):
            raise open_cloud.OpenCloudError("403 Forbidden")
        with mock.patch.object(open_cloud, "publish", broken):
            click = Interaction()
            await view.send_anyway.callback(click)
        again = click.edited[-1]["view"]
        self.assertIsInstance(again, self.panel.AnnounceFixView, "nothing was sent: ✏️ still has the text")
        self.assertEqual((again.text, again.seconds), ("Join us: discord.gg/abc", 30))

    async def test_other_refusals_get_no_fix_button(self):
        async def broken(message):
            raise open_cloud.OpenCloudError("403 Forbidden")
        with mock.patch.object(open_cloud, "publish", broken):
            inter = Interaction()
            await self.link_form(text="2x coins this weekend!").on_submit(inter)
        self.assertNotIsInstance(inter.followup.sent[-1][1]["view"], self.panel.AnnounceFixView,
                                 "the text is fine: fixing it would not help")


if __name__ == "__main__":
    unittest.main()
