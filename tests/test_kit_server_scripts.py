"""The server scripts of the Roblox kit (scripts/DiscordCodes/Core.luau, Live.luau, Report.luau), run for real under lupa
against a small Roblox mock (tests/roblox_server_mock.lua). Every test gets a fresh Lua runtime, so they run in any order.

Covered:
- Core.IsStudioError and where it is used: Core.Refresh, Live (events/eggs loading, gifts), Report (version, game, catalog):
  the Roblox error "Cannot write to DataStore from studio if API access is disabled" (lower case "studio") is the Studio
  case, not a warning about a broken game;
- Report: "saved" (time of the last write) next to "at" (start of the 12-hour window), "placeVersion" of the report, and
  the merge of the reports of several servers: egg spots, egg models and own functions come from the newest report (a
  removed spot disappears at once), unless the saved one comes from a newer version of the game; the lists of names in
  player data are still joined;
- the catalog is not written again by a second server when nothing changed;
- Live: the chance text of a pet (Roblox: rounded only 4 places below the first digit, with the rounding note), the egg model (a Folder with the model's name is skipped),
  the spots of the egg stands (an egg stays where it stood, a named spot comes first).

Without lupa (not in the project's .venv; set BOTDC_LUPA_PATH to a folder that holds it) these tests are SKIPPED."""
import json
import os
import time
import unittest
from unittest import mock

from tests.helpers import ROOT
from tests.test_kit_live_client import lua_runtime

SOURCE = os.path.join(ROOT, "scripts", "DiscordCodes")
MOCK = os.path.join(ROOT, "tests", "roblox_server_mock.lua")
HAVE_LUA = lua_runtime() is not None
STUDIO_ERROR = "Cannot write to DataStore from studio if API access is disabled"

PRELUDE = r"""
function newSpot(name, x)
	local spot = M.new("Part", { Name = name, Size = Vector3.new(6, 1, 6), CFrame = CFrame.new(x, 0, 0) })
	spot.Parent = M.services.Workspace
	M.tagged.DiscordEggSpot = M.tagged.DiscordEggSpot or {}
	table.insert(M.tagged.DiscordEggSpot, spot)
	return spot
end
function dropSpot(spot)
	for i, s in ipairs(M.tagged.DiscordEggSpot) do
		if s == spot then table.remove(M.tagged.DiscordEggSpot, i) break end
	end
	spot.Parent = nil
end
function stand(id)
	local folder = M.services.Workspace:FindFirstChild("DiscordEggStands")
	return folder and folder:FindFirstChild("DiscordEgg_" .. tostring(id)) or nil
end
function standX(id)
	local model = stand(id)
	return model and model:GetPivot().Position.X or nil
end
function setEggs(list)
	M.stores["DiscordLiveContent"].data.Eggs = { eggs = list }
	Live.RefreshEggs()
	M.flush()
end
function countWrites(store)
	local writes = { n = 0 }
	local real = store.UpdateAsync
	store.UpdateAsync = function(self, key, fn)
		local result = real(self, key, fn)
		if result ~= nil then writes.n = writes.n + 1 end
		return result
	end
	return writes
end
function templatesFolder()
	local folder = M.services.ReplicatedStorage:FindFirstChild("DiscordEggs")
	if not folder then
		folder = M.new("Folder", { Name = "DiscordEggs" })
		folder.Parent = M.services.ReplicatedStorage
	end
	return folder
end
-- a model with one part called <name>Part (the part tells which template a stand was made from)
function addModel(name)
	local model = M.new("Model", { Name = name })
	M.new("Part", { Name = name .. "Part", Size = Vector3.new(4, 4, 4) }).Parent = model
	model.Parent = templatesFolder()
end
"""


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


class Kit:
    """One game server: its own Lua runtime with the mock and the three kit scripts loaded."""

    def __init__(self, place_id: int = 555, studio: bool = False, place_version=None):
        self.lua = lua = lua_runtime()
        self.M = M = lua.execute(read(MOCK))
        M.encode = lambda value: json.dumps(self.from_lua(value), sort_keys=True)
        M.decode = lambda text: self.to_lua(json.loads(text))
        lua.globals().M = M
        self.core = core = lua.execute(read(os.path.join(SOURCE, "Core.luau")))
        marker = lua.table_from({"module": core})
        lua.globals().Core = core
        lua.globals().script = lua.eval(
            "function(marker) return { Parent = { WaitForChild = function(_, name) return marker end } } end")(marker)
        lua.globals().require = lua.eval("function(m) return m.module end")
        self.live = lua.globals().Live = lua.execute(read(os.path.join(SOURCE, "Live.luau")))
        self.report = lua.globals().Report = lua.execute(read(os.path.join(SOURCE, "Report.luau")))
        lua.execute(f"game.PlaceId = {int(place_id)}; M.studio = {'true' if studio else 'false'}")
        if place_version is not None:
            lua.execute(f"game.PlaceVersion = {int(place_version)}")
        lua.execute(PRELUDE)

    # --- Python <-> Lua
    def to_lua(self, value):
        if isinstance(value, dict):
            return self.lua.table_from({k: self.to_lua(v) for k, v in value.items() if v is not None})
        if isinstance(value, (list, tuple)):
            return self.lua.table_from([self.to_lua(v) for v in value])
        return value

    def from_lua(self, value):
        if self.lua.globals().type(value) != "table":
            return value
        keys = list(value.keys())
        if not keys:
            return []  # the JSON of an empty Lua table is an empty list
        if all(isinstance(k, int) for k in keys) and sorted(keys) == list(range(1, len(keys) + 1)):
            return [self.from_lua(value[k]) for k in sorted(keys)]
        return {str(k): self.from_lua(value[k]) for k in keys}

    def run(self, code: str):
        return self.from_lua(self.lua.execute(code))

    # --- the game server
    def warnings(self) -> list:
        return [self.M.warnings[i] for i in range(1, len(self.M.warnings) + 1)]

    def store(self, name: str = "DiscordLiveContent") -> dict:
        return self.from_lua(self.M.stores[name].data)

    def load_store(self, data: dict, name: str = "DiscordLiveContent"):
        """What another server saved (the real DataStore keeps JSON: the data goes through it)."""
        self.M.stores[name].data = self.M.decode(json.dumps(data))

    def writes(self, store: str = "DiscordLiveContent"):
        """A counter of the writes (UpdateAsync calls that wrote something) to a store: call it, read counter()."""
        table = self.lua.globals().countWrites(self.M.stores[store])
        return lambda: int(table["n"])

    def set_now(self, seconds: int):
        self.M.now = seconds

    def start_live(self):
        """A player is on the server (text is filtered with a player's id), Live is running."""
        self.run("M.addPlayer(101, 1000, { 'Cat' }); Live.Config.GiftDelaySeconds = 0; Live.Start(); M.flush()")

    def set_eggs(self, eggs: list):
        self.lua.globals().setEggs(self.to_lua(eggs))

    def stands(self, *ids) -> dict:
        """id -> x position of the stand of that egg (None: no stand)."""
        return {i: self.lua.globals().standX(i) for i in ids}


def egg(egg_id: int, **fields) -> dict:
    data = {"id": egg_id, "name": f"Egg {egg_id}", "currency": "Coins", "price": 10, "color": "#FFD700", "spot": "",
            "template": "", "ends_at": 0, "pets": [{"name": "Cat", "chance": 100}]}
    data.update(fields)
    return data


@unittest.skipIf(not HAVE_LUA, "lupa is not installed (set BOTDC_LUPA_PATH): the kit server scripts were not run")
class StudioErrors(unittest.TestCase):
    """A DataStore error of Studio (API access off) is told once as a hint, never as a failure of the game."""

    def setUp(self):
        self.kit = Kit()

    def test_what_counts_as_a_studio_error(self):
        studio = self.kit.core.IsStudioError
        for text in (STUDIO_ERROR, "403: Studio access to APIs is not allowed", "StudioAccessToApisNotAllowed",
                     "104: Cannot write to DataStore from STUDIO", "x studio y"):
            self.assertTrue(studio(text), text)
        for text in ("502: API Services rejected request with error. Error code: 1", "request was rejected", "",
                     "HTTP 429 (Too Many Requests)", "Stud io", "stud"):
            self.assertFalse(studio(text), text)
        self.assertFalse(studio(None), "nil is not an error text")
        self.assertFalse(studio(502))
        self.assertFalse(self.kit.run("return Core.IsStudioError({})"), "a table is not a Studio error")
        self.assertTrue(self.kit.run("return Core.IsStudioError(setmetatable({}, { __tostring = function() return 'from studio' end }))"),
                        "an error object is read through tostring")

    def test_core_refresh_says_it_once_for_studio_and_warns_for_anything_else(self):
        self.kit.run(f"M.stores['DiscordCodeSync'].GetAsync = function() error({STUDIO_ERROR!r}, 0) end")
        self.assertFalse(self.kit.run("return Core.Refresh()"))
        self.assertFalse(self.kit.run("return Core.Refresh()"))
        warnings = self.kit.warnings()
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn("Enable Studio Access to API Services", warnings[0])
        self.assertNotIn("Could not load", warnings[0])
        self.kit.run("M.stores['DiscordCodeSync'].GetAsync = function() error('503: service unavailable', 0) end")
        self.assertFalse(self.kit.run("return Core.Refresh()"))
        self.assertIn("Could not load the codes: 503: service unavailable", self.kit.warnings()[-1])
        self.assertEqual(len(self.kit.warnings()), 2)

    def test_core_refresh_still_reads_codes_when_the_store_works(self):
        self.assertTrue(self.kit.run("return Core.Refresh()"))
        self.assertEqual(self.kit.warnings(), [])

    def test_live_loading_events_and_eggs_in_studio(self):
        self.kit.run(f"M.stores['DiscordLiveContent'].GetAsync = function() error({STUDIO_ERROR!r}, 0) end")
        self.assertFalse(self.kit.run("return Live.RefreshEvents()"))
        self.assertFalse(self.kit.run("return Live.RefreshEggs()"))
        self.assertFalse(self.kit.run("return Live.RefreshEggs()"))
        warnings = self.kit.warnings()
        self.assertEqual(len(warnings), 1, "one hint for events and eggs together, not a warning per poll")
        self.assertIn("DataStore is not available in Studio", warnings[0])
        self.assertNotIn("Could not load", warnings[0])

    def test_live_loading_with_another_error_warns_with_the_name_of_the_entry(self):
        self.kit.run("M.stores['DiscordLiveContent'].GetAsync = function() error('HTTP 500', 0) end")
        self.assertFalse(self.kit.run("return Live.RefreshEggs()"))
        self.assertEqual(self.kit.warnings(), ["[DiscordLive] Could not load Eggs: HTTP 500"])

    def test_gifts_check_in_studio_is_silent_and_another_error_warns(self):
        self.kit.run("M.addPlayer(101, 5, {})")
        self.kit.run(f"M.stores['DiscordGifts'].ListKeysAsync = function() error({STUDIO_ERROR!r}, 0) end")
        self.kit.run("Live.DeliverGifts(M.players[1])")
        self.assertEqual(self.kit.warnings(), [], "Studio: no warning for a gift check")
        self.kit.run("M.stores['DiscordGifts'].ListKeysAsync = function() error('HTTP 500', 0) end")
        self.kit.run("Live.DeliverGifts(M.players[1])")
        warnings = self.kit.warnings()
        self.assertEqual(len(warnings), 1)
        self.assertIn("Could not check gifts for Player101: HTTP 500", warnings[0])

    def test_reports_in_studio_return_false_without_a_warning(self):
        self.kit.run("Report.Setup({ edition = 'full', live = Live })")
        self.kit.run(f"M.stores['DiscordLiveContent'].UpdateAsync = function() error({STUDIO_ERROR!r}, 0) end")
        self.assertFalse(self.kit.run("return Report.ReportVersion(14)"))
        self.assertFalse(self.kit.run("return Report.ReportGame()"))
        self.assertFalse(self.kit.run("return Report.ReportCatalog()"))
        self.assertEqual(self.kit.warnings(), [], "Studio without API access: the hint comes from Core/Live, not a warning here")

    def test_reports_with_another_error_warn(self):
        self.kit.run("Report.Setup({ edition = 'full', live = Live })")
        self.kit.run("M.stores['DiscordLiveContent'].UpdateAsync = function() error('HTTP 500', 0) end")
        self.assertFalse(self.kit.run("return Report.ReportVersion(14)"))
        self.assertFalse(self.kit.run("return Report.ReportGame()"))
        self.assertFalse(self.kit.run("return Report.ReportCatalog()"))
        self.assertEqual(len(self.kit.warnings()), 3, self.kit.warnings())
        self.assertTrue(all("HTTP 500" in w for w in self.kit.warnings()))


