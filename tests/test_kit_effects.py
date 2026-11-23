"""The event animations (scripts/DiscordCodes/Effects.luau, on each player's device): which event shows its animation.
Only the choice is run here (under lupa, with a tiny stand-in for Roblox); how an animation looks is checked in Studio."""
import os
import unittest

from tests.helpers import ROOT
from tests.test_kit_live_client import lua_runtime

SOURCE = os.path.join(ROOT, "scripts", "DiscordCodes", "Effects.luau")
STUBS = r"""
local function any() return setmetatable({}, { __index = function() return any() end, __call = function() return any() end,
	__newindex = function() end }) end
game = { GetService = function() return any() end }
Enum = any()
RaycastParams = { new = function() return {} end }
"""
LUA = lua_runtime()


@unittest.skipIf(LUA is None, "lupa is not installed (set BOTDC_LUPA_PATH): the Luau effects were not run")
class WhichEventIsAnimated(unittest.TestCase):
    def setUp(self):
        LUA.execute(STUBS)
        with open(SOURCE, encoding="utf-8") as f:
            self.effects = LUA.execute(f.read())

    def pick(self, events, now=1000):
        table = LUA.table_from([LUA.table_from(e) for e in events])
        chosen = self.effects.Pick(table, now)
        return chosen["id"] if chosen else None

    def test_the_newest_event_with_a_known_animation_that_runs(self):
        events = [{"id": "a", "animation": "coin_storm", "starts_at": 100, "ends_at": 2000},
                  {"id": "b", "animation": "coin_storm", "starts_at": 500, "ends_at": 2000},
                  {"id": "c", "starts_at": 900, "ends_at": 2000},
                  {"id": "d", "animation": "laser_show", "starts_at": 950, "ends_at": 2000},
                  {"id": "e", "animation": "coin_storm", "starts_at": 990, "ends_at": 999}]
        self.assertEqual(self.pick(events), "b", "no animation, an unknown one and an ended one don't count")
        self.assertIsNone(self.pick([{"id": "x", "starts_at": 1, "ends_at": 5000}]))
        self.assertIsNone(self.pick([{"id": "soon", "animation": "coin_storm", "starts_at": 1005, "ends_at": 5000}]),
                          "an event still counting down has no animation yet")
        self.assertIsNone(self.pick([]))

    def test_the_names(self):
        names = self.effects.Names()
        listed = [names[i] for i in range(1, len(names) + 1)]
        self.assertIn("coin_storm", listed)
        self.assertIn("aurora", listed)
        self.assertIn("lucky_breeze", listed)
        self.assertIn("meteor_shower", listed)
        self.assertIn("sakura_festival", listed)

    def test_preview_of_an_unknown_name_shows_nothing(self):
        self.assertFalse(self.effects.Preview("laser_show", 5))
        self.assertFalse(self.effects.Preview("", 5))
        self.assertFalse(self.effects.Preview(None, 5))


if __name__ == "__main__":
    unittest.main()
