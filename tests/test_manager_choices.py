"""The lists the in-game ⚙️ Manager offers (ManagerClient.client.luau) are the same choices the bot accepts for a request
from the game (cogs/game_requests.py), so no choice in the game can be refused by the bot."""
import os
import re
import unittest

from cogs import game_codes, game_requests, live_game

CLIENT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "scripts", "DiscordCodes", "ManagerClient.client.luau")


def lua_list(name: str) -> list:
    source = open(CLIENT, encoding="utf-8").read()
    match = re.search(rf"^local {name} = \{{(.*?)\}}", source, re.M)
    assert match, name
    return re.findall(r'"([^"]+)"', match.group(1))


class ManagerChoices(unittest.TestCase):
    def test_every_list_in_the_game_is_accepted_by_the_bot(self):
        pairs = {
            "CODE_VALIDITY": game_codes.CODE_VALIDITY,
            "ITEM_DURATIONS": game_codes.ITEM_DURATIONS,
            "EGG_DURATIONS": live_game.EGG_DURATIONS,
            "EVENT_DURATIONS": live_game.EVENT_DURATIONS,
            "BAN_DURATIONS": game_requests.BAN_DURATIONS,
            "MULTIPLIERS": live_game.MULTIPLIERS,
        }
        for name, accepted in pairs.items():
            offered = lua_list(name)
            self.assertTrue(offered, name)
            for value in offered:
                self.assertIn(value, accepted, f"{name}: the game offers {value}, the bot would refuse it")

    def test_the_announcement_seconds_match(self):
        source = open(CLIENT, encoding="utf-8").read()
        offered = [int(n) for n in re.findall(r"\{ (\d+), \"\d+ s\" \}", source)]
        self.assertEqual(sorted(offered), sorted(game_requests.ANNOUNCE_SECONDS))


if __name__ == "__main__":
    unittest.main()