@unittest.skipIf(not HAVE_LUA, "lupa is not installed (set BOTDC_LUPA_PATH): the kit server scripts were not run")
class SavedAndPlaceVersion(unittest.TestCase):
    """Every report entry has "at" (the window of 12 hours starts), "saved" (the last write) and a place version."""

    def setUp(self):
        self.kit = Kit(place_version=7)
        self.kit.run("Report.Setup({ edition = 'full', live = Live })")
        self.kit.run("M.addPlayer(1, 5, { 'Cat' })")
        self.now = int(self.kit.M.now)

    def entry(self, kind="live"):
        return self.kit.store()["GameScan"]["places"]["555"][kind]

    def test_the_game_report_carries_saved_at_and_the_place_version(self):
        self.kit.run("Report.ScanPlayer(M.players[1])")
        self.assertTrue(self.kit.run("return Report.ReportGame()"))
        first = self.entry()
        self.assertEqual((first["at"], first["saved"], first["placeVersion"]), (self.now, self.now, 7))
        self.kit.run("newSpot('Spawn', 0)")
        self.kit.set_now(self.now + 100)
        self.assertTrue(self.kit.run("return Report.ReportGame()"))
        second = self.entry()
        self.assertEqual(second["at"], self.now, "the window of 12 hours still starts when it was opened")
        self.assertEqual(second["saved"], self.now + 100, "saved is the time of the newest write")
        self.assertEqual(second["spots"], ["Spawn"])
        self.kit.set_now(self.now + 12 * 3600 + 50)
        self.kit.run("newSpot('Lobby', 5)")
        self.assertTrue(self.kit.run("return Report.ReportGame()"))
        third = self.entry()
        self.assertEqual((third["at"], third["saved"]), (self.now + 12 * 3600 + 50,) * 2, "after 12 hours a new window")

    def test_without_a_place_version_the_report_still_works(self):
        kit = Kit()  # a game where PlaceVersion is not there (older engine, tests)
        kit.run("Report.Setup({ edition = 'full', live = Live })")
        self.assertTrue(kit.run("return Report.ReportGame()"))
        entry = kit.store()["GameScan"]["places"]["555"]["live"]
        self.assertEqual(entry.get("placeVersion", 0), 0)
        self.assertEqual(entry["saved"], entry["at"])

    def test_version_and_catalog_reports_have_saved_too(self):
        self.assertTrue(self.kit.run("return Report.ReportVersion(14)"))
        version = self.kit.store()["KitVersions"]["places"]["555"]["live"]
        self.assertEqual((version["version"], version["at"], version["saved"]), (14, self.now, self.now))
        self.assertTrue(self.kit.run("return Report.ReportCatalog()"))
        self.assertEqual(self.kit.store()["GameCatalog"]["places"]["555"]["live"]["saved"], self.now)

    def test_studio_and_the_published_game_are_saved_apart(self):
        studio = Kit(studio=True, place_version=7)
        studio.run("Report.Setup({ edition = 'full', live = Live })")
        studio.run("newSpot('StudioSpot', 0)")
        self.assertTrue(studio.run("return Report.ReportGame()"))
        place = studio.store()["GameScan"]["places"]["555"]
        self.assertEqual(list(place), ["studio"])
        self.assertEqual(place["studio"]["spots"], ["StudioSpot"])


@unittest.skipIf(not HAVE_LUA, "lupa is not installed (set BOTDC_LUPA_PATH): the kit server scripts were not run")
class ReportMerge(unittest.TestCase):
    """mergeScan: spots, egg models and own functions are the same on every server of one version of the game, so the
    newest report replaces them; the names in player data differ per player, so those are still joined."""

    def saved(self, **fields) -> dict:
        """The entry another server left in the DataStore, 100 s ago."""
        entry = {"at": 1_000_000 - 100, "saved": 1_000_000 - 100, "placeVersion": 5, "players": 3, "sig": "other",
                 "values": ["leaderstats.Coins:IntValue", "Old.Thing:IntValue"], "attributes": ["Gems:number"], "multipliers": ["Coins"],
                 "spots": ["Old", "Keep"], "templates": ["OldModel"], "hooks": ["OnHatch", "OnReward"]}
        entry.update(fields)
        return {"GameScan": {"places": {"555": {"live": entry}}}}

    def server(self, saved=None, spots=(), models=(), hooks=(), version=5, values=("Gems",), players=1):
        kit = Kit(place_version=version)
        kit.set_now(1_000_000)
        kit.run("Report.Setup({ edition = 'full', live = Live })")
        if saved is not None:
            kit.load_store(saved)
        for i, name in enumerate(spots):
            kit.run(f"newSpot({name!r}, {i * 10})")
        for name in models:
            kit.run(f"addModel({name!r})")
        for hook in hooks:
            kit.run(f"Core.{hook} = function() return true end" if hook in ("OnReward", "OnSpend") else f"Live.{hook} = function() return true end")
        for i in range(players):
            kit.run(f"M.addPlayer({100 + i}, 5, {{}}); M.new('IntValue', {{ Name = {values[0]!r} }}).Parent = M.players[#M.players]"
                    f"; Report.ScanPlayer(M.players[#M.players])")
        self.assertTrue(kit.run("return Report.ReportGame()"))
        return kit

    def result(self, kit) -> dict:
        return kit.store()["GameScan"]["places"]["555"]["live"]

    def test_the_newest_report_replaces_spots_models_and_functions_at_once(self):
        kit = self.server(self.saved(), spots=["Keep", "New"], models=["NewModel"], hooks=["OnReward"])
        merged = self.result(kit)
        self.assertEqual(merged["spots"], ["Keep", "New"], "the removed spot 'Old' is gone")
        self.assertEqual(merged["templates"], ["NewModel"], "the removed model is gone")
        self.assertEqual(merged["hooks"], ["OnReward"], "the removed function (OnHatch) is gone")
        self.assertEqual(merged["placeVersion"], 5)

    def test_copies_of_one_spot_are_counted_not_just_named(self):
        kit = self.server(self.saved(spotCount=9), spots=["EggSpot", "EggSpot", "EggSpot"])
        merged = self.result(kit)
        self.assertEqual(merged["spots"], ["EggSpot"])
        self.assertEqual(merged["spotCount"], 3, "three parts with the tag, one name (Ctrl+D keeps it)")
        from utils import roblox_kit
        with mock.patch.object(roblox_kit.cloud_sync, "status", return_value="ready"), \
                mock.patch.object(roblox_kit.cloud_sync, "universe_id", return_value=1):
            scan = roblox_kit.game_scan({"universe": 1, "scan": {"555": {"live": {**merged, "at": time.time()}}}})
        self.assertEqual(scan["spot_count"], 3)
        self.assertEqual(roblox_kit.spots_warning(scan, 3), "", "three eggs, three spots: no warning")
        self.assertIn("4", roblox_kit.spots_warning(scan, 4))
        old_file = {"universe": 1, "scan": {"555": {"live": {"spots": ["A", "B"], "at": time.time()}}}}
        with mock.patch.object(roblox_kit.cloud_sync, "status", return_value="ready"), \
                mock.patch.object(roblox_kit.cloud_sync, "universe_id", return_value=1):
            self.assertEqual(roblox_kit.game_scan(old_file)["spot_count"], 2, "an older file: the names")

    def test_the_names_in_player_data_and_multipliers_are_still_joined(self):
        kit = self.server(self.saved(), spots=["Keep"], values=("Rubies",))
        merged = self.result(kit)
        self.assertEqual(merged["values"], ["leaderstats.Coins:IntValue", "Rubies:IntValue", "Old.Thing:IntValue"],
                         "the values of both servers, leaderstats first (a cut at the limit never drops them)")
        self.assertEqual(merged["attributes"], ["Gems:number"], "the attribute of the other server stays")
        self.assertEqual(merged["multipliers"], ["Coins"], "the multiplier of the other server stays")
        self.assertGreaterEqual(merged["players"], 3, "the highest number of players seen")

    def test_a_big_pets_folder_never_pushes_leaderstats_out_of_the_report(self):
        kit = Kit()
        kit.lua.globals().petNames = kit.to_lua([f"Pet{i}" for i in range(200)])
        paths = kit.run("local p = M.addPlayer(77, 5, petNames); local s = p:FindFirstChild('leaderstats'); "
                        "s.Parent = nil; s.Parent = p; "  # leaderstats now comes after the Pets folder
                        "local values = Core.DescribePlayerData(p); local out = {}; "
                        "for i, v in ipairs(values) do out[i] = v.path end; return table.concat(out, ',')").split(",")
        self.assertEqual(len(paths), 150)
        self.assertEqual(paths[0], "leaderstats.Coins")

    def test_more_than_2000_values_before_leaderstats_still_keep_it(self):
        kit = Kit()
        kit.lua.globals().petNames = kit.to_lua([f"Pet{i}" for i in range(2100)])
        paths = kit.run("local p = M.addPlayer(78, 5, petNames); local s = p:FindFirstChild('leaderstats'); "
                        "s.Parent = nil; s.Parent = p; "
                        "local values = Core.DescribePlayerData(p); local out = {}; "
                        "for i, v in ipairs(values) do out[i] = v.path end; return table.concat(out, ',')").split(",")
        self.assertEqual(paths[0], "leaderstats.Coins", "leaderstats is read before the folder that fills the 2000")

    def test_a_server_of_an_older_version_never_replaces_the_newer_lists(self):
        newer = self.saved(placeVersion=8, spots=["Spawn"], templates=["Golden"], hooks=["OnReward"])
        kit = self.server(newer, spots=["Old", "Keep"], models=["OldModel"], hooks=["OnHatch"], version=7, values=("Rubies",))
        merged = self.result(kit)
        self.assertEqual(merged["spots"], ["Spawn"])
        self.assertEqual(merged["templates"], ["Golden"])
        self.assertEqual(merged["hooks"], ["OnReward"])
        self.assertEqual(merged["placeVersion"], 8, "the newer version is kept")
        self.assertIn("Rubies:IntValue", merged["values"], "but its player data names are still joined")

    def test_a_server_of_a_newer_version_replaces_the_lists_and_raises_the_version(self):
        older = self.saved(placeVersion=8, spots=["Spawn"], templates=["Golden"], hooks=["OnReward"])
        kit = self.server(older, spots=["Lobby"], models=["Ice"], hooks=[], version=9)
        merged = self.result(kit)
        self.assertEqual((merged["spots"], merged["templates"], merged["hooks"]), (["Lobby"], ["Ice"], []))
        self.assertEqual(merged["placeVersion"], 9)

    def test_the_same_version_the_report_of_this_server_wins(self):
        kit = self.server(self.saved(placeVersion=5), spots=["Mine"], version=5)
        self.assertEqual(self.result(kit)["spots"], ["Mine"])

    def test_a_report_of_the_old_kit_without_a_version_is_replaced_by_a_versioned_one(self):
        old = self.saved()
        del old["GameScan"]["places"]["555"]["live"]["placeVersion"]
        kit = self.server(old, spots=["Mine"], version=3)
        merged = self.result(kit)
        self.assertEqual(merged["spots"], ["Mine"])
        self.assertEqual(merged["placeVersion"], 3)

    def test_a_game_without_a_place_version_replaces_a_report_without_one(self):
        old = self.saved()
        del old["GameScan"]["places"]["555"]["live"]["placeVersion"]
        kit = Kit()  # PlaceVersion is nil: 0 against 0, this server is the newest
        kit.set_now(1_000_000)
        kit.run("Report.Setup({ edition = 'full', live = Live })")
        kit.load_store(old)
        kit.run("newSpot('Mine', 0)")
        self.assertTrue(kit.run("return Report.ReportGame()"))
        self.assertEqual(self.result(kit)["spots"], ["Mine"])

    def test_an_old_report_is_not_merged_at_all(self):
        old = self.saved(at=1_000_000 - 13 * 3600, saved=1_000_000 - 13 * 3600, placeVersion=99)
        kit = self.server(old, spots=["Mine"], version=1)
        merged = self.result(kit)
        self.assertEqual((merged["spots"], merged["placeVersion"], merged["at"]), (["Mine"], 1, 1_000_000),
                         "a report older than 12 hours starts again from scratch, whatever its version")
        self.assertNotIn("Old.Thing:IntValue", merged["values"])

    def test_nothing_changed_nothing_written(self):
        first = self.server(None, spots=["Spawn"], models=["Golden"], hooks=["OnReward"], version=5)
        data = first.store()
        second = Kit(place_version=5)
        second.set_now(1_000_000 + 600)
        second.run("Report.Setup({ edition = 'full', live = Live })")
        second.load_store(data)
        for name in ("Spawn",):
            second.run(f"newSpot({name!r}, 0)")
        second.run("addModel('Golden'); Core.OnReward = function() return true end")
        second.run("M.addPlayer(100, 5, {}); M.new('IntValue', { Name = 'Gems' }).Parent = M.players[1]; Report.ScanPlayer(M.players[1])")
        writes = second.writes()
        self.assertTrue(second.run("return Report.ReportGame()"))
        self.assertEqual(writes(), 0, "the same lists as the saved report: no write")

    def test_a_removed_spot_is_written_even_when_everything_else_is_the_same(self):
        first = self.server(None, spots=["Spawn", "Lobby"], version=5)
        second = Kit(place_version=5)
        second.set_now(1_000_000 + 600)
        second.run("Report.Setup({ edition = 'full', live = Live })")
        second.load_store(first.store())
        second.run("newSpot('Spawn', 0)")
        second.run("M.addPlayer(100, 5, {}); M.new('IntValue', { Name = 'Gems' }).Parent = M.players[1]; Report.ScanPlayer(M.players[1])")
        self.assertTrue(second.run("return Report.ReportGame()"))
        entry = second.store()["GameScan"]["places"]["555"]["live"]
        self.assertEqual(entry["spots"], ["Spawn"])
        self.assertEqual(entry["saved"], 1_000_000 + 600)
        self.assertEqual(entry["at"], 1_000_000, "still the first window")

    def test_a_long_list_is_cut_at_the_limit(self):
        limit = int(Kit().run("return Report.Config.ScanMaxList"))
        kit = Kit(place_version=5)
        kit.set_now(1_000_000)
        kit.run("Report.Setup({ edition = 'full', live = Live })")
        kit.load_store(self.saved())
        for i in range(limit + 10):
            kit.run(f"newSpot('Spot{i:04d}', {i})")
        self.assertTrue(kit.run("return Report.ReportGame()"))
        self.assertEqual(len(self.result(kit)["spots"]), limit)


