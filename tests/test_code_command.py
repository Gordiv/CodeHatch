"""/code-add (the command) after the shared rules of code_params, and the edge cases of the /setup-roblox draft:
several clicks on the gear button, a game catalog that changes between the draft and Save, two drafts of one code.
Uses tests/fakes.py: a double answer or a message over Discord's limits fails the test."""
import time
import unittest
from unittest import mock

import discord
from discord import app_commands

from tests.fakes import Interaction
from tests.helpers import TempBot
from utils import catalog, config_store, database, i18n

LANGS = ("en", "pl", "es")


def fake_catalog(currencies=(), items=(), pets=()):
    return {"currencies": list(currencies), "items": list(items), "multipliers": [], "pets": [{"name": p, "rarity": ""} for p in pets],
            "eggs": [], "problems": [], "at": int(time.time()), "studio": False, "missing": False, "template": False}


class Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import game_codes, setup_roblox
        self.codes, self.panel = game_codes, setup_roblox
        self.cog = game_codes.GameCodes.__new__(game_codes.GameCodes)  # without the clean-up loop
        self.cog.bot = mock.Mock(get_cog=lambda name: None)  # no CloudSync: nothing is sent to Roblox
        config_store.write_json(game_codes.ECONOMY_FILE, {"configured": True, "currencies": ["Coins", "Gems"], "items": ["VIP"]})

    async def asyncTearDown(self):
        await database.close_db()
        self.temp.__exit__(None, None, None)

    def inter(self):
        return Interaction(GameCodes=self.cog)

    async def code_add(self, code="SUMMER24", validity="7d", currency="none", amount=0, exp=0, item="none", duration=None):
        inter = self.inter()
        await self.cog.code_add.callback(
            self.cog, inter, code, app_commands.Choice(name=validity, value=validity), currency, amount, exp, item,
            app_commands.Choice(name=duration, value=duration) if duration else None)
        return inter


