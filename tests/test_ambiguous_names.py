"""A name the game has in several places (e.g. leaderstats.Coins next to Data.Coins) is refused by the game (Core.luau
findTarget: "ambiguous"), so the bot warns about it instead of showing ✅ (utils/roblox_kit.py)."""
import unittest

from utils import roblox_kit


def scan(values, hooks=()):
    return {"values": list(values), "attributes": [], "hooks": list(hooks), "spots": ["A"], "templates": [],
            "multipliers": []}


class AmbiguousNames(unittest.TestCase):
    def test_a_currency_in_two_places_is_warned_about(self):
        game = scan([("leaderstats.Coins", "IntValue"), ("Data.Coins", "NumberValue")])
        warnings = roblox_kit.reward_warnings(game, {"currency": {"name": "Coins", "amount": 10}})
        self.assertEqual(len(warnings), 1)
        self.assertIn("leaderstats.Coins", warnings[0])
        self.assertTrue(roblox_kit.name_mark(game, "Coins").startswith("⚠️"))

    def test_one_place_is_fine(self):
        game = scan([("leaderstats.Coins", "IntValue")])
        self.assertEqual(roblox_kit.reward_warnings(game, {"currency": {"name": "Coins", "amount": 10}}), [])
        self.assertEqual(roblox_kit.name_mark(game, "Coins"), "✅ Coins")

    def test_the_games_own_function_takes_over(self):
        game = scan([("leaderstats.Coins", "IntValue"), ("Data.Coins", "IntValue")], hooks=["OnReward"])
        self.assertEqual(roblox_kit.reward_warnings(game, {"currency": {"name": "Coins", "amount": 10}}), [])

    def test_pets_in_two_folders_and_exp_in_two_places(self):
        game = scan([("Pets.Dog", "IntValue"), ("PetIndex.Dog", "BoolValue"), ("leaderstats.Coins", "IntValue"),
                     ("leaderstats.XP", "IntValue"), ("Data.Exp", "IntValue")])
        warnings = roblox_kit.egg_warnings(game, "Coins", ["Dog"])
        self.assertEqual(len(warnings), 1)
        self.assertIn("Live.OnHatch", warnings[0])
        self.assertEqual(len(roblox_kit.reward_warnings(game, {"exp": 50})), 1)


if __name__ == "__main__":
    unittest.main()