@unittest.skipIf(not HAVE_LUA, "lupa is not installed (set BOTDC_LUPA_PATH): the kit server scripts were not run")
class CatalogAndSecondServer(unittest.TestCase):
    """A second server that reports what the first one already saved writes nothing (one DataStore request less per
    server start): the version, the game report and the catalog."""

    def servers(self):
        first = Kit(place_version=5)
        first.run("Report.Setup({ edition = 'full', live = Live })")
        module = "local m = M.new('ModuleScript', { Name = 'DiscordCatalog' }); " \
                 "m.module = { Currencies = { 'Coins', 'Gems' }, Items = { 'Sword' }, Pets = { { Name = 'Dog', Rarity = 'Common' } }," \
                 " Eggs = { { Name = 'Basic Egg', Currency = 'Coins', Price = 100, Pets = { Dog = 100 } } }, Multipliers = { 'Coins' } };" \
                 " m.Parent = M.services.ServerScriptService"
        first.run(module)
        first.run("newSpot('Spawn', 0); addModel('Golden')")
        for call in ("Report.ReportVersion(14)", "Report.ReportCatalog()", "Report.ReportGame()"):
            self.assertTrue(first.run(f"return {call}"), call)
        second = Kit(place_version=5)
        second.run("Report.Setup({ edition = 'full', live = Live })")
        second.run(module)
        second.run("newSpot('Spawn', 0); addModel('Golden')")
        second.load_store(first.store())
        second.set_now(int(first.M.now) + 600)
        return first, second

    def test_the_catalog_of_an_unchanged_game_is_not_written_by_the_next_server(self):
        first, second = self.servers()
        writes = second.writes()
        self.assertTrue(second.run("return Report.ReportCatalog()"))
        before = first.store()["GameCatalog"]["places"]["555"]["live"]
        after = second.store()["GameCatalog"]["places"]["555"]["live"]
        self.assertEqual(writes(), 0, "the saved catalog is the same as this server's (saved/at are not part of it)")
        self.assertEqual(after, before)

    def test_the_version_report_of_the_next_server_is_not_written_again(self):
        _, second = self.servers()
        writes = second.writes()
        self.assertTrue(second.run("return Report.ReportVersion(14)"))
        self.assertEqual(writes(), 0)

    def test_the_game_report_with_the_same_lists_is_not_written_again(self):
        _, second = self.servers()
        writes = second.writes()  # neither server scanned a player: the lists are the same
        self.assertTrue(second.run("return Report.ReportGame()"))
        self.assertEqual(writes(), 0)

    def test_what_players_buy_with_robux_goes_to_the_bot(self):
        first, second = self.servers()
        self.assertEqual(first.store()["GameCatalog"]["places"]["555"]["live"].get("robux"), [],
                         "a catalog without SoldForRobux sends an empty list")
        # each server reads the catalog once: the next server has the new list
        second.run("local m = M.services.ServerScriptService:FindFirstChild('DiscordCatalog'); m.module.SoldForRobux = { 'Gems', 'Gems', 'Sword' }")
        self.assertTrue(second.run("return Report.ReportCatalog()"))
        self.assertEqual(second.store()["GameCatalog"]["places"]["555"]["live"]["robux"], ["Gems", "Sword"])

    def test_a_changed_catalog_is_written(self):
        _, second = self.servers()
        second.run("local m = M.services.ServerScriptService:FindFirstChild('DiscordCatalog'); table.insert(m.module.Currencies, 'Rubies')")
        writes = second.writes()
        self.assertTrue(second.run("return Report.ReportCatalog()"))
        self.assertEqual(writes(), 1)
        self.assertIn("Rubies", second.store()["GameCatalog"]["places"]["555"]["live"]["currencies"])


