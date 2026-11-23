"""/setup-roblox -> Promo codes: the form checks a code like /code-add, fits Discord's limits in every language and
saves through the same code as the command (EXP and the item's time come from the button under the saved code)."""
import time
import unittest
from unittest import mock

import discord

from tests.helpers import TempBot
from utils import config_store, database, i18n

LANGS = ("en", "pl", "es")


class Response:
    def __init__(self):
        self.sent, self.edits, self.modals, self.deferred = [], [], [], False

    def is_done(self):
        return bool(self.sent or self.edits or self.modals or self.deferred)

    async def send_message(self, content=None, **kwargs):
        self.sent.append((content, kwargs))

    async def edit_message(self, **kwargs):
        self.edits.append(kwargs)

    async def send_modal(self, modal):
        self.modals.append(modal)

    async def defer(self, **kwargs):
        self.deferred = True


class Followup:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, **kwargs):
        kwargs.pop("wait", None)
        self.sent.append((content, kwargs))


class Client:
    def __init__(self, cog=None):
        self.cog = cog

    def get_cog(self, name):
        return self.cog if name == "GameCodes" else None


class Interaction:
    def __init__(self, cog=None):
        self.user = type("User", (), {"id": 7, "display_name": "Admin", "mention": "<@7>",
                                      "guild_permissions": discord.Permissions(administrator=True)})()
        self.guild_id = 4242
        self.guild = type("Guild", (), {"id": 4242, "owner_id": 0})()  # the game-staff check needs the server
        self.response, self.followup, self.client = Response(), Followup(), Client(cog)
        self.edited, self.deleted = [], False

    async def edit_original_response(self, **kwargs):
        self.edited.append(kwargs)

    async def delete_original_response(self):
        self.deleted = True

    async def original_response(self):
        return None


def labels(data):
    """Every label of the form's fields (Discord allows 45 characters)."""
    found = []
    if isinstance(data, dict):
        if data.get("type") in (4, 18):  # text field, label around a menu
            found.append(data.get("label", ""))
        for value in data.values():
            found += labels(value)
    elif isinstance(data, list):
        for value in data:
            found += labels(value)
    return found


class CodeRules(unittest.TestCase):
    def test_same_rules_as_the_command(self):
        from cogs import game_codes
        with TempBot():
            for args in (("SUMMER 24", "7d", "Coins", 5), ("ZAŻÓŁĆ", "7d", "Coins", 5), ("COINS", "7d", "Coins", 0),
                         ("AMOUNT", "7d", game_codes.NONE, 50), ("EMPTY", "7d")):
                with self.assertRaises(game_codes.CodeError, msg=args):
                    game_codes.code_params(*args)
            params = game_codes.code_params(" start_1 ", "7d", "Coins", 100)
            self.assertEqual(params, {"code": "START_1", "validity": "7d", "currency_type": "Coins", "currency_amount": 100,
                                      "exp_amount": 0, "item_reward": game_codes.NONE, "item_key": "permanent"})
            self.assertEqual(game_codes.code_params("XP", "7d", exp_amount=50)["exp_amount"], 50, "EXP alone is a reward")
            self.assertEqual(game_codes.code_params("DRAFT", "7d", allow_empty=True)["code"], "DRAFT",
                             "a draft may still get its EXP before saving")

    def test_a_name_the_game_catalog_lacks_is_refused(self):
        from cogs import game_codes
        with TempBot(), mock.patch.object(game_codes.catalog, "resolve", return_value=("Gem", "no Gem, did you mean Gems?")):
            with self.assertRaises(game_codes.CodeError):
                game_codes.code_params("GEMS", "7d", "Gem", 5)

    def test_an_expired_code_is_not_live(self):
        from cogs import game_codes
        now = time.time()
        self.assertTrue(game_codes.is_live({"is_active": 1, "expires_at": 0}))
        self.assertTrue(game_codes.is_live({"is_active": 1, "expires_at": now + 60}))
        self.assertFalse(game_codes.is_live({"is_active": 1, "expires_at": now - 1}), "expired, not cleaned up yet")
        self.assertFalse(game_codes.is_live({"is_active": 0, "expires_at": 0}))
        self.assertFalse(game_codes.is_live(None))