class CodeAddCommand(Base):
    async def test_a_valid_code_is_saved_and_answered_publicly(self):
        inter = await self.code_add(code="Summer24", currency="Coins", amount=500, exp=20, item="VIP", duration="24h")
        row = await database.get_game_code("SUMMER24")
        self.assertEqual((row["reward_currency"], row["currency_amount"], row["exp_amount"], row["reward_item"],
                          row["item_duration_label"], row["is_temporary_item"]), ("Coins", 500, 20, "VIP", "24h", 1))
        self.assertGreater(row["expires_at"], time.time() + 6 * 86400)
        self.assertEqual(inter.response.defers, [{"ephemeral": False, "thinking": False}], "deferred, as before")
        content, kwargs = inter.followup.sent[-1]
        self.assertFalse(kwargs["ephemeral"], "the command answers in the channel, like before")
        self.assertIn("SUMMER24", kwargs["embed"].description)

    async def test_currency_without_an_amount_or_the_other_way_round(self):
        for currency, amount in (("Coins", 0), ("none", 25)):
            inter = await self.code_add(code="HALF", currency=currency, amount=amount)
            content, kwargs = inter.response.sent[-1]
            self.assertTrue(content.startswith("❌") and kwargs["ephemeral"], (currency, amount))
            self.assertFalse(inter.response.defers)
        self.assertIsNone(await database.get_game_code("HALF"))

    async def test_exp_alone_is_a_reward_and_an_empty_code_is_not(self):
        await self.code_add(code="JUSTEXP", exp=100)
        self.assertEqual((await database.get_game_code("JUSTEXP"))["exp_amount"], 100)
        inter = await self.code_add(code="NOTHING")
        self.assertTrue(inter.response.sent[-1][0].startswith("❌") and inter.response.sent[-1][1]["ephemeral"])
        self.assertIsNone(await database.get_game_code("NOTHING"))

    async def test_item_only_code_and_the_legacy_empty_choice(self):
        await self.code_add(code="JUSTITEM", item="VIP")
        self.assertEqual((await database.get_game_code("JUSTITEM"))["reward_item"], "VIP")
        inter = await self.code_add(code="OLDNONE", currency="Brak", item="Brak")  # older bot versions stored "Brak"
        self.assertTrue(inter.response.sent[-1][0].startswith("❌"), "'Brak' still means no reward")

    async def test_invalid_names_are_refused_before_anything_is_saved(self):
        for code in ("WITH SPACE", "ZAŻÓŁĆ", "TAB\tCODE", "ZERO​WIDTH", "A" * 51, "emoji😀", "DOT.COM", "   "):
            inter = await self.code_add(code=code, exp=5)
            self.assertTrue(inter.response.sent and inter.response.sent[-1][0].startswith("❌"), repr(code))
        self.assertEqual(await database.get_active_game_codes(), [])

    async def test_a_name_the_catalog_does_not_list_is_refused(self):
        with mock.patch.object(catalog, "game_catalog", return_value=fake_catalog(["Coins"], ["VIP"])):
            for kwargs in ({"currency": "Coinz", "amount": 5}, {"item": "VIPP"}, {"currency": "coins", "amount": 5, "item": "Nope"}):
                inter = await self.code_add(code="TYPO", **kwargs)
                self.assertTrue(inter.response.sent[-1][0].startswith("❌"), kwargs)
            self.assertIsNone(await database.get_game_code("TYPO"))
            await self.code_add(code="FINE", currency="coins", amount=5)  # letter case is fixed to the catalog's
            self.assertEqual((await database.get_game_code("FINE"))["reward_currency"], "Coins")

    async def test_an_active_code_asks_before_it_is_replaced(self):
        await self.code_add(code="TWICE", currency="Coins", amount=10)
        inter = await self.code_add(code="TWICE", currency="Gems", amount=99)
        self.assertEqual((await database.get_game_code("TWICE"))["currency_amount"], 10, "nothing changed yet")
        content, kwargs = inter.response.sent[-1]
        self.assertIn("TWICE", content)
        self.assertTrue(kwargs["ephemeral"], "the question is only for the admin")
        view = kwargs["view"]
        self.assertIsInstance(view, self.codes.OverwriteView)
        self.assertFalse(view.panel)

        stranger = self.inter()
        stranger.user = type("Other", (), {"id": 99})()
        self.assertFalse(await view.interaction_check(stranger), "only the admin who asked may answer")

        click = self.inter()
        await view.overwrite.callback(click)
        row = await database.get_game_code("TWICE")
        self.assertEqual((row["reward_currency"], row["currency_amount"]), ("Gems", 99))
        self.assertFalse(click.followup.sent[-1][1]["ephemeral"], "the command's answer is public, as before")
        self.assertEqual(len(await database.get_active_game_codes()), 1)

    async def test_cancel_keeps_the_old_code(self):
        await self.code_add(code="KEEP", currency="Coins", amount=10)
        view = (await self.code_add(code="KEEP", currency="Coins", amount=77)).response.sent[-1][1]["view"]
        click = self.inter()
        await view.cancel.callback(click)
        self.assertEqual((await database.get_game_code("KEEP"))["currency_amount"], 10)
        self.assertFalse(click.followup.sent)

    async def test_an_expired_code_still_marked_active_is_made_again_without_asking(self):
        await self.code_add(code="OLD", currency="Coins", amount=10)
        await database._write(("UPDATE game_codes SET expires_at = ? WHERE code = 'OLD'", (int(time.time()) - 5,)))
        self.assertEqual((await database.get_game_code("OLD"))["is_active"], 1, "the clean-up loop has not run yet")
        inter = await self.code_add(code="OLD", validity="30d", currency="Gems", amount=5)
        self.assertFalse(inter.response.sent, "no question: an expired code is not 'existing'")
        row = await database.get_game_code("OLD")
        self.assertEqual((row["reward_currency"], row["is_active"]), ("Gems", 1))
        self.assertGreater(row["expires_at"], time.time() + 29 * 86400)

    async def test_a_removed_code_can_be_made_again(self):
        await self.code_add(code="GONE", exp=5)
        await database.delete_game_code("GONE")
        inter = await self.code_add(code="GONE", exp=9)
        self.assertFalse(inter.response.sent)
        row = await database.get_game_code("GONE")
        self.assertEqual((row["is_active"], row["exp_amount"]), (1, 9))

    async def test_the_boundary_of_the_expiry_second(self):
        now = time.time()
        for expires, live in ((int(now) + 3, True), (int(now) - 1, False), (0, True)):
            self.assertEqual(self.codes.is_live({"is_active": 1, "expires_at": expires}), live, expires)

    async def test_largest_values_and_unusual_digits(self):
        await self.code_add(code="BIG", currency="Coins", amount=self.codes.MAX_AMOUNT, exp=self.codes.MAX_AMOUNT)
        row = await database.get_game_code("BIG")
        self.assertEqual((row["currency_amount"], row["exp_amount"]), (self.codes.MAX_AMOUNT, self.codes.MAX_AMOUNT))
        inter = await self.code_add(code="BIG2", currency="Coins", amount=self.codes.MAX_AMOUNT, exp=self.codes.MAX_AMOUNT,
                                    item="VIP", duration="30d")
        embed = inter.followup.sent[-1][1]["embed"]
        self.assertLess(len(embed), 6000)

    async def test_answers_fit_discord_in_every_language(self):
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                for kwargs in ({"code": f"A{lang}", "currency": "Coins", "amount": 5}, {"code": f"B{lang}"},
                               {"code": f"C{lang}", "currency": "Coins"}, {"code": "BAD CODE", "exp": 1}):
                    inter = await self.code_add(**kwargs)  # the fakes check every message against Discord's limits
                    self.assertTrue(inter.response.sent or inter.followup.sent)


