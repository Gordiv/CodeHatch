"""utils/roblox_kit.game_scan: egg spots, egg models and the game's own functions come from the NEWEST report of each
place (the published game or Studio; "saved" = the last write, "at" before file version 14), so a spot or a function
removed since an older test doesn't stay for 30 days. The names in player data and the multipliers are still joined
from every report. Several places are joined with each other. Pure data: no game, no network."""
import unittest
from unittest import mock

from utils import cloud_sync, roblox_kit

UNIVERSE = 99
NOW = 1_800_000_000


def entry(at: int, saved: int = None, **fields) -> dict:
    data = {"at": at, "players": 1, "values": [], "attributes": [], "spots": [], "templates": [], "multipliers": [], "hooks": []}
    if saved is not None:
        data["saved"] = saved
    data.update(fields)
    return data


class Base(unittest.TestCase):
    def setUp(self):
        patches = [mock.patch.object(cloud_sync, "status", return_value="ready"),
                   mock.patch.object(cloud_sync, "universe_id", return_value=UNIVERSE),
                   mock.patch.object(roblox_kit, "time", mock.Mock(time=lambda: NOW))]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def scan(self, places: dict, universe: int = UNIVERSE):
        return roblox_kit.game_scan({"universe": universe, "scan": places})


class NewestReportOfAPlace(Base):
    def test_studio_written_later_than_the_published_game_wins_for_spots_models_and_functions(self):
        scan = self.scan({"1": {
            "live": entry(NOW - 5000, NOW - 4000, spots=["Old", "Both"], templates=["OldModel"], hooks=["OnHatch"]),
            "studio": entry(NOW - 900, NOW - 800, spots=["Both", "New"], templates=["Golden"], hooks=["OnReward"])}})
        self.assertEqual(scan["spots"], ["Both", "New"])
        self.assertEqual(scan["templates"], ["Golden"])
        self.assertEqual(scan["hooks"], ["OnReward"])
        self.assertTrue(scan["studio"], "the newest write is Studio's")
        self.assertEqual(scan["at"], NOW - 800)

    def test_the_published_game_written_later_than_studio_wins(self):
        scan = self.scan({"1": {
            "live": entry(NOW - 500, NOW - 100, spots=["Live"], hooks=["OnHatch"]),
            "studio": entry(NOW - 3000, NOW - 2900, spots=["Studio"], hooks=["OnReward"])}})
        self.assertEqual((scan["spots"], scan["hooks"]), (["Live"], ["OnHatch"]))
        self.assertFalse(scan["studio"])
        self.assertEqual(scan["at"], NOW - 100)

    def test_saved_decides_not_the_start_of_the_12_hour_window(self):
        # the published game's report was opened long ago (at) but written just now (saved): it is the newest
        scan = self.scan({"1": {
            "live": entry(NOW - 40000, NOW - 60, spots=["Live"]),
            "studio": entry(NOW - 1000, NOW - 900, spots=["Studio"])}})
        self.assertEqual(scan["spots"], ["Live"], "by 'at' Studio would look newer; by 'saved' it is the live report")
        self.assertEqual(scan["at"], NOW - 60)
        self.assertFalse(scan["studio"])

    def test_a_report_of_the_old_kit_without_saved_is_dated_by_at(self):
        scan = self.scan({"1": {
            "live": entry(NOW - 3000, spots=["Old live"]),
            "studio": entry(NOW - 100, spots=["Old studio"])}})
        self.assertEqual(scan["spots"], ["Old studio"])
        scan = self.scan({"1": {
            "live": entry(NOW - 100, spots=["Old live"]),
            "studio": entry(NOW - 3000, NOW - 2900, spots=["New studio"])}})
        self.assertEqual(scan["spots"], ["Old live"], "an entry with saved and one without are compared by their last write")

    def test_a_removed_spot_or_function_is_gone_at_once_not_after_30_days(self):
        scan = self.scan({"1": {
            "studio": entry(NOW - 10 * 86400, NOW - 10 * 86400, spots=["Spawn", "Removed"], hooks=["OnHatch", "OnReward"]),
            "live": entry(NOW - 60, NOW - 30, spots=["Spawn"], hooks=["OnReward"])}})
        self.assertEqual((scan["spots"], scan["hooks"]), (["Spawn"], ["OnReward"]))

    def test_empty_lists_of_the_newest_report_count(self):
        scan = self.scan({"1": {
            "live": entry(NOW - 3000, NOW - 2900, spots=["Spawn"], templates=["Golden"], hooks=["OnReward"]),
            "studio": entry(NOW - 60, NOW - 30, spots={}, templates=[], hooks={})}})  # an empty Lua table arrives as {}
        self.assertEqual((scan["spots"], scan["templates"], scan["hooks"]), ([], [], []), "the newest report has none")

    def test_player_data_and_multipliers_are_still_joined_from_every_report(self):
        scan = self.scan({"1": {
            "live": entry(NOW - 5000, NOW - 4000, values=["leaderstats.Coins:IntValue"], attributes=["Gems:number"],
                          multipliers=["Coins"], players=4),
            "studio": entry(NOW - 100, NOW - 50, values=["leaderstats.Rubies:IntValue"], multipliers=["Luck", "coins"], players=1)}})
        self.assertEqual([p for p, _ in scan["values"]], ["leaderstats.Coins", "leaderstats.Rubies"])
        self.assertEqual(scan["attributes"], [("Gems", "number")])
        self.assertEqual(sorted(m.lower() for m in scan["multipliers"]), ["coins", "luck"], "Coins/coins are one name")
        self.assertEqual(scan["players"], 4)

    def test_a_tie_is_not_an_error(self):
        scan = self.scan({"1": {"live": entry(NOW - 100, NOW - 50, spots=["Live"]), "studio": entry(NOW - 100, NOW - 50, spots=["Studio"])}})
        self.assertEqual(len(scan["spots"]), 1, "one of them, never both mixed")