@unittest.skipIf(not HAVE_LUA, "lupa is not installed (set BOTDC_LUPA_PATH): the kit server scripts were not run")
class EggStands(unittest.TestCase):
    """Live: what a stand shows and where it stands."""

    def setUp(self):
        self.kit = Kit()
        self.kit.start_live()

    def pets_text(self, egg_id: int) -> str:
        return self.kit.run(f"local info = stand({egg_id}).PrimaryPart:FindFirstChild('EggInfo'); local out = {{}}; local tag = info:FindFirstChild('LuckTag'); if tag.Visible then table.insert(out, tag.Text) end; for _, row in ipairs(info:FindFirstChild('Pets'):GetChildren()) do table.insert(out, row:FindFirstChild('Name').Text .. '  ' .. row:FindFirstChild('Percent').Text) end; return table.concat(out, '\\n')")

    def test_a_drawing_that_waited_for_the_filter_leaves_no_stand_with_old_chances(self):
        self.spots("A", "B")
        self.kit.run("M.pauseOn['Slow egg'] = true")
        self.kit.set_eggs([egg(1, name="Slow egg", pets=[{"name": "Cat", "chance": 50}, {"name": "Dog", "chance": 50}])])
        # while that drawing waits for Roblox's text filter, the owner changes the chances
        self.kit.set_eggs([egg(1, name="New egg", pets=[{"name": "Cat", "chance": 90}, {"name": "Dog", "chance": 10}])])
        self.kit.run("coroutine.resume(M.paused); M.flush()")
        count = self.kit.run("return #M.services.Workspace:FindFirstChild('DiscordEggStands'):GetChildren()")
        self.assertEqual(count, 1, "one stand, no second one with the old chances")
        self.assertEqual(self.pets_text(1), "Cat  90%\nDog  10%")

    def note_shown(self, egg_id: int) -> bool:
        return self.kit.run(f"return stand({egg_id}).PrimaryPart:FindFirstChild('EggInfo'):FindFirstChild('RoundedNote').Visible")

    # --- chance text (Roblox, paid random items: rounded only 4 decimal places below the first non-zero digit, and a
    # rounded list carries the sentence about rounding)
    def test_a_tiny_chance_is_not_shown_as_zero(self):
        self.spots("A", "B")
        pets = [{"name": "Rare", "chance": 0.001}, {"name": "Never", "chance": 0}, {"name": "Edge", "chance": 0.005},
                {"name": "Under", "chance": 0.0049}, {"name": "Almost", "chance": 9.999},
                {"name": "Big", "chance": 89.9901}]  # 100 in all, as the bot saves the chances
        self.kit.set_eggs([egg(1, pets=pets)])
        lines = dict(line.rsplit("  ", 1) for line in self.pets_text(1).split("\n"))
        self.assertEqual(lines, {"Rare": "0.001%", "Never": "0%", "Edge": "0.005%", "Under": "0.0049%", "Almost": "9.999%",
                                 "Big": "89.99%"})
        self.assertTrue(self.note_shown(1), "89.9901 is shown rounded, so the rounding sentence is there")

    def test_the_other_chances_read_as_before(self):
        self.spots("A", "B")
        pets = [{"name": "A", "chance": 60}, {"name": "B", "chance": 26.349}, {"name": "C", "chance": 12.4}, {"name": "D", "chance": 1},
                {"name": "E", "chance": 0.25}, {"name": "F", "chance": "0.001"}]
        self.kit.set_eggs([egg(1, pets=pets)])
        self.assertEqual(self.pets_text(1), "A  60%\nB  26.349%\nC  12.4%\nD  1%\nE  0.25%\nF  0.001%")
        self.assertFalse(self.note_shown(1), "nothing rounded: no rounding sentence")

    def test_thirds_are_shown_to_three_decimals_with_the_rounding_sentence(self):
        self.spots("A", "B")
        pets = [{"name": "A", "chance": 33.3333}, {"name": "B", "chance": 33.3333}, {"name": "C", "chance": 33.3334}]
        self.kit.set_eggs([egg(1, pets=pets)])
        self.assertEqual(sorted(self.pets_text(1).split("\n")), ["A  33.333%", "B  33.333%", "C  33.333%"])
        self.assertTrue(self.note_shown(1))

    def test_chances_that_do_not_add_up_to_100_show_what_a_player_really_gets(self):
        self.spots("A", "B")
        self.kit.set_eggs([egg(1, pets=[{"name": "Cat", "chance": 3}, {"name": "Dog", "chance": 1}])])
        self.assertEqual(self.pets_text(1), "Cat  75%\nDog  25%")

    # --- the model of the egg
    def test_a_folder_with_the_name_of_the_model_does_not_hide_the_default_model(self):
        self.spots("A", "B")
        self.kit.run("addModel('Default'); templatesFolder(); M.new('Folder', { Name = 'Golden' }).Parent = templatesFolder()")
        self.kit.set_eggs([egg(1, template="Golden"), egg(2, template="")])
        primary = lambda i: self.kit.run(f"return stand({i}).PrimaryPart.Name")
        self.assertEqual(primary(1), "DefaultPart", "'Golden' is a Folder: the game falls back to the Default model")
        self.assertEqual(primary(2), "DefaultPart")
        self.assertEqual(self.kit.warnings(), [])

    def test_a_folder_in_place_of_the_default_model_gives_the_plain_egg(self):
        self.spots("A", "B")
        self.kit.run("M.new('Folder', { Name = 'Default' }).Parent = templatesFolder()")
        self.kit.set_eggs([egg(1)])
        self.assertEqual(self.kit.run("return stand(1).PrimaryPart.Name"), "Egg", "the plain egg, nothing built from the folder")

    def test_a_folder_named_like_the_model_without_a_default_gives_the_plain_egg_and_a_hint(self):
        self.spots("A", "B")
        self.kit.run("M.new('Folder', { Name = 'Golden' }).Parent = templatesFolder()")
        self.kit.set_eggs([egg(1, template="Golden")])
        self.assertEqual(self.kit.run("return stand(1).PrimaryPart.Name"), "Egg")
        self.assertTrue(any("Egg template 'Golden' not found" in w for w in self.kit.warnings()), self.kit.warnings())

    def test_a_model_and_a_single_part_both_work_as_a_template(self):
        self.spots("A", "B")
        self.kit.run("addModel('Golden'); M.new('Part', { Name = 'Ice', Size = Vector3.new(4, 4, 4) }).Parent = templatesFolder()")
        self.kit.set_eggs([egg(1, template="Golden"), egg(2, template="Ice")])
        self.assertEqual(self.kit.run("return stand(1).PrimaryPart.Name"), "GoldenPart")
        self.assertEqual(self.kit.run("return stand(2).PrimaryPart.Name"), "Ice")
        self.assertEqual(self.kit.warnings(), [])

    def test_a_model_that_is_not_there_falls_back_to_default_then_to_the_plain_egg(self):
        self.spots("A", "B")
        self.kit.run("addModel('Default')")
        self.kit.set_eggs([egg(1, template="Missing")])
        self.assertEqual(self.kit.run("return stand(1).PrimaryPart.Name"), "DefaultPart")
        self.kit.run("templatesFolder():FindFirstChild('Default'):Destroy()")
        self.kit.set_eggs([egg(1, template="Missing", price=11)])
        self.assertEqual(self.kit.run("return stand(1).PrimaryPart.Name"), "Egg")

    def test_the_plain_egg_has_the_color_and_a_model_does_not(self):
        self.spots("A", "B")
        self.kit.set_eggs([egg(1, color="#E74C3C")])
        self.assertEqual(self.kit.run("return stand(1).PrimaryPart.Color[1]"), 0xE7)

    # --- spots
    def spots(self, *names):
        for i, name in enumerate(names):
            self.kit.run(f"{name} = newSpot({name!r}, {(i + 1) * 10})")

    def test_a_long_text_with_polish_letters_and_emoji_is_cut_between_characters(self):
        text = "ą" * 150 + "🎉" * 60  # 210 characters, 540 bytes
        self.kit.run("M.fired = {}")
        self.kit.lua.globals().longText = text
        self.kit.run("Live.Preview(M.players[1], 'announce', { text = longText })")
        shown = self.kit.from_lua(self.kit.M.fired[1].payload)["text"]
        self.assertEqual(shown, "ą" * 150 + "🎉" * 50, "200 characters, none of them broken")

    def test_an_egg_on_a_turned_spot_stands_on_its_top(self):
        self.spots("A", "B")
        # B: a round pedestal made of a Cylinder turned 90° (its own X axis points up): 1 stud thick like A
        self.kit.run("B.Size = Vector3.new(1, 6, 6); B.CFrame.RightVector = Vector3.new(0, 1, 0); "
                     "B.CFrame.UpVector = Vector3.new(-1, 0, 0)")
        self.kit.set_eggs([egg(1), egg(2)])
        height = "return stand({}):GetPivot().Position.Y"
        self.assertAlmostEqual(self.kit.run(height.format(2)), self.kit.run(height.format(1)),
                               msg="on top of the turned part, not on its side at the height of its middle")

    def test_the_first_placement_goes_by_the_order_of_the_spots(self):
        self.spots("A", "B", "C")
        self.kit.set_eggs([egg(1), egg(2)])
        self.assertEqual(self.kit.stands(1, 2), {1: 10, 2: 20})

    def test_an_egg_stays_where_it_stood_when_another_egg_goes_away(self):
        self.spots("A", "B", "C")
        self.kit.set_eggs([egg(1), egg(2)])
        self.kit.set_eggs([egg(2)])
        self.assertEqual(self.kit.stands(1, 2), {1: None, 2: 20}, "the egg 2 doesn't jump to the free spot A")
        self.kit.set_eggs([egg(2), egg(3)])
        self.assertEqual(self.kit.stands(2, 3), {2: 20, 3: 10}, "the new egg takes the first free spot")

    def test_a_change_of_an_egg_does_not_move_the_others(self):
        self.spots("A", "B", "C")
        self.kit.set_eggs([egg(1), egg(2), egg(3)])
        self.kit.set_eggs([egg(3), egg(1, price=99), egg(2)])  # even the order in the list changed
        self.assertEqual(self.kit.stands(1, 2, 3), {1: 10, 2: 20, 3: 30})

    def test_a_named_spot_comes_first_and_the_displaced_egg_moves_to_a_free_one(self):
        self.spots("A", "B", "C")
        self.kit.set_eggs([egg(1), egg(2)])
        self.kit.set_eggs([egg(1), egg(2), egg(3, spot="B")])
        self.assertEqual(self.kit.stands(1, 2, 3), {1: 10, 2: 30, 3: 20}, "egg 3 asked for B; egg 2 stood there and goes to C")

    def test_two_eggs_with_the_same_named_spot_the_second_goes_elsewhere(self):
        self.spots("A", "B")
        self.kit.set_eggs([egg(1, spot="B"), egg(2, spot="B")])
        self.assertEqual(self.kit.stands(1, 2), {1: 20, 2: 10})
        self.assertTrue(any("'B' not found (or already taken)" in w for w in self.kit.warnings()))

    def test_an_egg_whose_spot_was_removed_goes_to_a_free_spot(self):
        self.spots("A", "B", "C")
        self.kit.set_eggs([egg(1), egg(2)])
        self.kit.run("dropSpot(B)")
        self.kit.set_eggs([egg(1), egg(2, price=11)])
        self.assertEqual(self.kit.stands(1, 2), {1: 10, 2: 30})

    def test_an_egg_does_not_take_a_spot_that_is_taken_by_a_named_egg(self):
        self.spots("A", "B")
        self.kit.set_eggs([egg(1)])
        self.kit.set_eggs([egg(2, spot="A"), egg(1)])
        self.assertEqual(self.kit.stands(1, 2), {1: 20, 2: 10})

    def test_more_eggs_than_spots_leave_the_extra_egg_out_with_a_hint(self):
        self.spots("A")
        self.kit.set_eggs([egg(1), egg(2)])
        self.assertEqual(self.kit.stands(1, 2), {1: 10, 2: None})
        self.assertTrue(any("Not enough egg spots for 'Egg 2'" in w for w in self.kit.warnings()))
        self.kit.set_eggs([egg(2)])
        self.assertEqual(self.kit.stands(2), {2: 10}, "the first egg went away: the other takes the spot")

    def test_an_egg_remembered_on_a_spot_that_a_named_egg_now_needs(self):
        self.spots("A", "B")
        self.kit.set_eggs([egg(1), egg(2)])
        self.kit.set_eggs([egg(1, spot="B"), egg(2)])
        self.assertEqual(self.kit.stands(1, 2), {1: 20, 2: 10})

    def test_all_eggs_gone_then_back_start_from_the_first_spot_again(self):
        self.spots("A", "B")
        self.kit.set_eggs([egg(1), egg(2)])
        self.kit.set_eggs([egg(2)])
        self.kit.set_eggs([])
        self.kit.set_eggs([egg(2), egg(1)])
        self.assertEqual(self.kit.stands(1, 2), {2: 10, 1: 20}, "nothing is remembered for eggs that were away")

    def test_no_spots_at_all_is_a_hint_and_no_error(self):
        self.kit.set_eggs([egg(1)])
        self.assertEqual(self.kit.stands(1), {1: None})
        self.assertTrue(any("no egg spots" in w for w in self.kit.warnings()))
        self.spots("A")
        self.kit.set_eggs([egg(1, price=12)])
        self.assertEqual(self.kit.stands(1), {1: 10})



def set_limit(kit, limit):
    """Settings -> MaxCurrencyPerCode of this server (0 = no limit)."""
    kit.run(f"""
        local wait = script.Parent.WaitForChild
        script = {{ Parent = {{ WaitForChild = wait, FindFirstChild = function(_, name)
            if name == "Settings" then
                return {{ FindFirstChild = function(_, key)
                    if key == "MaxCurrencyPerCode" then return {{ Value = {int(limit)} }} end
                end }}
            end
        end }} }}""")


@unittest.skipIf(not HAVE_LUA, "lupa is not installed (set BOTDC_LUPA_PATH): the kit server scripts were not run")
class CurrencyLimitAndStudioVersion(unittest.TestCase):
    """The game report carries Settings -> MaxCurrencyPerCode (the bot warns about codes and gifts above it), and an
    older file put back into Studio is reported at once (the published game still keeps the newer version)."""

    def report(self, kit) -> dict:
        self.assertTrue(kit.run("return Report.ReportGame()"))
        return kit.store()["GameScan"]["places"]["555"]["live"]

    def test_the_limit_is_in_the_report_and_a_change_is_written(self):
        kit = Kit(place_version=3)
        kit.run("Report.Setup({ edition = 'full', live = Live })")
        self.assertEqual(self.report(kit)["maxCurrency"], 0, "no Settings: no limit")
        set_limit(kit, 1000)
        self.assertEqual(kit.run("return Core.CurrencyLimit()"), 1000)
        self.assertEqual(self.report(kit)["maxCurrency"], 1000, "a changed limit is written although the lists are the same")
        allowed, why = kit.run("return Core.CanGive(nil, { currency = { name = 'Gems', amount = 5000 } })")
        self.assertFalse(allowed)
        self.assertIn("MaxCurrencyPerCode (1000)", why)

    def test_the_newest_place_version_decides_the_limit(self):
        old = Kit(place_version=5)
        old.set_now(1_000_000)
        old.run("Report.Setup({ edition = 'full', live = Live })")
        set_limit(old, 1000)
        old.load_store({"GameScan": {"places": {"555": {"live": {
            "at": 1_000_000 - 100, "saved": 1_000_000 - 100, "placeVersion": 6, "players": 1, "sig": "x", "values": [],
            "attributes": [], "multipliers": [], "spots": [], "templates": [], "hooks": [], "maxCurrency": 500}}}}})
        self.assertEqual(self.report(old)["maxCurrency"], 500, "a server of an older version never changes the limit")
        new = Kit(place_version=7)
        new.set_now(1_000_000)
        new.run("Report.Setup({ edition = 'full', live = Live })")
        new.load_store(old.store())
        self.assertEqual(self.report(new)["maxCurrency"], 0, "the newer version's limit (none) replaces it")

    def test_an_older_file_in_studio_is_reported_at_once(self):
        studio = Kit(studio=True)
        self.assertTrue(studio.run("return Report.ReportVersion(15)"))
        self.assertTrue(studio.run("return Report.ReportVersion(14)"))
        self.assertEqual(studio.store()["KitVersions"]["places"]["555"]["studio"]["version"], 14)

    def test_the_published_game_still_keeps_the_newer_version(self):
        live = Kit()
        self.assertTrue(live.run("return Report.ReportVersion(15)"))
        self.assertTrue(live.run("return Report.ReportVersion(14)"))
        self.assertEqual(live.store()["KitVersions"]["places"]["555"]["live"]["version"], 15,
                         "a server started before the publish never hides the newer file")

    def test_an_egg_price_above_the_limit_is_still_refunded(self):
        kit = Kit()
        set_limit(kit, 1000)
        reward = "{ currency = { name = 'Gems', amount = 5000 } }"
        self.assertFalse(kit.run(f"return (Core.GiveReward(nil, {reward}))"), "a gift above the limit is refused")
        kit.run("Core.OnReward = function() return true end")
        self.assertTrue(kit.run(f"return (Core.GiveReward(nil, {reward}, true))"),
                        "giving back the player's own money is not limited")
        self.assertIn("}, true)", read(os.path.join(SOURCE, "Live.luau")).split("refundDetails = Core.GiveReward")[1][:120],
                      "Live refunds an egg's price as a refund")

    def test_the_games_own_reward_function_knows_a_refund(self):
        kit = Kit()
        kit.run("seen = {}; Core.OnReward = function(_, reward) table.insert(seen, reward.refund == true); return true end")
        kit.run("Core.GiveReward(nil, { currency = { name = 'Coins', amount = 100 } }, true)")
        kit.run("Core.GiveReward(nil, { currency = { name = 'Coins', amount = 100 } })")
        self.assertEqual(kit.run("return tostring(seen[1]) .. ',' .. tostring(seen[2])"), "true,false",
                         "an egg's price given back is marked, so a 2x gamepass in OnReward can't double it")


    def test_a_declined_reward_never_falls_back_to_the_automatic_mode(self):
        # a game with its own save system (ProfileStore...): leaderstats is only a copy, so when OnReward says
        # false (profile not loaded yet) nothing may be written into it and the code stays unused
        kit = Kit()
        kit.run("Core.Config.CooldownSeconds = 0; Core.OnReward = function() return false end; "
                "local p = M.addPlayer(77, 5, {}); "
                "game:GetService('DataStoreService'):GetDataStore(Core.Config.CodesDataStore):SetAsync("
                "Core.Config.CodesEntryKey, { codes = { TEST = { currency = { name = 'Coins', amount = 50 } } }, updated_at = 1 }); "
                "Core.Refresh(); player = p; coins = p:FindFirstChild('leaderstats'):FindFirstChild('Coins')")
        given = kit.run("local ok, reason = Core.GiveReward(player, { currency = { name = 'Coins', amount = 50 } }); "
                        "return tostring(ok) .. ',' .. tostring(reason)")
        self.assertEqual(given, "false,unsupported", "a gift waits instead of going into the copy")
        redeemed = kit.run("local ok, key = Core.RedeemCode(player, 'test'); return tostring(ok) .. ',' .. tostring(key)")
        self.assertEqual(redeemed, "false,unsupported")
        self.assertEqual(kit.run("return coins.Value"), 5, "nothing was written into leaderstats")
        kit.run("Core.OnReward = function() return true end")
        self.assertTrue(kit.run("return (Core.RedeemCode(player, 'test'))"), "the code was not used up: it works once OnReward can give")