class DraftEdgeCases(Base):
    def form(self, code="DRAFT1", currency="Coins", amount="100", item=None, validity="7d"):
        modal = self.panel.CodeModal()
        modal.code._value = code
        modal.validity._values = [validity]
        modal.currency._values = [currency or self.codes.NONE]
        modal.amount._value = amount
        modal.item._values = [item or self.codes.NONE]
        return modal

    async def draft(self, **kwargs):
        inter = self.inter()
        await self.form(**kwargs).on_submit(inter)
        content, sent = inter.response.sent[-1]
        self.assertIsInstance(sent["view"], self.codes.CodeDraftView, content)
        return sent["view"], sent["embed"]

    async def extras(self, draft, exp="", duration=None):
        modal = self.codes.CodeExtrasModal(draft)
        modal.exp._value = exp
        if duration:
            modal.duration._values = [duration]
        inter = self.inter()
        await modal.on_submit(inter)
        return modal, inter

    async def save(self, draft):
        inter = self.inter()
        await draft.save.callback(inter)
        return inter

    async def test_gear_button_can_be_used_many_times(self):
        draft, _ = await self.draft(code="GEARS", currency=None, amount="", item="VIP")
        shown = ("", "permanent")  # what the form should show: the draft's EXP (empty = none) and item time
        for exp, duration in (("100", "1h"), ("", "7d"), ("2 500", "30d"), ("0", "permanent")):
            modal = self.codes.CodeExtrasModal(draft)  # the form opens with what the draft has now
            self.assertEqual(modal.exp.default or "", shown[0])
            self.assertEqual([o.value for o in modal.duration.options if o.default], [shown[1]])
            _, inter = await self.extras(draft, exp, duration)
            self.assertIs(inter.edited[-1]["view"], draft)
            shown = (str(draft.params["exp_amount"]) if draft.params["exp_amount"] else "", duration)
        self.assertEqual((draft.params["exp_amount"], draft.params["item_key"]), (0, "permanent"))
        self.assertIsNone(await database.get_game_code("GEARS"), "nothing saved by the gear button")
        await self.extras(draft, "40", "24h")
        await self.save(draft)
        row = await database.get_game_code("GEARS")
        self.assertEqual((row["exp_amount"], row["item_duration_label"]), (40, "24h"))

    async def test_gear_values_with_wrong_digits_leave_the_draft_alone(self):
        draft, _ = await self.draft(code="GEARBAD")
        before = dict(draft.params)
        for text in ("1e9", "-5", "٣٤", "1,5x", "9" * 15, str(self.codes.MAX_AMOUNT + 1), "²"):
            _, inter = await self.extras(draft, text)
            self.assertTrue(inter.response.sent and inter.response.sent[-1][0].startswith("❌"), text)
            self.assertEqual(draft.params, before, text)
        _, inter = await self.extras(draft, str(self.codes.MAX_AMOUNT))
        self.assertEqual(draft.params["exp_amount"], self.codes.MAX_AMOUNT)

    async def test_a_catalog_change_between_the_draft_and_save_is_caught(self):
        with mock.patch.object(catalog, "game_catalog", return_value=fake_catalog(["Coins", "Gems"], ["VIP"])):
            draft, _ = await self.draft(code="LATE", currency="coins", amount="5", item="vip")
            self.assertEqual((draft.params["currency_type"], draft.params["item_reward"]), ("Coins", "VIP"),
                             "the draft already has the catalog's spelling")
        with mock.patch.object(catalog, "game_catalog", return_value=fake_catalog(["Gems"], ["Sword"])):
            inter = await self.save(draft)
            self.assertTrue(inter.response.sent and inter.response.sent[-1][0].startswith("❌"),
                            "Coins and VIP were removed from the game: Save asks again and refuses")
            self.assertFalse(inter.response.edits, "the draft keeps its buttons so the admin can cancel or fix it")
        self.assertIsNone(await database.get_game_code("LATE"))
        # a draft with a name the catalog did not know at all (no catalog yet) and a catalog that appears later
        draft, _ = await self.draft(code="LATE2", currency="Coinz", amount="5")
        with mock.patch.object(catalog, "game_catalog", return_value=fake_catalog(["Coins"])):
            inter = await self.save(draft)
            self.assertTrue(inter.response.sent[-1][0].startswith("❌"))
        self.assertIsNone(await database.get_game_code("LATE2"))
        # the draft is still usable when the catalog is gone again
        inter = await self.save(draft)
        self.assertIsNotNone(await database.get_game_code("LATE2"))

    async def test_a_second_draft_of_the_same_code_asks_before_replacing(self):
        first, _ = await self.draft(code="PAIR", amount="10")
        second, embed = await self.draft(code="PAIR", amount="20")
        self.assertNotIn(self.codes.t("codes.draft_replaces_title"), [f.name for f in embed.fields], "nothing exists yet")
        await self.save(first)
        self.assertEqual((await database.get_game_code("PAIR"))["currency_amount"], 10)
        inter = await self.save(second)
        view = inter.edited[-1]["view"]  # the second draft itself becomes the "replace?" question
        self.assertIsInstance(view, self.codes.OverwriteView)
        self.assertTrue(view.panel)
        self.assertEqual((await database.get_game_code("PAIR"))["currency_amount"], 10, "the second draft waits for the click")
        click = self.inter()
        await view.overwrite.callback(click)
        self.assertEqual((await database.get_game_code("PAIR"))["currency_amount"], 20)
        self.assertFalse(click.followup.sent, "from the panel the answer replaces the private question")
        self.assertIn("PAIR", click.edited[-1]["embed"].description)
        self.assertEqual(len(await database.get_active_game_codes()), 1)

    async def test_a_code_removed_while_the_draft_is_open_is_just_saved(self):
        first, _ = await self.draft(code="GHOST", amount="10")
        await self.save(first)
        second, embed = await self.draft(code="GHOST", amount="30")
        self.assertIn(self.codes.t("codes.draft_replaces_title"), [f.name for f in embed.fields])
        await database.delete_game_code("GHOST")
        inter = await self.save(second)
        self.assertFalse([m for m in inter.followup.sent if "view" in m[1]], "removed meanwhile: no question")
        self.assertEqual((await database.get_game_code("GHOST"))["currency_amount"], 30)

    async def test_save_twice_and_cancel_after_save(self):
        draft, _ = await self.draft(code="ONCE", amount="10")
        await self.save(draft)
        self.assertTrue(draft.is_finished(), "the draft view stops after Save")
        cancel = self.inter()
        await draft.cancel.callback(cancel)  # a late click can't undo or duplicate anything
        self.assertEqual(len(await database.get_active_game_codes()), 1)

    async def test_the_draft_belongs_to_the_admin_who_made_it(self):
        draft, _ = await self.draft(code="MINE")
        stranger = self.inter()
        stranger.user = type("Other", (), {"id": 99})()
        self.assertFalse(await draft.interaction_check(stranger))
        self.assertTrue(stranger.response.sent[-1][1]["ephemeral"])

    async def test_form_edge_values(self):
        for kwargs, ok in (({"amount": "0", "currency": None}, True), ({"amount": "1_000", "currency": "Coins"}, True),
                           ({"amount": "1.000.000", "currency": "Coins"}, True), ({"amount": "00500", "currency": "Coins"}, True),
                           ({"amount": "   ", "currency": None, "item": "VIP"}, True),
                           ({"amount": "1 000 000 001", "currency": "Coins"}, False),
                           ({"amount": "٣", "currency": "Coins"}, False),
                           ({"amount": "-5", "currency": "Coins"}, False), ({"amount": "5,5", "currency": "Coins"}, True)):
            inter = self.inter()
            await self.form(code="EDGE", **kwargs).on_submit(inter)
            content, sent = inter.response.sent[-1]
            self.assertEqual(isinstance(sent.get("view"), self.codes.CodeDraftView), ok, (kwargs, content))

    async def test_draft_with_the_longest_values_fits_in_every_language(self):
        long_name = "N" * 100
        config_store.write_json(self.codes.ECONOMY_FILE, {"configured": True, "currencies": [long_name], "items": [long_name + "I"]})
        for lang in LANGS:
            with mock.patch.object(i18n, "language", return_value=lang):
                params = self.codes.code_params("C" * 30, "unlimited", long_name, self.codes.MAX_AMOUNT, self.codes.MAX_AMOUNT,
                                                long_name + "I", "30d")
                embed = self.codes.draft_embed(params, "x" * 400)
                self.assertLess(len(embed), 6000, lang)
                draft = self.codes.CodeDraftView(self.cog, 7, params, "x" * 400)
                inter = self.inter()
                await inter.response.send_message(embed=embed, view=draft)  # checked by the fakes
                self.codes.CodeExtrasModal(draft).to_dict()
                from tests.fakes import check_modal
                check_modal(self.codes.CodeExtrasModal(draft))
                store = await self.cog.store_code(inter.user, params["code"], params["validity"], params["currency_type"],
                                                  params["currency_amount"], params["exp_amount"], params["item_reward"],
                                                  params["item_key"])
                self.assertLess(len(store), 6000, lang)

    async def test_draft_and_saved_code_warn_about_what_the_game_lacks(self):
        scan = {"values": [("leaderstats.Gems", "IntValue")], "attributes": [], "spots": [], "templates": [], "multipliers": [],
                "hooks": [], "at": int(time.time()), "studio": False, "players": 1}
        with mock.patch.object(self.codes.roblox_kit, "game_scan", return_value=scan):
            for lang in LANGS:
                with mock.patch.object(i18n, "language", return_value=lang):
                    draft, embed = await self.draft(code="WARN" + lang, currency="Coins", amount="5", item="VIP")
                    draft.params = dict(draft.params, exp_amount=10)
                    embed = self.codes.draft_embed(draft.params)
                    names = [f.name for f in embed.fields]
                    self.assertIn(self.codes.t("codes.draft_warnings"), names, lang)
                    warnings = next(f.value for f in embed.fields if f.name == self.codes.t("codes.draft_warnings"))
                    self.assertEqual(warnings.count("⚠️"), 3, f"{lang}: no Coins, no EXP, no VIP in the game: {warnings}")
                    self.assertTrue(all(len(f.value) <= 1024 for f in embed.fields))
            draft, embed = await self.draft(code="NOWARN", currency="Gems", amount="5")
            self.assertNotIn(self.codes.t("codes.draft_warnings"), [f.name for f in embed.fields])

    async def test_save_survives_a_modal_opened_for_a_finished_draft(self):
        draft, _ = await self.draft(code="LATEGEAR", currency=None, amount="", item="VIP")
        modal = self.codes.CodeExtrasModal(draft)
        modal.exp._value = "5"
        await self.save(draft)
        inter = self.inter()
        await modal.on_submit(inter)  # the form was opened before Save and sent after it
        row = await database.get_game_code("LATEGEAR")
        self.assertEqual(row["exp_amount"], 0, "a code that is already saved is never changed from the draft")


if __name__ == "__main__":
    unittest.main()
