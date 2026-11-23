"""Rewards players can buy with Robux (Catalog.SoldForRobux in the game's DiscordCatalog): Roblox doesn't allow them in
codes posted outside Roblox (e.g. on Discord) or as prizes of contests outside Roblox (Promo Offers for Virtual Rewards,
checked 2026-10-17). The bot warns in the code draft, after /code-add, in the gift draft and on the "Gift sent" card.
The game side (the list sent in the catalog report): tests/test_kit_server_scripts.py CatalogAndSecondServer."""
import json
import time
import unittest
from unittest import mock

from tests.helpers import ROOT, TempBot
from utils import catalog, config_store, database

LANGS = ("en", "pl", "es")


def fake_catalog(robux=(), currencies=("Coins", "Gems"), items=("VIP Pass", "Sword")):
    return {"currencies": list(currencies), "items": list(items), "multipliers": [], "robux": list(robux), "pets": [],
            "eggs": [], "problems": [], "at": int(time.time()), "studio": False, "missing": False, "template": False}


class RobuxRewards(unittest.TestCase):
    def test_which_names_of_a_reward_are_sold_for_robux(self):
        cat = fake_catalog(robux=["gems", "VIP Pass"])
        self.assertEqual(catalog.robux_rewards({"currency": {"name": "Gems", "amount": 5}, "item": {"name": "VIP pass"}}, cat),
                         ["Gems", "VIP pass"], "letter case doesn't matter")
        self.assertEqual(catalog.robux_rewards({"currency": {"name": "Coins", "amount": 5}, "exp": 10}, cat), [])
        self.assertEqual(catalog.robux_rewards({}, cat), [])
        self.assertEqual(catalog.robux_rewards({"currency": {"name": "Gems", "amount": 5}}, fake_catalog()), [],
                         "an empty list warns about nothing")
        self.assertEqual(catalog.robux_rewards({"currency": {"name": "Gems", "amount": 5}}, None), [], "no catalog")

    def test_names_compare_like_the_game_compares_them(self):
        cat = fake_catalog(robux=["VIP_Pass"])
        self.assertEqual(catalog.robux_rewards({"item": {"name": "VIP Pass"}}, cat), ["VIP Pass"])

    def test_the_list_counts_next_to_the_old_template_names(self):
        cat = fake_catalog(robux=["Gems"])
        cat["template"] = True
        self.assertEqual(catalog.robux_rewards({"currency": {"name": "Gems", "amount": 1}}, cat), ["Gems"])

    def test_a_name_the_other_lists_do_not_have_is_reported_as_a_problem(self):
        problems = catalog.problems(fake_catalog(robux=["Gem", "Gems"]))
        self.assertTrue(any("Gem" in p and "Gems" not in p.split(":")[-1] for p in problems), problems)

    def test_a_catalog_saved_by_an_older_bot_has_no_list_and_works(self):
        old = fake_catalog()
        del old["robux"]
        self.assertEqual(catalog.names(old, "robux"), [])
        self.assertEqual(catalog.robux_warnings({"currency": {"name": "Gems", "amount": 5}}, old), [])

    def test_the_warning_names_the_reward_in_every_language(self):
        warning = catalog.robux_warnings({"currency": {"name": "Gems", "amount": 5}}, fake_catalog(robux=["Gems"]))
        self.assertEqual(len(warning), 1)
        self.assertIn("Gems", warning[0])
        for lang in LANGS:
            with open(f"{ROOT}/locales/{lang}.json", encoding="utf-8") as f:
                texts = json.load(f)
            for key in ("catalog.robux_warning", "catalog.field_robux", "catalog.robux_empty"):
                self.assertIn(key, texts, lang)
            self.assertIn("{names}", texts["catalog.robux_warning"], lang)
            self.assertLess(len(texts["catalog.robux_warning"]), 400, lang)


class WarningsInDrafts(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TempBot()
        self.temp.__enter__()
        await database.init_db()
        config_store.write_json("game_economy.json", {"configured": True, "currencies": ["Coins", "Gems"], "items": ["VIP Pass"]})
        self.patch = mock.patch.object(catalog, "game_catalog", return_value=fake_catalog(robux=["Gems"]))
        self.patch.start()

    async def asyncTearDown(self):
        self.patch.stop()
        await database.close_db()
        self.temp.__exit__(None, None, None)

    @staticmethod
    def fields(embed) -> str:
        return " ".join(f.value for f in embed.fields)

    async def test_the_code_draft_warns_about_a_reward_sold_for_robux(self):
        from cogs import game_codes
        warning = catalog.robux_warnings({"currency": {"name": "Gems", "amount": 50}})[0]
        params = game_codes.code_params("GEMS50", "7d", currency_type="Gems", currency_amount=50)
        self.assertIn(warning, self.fields(game_codes.draft_embed(params)))
        plain = game_codes.code_params("COINS50", "7d", currency_type="Coins", currency_amount=50)
        self.assertNotIn(warning, self.fields(game_codes.draft_embed(plain)))

    async def test_the_gift_draft_warns_too(self):
        from cogs import setup_roblox
        draft = {"currency": "Gems", "amount": 50, "exp": 0, "item": "none", "item_key": "permanent", "message": "",
                 "user": (1, "Builderman")}
        warning = catalog.robux_warnings({"currency": {"name": "Gems", "amount": 50}}, gift=True)[0]
        self.assertIn(warning, self.fields(setup_roblox.gift_draft_embed(draft)), "the gift text (a compensation is fine)")
        self.assertNotEqual(warning, catalog.robux_warnings({"currency": {"name": "Gems", "amount": 50}})[0])
        draft["currency"] = "Coins"
        self.assertNotIn(warning, self.fields(setup_roblox.gift_draft_embed(draft)))

    async def test_check_everything_names_an_old_code_with_a_reward_sold_for_robux(self):
        from cogs import setup_roblox
        await database.add_game_code("OLDGEMS", "Gems", 5, 0, "", "", 0, 0, int(time.time()) + 3600, 1)
        lines = await setup_roblox.catalog_checks()
        self.assertTrue(any("OLDGEMS" in line and "Gems" in line and line.startswith("⚠️") for line in lines), lines)


if __name__ == "__main__":
    unittest.main()