@unittest.skipIf(not HAVE_LUA, "lupa is not installed (set BOTDC_LUPA_PATH): the kit server scripts were not run")
class FreshReadsAfterANotification(unittest.TestCase):
    """Two changes on Discord a moment apart (an event, then ⏹️ right after it): Roblox keeps a read in the server's
    cache for 4 s, so the second notification read the first change again and the game waited for the next poll
    (50-61 s in the published test game on 2026-10-17). Reads skip the cache now, and a notification carries the save
    time ("at"): data older than that is read again 5 s later, at most 3 times."""
    NOW = 100000

    def setUp(self):
        self.kit = Kit()
        self.kit.set_now(self.NOW)
        self.kit.run("M.readCache = true")
        self.kit.start_live()
        self.kit.run("Core.Start(); M.flush()")

    def notify(self, topic: str, message: dict):
        self.kit.M.subscriptions[topic](self.kit.to_lua({"Data": json.dumps(message)}))
        self.kit.M.flush()

    def save_events(self, count: int, at: int):
        events = [{"id": i, "name": f"E{i}", "multipliers": {"Coins": 2}, "ends_at": self.NOW + 3600}
                  for i in range(1, count + 1)]
        self.kit.M.stores["DiscordLiveContent"].data.Events = self.kit.to_lua(
            {"version": 1, "events": events, "updated_at": at})

    def active_events(self) -> int:
        return self.kit.run("return #Live.GetActiveEvents()")

    def stale_reads(self, times: int):
        """The next `times` reads of Events return the data saved now (as if Roblox still served an older copy)."""
        self.kit.run(f"""
            local store = M.stores.DiscordLiveContent
            local real, stale = store.GetAsync, store.data.Events
            staleLeft, eventReads = {times}, 0
            store.GetAsync = function(self, key, options)
                if key == 'Events' then
                    eventReads = eventReads + 1
                    if staleLeft > 0 then staleLeft = staleLeft - 1; return stale end
                end
                return real(self, key, options)
            end""")

    def test_the_mock_cache_does_keep_an_old_copy(self):
        self.save_events(1, self.NOW)
        self.assertEqual(self.kit.run("return #M.stores.DiscordLiveContent:GetAsync('Events').events"), 1)
        self.save_events(0, self.NOW + 2)
        self.assertEqual(self.kit.run("return #M.stores.DiscordLiveContent:GetAsync('Events').events"), 1,
                         "a plain read within 4 s gets the cached copy: without it the next test proves nothing")

    def test_an_event_ended_two_seconds_after_it_started_ends_in_the_game_at_once(self):
        self.save_events(1, self.NOW)
        self.notify("DiscordLive", {"type": "events", "at": self.NOW})
        self.assertEqual(self.active_events(), 1)
        self.kit.set_now(self.NOW + 2)
        self.save_events(0, self.NOW + 2)
        self.notify("DiscordLive", {"type": "events", "at": self.NOW + 2})
        self.assertEqual(self.active_events(), 0, "the second change is read at once, not at the next poll")

    def test_eggs_and_codes_read_the_second_change_at_once_too(self):
        store = self.kit.M.stores["DiscordLiveContent"]
        for at, count in ((self.NOW, 1), (self.NOW + 1, 2)):
            self.kit.set_now(at)
            store.data.Eggs = self.kit.to_lua({"version": 1, "updated_at": at, "eggs": [egg(i) for i in range(1, count + 1)]})
            self.notify("DiscordLive", {"type": "eggs", "at": at})
            self.assertEqual(self.kit.run("return #Live.GetEggs()"), count)
        codes = self.kit.M.stores["DiscordCodeSync"]
        for at, names in ((self.NOW + 2, ["A"]), (self.NOW + 3, ["A", "B"])):
            self.kit.set_now(at)
            codes.data.ActiveCodes = self.kit.to_lua(
                {"version": 1, "updated_at": at, "codes": {n: {"currency": {"name": "Coins", "amount": 1}} for n in names}})
            self.notify("DiscordCodes", {"type": "refresh", "at": at})
            self.assertEqual(sorted(self.kit.from_lua(self.kit.run("return Core.GetActiveCodes()"))), names)

    def test_older_data_is_read_again_until_the_change_arrives(self):
        self.save_events(1, self.NOW)
        self.stale_reads(2)
        self.save_events(0, self.NOW + 2)
        self.notify("DiscordLive", {"type": "events", "at": self.NOW + 2})
        self.assertEqual(self.active_events(), 0, "read again after the stale copies")
        self.assertEqual(self.kit.run("return eventReads"), 3)

    def test_it_gives_up_after_three_more_reads(self):
        self.save_events(1, self.NOW)
        self.stale_reads(100)
        self.notify("DiscordLive", {"type": "events", "at": self.NOW + 2})
        self.assertEqual(self.kit.run("return eventReads"), 4, "one read + 3 retries, then the 60 s poll takes over")
        self.assertEqual(self.active_events(), 1)

    def test_a_notification_without_a_save_time_reads_once(self):
        self.save_events(1, self.NOW)
        self.stale_reads(100)
        self.notify("DiscordLive", {"type": "events"})
        self.assertEqual(self.kit.run("return eventReads"), 1, "an older bot sends no time: nothing to compare with")

    def test_data_saved_later_than_the_notification_is_not_read_again(self):
        self.save_events(1, self.NOW + 5)
        self.stale_reads(0)
        self.notify("DiscordLive", {"type": "events", "at": self.NOW + 2})
        self.assertEqual(self.kit.run("return eventReads"), 1)

    def test_an_older_read_that_ends_later_does_not_bring_the_old_data_back(self):
        """Read 1 starts before ⏹️ is saved and ends after read 2: one read at a time, then one more read."""
        self.save_events(1, self.NOW)
        self.kit.run("""
            local store = M.stores.DiscordLiveContent
            local real = store.GetAsync
            eventReads = 0
            store.GetAsync = function(self, key, options)
                local value = real(self, key, options)
                if key == 'Events' then
                    eventReads = eventReads + 1
                    if holdNext then holdNext = false; held = coroutine.running(); coroutine.yield() end
                end
                return value
            end
            holdNext = true""")
        self.notify("DiscordLive", {"type": "events", "at": self.NOW})  # read 1 got 1 event and is still running
        self.kit.set_now(self.NOW + 1)
        self.save_events(0, self.NOW + 1)
        self.notify("DiscordLive", {"type": "events", "at": self.NOW + 1})
        self.assertEqual(self.kit.run("return eventReads"), 1, "no second read while the first one runs")
        self.kit.run("local ok, err = coroutine.resume(held); assert(ok, err); M.flush()")
        self.assertEqual(self.active_events(), 0, "the read after the slow one brings the newest data")
        self.assertEqual(self.kit.run("return eventReads"), 2)
        self.kit.run("Live.RefreshEvents()")  # the next poll
        self.assertEqual(self.active_events(), 0)

    def test_a_gift_sent_while_the_previous_one_is_given_arrives_too(self):
        """Two /give a second apart: the second gift's key was not on the list the first delivery read, and gifts
        have no 60 s poll: it used to wait for the player's next join."""
        gift = {"reward": {"currency": {"name": "Coins", "amount": 5}}, "message": "one"}
        self.kit.M.stores["DiscordGifts"].data["gift_101_1"] = self.kit.to_lua(gift)
        self.kit.run("""
            local store = M.stores.DiscordGifts
            local real = store.ListKeysAsync
            local first = true
            store.ListKeysAsync = function(self, prefix, size)
                local pages = real(self, prefix, size)
                if first then
                    first = false
                    store.data.gift_101_2 = { reward = { currency = { name = 'Coins', amount = 7 } }, message = 'two' }
                    M.subscriptions.DiscordLive({ Data = '{"type":"gift","user_id":101}' })
                end
                return pages
            end""")
        coins = "return M.players[1]:FindFirstChild('leaderstats'):FindFirstChild('Coins').Value"
        before = self.kit.run(coins)
        self.kit.run("Live.DeliverGifts(M.players[1]); M.flush()")
        self.assertEqual(self.kit.run(coins) - before, 12, "both gifts are given in this visit")
        self.assertEqual(self.kit.store("DiscordGifts"), [], "no gift left waiting")

    def test_an_error_while_giving_gifts_does_not_block_the_next_try(self):
        self.kit.run("""
            Core.GiveReward = (function(real) local n = 0
                return function(...) n = n + 1; if n == 1 then error('odd reward') end; return real(...) end end)(Core.GiveReward)""")
        self.kit.M.stores["DiscordGifts"].data["gift_101_1"] = self.kit.to_lua(
            {"reward": {"currency": {"name": "Coins", "amount": 5}}, "message": "one"})
        coins = "return M.players[1]:FindFirstChild('leaderstats'):FindFirstChild('Coins').Value"
        before = self.kit.run(coins)
        self.kit.run("Live.DeliverGifts(M.players[1]); M.flush()")
        self.assertTrue(any("odd reward" in w for w in self.kit.warnings()), self.kit.warnings())
        self.kit.set_now(self.NOW + 86401)  # the claim of the failed try has expired
        self.kit.run("Live.DeliverGifts(M.players[1]); M.flush()")
        self.assertEqual(self.kit.run(coins) - before, 5, "the player's gifts were not left blocked on this server")


