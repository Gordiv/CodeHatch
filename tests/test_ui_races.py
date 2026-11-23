"""Timers and races of the windows (utils/ui.py): a window replaced many times in a row, a form open when the window
expires, ✖️ clicked twice, the timers after a manual close, the end of Discord's right to edit with many answers in
place. Time is shortened by patching ui.PANEL_TIMEOUT (and the timeout of the window), never slept for real minutes."""
import asyncio
import time
import unittest
from unittest import mock

import discord

from tests import fakes
from tests.helpers import TempBot
from tests.panel_fakes import STAFF, LiveInteraction, Message, interaction_for, make_guild, not_found
from utils import database, ui


async def until(condition, seconds: float = 3.0) -> bool:
    """Waits (at most `seconds`) until condition() is true; True when it became true."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        await asyncio.sleep(0.01)
    return condition()


def close_button(view):
    view.to_components()
    return next(item for item in view.children if isinstance(item, ui.CloseButton))


class Store:
    """What discord.py gives a view when it is sent: a place to remove itself from (starts the view's own timeout)."""

    def remove_view(self, view):
        pass


class Replacing(unittest.IsolatedAsyncioTestCase):
    async def test_a_window_replaced_several_times_in_a_row_leaves_only_the_last_one_alive(self):
        with mock.patch.object(ui, "PANEL_TIMEOUT", 0.15):
            message = Message()
            ui._remember_token(message, fresh=True)
            windows = []
            for _ in range(6):
                window = ui.Panel()
                window.message = message  # an answer in place, six times
                windows.append(window)
            self.assertEqual([w.is_finished() for w in windows], [True] * 5 + [False])
            self.assertTrue(all(w._deadline_task is None for w in windows[:5]), "the old timers are cancelled")
            for old in windows[:5]:
                await old.on_timeout()  # even when an old timer still ran, it can't remove the new content
            self.assertEqual(message.delete_calls, 0)
            self.assertTrue(await until(lambda: message.deleted), "only the last window removes the message, at the end")
            self.assertEqual(message.delete_calls, 1, "removed exactly once")

    async def test_answers_in_place_move_the_end_of_the_token_and_the_message_is_removed_once(self):
        with mock.patch.object(ui, "PANEL_TIMEOUT", 0.6):
            first = LiveInteraction()
            view = ui.Panel()
            await ui.send_panel(first, view, content="start")
            seen = [view]
            began = time.monotonic()
            for step in range(5):  # 5 answers in place, 0.15 s apart: longer than one token lives (0.6 s)
                await asyncio.sleep(0.15)
                click = LiveInteraction(message=seen[-1].message)
                await click.response.defer()
                nxt = ui.Panel()
                await ui.show_in_place(click, view=nxt, content=str(step))
                self.assertEqual(nxt.message.id, seen[-1].message.id, "the same message")
                seen.append(nxt)
                self.assertFalse(any(v.message.deleted for v in seen), f"nothing removed while it is used (step {step})")
            self.assertGreater(time.monotonic() - began, 0.6, "longer than the token lives")
            self.assertEqual([v.is_finished() for v in seen], [True] * 5 + [False], "every older window stopped")
            last = seen[-1]
            self.assertTrue(await until(lambda: last.message.deleted), "after the last answer the window goes by itself")
            self.assertEqual(sum(v.message.delete_calls for v in seen), 1, "exactly one removal")

    async def test_the_old_window_may_still_try_to_remove_its_message_with_an_expired_token(self):
        message = Message(locked=True)  # the token ended: Discord refuses both delete and edit
        view = ui.Panel()
        view.add_item(discord.ui.Button(label="x"))
        view.message = message
        await view.on_timeout()  # must not raise
        self.assertTrue(all(item.disabled for item in view.children), "buttons turned off when nothing could be removed")


class ClosingTwice(unittest.IsolatedAsyncioTestCase):
    async def test_close_clicked_twice_on_the_same_message(self):
        view = ui.CloseView()
        message = Message()
        view.message = message
        button = close_button(view)
        first, second = LiveInteraction(message=message), LiveInteraction(message=message)
        await button.callback(first)
        self.assertTrue(first.deleted)
        self.assertTrue(view.is_finished())
        second.gone = True  # the second click comes after the message is gone: Discord answers "unknown message"
        await button.callback(second)  # must not raise
        self.assertEqual(second.response.defers, [{}], "answered once, nothing else sent")
        self.assertFalse(second.followup.sent)

    async def test_close_after_something_else_already_answered_the_click(self):
        view = ui.CloseView()
        button = close_button(view)
        inter = LiveInteraction()
        await inter.response.defer()
        await button.callback(inter)  # a second answer would raise in the strict stand-in
        self.assertTrue(inter.deleted)

    async def test_two_clicks_at_the_same_moment(self):
        view = ui.CloseView()
        view.message = Message()
        button = close_button(view)
        first, second = LiveInteraction(), LiveInteraction()
        await asyncio.gather(button.callback(first), button.callback(second))
        self.assertTrue(first.deleted and second.deleted)

    async def test_no_timer_touches_a_window_that_was_closed(self):
        with mock.patch.object(ui, "PANEL_TIMEOUT", 0.1):
            message = Message()
            ui._remember_token(message, fresh=True)
            view = ui.Panel(timeout=0.1)
            view.message = message
            view._start_listening_from_store(Store())  # the library's own timer runs too
            button = close_button(view)
            await button.callback(LiveInteraction(message=message))
            await asyncio.sleep(0.35)  # both timers would have fired by now
            self.assertEqual(message.delete_calls, 0, "no timer removes or edits a window the person already closed")
            self.assertEqual(message.edits, [])
            self.assertIsNone(view._deadline_task)

    async def test_on_timeout_called_by_hand_after_a_close_is_harmless(self):
        view = ui.CloseView()
        message = Message()
        view.message = message
        await close_button(view).callback(LiveInteraction(message=message))
        message.deleted = True  # as Discord has it after the close
        await view.on_timeout()  # must not raise (the delete fails, the edit fails: both are ignored)


class BothTimers(unittest.IsolatedAsyncioTestCase):
    async def test_the_library_timer_and_the_deadline_firing_together_remove_the_message_once(self):
        with mock.patch.object(ui, "PANEL_TIMEOUT", 0.1):
            message = Message()
            ui._remember_token(message, fresh=True)
            view = ui.Panel(timeout=0.1)
            view.message = message
            view._start_listening_from_store(Store())
            self.assertTrue(await until(lambda: message.deleted))
            await asyncio.sleep(0.3)
            self.assertEqual(message.delete_calls, 1)

    async def test_an_open_form_gives_a_running_window_more_time(self):
        with mock.patch.object(ui, "PANEL_TIMEOUT", 0.6):
            message = Message()
            ui._remember_token(message, fresh=True)
            view = ui.Panel(timeout=0.1)  # the 5 minutes of this test
            view.message = message
            view._start_listening_from_store(Store())
            view.hold_for_form()  # the person opens a form from this window
            await asyncio.sleep(0.3)
            self.assertFalse(view.is_finished(), "waiting for the form: not removed after the short idle time")
            self.assertFalse(message.deleted)
            self.assertTrue(await until(lambda: message.deleted, 2), "but not kept forever: removed at the end")

    async def test_a_window_without_a_message_object_never_fails(self):
        class NoMessage(LiveInteraction):
            async def original_response(self):
                raise not_found()
        inter = NoMessage()
        view = ui.Panel(timeout=0.05)
        await ui.send_panel(inter, view, content="x")
        self.assertIsNone(view.message)
        view.stop()
        await view.on_timeout()


class FormsOpenWhenTheWindowExpires(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import game_codes, roblox_admin
        self.admin_cog, self.codes = roblox_admin, game_codes
        self.guild = make_guild([STAFF])

    async def asyncTearDown(self):
        await database.close_db()
        self.temp.__exit__(None, None, None)

    def cloud(self):
        self.set_ban = mock.AsyncMock()
        return mock.patch.multiple("utils.open_cloud", set_ban=self.set_ban,
                                   get_ban=mock.AsyncMock(return_value={"active": True, "duration": ""}))

    def roblox(self):
        return mock.patch.multiple("utils.roblox_api", get_user=mock.AsyncMock(return_value={}),
                                   avatar_url=mock.AsyncMock(return_value=""),
                                   find_users=mock.AsyncMock(return_value=[(4242, "Builderman", "name")]))

    async def show_card(self):
        card = self.admin_cog.PlayerCardView(4242, "Builderman", False)
        await ui.send_panel(interaction_for(self.guild, "staff"), card, content="card")
        return card

    async def test_the_ban_form_sent_after_the_card_expired_still_bans_and_answers_in_a_new_message(self):
        with mock.patch.object(ui, "PANEL_TIMEOUT", 0.15):
            card = await self.show_card()
            click = interaction_for(self.guild, "staff", message=card.message)
            await card.ban.callback(click)  # opens the form: the card waits for it
            modal = click.response.modals[-1]
            self.assertTrue(await until(lambda: card.message.deleted), "the card was removed while the form was open")
            modal.duration._values = ["24h"]
            modal.reason._value = "Exploiting"
            modal.note._value = ""
            inter = interaction_for(self.guild, "staff", message=card.message, gone=True)
            with self.cloud(), self.roblox():
                await modal.on_submit(inter)
            self.set_ban.assert_awaited_once()
            self.assertEqual(inter.response.defers, [{"ephemeral": True, "thinking": True}], "a new private message")
            self.assertIn("Builderman", str(inter.followup.sent[-1]), "the card comes back as a new message")

    async def test_another_player_form_sent_after_the_card_expired(self):
        with mock.patch.object(ui, "PANEL_TIMEOUT", 0.15):
            card = await self.show_card()
            click = interaction_for(self.guild, "staff", message=card.message)
            await card.other.callback(click)
            modal = click.response.modals[-1]
            self.assertTrue(await until(lambda: card.is_finished()))
            modal.player._value = "Builderman"
            inter = interaction_for(self.guild, "staff", message=card.message, gone=True)
            with self.cloud(), self.roblox():
                await modal.on_submit(inter)
            self.assertEqual(inter.response.defers, [{"ephemeral": True, "thinking": True}])
            self.assertTrue(inter.followup.sent, "answered in a new message")

    async def test_the_code_extras_form_sent_after_the_draft_expired_brings_the_draft_back(self):
        cog = self.codes.GameCodes.__new__(self.codes.GameCodes)
        cog.bot = fakes.Client()
        params = self.codes.code_params("SLOW", "7d", "Coins", 5)
        with mock.patch.object(ui, "PANEL_TIMEOUT", 0.15):
            draft = self.codes.CodeDraftView(cog, 50, params)
            await ui.send_panel(interaction_for(self.guild, "staff"), draft, content="draft")
            click = interaction_for(self.guild, "staff", message=draft.message)
            await draft.extras.callback(click)
            modal = click.response.modals[-1]
            self.assertTrue(await until(lambda: draft.is_finished()))
            modal.exp._value = "300"
            inter = interaction_for(self.guild, "staff", gone=True)
            await modal.on_submit(inter)
            view = inter.response.sent[-1][1]["view"]
            self.assertIsInstance(view, self.codes.CodeDraftView)
            self.assertEqual(view.params["exp_amount"], 300, "what was typed is not lost")


if __name__ == "__main__":
    unittest.main()


class DoubleClicks(unittest.IsolatedAsyncioTestCase):
    """The same button clicked twice within the time a network answer takes (the person double-clicks)."""

    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        self.guild = make_guild([STAFF])

    async def asyncTearDown(self):
        await database.close_db()
        self.temp.__exit__(None, None, None)

    async def test_a_double_click_on_refresh_leaves_a_card_with_working_buttons(self):
        # BUG (cogs/roblox_admin.py PlayerCardView.redraw + utils/ui.py Panel.message): both clicks build a new card and
        # each one assigns the message to its card twice (before the edit and in show_in_place): the second card stops
        # the first, then the first's late assignment stops the second. Both end finished: dead buttons, dead ✖️ Close,
        # no timer, until the person dismisses the message by hand.
        from cogs import roblox_admin
        card = roblox_admin.PlayerCardView(4242, "Builderman", False)
        first = interaction_for(self.guild, "staff")
        await ui.send_panel(first, card, content="card")
        message = card.message

        async def slow_card(user_id, username):
            await asyncio.sleep(0.05)
            return discord.Embed(title="card"), False

        class SlowEdit(LiveInteraction):
            async def edit_original_response(self, **kwargs):
                await asyncio.sleep(0.05)
                return await super().edit_original_response(**kwargs)

        made = []
        original = roblox_admin.PlayerCardView.__init__

        def spy(view, *args, **kwargs):
            original(view, *args, **kwargs)
            made.append(view)

        async def click(delay):
            await asyncio.sleep(delay)
            await card.refresh.callback(SlowEdit(guild=self.guild, user=first.user, message=message))

        with mock.patch.object(roblox_admin, "player_card", slow_card), \
                mock.patch.object(roblox_admin.PlayerCardView, "__init__", spy):
            await asyncio.gather(click(0), click(0.02))
            await asyncio.sleep(0.2)
        self.assertEqual(len(made), 2)
        self.assertFalse(ui._shown[message.id].is_finished(), "the card on screen must still answer clicks")
        self.assertTrue(any(not view.is_finished() for view in made))

    async def test_a_double_click_on_remove_selected_removes_the_codes_once(self):
        # LOW: cogs/game_codes.py CodeRemoveView.confirm answers (an HTTP call) before it stops the window, so a
        # second click in that moment runs it again: remove_codes twice, two answers fighting over one message.
        from cogs import game_codes
        calls = []

        class Cog:
            async def remove_codes_counted(self, codes):
                calls.append(list(codes))
                return "removed", len(codes)

        row = {"code": "A", "is_active": 1, "expires_at": 0, "reward_currency": "", "currency_amount": 0, "exp_amount": 0,
               "reward_item": ""}
        view = game_codes.CodeRemoveView(Cog(), 50, [row])
        view.selected = ["A"]

        def slow(inter):
            real = inter.response.defer

            async def defer(**kwargs):
                await asyncio.sleep(0.05)
                await real(**kwargs)
            inter.response.defer = defer
            return inter
        first, second = (slow(interaction_for(self.guild, "staff")) for _ in range(2))
        await asyncio.gather(view.confirm.callback(first), view.confirm.callback(second))
        self.assertEqual(calls, [["A"]])

    async def test_closing_while_a_refresh_is_running_brings_the_card_back_as_a_new_message(self):
        # Observed behaviour, not a failure: the refresh answers "in place", the message is gone, so the answer is a
        # new private message (documented in utils/ui.py show_in_place). The person who pressed ✖️ sees a card again.
        from cogs import roblox_admin
        card = roblox_admin.PlayerCardView(4242, "Builderman", False)
        first = interaction_for(self.guild, "staff")
        await ui.send_panel(first, card, content="card")
        with mock.patch.object(roblox_admin, "player_card", mock.AsyncMock(return_value=(discord.Embed(title="card"), False))):
            click = interaction_for(self.guild, "staff", message=card.message, gone=True)
            await card.refresh.callback(click)
        self.assertTrue(click.followup.sent, "a new message instead of an edit of the removed one")
        self.assertFalse(click.deleted)