class SeveralPlaces(Base):
    def test_places_are_joined_each_with_its_own_newest_report(self):
        scan = self.scan({
            "1": {"live": entry(NOW - 5000, NOW - 4000, spots=["Old A"], hooks=["OnHatch"]),
                  "studio": entry(NOW - 90, NOW - 80, spots=["A"], hooks=["OnReward"])},
            "2": {"live": entry(NOW - 200, NOW - 100, spots=["B1", "B2"], templates=["Golden"], hooks=["OnSpend"])}})
        self.assertEqual(scan["spots"], ["A", "B1", "B2"])
        self.assertEqual(scan["templates"], ["Golden"])
        self.assertEqual(scan["hooks"], ["OnReward", "OnSpend"])
        self.assertEqual(scan["at"], NOW - 80, "the newest write of all places")

    def test_a_place_that_did_not_report_for_30_days_is_ignored_with_its_lists(self):
        scan = self.scan({
            "1": {"live": entry(NOW - 31 * 86400, NOW - 31 * 86400, spots=["Ancient"], hooks=["OnHatch"], values=["Ancient.Value:IntValue"])},
            "2": {"live": entry(NOW - 100, NOW - 50, spots=["Now"])}})
        self.assertEqual(scan["spots"], ["Now"])
        self.assertEqual(scan["hooks"], [])
        self.assertEqual(scan["values"], [])

    def test_only_a_stale_entry_in_a_place_leaves_the_other_one_alone(self):
        scan = self.scan({"1": {"live": entry(NOW - 31 * 86400, NOW - 31 * 86400, spots=["Ancient"]),
                                "studio": entry(NOW - 100, NOW - 50, spots=["Studio"])}})
        self.assertEqual(scan["spots"], ["Studio"])
        self.assertTrue(scan["studio"])

    def test_everything_stale_or_missing_is_no_report(self):
        self.assertIsNone(self.scan({"1": {"live": entry(NOW - 31 * 86400, NOW - 31 * 86400, spots=["Ancient"])}}))
        self.assertIsNone(self.scan({}))
        self.assertIsNone(self.scan({"1": "broken", "2": {"live": "broken"}}))

    def test_another_game_or_a_game_that_is_not_connected_is_no_report(self):
        places = {"1": {"live": entry(NOW - 100, NOW - 50, spots=["Spawn"])}}
        self.assertIsNone(self.scan(places, universe=UNIVERSE + 1))
        with mock.patch.object(cloud_sync, "status", return_value="off"):
            self.assertIsNone(self.scan(places))


class OddData(Base):
    def test_odd_values_do_not_break_the_scan(self):
        scan = self.scan({"1": {"live": entry(NOW - 100, "not a number", spots=[None, 5, "Spawn"], templates="Golden", hooks=None,
                                              values=["Coins"], players="3")}})
        self.assertIn("Spawn", scan["spots"])
        self.assertEqual(scan["templates"], [], "a text is not a list")
        self.assertEqual(scan["at"], NOW - 100, "a saved that is not a number falls back to at")
        self.assertEqual(scan["players"], 3)

    def test_the_same_scan_with_lists_as_dicts_like_the_data_store_gives_back(self):
        scan = self.scan({"1": {"live": entry(NOW - 100, NOW - 50, spots={"1": "A", "2": "B"}, templates={"1": "Golden"})}})
        self.assertEqual((scan["spots"], scan["templates"]), (["A", "B"], ["Golden"]))


if __name__ == "__main__":
    unittest.main()