@unittest.skipIf(not HAVE_LUA, "lupa is not installed (set BOTDC_LUPA_PATH): the kit server scripts were not run")
class EggsFollowRobloxRules(unittest.TestCase):
    """Eggs bought with a currency players can buy with Robux are "paid random items" (Roblox Community Standards,
    checked 2026-10-17): the chances must be shown accurately before the purchase (also during a luck event), and
    players Roblox doesn't allow to buy them (PolicyService ArePaidRandomItemsRestricted) can't open eggs."""
    NOW = 200000

    def setUp(self):
        self.start()

    def start(self, before: str = "", studio: bool = False):
        """A fresh server; `before` runs before the player joins (e.g. what PolicyService will say about them)."""
        self.kit = Kit(studio=studio)
        self.kit.set_now(self.NOW)
        if before:
            self.kit.run(before)
        self.kit.start_live()
        self.kit.run("Live.Config.OpenCooldownSeconds = 0; newSpot('A', 10)")  # the cooldown counts in real time
        pets = [{"name": "Cat", "chance": 85}, {"name": "Dragon", "chance": 10}, {"name": "Unicorn", "chance": 5}]
        self.kit.run("for _, n in ipairs({'Dragon', 'Unicorn'}) do M.new('IntValue', { Name = n, Value = 0 }).Parent = "
                     "M.players[1]:FindFirstChild('Pets') end")
        self.kit.set_eggs([egg(1, pets=pets, price=10)])

    def pets_text(self) -> str:
        return self.kit.run("local info = stand(1).PrimaryPart:FindFirstChild('EggInfo'); local out = {}; local tag = info:FindFirstChild('LuckTag'); if tag.Visible then table.insert(out, tag.Text) end; for _, row in ipairs(info:FindFirstChild('Pets'):GetChildren()) do table.insert(out, row:FindFirstChild('Name').Text .. '  ' .. row:FindFirstChild('Percent').Text) end; return table.concat(out, '\\n')")

    def coins(self) -> int:
        return self.kit.run("return M.players[1]:FindFirstChild('leaderstats'):FindFirstChild('Coins').Value")

    def open_egg(self) -> dict:
        self.kit.run("M.fired = {}; Live.OpenEgg(M.players[1], 1); M.flush()")
        sent = [self.kit.from_lua(self.kit.M.fired[i].payload) for i in range(1, len(self.kit.M.fired) + 1)]
        return [p for p in sent if p.get("type") in ("hatch", "egg_error")][-1]

    def luck(self, factor, ends_in=600):
        self.kit.M.stores["DiscordLiveContent"].data.Events = self.kit.to_lua(
            {"events": [{"id": 1, "name": "Luck", "multipliers": {"luck": factor}, "ends_at": self.NOW + ends_in}]})
        self.kit.run("Live.RefreshEvents()")

    def test_a_player_roblox_does_not_allow_cannot_open_an_egg(self):
        self.start("M.policy[101] = { ArePaidRandomItemsRestricted = true }")
        before = self.coins()
        self.assertEqual(self.open_egg(), {"type": "egg_error", "key": "restricted"})
        self.assertEqual(self.coins(), before, "nothing is taken")

    def test_the_check_runs_when_the_player_joins_and_once(self):
        self.assertEqual(self.kit.M.policyCalls, 1, "asked when the player joined, so the first egg doesn't wait")
        before = self.coins()
        self.assertEqual(self.open_egg()["type"], "hatch")
        self.assertEqual(self.coins(), before - 10)
        self.open_egg()
        self.assertEqual(self.kit.M.policyCalls, 1, "PolicyService is asked once per player")

    def test_when_the_check_fails_the_egg_is_not_opened_and_the_next_try_asks_again(self):
        self.start("M.policyError = 'HTTP 500'")
        before = self.coins()
        self.assertEqual(self.open_egg(), {"type": "egg_error", "key": "try_again"}, "not the message about rules")
        self.assertEqual(self.coins(), before)
        self.assertTrue(any("PaidRandomItems" in w for w in self.kit.warnings()), "the warning says what to do")
        self.kit.run("M.policyError = nil")
        self.assertEqual(self.open_egg()["type"], "hatch")

    def test_in_studio_a_failing_check_does_not_block_testing(self):
        self.start("M.policyError = 'HTTP 403'", studio=True)
        self.assertEqual(self.open_egg()["type"], "hatch")

    def test_a_game_whose_egg_currency_is_not_sold_for_robux_can_turn_the_check_off(self):
        self.start("M.policy[101] = { ArePaidRandomItemsRestricted = true }; Live.Config.PaidRandomItems = false")
        self.assertEqual(self.open_egg()["type"], "hatch")
        self.assertEqual(self.kit.M.policyCalls, 0)

    def test_an_egg_stands_on_a_pedestal_and_may_float(self):
        info = "local info = stand(1).PrimaryPart:FindFirstChild('EggInfo'); "
        self.assertTrue(self.kit.run("return stand(1):FindFirstChild('DiscordPedestal') ~= nil"))
        self.assertEqual(self.kit.run(info + "return info.Adornee.Name"), "InfoPoint",
                         "the chances hang on the pedestal, so they stay still while the egg floats")
        self.assertTrue(self.kit.run("return stand(1):GetAttribute('DiscordFloat')"))
        self.kit.run("Live.Config.Pedestal = false; Live.Config.EggAnimation = false")
        self.kit.set_eggs([egg(1, pets=[{"name": "Cat", "chance": 100}])])
        self.assertFalse(self.kit.run("return stand(1):FindFirstChild('DiscordPedestal') ~= nil"), "the game's own pedestals")
        self.assertEqual(self.kit.run(info + "return info.Adornee == stand(1).PrimaryPart"), True)
        self.assertFalse(self.kit.run("return stand(1):GetAttribute('DiscordFloat')"))

    def test_every_pet_is_listed_however_many_and_the_stand_grows(self):
        height = "return stand(1).PrimaryPart:FindFirstChild('EggInfo').Size.Y"
        self.assertAlmostEqual(self.kit.run(height), 6.94, msg="3 pets: the usual stand (4 rows at least, a line for the rounding note)")
        pets = [{"name": f"Pet{i}", "chance": 10} for i in range(10)]
        self.kit.set_eggs([egg(1, pets=pets)])
        self.assertEqual(self.pets_text().count("10%"), 10, "no pet is hidden behind +N...")
        self.assertAlmostEqual(self.kit.run(height), 6.94 + 6 * 0.66, msg="6 pets more than 4 rows: the stand grows by 6 rows")

    def test_an_egg_edited_a_moment_before_the_purchase_takes_nothing(self):
        before = self.coins()
        edited = [{"name": "Cat", "chance": 50}, {"name": "Dragon", "chance": 50}]
        self.kit.M.stores["DiscordLiveContent"].data.Eggs = self.kit.to_lua({"eggs": [egg(1, pets=edited, price=10)]})
        self.kit.run("Live.RefreshEggs()")  # the stand is rebuilt half a second later
        self.kit.run("M.fired = {}; Live.OpenEgg(M.players[1], 1)")
        sent = [self.kit.from_lua(self.kit.M.fired[i].payload) for i in range(1, len(self.kit.M.fired) + 1)]
        self.assertIn({"type": "egg_error", "key": "chances_changed"}, sent)
        self.assertEqual(self.coins(), before, "the stand still showed the old chances: nothing is taken")
        self.kit.run("M.flush()")
        self.assertEqual(self.pets_text(), "Cat  50%\nDragon  50%")
        self.assertEqual(self.open_egg()["type"], "hatch")

    def test_a_poll_that_finds_nothing_new_does_not_stop_purchases(self):
        self.kit.run("Live.RefreshEggs()")
        self.kit.run("M.fired = {}; Live.OpenEgg(M.players[1], 1)")
        sent = [self.kit.from_lua(self.kit.M.fired[i].payload) for i in range(1, len(self.kit.M.fired) + 1)]
        self.assertTrue(any(p.get("type") == "hatch" for p in sent), sent)

    def test_the_luck_line_only_where_luck_changes_the_chances(self):
        self.kit.set_eggs([egg(1, pets=[{"name": "Cat", "chance": 50}, {"name": "Dog", "chance": 50}])])
        self.luck(3)
        self.assertEqual(self.pets_text(), "Cat  50%\nDog  50%", "no rare pets: luck changes nothing, no ⚡")

    def test_a_luck_change_right_before_the_purchase_takes_nothing(self):
        self.luck(3, ends_in=30)
        self.kit.run("M.now = M.now + 31")  # the event ended, the label didn't follow yet
        before = self.coins()
        self.assertEqual(self.open_egg(), {"type": "egg_error", "key": "chances_changed"})
        self.assertEqual(self.coins(), before, "the player didn't see these chances: nothing is taken")
        self.assertEqual(self.pets_text(), "Cat  85%\nDragon  10%\nUnicorn  5%")
        self.assertEqual(self.open_egg()["type"], "hatch", "the next try opens it")

    def test_the_egg_shows_the_chances_of_a_luck_event_and_rolls_with_them(self):
        self.assertEqual(self.pets_text(), "Cat  85%\nDragon  10%\nUnicorn  5%")
        self.luck(3)  # Unicorn (5% = rare) x3: 15 of 110
        self.assertEqual(self.pets_text(), "⚡ Luck x3\nCat  77.273%\nUnicorn  13.636%\nDragon  9.0909%")
        chances = {c["name"]: round(c["chance"], 2) for c in self.kit.from_lua(self.kit.run("return Live.GetChances(1)"))}
        self.assertEqual(chances, {"Cat": 77.27, "Dragon": 9.09, "Unicorn": 13.64}, "the same for your own shop UI")
        self.kit.run("math.random = function() return 0.999 end")  # the last pet in the list
        hatch = self.open_egg()
        self.assertEqual((hatch["pet"], round(hatch["chance"], 2), hatch["rare"]), ("Unicorn", 13.64, True),
                         "the message shows the chance the egg showed; a rare pet stays gold with a higher chance")

    def test_the_hatch_message_carries_the_id_of_the_egg_also_in_the_manager_preview(self):
        self.assertEqual(self.open_egg()["egg_id"], 1, "the client picks the sky effect of the egg by this id")
        self.kit.run("M.fired = {}; Live.Preview(M.players[1], 'hatch', { egg = 1 }); M.flush()")
        sent = [self.kit.from_lua(self.kit.M.fired[i].payload) for i in range(1, len(self.kit.M.fired) + 1)]
        self.assertEqual([p["egg_id"] for p in sent if p.get("type") == "hatch"], [1], "the draw preview too")

    def test_when_the_luck_event_ends_the_chances_go_back(self):
        self.luck(3, ends_in=30)
        self.assertIn("⚡", self.pets_text())
        self.kit.run("M.now = M.now + 31; Live.UpdateLuck()")
        self.assertEqual(self.pets_text(), "Cat  85%\nDragon  10%\nUnicorn  5%")
        hatch = self.open_egg()
        self.assertIn(round(hatch["chance"], 2), (85, 10, 5), "the roll after the end uses the plain chances")