class CodePanel(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        from cogs import game_codes, setup_roblox
        from utils import ui
        self.codes, self.panel, self.ui = game_codes, setup_roblox, ui
        self.cog = game_codes.GameCodes.__new__(game_codes.GameCodes)  # without the clean-up loop
        self.cog.bot = Client()  # no CloudSync cog: nothing is sent to Roblox
        config_store.write_json(game_codes.ECONOMY_FILE, {"configured": True, "currencies": ["Coins", "Gems"], "items": ["VIP"]})

    async def asyncTearDown(self):
        await database.close_db()
        self.temp.__exit__(None, None, None)

    def form(self, code="start2026", validity="24h", currency="Coins", amount="1 500", item=None):
        modal = self.panel.CodeModal()
        modal.code._value = code
        modal.validity._values = [validity]
        modal.currency._values = [currency or self.codes.NONE]
        modal.amount._value = amount
        modal.item._values = [item or self.codes.NONE]
        return modal

    async def submit(self, modal):
        inter = Interaction(self.cog)
        await modal.on_submit(inter)
        return inter

    async def draft(self, **form):
        """The form's answer: a draft that is not saved yet."""
        inter = await self.submit(self.form(**form))
        content, kwargs = inter.response.sent[-1]
        self.assertTrue(kwargs["ephemeral"])
        self.assertIsInstance(kwargs["view"], self.codes.CodeDraftView)
        return kwargs["view"], kwargs["embed"]

    async def save(self, draft):
        inter = Interaction(self.cog)
        await draft.save.callback(inter)
        return inter

    async def test_form_fits_discord_limits_in_every_language(self):
        many = {"configured": True, "currencies": [f"Coin{i}" for i in range(40)], "items": [f"Item{i}" for i in range(40)]}
        for economy in (None, many):
            if economy:
                config_store.write_json(self.codes.ECONOMY_FILE, economy)
            for lang in LANGS:
                with mock.patch.object(i18n, "language", return_value=lang):
                    data = self.panel.CodeModal().to_dict()
                    self.assertLessEqual(len(data["title"]), 45, lang)
                    self.assertLessEqual(len(data["components"]), 5, lang)
                    self.assertEqual(len(labels(data)), 5, lang)
                    self.assertTrue(all(0 < len(label) <= 45 for label in labels(data)), (lang, labels(data)))
                    view = self.panel.CodesView()
                    embed = await view.embed()
                    self.assertLess(len(embed), 6000)
                    self.assertTrue(all(button.label for button in view.children), lang)
                    draft = self.codes.CodeDraftView(self.cog, 7, self.codes.code_params("X", "7d", "Coins", 5, 0, "VIP"))
                    self.assertTrue(all(button.label for button in draft.children), lang)
                    extras = self.codes.CodeExtrasModal(draft).to_dict()
                    self.assertTrue(len(extras["title"]) <= 45 and all(0 < len(x) <= 45 for x in labels(extras)), lang)
                    self.assertLess(len(self.codes.draft_embed(draft.params, "500 Coins")), 6000)
        # 40 names don't fit in a menu: the form has text fields instead, with examples from the game
        modal = self.panel.CodeModal()
        self.assertIsInstance(modal.currency, discord.ui.TextInput)
        self.assertIn("Coin0", modal.currency.placeholder)

    async def test_no_names_yet_gives_text_fields(self):
        config_store.write_json(self.codes.ECONOMY_FILE, {})
        modal = self.panel.CodeModal()
        self.assertIsInstance(modal.currency, discord.ui.TextInput)
        self.assertIsInstance(modal.item, discord.ui.TextInput)
        embed = await self.panel.CodesView().embed()
        self.assertEqual(len(embed.fields), 2, "the panel explains where the names come from")

    async def test_form_offers_pets(self):
        """Eggs (and so pets) are in the bot: the item menu is "Item or pet"."""
        with mock.patch.object(i18n, "language", return_value="en"):
            text = str(self.panel.CodeModal().to_dict()).lower()
            self.assertIn("item or pet", text)
            for word in ("gift", "ban ", "leaderboard", "announce"):
                self.assertNotIn(word, text, f"the code form says nothing about {word}")

    async def test_the_form_gives_a_draft_and_only_save_reaches_the_game(self):
        draft, embed = await self.draft()
        self.assertIsNone(await database.get_game_code("START2026"), "nothing saved before Save")
        self.assertIn("START2026", embed.title)
        inter = await self.save(draft)
        row = await database.get_game_code("START2026")
        self.assertTrue(row and row["is_active"])
        self.assertEqual((row["reward_currency"], row["currency_amount"], row["reward_item"]), ("Coins", 1500, None))
        self.assertGreater(row["expires_at"], 0)
        self.assertTrue(inter.response.deferred and not inter.followup.sent, "no second message")
        result = inter.edited[-1]
        self.assertIn("START2026", result["embed"].description, "the draft itself turns into the result")
        self.assertIsNone(result["content"])
        self.assertIsInstance(result["view"], self.ui.CloseView, "the result has ✖️ Close")

    async def test_wrong_forms_are_refused(self):
        for currency, amount in (("Coins", ""), (None, "50"), ("Coins", "abc"), ("Coins", "\u00b2")):
            inter = await self.submit(self.form(code="HALF", currency=currency, amount=amount))
            self.assertTrue(inter.response.sent and "❌" in inter.response.sent[-1][0], (currency, amount))
        inter = await self.submit(self.form(code="BAD CODE"))
        self.assertTrue(inter.response.sent and "❌" in inter.response.sent[-1][0], "a code with a space is refused")
        self.assertIsNone(await database.get_game_code("HALF"))

    async def test_extras_set_exp_and_the_item_time_before_saving(self):
        draft, embed = await self.draft(code="VIPDAY", currency=None, amount="", item="VIP")
        modal = self.codes.CodeExtrasModal(draft)
        self.assertIsNotNone(modal.duration, "an item: its time can be set")
        modal.exp._value = "250"
        modal.duration._values = ["24h"]
        inter = await self.submit(modal)
        self.assertTrue(inter.response.deferred and inter.edited and inter.edited[-1]["view"] is draft,
                        "the same draft is updated, the buttons stay")
        self.assertIn("250", str(inter.edited[-1]["embed"].to_dict()))
        self.assertIsNone(await database.get_game_code("VIPDAY"), "still only a draft: a permanent VIP never went live")
        await self.save(draft)
        row = await database.get_game_code("VIPDAY")
        self.assertEqual((row["exp_amount"], row["item_duration_label"], row["is_temporary_item"]), (250, "24h", 1))

    async def test_exp_only_code_and_an_empty_code(self):
        draft, embed = await self.draft(code="XPONLY", currency=None, amount="")
        inter = await self.save(draft)
        self.assertTrue(inter.response.sent and "❌" in inter.response.sent[-1][0], "no reward: not saved")
        self.assertIsNone(await database.get_game_code("XPONLY"))
        modal = self.codes.CodeExtrasModal(draft)
        self.assertIsNone(modal.duration, "no item: only EXP is asked")
        modal.exp._value = "lots"
        inter = await self.submit(modal)
        self.assertTrue(inter.response.sent and "❌" in inter.response.sent[-1][0])
        modal.exp._value = "1 000"
        await self.submit(modal)
        await self.save(draft)
        self.assertEqual((await database.get_game_code("XPONLY"))["exp_amount"], 1000)

    async def test_cancel_saves_nothing(self):
        draft, embed = await self.draft(code="NOPE")
        inter = Interaction(self.cog)
        await draft.cancel.callback(inter)
        self.assertIsNone(await database.get_game_code("NOPE"))
        self.assertTrue(inter.deleted, "Cancel removes the draft message")

    async def test_an_active_code_is_replaced_only_after_a_click(self):
        await self.save((await self.draft(code="TWICE", amount="10"))[0])
        draft, embed = await self.draft(code="TWICE", amount="20")
        self.assertIn("10", str(embed.to_dict()), "the draft says the code exists and what it gives now")
        inter = await self.save(draft)
        view = inter.edited[-1]["view"]
        self.assertIsInstance(view, self.codes.OverwriteView, "the draft becomes the question")
        self.assertFalse(inter.followup.sent)
        self.assertEqual((await database.get_game_code("TWICE"))["currency_amount"], 10)
        inter = Interaction(self.cog)
        await view.overwrite.callback(inter)
        self.assertEqual((await database.get_game_code("TWICE"))["currency_amount"], 20)
        self.assertIsInstance(inter.edited[-1]["view"], self.ui.CloseView, "and then the result")
        self.assertFalse(inter.followup.sent)

    async def test_an_expired_code_is_simply_made_again(self):
        await self.save((await self.draft(code="OLD", amount="10"))[0])
        await database._write(("UPDATE game_codes SET expires_at = ? WHERE code = 'OLD'", (int(time.time()) - 5,)))
        draft, embed = await self.draft(code="OLD", amount="30")
        await self.save(draft)
        row = await database.get_game_code("OLD")
        self.assertEqual(row["currency_amount"], 30)
        self.assertGreater(row["expires_at"], time.time())

    async def test_codes_list_fits_with_many_codes(self):
        for i in range(30):
            await self.save((await self.draft(code=f"CODE{i}"))[0])
        embed = await self.panel.CodesView().embed()
        self.assertLess(len(embed), 6000)
        self.assertTrue(all(len(field.value) <= 1024 for field in embed.fields))
        self.assertIn("30", embed.fields[0].name)

    async def test_panel_button_and_tutorial(self):
        view = self.panel.RobloxPanelView()
        self.assertIn(view.codes, view.children)
        rows = view.to_components()
        self.assertTrue(len(rows) <= 5 and all(len(r["components"]) <= 5 for r in rows))
        inter = Interaction(self.cog)
        await view.codes.callback(inter)
        self.assertIsInstance(inter.followup.sent[-1][1]["view"], self.panel.CodesView)
        from cogs import tutorial
        inter = Interaction(self.cog)
        await tutorial.run_action("codes", inter)
        self.assertIsInstance(inter.followup.sent[-1][1]["view"], self.panel.CodesView)


if __name__ == "__main__":
    unittest.main()