@unittest.skipUnless(HAVE_LUA, "lupa is not installed (set BOTDC_LUPA_PATH): the kit server scripts were not run")
class ManagerAccess(unittest.TestCase):
    """The ⚙️ Manager (scripts/DiscordCodes/Manager.luau): only the game's owner (game.CreatorId = 1 in the mock),
    the UserIds in Settings -> ManagerUsers and everyone in Studio may use its actions; anyone else gets nothing."""

    def start(self, users="", studio=False, on=True, access=None):
        self.kit = Kit(studio=studio)
        self.kit.start_live()
        if access is not None:  # what the bot wrote in the DataStore entry ManagerAccess
            self.kit.lua.globals().accessEntry = self.kit.to_lua(access)
            self.kit.run("M.stores['DiscordLiveContent'] = M.stores['DiscordLiveContent'] or { data = {} }; "
                         "M.stores['DiscordLiveContent'].data.ManagerAccess = accessEntry")
        self.kit.lua.globals().Control = self.kit.lua.execute(read(os.path.join(SOURCE, "Control.luau")))
        self.kit.lua.globals().Manager = self.kit.lua.execute(read(os.path.join(SOURCE, "Manager.luau")))
        self.kit.run(
            "kitSettings = M.new('Configuration', { Name = 'Settings' }); local settings = kitSettings; "
            f"M.new('StringValue', {{ Name = 'ManagerUsers', Value = '{users}' }}).Parent = settings; "
            f"M.new('BoolValue', {{ Name = 'Manager', Value = {'true' if on else 'false'} }}).Parent = settings; "
            "M.new('BoolValue', { Name = 'ShowButton', Value = true }).Parent = settings; "
            "M.new('StringValue', { Name = 'ButtonPosition', Value = 'Left' }).Parent = settings; "
            "Control.Start({ core = Core, live = Live, report = Report }); "
            "Manager.Start({ core = Core, live = Live, control = Control, version = 22, settings = settings })")
        # the panel's changes wait 1 s between two (os.clock): the tests move this clock instead of waiting
        self.kit.run("M.clock = 0; os.clock = function() return M.clock end")
        self.kit.run("owner = M.addPlayer(1, 50, {}); stranger = M.players[1]")  # player 101 joined in start_live

    def invoke(self, who, action, arg=None):
        self.kit.lua.globals().panelArg = self.kit.to_lua(arg)
        remote = "M.services.ReplicatedStorage:FindFirstChild('DiscordManager')"
        self.kit.run("M.clock = M.clock + 2")
        return self.kit.run(f"local r = {remote}; return r and r.OnServerInvoke({who}, '{action}', panelArg) or 'no remote'")

    def change(self, kind, data, who="owner"):
        return self.invoke(who, "change", {"kind": kind, "data": data})

    def test_a_player_who_is_not_the_owner_gets_no_action(self):
        self.start()
        for action in ("state", "codes", "player", "events", "eggs", "log", "gifts", "refresh"):
            self.assertEqual(self.invoke("stranger", action), {"ok": False, "denied": True}, action)
        self.assertEqual(self.invoke("stranger", "forget", "TEST1"), {"ok": False, "denied": True})
        self.assertEqual(self.invoke("stranger", "simulate"), {"ok": False, "denied": True})

    def test_the_owner_can_use_it_and_an_unknown_action_does_nothing(self):
        self.start()
        state = self.invoke("owner", "state")
        self.assertEqual(state["version"], 22)
        self.assertNotIn("edition", state, "there is only one edition")
        self.assertEqual(state["settings"]["ManagerUsers"], "", "the Settings tab shows the settings as they work now")
        self.assertEqual(self.invoke("owner", "nothing"), {"ok": False})

    def test_people_from_the_settings_and_everyone_in_studio(self):
        self.start(users="101, 555")
        self.assertIn("version", self.invoke("stranger", "state"))
        self.start(studio=True)
        self.assertIn("version", self.invoke("stranger", "state"))

    def test_a_player_from_the_bots_list_does_only_what_was_ticked(self):
        entry = {"version": 1, "users": {"101": {"name": "Helper", "permissions": ["codes"]}}}
        self.start(access=entry)
        state = self.invoke("stranger", "state")
        self.assertIn("version", state, "a player on the list gets the panel")
        self.assertEqual(self.invoke("stranger", "forms")["can"]["codes"], True)
        for name in ("events", "eggs", "gifts", "announce", "players", "bans", "settings"):
            self.assertFalse(self.invoke("stranger", "forms")["can"][name], name)
        answer = self.change("code_add", {"code": "HELPER1", "validity": "7d"}, who="stranger")
        self.assertNotEqual(answer.get("ownerOnly"), True, "the ticked permission is enough")
        self.assertTrue(answer["ok"])
        for kind in ("event_start", "egg_create", "gift", "announce", "ban"):
            self.assertEqual(self.change(kind, {"name": "X"}, who="stranger"), {"ok": False, "noPermission": True}, kind)
        self.assertEqual(self.invoke("stranger", "setting", {"name": "ShowButton", "value": False}),
                         {"ok": False, "noPermission": True}, "settings were not ticked")
        self.assertTrue(self.invoke("owner", "forms")["can"]["settings"], "the owner may do everything")

    def saved_access(self):
        return self.kit.run("local e = M.stores['DiscordLiveContent'] and M.stores['DiscordLiveContent'].data.ManagerAccess; "
                            "return e")

    def test_the_owner_gives_access_in_the_game_by_name(self):
        self.start()
        self.kit.run("M.accounts[777] = 'Builder'")
        found = self.invoke("owner", "access", {"op": "find", "name": "builder"})
        self.assertEqual((found["ok"], found["user"]["id"], found["user"]["name"], found["user"]["listed"]),
                         (True, 777, "Builder", False), "found by name, written as Roblox writes it")
        saved = self.invoke("owner", "access", {"op": "save", "userId": 777, "name": "Builder",
                                                "permissions": ["codes", "events", "root", "codes"]})
        self.assertEqual(saved["users"], [{"id": 777, "name": "Builder", "permissions": ["codes", "events"], "listed": True}])
        entry = self.saved_access()
        self.assertEqual(entry["users"]["777"], {"name": "Builder", "permissions": ["codes", "events"]},
                         "the same entry the bot reads and writes")
        self.assertEqual(entry["by"], "game")
        self.assertGreater(entry["updated_at"], 0, "the bot sees which side changed it last")
        self.assertTrue(any('"access"' in p["data"] for p in self.kit.run("return M.published")), "the other servers are told")
        removed = self.invoke("owner", "access", {"op": "remove", "userId": 777})
        self.assertEqual(removed["users"], [])
        self.assertNotIn("777", self.saved_access()["users"])

    def test_a_player_added_in_the_game_gets_the_panel_with_only_their_tabs(self):
        self.start()
        self.assertEqual(self.invoke("stranger", "state"), {"ok": False, "denied": True})
        self.invoke("owner", "access", {"op": "save", "userId": 101, "name": "Player101", "permissions": ["events"]})
        self.assertIn("version", self.invoke("stranger", "state"), "Start is for everyone with the panel")
        self.assertIn("list", self.invoke("stranger", "events"))
        self.assertIn("list", self.invoke("stranger", "log"))
        for action in ("codes", "eggs", "player", "gifts", "preview", "testCode", "simulate"):
            self.assertEqual(self.invoke("stranger", action), {"ok": False, "noPermission": True}, action)
        self.assertEqual(self.invoke("stranger", "access", {"op": "list"}), {"ok": False, "ownerOnly": True},
                         "only the owner gives access")

    def test_the_owner_cannot_be_put_on_the_list_and_a_wrong_name_is_said(self):
        self.start()
        self.assertEqual(self.invoke("owner", "access", {"op": "find", "name": "nobody_here"}),
                         {"ok": False, "key": "accessNotFound"})
        self.assertEqual(self.invoke("owner", "access", {"op": "find", "name": "a b; c"}),
                         {"ok": False, "key": "accessNotFound"})
        self.assertEqual(self.invoke("owner", "access", {"op": "find", "name": "Player1"}),
                         {"ok": False, "key": "accessOwner"})
        self.assertEqual(self.invoke("owner", "access", {"op": "save", "userId": 1, "permissions": ["codes"]}),
                         {"ok": False, "key": "accessOwner"})

    def test_a_helper_cannot_get_a_gift_by_typing_their_user_id(self):
        self.start(access={"version": 1, "users": {"101": {"name": "Helper", "permissions": ["gifts"]}}})
        for typed in ("101", " Player101 "):
            answer = self.change("gift", {"player": typed, "currency": "Coins", "amount": 5}, who="stranger")
            self.assertEqual((answer["done"], answer["key"]), (False, "giftSelf"), typed)

    def test_a_helpers_reset_leaves_the_owners_currency_limit(self):
        self.start(access={"version": 1, "users": {"101": {"name": "Helper", "permissions": ["settings"]}}})
        self.kit.run("M.new('IntValue', { Name = 'MaxCurrencyPerCode', Value = 0 }).Parent = kitSettings")
        self.kit.run("Manager.Start({ core = Core, live = Live, control = Control, version = 22, settings = kitSettings })")
        self.invoke("owner", "setting", {"name": "MaxCurrencyPerCode", "value": 1000})
        self.invoke("stranger", "resetSettings")
        self.assertEqual(self.invoke("owner", "state")["settings"]["MaxCurrencyPerCode"], 1000)

    def test_the_saved_name_is_the_one_roblox_has_and_time_only_goes_forward(self):
        self.start(access={"version": 1, "updated_at": 9999999999, "users": {}})
        self.kit.run("M.accounts[777] = 'Builder'")
        self.invoke("owner", "access", {"op": "save", "userId": 777, "name": "@everyone **x**", "permissions": []})
        entry = self.saved_access()
        self.assertEqual(entry["users"]["777"]["name"], "Builder")
        self.assertEqual(entry["updated_at"], 10000000000, "later than the last change even if this clock is behind")

    def test_the_game_keeps_the_bots_limit_of_25_players(self):
        users = {str(1000 + i): {"name": f"P{i}", "permissions": []} for i in range(25)}
        self.start(access={"version": 1, "users": users})
        self.assertEqual(self.invoke("owner", "access", {"op": "save", "userId": 5000, "permissions": []}),
                         {"ok": False, "key": "accessFull"})
        changed = self.invoke("owner", "access", {"op": "save", "userId": 1000, "name": "P0", "permissions": ["bans"]})
        self.assertTrue(changed["ok"], "someone already on the list can still be changed")

    def test_a_failed_save_is_said_and_the_list_stays(self):
        self.start()
        self.kit.run("M.updateError = 'HTTP 500'")
        answer = self.invoke("owner", "access", {"op": "save", "userId": 101, "name": "P", "permissions": ["codes"]})
        self.assertEqual(answer, {"ok": False, "key": "accessFailed"})
        self.assertEqual(self.invoke("stranger", "state"), {"ok": False, "denied": True})

    def test_a_helper_with_settings_leaves_the_currency_limit_to_the_owner(self):
        self.start(access={"version": 1, "users": {"101": {"name": "Helper", "permissions": ["settings"]}}})
        self.assertEqual(self.invoke("stranger", "setting", {"name": "MaxCurrencyPerCode", "value": 0}),
                         {"ok": False, "ownerOnly": True}, "the limit guards codes and gifts")
        self.assertIn("settings", self.invoke("stranger", "setting", {"name": "ShowButton", "value": False}),
                      "the look of the game may be changed")

    def test_a_helper_with_gifts_never_sends_one_to_themselves(self):
        self.start(access={"version": 1, "users": {"101": {"name": "Helper", "permissions": ["gifts"]}}})
        answer = self.change("gift", {"player": "player101", "currency": "Coins", "amount": 5}, who="stranger")
        self.assertEqual((answer["ok"], answer["done"], answer["key"]), (True, False, "giftSelf"))

    def test_a_player_not_on_the_bots_list_gets_nothing(self):
        self.start(access={"version": 1, "users": {"555": {"name": "Other", "permissions": ["codes", "events"]}}})
        self.assertEqual(self.invoke("stranger", "state"), {"ok": False, "denied": True})
        self.assertEqual(self.change("code_add", {"code": "NOPE"}, who="stranger"), {"ok": False, "denied": True})

    def test_unknown_permissions_in_the_bots_list_are_ignored(self):
        self.start(access={"version": 1, "users": {"101": {"name": "H", "permissions": ["root", "codes"]}}})
        can = self.invoke("stranger", "forms")["can"]
        self.assertEqual([k for k, v in can.items() if v], ["codes"])

    def test_turned_off_in_the_settings_there_is_no_panel(self):
        self.start(on=False)
        self.assertEqual(self.invoke("owner", "state"), "no remote")

    def test_only_the_owner_changes_settings_and_the_players_windows_get_them(self):
        self.start(users="101")
        change = {"name": "ShowButton", "value": False}
        self.assertEqual(self.invoke("stranger", "setting", change), {"ok": False, "noPermission": True},
                         "the people in ManagerUsers only look")
        self.assertFalse(self.invoke("owner", "setting", change)["settings"]["ShowButton"])
        remote = "M.services.ReplicatedStorage:FindFirstChild('DiscordCodesRedeem')"
        self.assertIs(self.kit.run(f"return {remote}:GetAttribute('ShowButton')"), False,
                      "the windows read a changed setting from the remote's attribute")
        self.assertEqual(self.invoke("owner", "setting", {"name": "ButtonPosition", "value": "Middle"}), {"ok": False})
        self.assertEqual(self.invoke("owner", "setting", {"name": "ManagerUsers", "value": "5"}), {"ok": False},
                         "who gets the panel is not changed from the game")
        self.invoke("owner", "resetSettings")
        self.assertIsNone(self.kit.run(f"return {remote}:GetAttribute('ShowButton')"), "Reset: back to DiscordSettings")

    def test_places_on_the_screen_can_be_changed_live_with_pixels(self):
        self.start()
        for name in ("ButtonPosition", "ManagerPosition", "EventPosition", "AnnouncementPosition", "NotificationPosition"):
            self.kit.run(f"M.new('StringValue', {{ Name = '{name}', Value = 'Left' }}).Parent = kitSettings")
        for value in ("TopRight 10,-5", "Center", "bottomleft", "Left +20, -40"):
            answer = self.invoke("owner", "setting", {"name": "NotificationPosition", "value": value})
            self.assertNotEqual(answer, {"ok": False}, value)
        for value in ("Nowhere", "Left 3000,0", "Left 0,-2001", 5, "Left 1,2,3", "x" * 50):
            self.assertEqual(self.invoke("owner", "setting", {"name": "EventPosition", "value": value}), {"ok": False}, value)
        settings = self.invoke("owner", "state")["settings"]
        for name in ("ManagerPosition", "EventPosition", "AnnouncementPosition", "NotificationPosition"):
            self.assertIn(name, settings, "the Settings tab shows it")

    def test_changes_come_only_from_the_owner_and_are_done_at_once(self):
        self.start(users="101")
        data = {"text": "hi", "seconds": 10, "nested": {"x": 1}}
        self.assertEqual(self.change("announce", data, who="stranger"), {"ok": False, "noPermission": True},
                         "the people in ManagerUsers only look")
        answer = self.change("announce", data)
        self.assertEqual((answer["ok"], answer["done"], answer["key"]), (True, True, "announced"))
        entry = self.kit.store()["PanelLog"]["entries"][0]
        self.assertEqual((entry["kind"], entry["by"], entry["name"], entry["data"]),
                         ("announce", 1, "Player1", {"text": "hi", "seconds": 10}),
                         "only plain values, with who did it, for the bot's log")
        self.assertEqual(self.change("nothing", {}), {"ok": False})

    def test_the_log_and_the_answer_are_not_hidden_whole_for_one_word(self):
        self.start()
        self.kit.run("table.insert(M.blockedWords, 'Discord'); "
                     "M.services.LogService.MessageOut:Fire('[DiscordCodes] Manager: Player1: egg_create done', "
                     "Enum.MessageType.MessageOutput); "
                     "M.services.LogService.MessageOut:Fire('[DiscordCodes] Your settings from DiscordSettings: Language', "
                     "Enum.MessageType.MessageOutput); "
                     "M.services.LogService.MessageOut:Fire('[DiscordCodes] Join our Discord', Enum.MessageType.MessageOutput)")
        texts = [entry["text"] for entry in self.invoke("owner", "log")["list"]]
        self.assertIn("Manager: Player1: egg_create done", texts, "the kit's tag isn't filtered")
        self.assertIn("Your settings from DiscordSettings: Language", texts, "nor the names of the kit's objects")
        self.assertIn("[filtered]", texts, "the word on its own is still filtered (a line hidden whole: the panel says so)")
        answer = self.change("event_start", {"name": "Discord Party", "duration": "1h", "exp_x": "2"})
        self.assertTrue(answer["done"])
        self.assertEqual(answer["args"][0], "[filtered]", "a name hidden whole: the panel says the filter hid it")
        self.assertEqual(self.kit.store()["Events"]["events"][0]["name"], "Discord Party", "saved as it was typed")

    # --- v31-v33: filteredLine / filteredLines (kit names are not filtered, the text around them is)
    def log_texts(self, *lines, words=("Discord",)):
        self.start()
        self.kit.lua.globals().logLines = self.kit.to_lua(list(lines))
        for word in words:
            self.kit.lua.globals().badWord = word
            self.kit.run("table.insert(M.blockedWords, badWord)")
        self.kit.run("for _, l in ipairs(logLines) do "
                     "M.services.LogService.MessageOut:Fire(l, Enum.MessageType.MessageOutput) end")
        return [entry["text"] for entry in self.invoke("owner", "log")["list"]]

    def answer_value(self, name, words=("Discord",)):
        """The name of a new event as the panel's answer shows it."""
        self.start()
        for word in words:
            self.kit.lua.globals().badWord = word
            self.kit.run("table.insert(M.blockedWords, badWord)")
        return self.change("event_start", {"name": name, "duration": "1h", "exp_x": "2"})["args"][0]

    def test_log_line_with_only_the_tag_or_empty_gives_an_empty_text_without_error(self):
        texts = self.log_texts("[DiscordCodes] ", "[DiscordCodes]", "[DiscordLive]", "[Discord] chat line")
        self.assertEqual(texts[:3], ["", "", ""])
        self.assertEqual(texts[3], "[filtered]", "only the kit's own tags are cut off")

    def test_log_several_kit_names_in_one_line_and_glued_to_other_characters(self):
        texts = self.log_texts(
            "[DiscordCodes] DiscordSettings and DiscordCatalog, then DiscordManager",
            "[DiscordCodes] copy DiscordCodes.rbxmx (DiscordCatalog) now",
            "[DiscordCodes] discord and Discord and DISCORD are filtered",
            "[DiscordCodes] DiscordSettings",
            "[DiscordCodes] in DiscordCatalog")
        self.assertEqual(texts[0], "DiscordSettings and DiscordCatalog, then DiscordManager")
        self.assertEqual(texts[1], "copy DiscordCodes.rbxmx (DiscordCatalog) now")
        self.assertEqual(texts[3], "DiscordSettings", "a name alone in the line, at its start")
        self.assertEqual(texts[4], "in DiscordCatalog", "a name at the end of the line")
        # the mock's word match is case-sensitive: only the bare capitalised word is checked
        self.assertNotIn("Discord and", texts[2], "bare 'Discord' goes through the filter")

    def test_log_a_name_typed_on_discord_that_starts_like_a_kit_name_is_filtered(self):
        """Only the exact names of the kit's objects are kept out of the filter, not anything that starts with Discord."""
        texts = self.log_texts("[DiscordCodes] Manager: owner created egg DiscordBADWORD", words=("BADWORD",))
        self.assertEqual(texts, ["[filtered]"], "a line hidden whole: the panel says the filter hid it")
        texts = self.log_texts("[DiscordCodes] egg DiscordSettingsBADWORD in DiscordCatalog", words=("BADWORD",))
        self.assertNotIn("BADWORD", texts[0], "a kit name glued to more letters is not a kit name")
        texts = self.log_texts("[DiscordCodes] code BADWORD here", words=("BADWORD",))
        self.assertNotIn("BADWORD", texts[0], "without the prefix the word is filtered")

    def test_a_name_typed_in_the_panel_that_starts_like_a_kit_name_is_filtered(self):
        self.assertNotIn("BADWORD", self.answer_value("Egg DiscordBADWORD", words=("BADWORD", "Discord")))
        self.assertNotIn("BADWORD", self.answer_value("Egg BADWORD", words=("BADWORD",)))
        self.assertEqual(self.answer_value("See DiscordSettings"), "See DiscordSettings")

    def test_kit_names_that_start_other_kit_names_and_a_typed_kit_word(self):
        texts = self.log_texts(
            "[DiscordCodes] DiscordCodes and DiscordCodesRedeem, DiscordEgg and DiscordEggs, DiscordLive in DiscordLiveContent",
            "[DiscordLive] egg KitEggs saved",
            "[DiscordLive] x_DiscordEgg_y")
        self.assertEqual(texts[0], "DiscordCodes and DiscordCodesRedeem, DiscordEgg and DiscordEggs, DiscordLive in DiscordLiveContent")
        self.assertEqual(texts[1], "egg KitEggs saved", "a name typed by someone stays as typed")
        self.assertEqual(texts[2], "[filtered]", "a kit name glued with _ is not a kit name")

    def test_numbers_split_by_a_kit_name_go_to_the_filter_as_one_line(self):
        """The line goes to the filter whole (one call), so a kit name in the middle doesn't cut it into pieces."""
        self.start()
        self.kit.run("seen = {}; local old = M.services.TextService.FilterStringAsync; "
                     "M.services.TextService.FilterStringAsync = function(s, t, ...) table.insert(seen, t); return old(s, t, ...) end; "
                     "M.services.LogService.MessageOut:Fire('[DiscordCodes] 555 DiscordSettings 123', Enum.MessageType.MessageOutput)")
        texts = [entry["text"] for entry in self.invoke("owner", "log")["list"]]
        self.assertEqual(texts, ["555 DiscordSettings 123"])
        self.assertEqual(self.kit.run("return #seen .. '|' .. seen[1]"), "1|555 KitSettings 123")

    def test_a_line_hidden_only_in_part_keeps_its_other_words(self):
        """Only a line that is nothing but # is replaced: a hidden word inside a line stays as Roblox wrote it."""
        texts = self.log_texts("[DiscordCodes] Egg created", "[DiscordCodes] #### and more", words=("Nothing",))
        self.assertEqual(texts, ["Egg created", "#### and more"])
        self.assertEqual(self.log_texts("[DiscordCodes] 12 345", words=("12 345",)), ["[filtered]"], "digits only, hidden whole")

    def test_when_the_filter_fails_the_answer_shows_a_question_mark(self):
        self.start()
        self.kit.run("M.services.TextService.FilterStringAsync = function() error('no filter') end")
        answer = self.change("event_start", {"name": "Party", "duration": "1h", "exp_x": "2"})
        self.assertTrue(answer["done"], "the change itself never needs the filter")
        self.assertEqual(answer["args"][0], "?", "nothing unfiltered is shown")

    def test_core_filter_text_for_announcements_and_gifts_is_the_plain_filter(self):
        """Core.FilterText is the plain GetNonChatStringForBroadcastAsync filter, no kit-name exceptions (as in v30)."""
        self.start()
        self.kit.run("table.insert(M.blockedWords, 'Discord')")
        self.assertEqual(self.kit.run("return Core.FilterText('Happy DiscordCatalog day', 1)"), "#" * len("Happy DiscordCatalog day"))
        self.assertEqual(self.kit.run("return Core.FilterText('hello', 1)"), "hello")
        self.assertEqual(self.kit.run("return Core.FilterText('', 1)"), "")

    def test_my_currency_works_only_in_studio_and_previews_and_code_tests_give_nothing(self):
        self.start()
        self.assertEqual(self.invoke("owner", "currency", {"index": 1, "delta": 1000}), {"ok": False, "studioOnly": True, "what": "currency"})
        self.assertEqual(self.invoke("owner", "testCode", "NOPE")["key"], "invalid")
        self.assertEqual(self.invoke("owner", "preview", {"kind": "nothing"}), {"ok": False})
        self.assertEqual(self.invoke("stranger", "preview", {"kind": "gift"}), {"ok": False, "denied": True})

    def test_forget_works_only_in_studio_and_only_for_a_code_the_panel_showed(self):
        self.start()
        self.kit.run("M.stores['PlayerRedeemedCodes_v1'].data['1_TEST1'] = 123")
        self.assertEqual(self.invoke("owner", "forget", 1), {"ok": False, "studioOnly": True},
                         "published game: one code redeemed again and again")
        self.start(studio=True)
        self.kit.run("M.stores['PlayerRedeemedCodes_v1'].data['1_TEST1'] = 123")
        self.assertEqual(self.invoke("owner", "forget", 1), {"ok": False}, "the panel hasn't shown any code yet")
        self.kit.run("Core.GetActiveCodes = function() return { TEST1 = { currency = { name = 'Coins', amount = 5 } } } end")
        codes = self.invoke("owner", "codes")
        self.assertNotIn("raw", codes["list"][0], "the panel gets only filtered text")
        self.assertTrue(self.invoke("owner", "forget", 1)["ok"])
        self.assertIsNone(self.kit.run("return M.stores['PlayerRedeemedCodes_v1'].data['1_TEST1']"))

    def test_refresh_waits_between_two_clicks(self):
        self.start()
        self.assertIn("codes", self.invoke("owner", "refresh"))
        self.assertIn("wait", self.invoke("owner", "refresh"), "every refresh reads DataStores")

    def test_a_simulation_gives_nothing(self):
        self.start()
        self.kit.set_eggs([egg(1, pets=[{"name": "Cat", "chance": 75}, {"name": "Dog", "chance": 25}])])
        coins = self.kit.run("return owner:FindFirstChild('leaderstats'):FindFirstChild('Coins').Value")
        result = self.invoke("owner", "simulate", {"id": 1, "times": 1000})
        self.assertEqual(sum(p["got"] for p in result["list"]), 1000)
        self.assertEqual(self.kit.run("return owner:FindFirstChild('leaderstats'):FindFirstChild('Coins').Value"), coins)


if __name__ == "__main__":
    unittest.main()
