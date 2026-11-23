"""The game's ⚙️ Manager changes the game BY ITSELF (scripts/DiscordCodes/Control.luau), with no bot running: codes,
events and eggs go into the same DataStore entries the bot uses (one UpdateAsync each), gifts into DiscordGifts,
announcements to every server, bans through Players:BanAsync; every change goes to the log the bot reads (PanelLog).
Run for real under lupa with the Roblox mock (tests/roblox_server_mock.lua), like tests/test_kit_server_scripts.py.
The bot's side of the same entries: tests/test_game_sync.py and tests/test_panel_log.py."""
import json
import os
import unittest

from tests.test_kit_server_scripts import HAVE_LUA, SOURCE, STUDIO_ERROR, Kit, read

CATALOG = ("local m = M.new('ModuleScript', { Name = 'DiscordCatalog' }); "
           "m.module = { Currencies = { 'Coins', 'Gems' }, Items = { 'Sword' }, "
           "Pets = { { Name = 'Dog', Rarity = 'Common' }, { Name = 'Cat' }, { Name = 'Shadow Dragon' } }, "
           "SoldForRobux = { 'Gems' } }; m.Parent = M.services.ServerScriptService")


@unittest.skipUnless(HAVE_LUA, "lupa is not installed (set BOTDC_LUPA_PATH): the kit server scripts were not run")
class PanelChangesTheGameItself(unittest.TestCase):
    def setUp(self):
        self.start()

    def start(self, studio=False, catalog=True, spots=("Spawn", "Lobby")):
        self.kit = kit = Kit(studio=studio)
        if catalog:
            kit.run(CATALOG)
        for i, name in enumerate(spots):
            kit.run(f"newSpot('{name}', {i * 10})")
        kit.start_live()  # player 101 is on the server: leaderstats.Coins = 1000, Pets.Cat
        kit.lua.globals().Control = kit.lua.execute(read(os.path.join(SOURCE, "Control.luau")))
        kit.lua.globals().Manager = kit.lua.execute(read(os.path.join(SOURCE, "Manager.luau")))
        kit.run("kitSettings = M.new('Configuration', { Name = 'Settings' }); "
                "M.new('BoolValue', { Name = 'Manager', Value = true }).Parent = kitSettings; "
                "Control.Start({ core = Core, live = Live, report = Report }); "
                "Manager.Start({ core = Core, live = Live, control = Control, version = 40, settings = kitSettings }); "
                "owner = M.addPlayer(1, 50, {}); M.clock = 0; os.clock = function() return M.clock end")

    def invoke(self, action, arg=None, who="owner"):
        self.kit.lua.globals().panelArg = self.kit.to_lua(arg)
        self.kit.run("M.clock = M.clock + 2")  # past the 1 s between two changes
        return self.kit.run("return M.services.ReplicatedStorage:FindFirstChild('DiscordManager')"
                            f".OnServerInvoke({who}, '{action}', panelArg)")

    def change(self, kind, **data):
        answer = self.invoke("change", {"kind": kind, "data": data})
        self.assertTrue(answer["ok"], answer)
        return answer

    def refused(self, kind, key, **data):
        answer = self.change(kind, **data)
        self.assertFalse(answer["done"], answer)
        self.assertEqual(answer["key"], key, answer)
        return answer

    def log(self) -> list:
        store = self.kit.store()  # an empty store comes back as []
        return ((store.get("PanelLog") if isinstance(store, dict) else None) or {}).get("entries", [])

    def published(self, topic=None) -> list:
        sent = [m for m in self.kit.run("return M.published") or []]
        return [(m["topic"], json.loads(m["data"])) for m in sent if topic is None or m["topic"] == topic]

    def codes(self) -> dict:
        store = self.kit.store("DiscordCodeSync")
        return (store.get("ActiveCodes") if isinstance(store, dict) else None) or {}

    def remove_code(self, code: str):
        """Like the panel: the Promo codes tab lists the codes, ✖ names one by its place in that list."""
        listed = [c["code"] for c in self.invoke("codes")["list"]]
        return self.invoke("change", {"kind": "code_remove", "data": {"index": listed.index(code) + 1}})

    # ---------- codes ----------

    def test_a_code_is_saved_in_the_game_and_works_at_once(self):
        answer = self.change("code_add", code="summer 24", currency="coins", amount=500, exp=0, item="",
                             item_duration="permanent", validity="7d")
        self.assertTrue(answer["done"], answer)
        self.assertEqual((answer["key"], answer["args"][0], answer["args"][2]), ("codeAdded", "SUMMER24", {"duration": "7d"}))
        self.assertEqual(answer["args"][1], "+500 Coins", "the reward as text, in the catalog's spelling")
        saved = self.codes()
        reward = saved["codes"]["SUMMER24"]
        self.assertEqual(reward["currency"], {"name": "Coins", "amount": 500})
        self.assertGreater(reward["expires_at"], 0)
        self.assertEqual(saved["meta"]["SUMMER24"]["origin"], "game")
        self.assertEqual(saved["meta"]["SUMMER24"]["by"], "Player1")
        self.assertEqual(saved["version"], 2)
        topic, message = self.published("DiscordCodes")[0]
        self.assertEqual((message["type"], message["at"]), ("refresh", saved["updated_at"]),
                         "the other servers read it at once (and know which save to wait for)")
        self.assertEqual(self.kit.run("return Core.GetActiveCodes().SUMMER24.currency.amount"), 500, "this server has it now")
        ok, key = self.kit.run("local ok, key = Core.RedeemCode(M.players[1], 'summer24'); return { ok, key }")
        self.assertEqual((ok, key), (True, "ok"), "a player can redeem it right away")
        entry = self.log()[0]
        self.assertEqual((entry["kind"], entry["data"]["code"]), ("code_add", "SUMMER24"))
        listed = self.invoke("codes")["list"][0]
        self.assertEqual((listed["origin"], listed["by"]), ("game", "Player1"))

    def test_a_code_keeps_the_codes_the_bot_saved(self):
        self.kit.load_store({"ActiveCodes": {"version": 1, "updated_at": 5, "codes": {"BOT": {"expires_at": 0, "exp": 10}}}},
                            "DiscordCodeSync")
        self.change("code_add", code="PANEL", currency="", amount=0, exp=50, item="", validity="unlimited")
        codes = self.codes()["codes"]
        self.assertEqual(sorted(codes), ["BOT", "PANEL"])
        self.assertEqual(codes["PANEL"], {"expires_at": 0, "exp": 50})
        listed = {c["code"]: c["origin"] for c in self.invoke("codes")["list"]}
        self.assertEqual(listed, {"BOT": "discord", "PANEL": "game"})

    def test_a_code_that_is_active_already_is_refused_and_an_ended_one_is_replaced(self):
        self.change("code_add", code="ONE", exp=10, validity="unlimited")
        self.refused("code_add", "codeExists", code="one", exp=20, validity="unlimited")
        self.assertEqual(self.codes()["codes"]["ONE"]["exp"], 10)
        self.kit.load_store({"ActiveCodes": {"codes": {"OLD": {"expires_at": 100, "exp": 1}}}}, "DiscordCodeSync")
        self.assertTrue(self.change("code_add", code="OLD", exp=5, validity="24h")["done"], "an ended code is not active")
        self.assertEqual(self.codes()["codes"]["OLD"]["exp"], 5)

    def test_wrong_codes_are_refused_before_anything_is_saved(self):
        self.refused("code_add", "badCode", code="NO$", exp=1, validity="7d")
        self.refused("code_add", "badCode", code="A" * 31, exp=1, validity="7d")
        self.refused("code_add", "noReward", code="EMPTY", validity="7d")
        self.refused("code_add", "currencyAmount", code="HALF", currency="Coins", validity="7d")
        self.refused("code_add", "currencyAmount", code="HALF", amount=5, validity="7d")
        self.refused("code_add", "unknownName", code="TYPO", currency="Coinz", amount=5, validity="7d")
        self.refused("code_add", "unknownName", code="TYPO", item="Swrod", validity="7d")
        self.refused("code_add", "badValue", code="LONG", exp=1, validity="1y")
        self.refused("code_add", "badValue", code="NEG", exp=-5, validity="7d")
        self.refused("code_add", "badValue", code="HALF", exp=2.5, validity="7d")
        self.kit.run("Core.CurrencyLimit = function() return 1000 end")
        answer = self.refused("code_add", "tooMuch", code="BIG", currency="Coins", amount=5000, validity="7d")
        self.assertEqual(answer["args"], ["5000", "1000"])
        self.assertEqual(self.codes(), {}, "nothing was saved")
        self.assertEqual(self.log(), [])

    def test_items_and_pets_from_the_catalog_and_a_robux_warning(self):
        answer = self.change("code_add", code="PET", item="shadow  dragon", item_duration="3d", validity="7d")
        self.assertEqual(self.codes()["codes"]["PET"]["item"],
                         {"name": "Shadow Dragon", "is_temporary": True, "duration_seconds": 3 * 86400})
        self.assertEqual(answer["warns"], [])
        answer = self.change("code_add", code="GEMS", currency="gems", amount=5, validity="7d")
        self.assertEqual(answer["warns"], [{"key": "warnRobux", "args": ["Gems"]}], "Roblox rules for promo codes")

    def test_without_a_catalog_any_name_goes(self):
        self.start(catalog=False)
        self.assertTrue(self.change("code_add", code="FREE", currency="Rubies", amount=3, validity="7d")["done"])

    def test_removing_a_code_takes_it_out_of_the_game(self):
        self.kit.load_store({"ActiveCodes": {"codes": {"BOT": {"expires_at": 0, "exp": 10}, "OTHER": {"expires_at": 0, "exp": 1}}}},
                            "DiscordCodeSync")
        self.kit.run("Core.Refresh()")
        index = [c["code"] for c in self.invoke("codes")["list"]].index("BOT") + 1
        answer = self.invoke("change", {"kind": "code_remove", "data": {"index": index}})
        self.assertEqual((answer["done"], answer["key"], answer["args"]), (True, "codeRemoved", ["BOT"]))
        self.assertEqual(list(self.codes()["codes"]), ["OTHER"])
        self.assertEqual(self.log()[0]["data"], {"code": "BOT"})
        again = self.invoke("change", {"kind": "code_remove", "data": {"index": index}})  # the list shown before
        self.assertEqual((again["done"], again["key"]), (False, "notFound"))
        self.assertEqual(self.invoke("change", {"kind": "code_remove", "data": {"index": 99}}), {"ok": False},
                         "only a code the panel showed")
        self.assertEqual(self.invoke("change", {"kind": "code_remove", "data": {"code": "OTHER"}}), {"ok": False},
                         "never a code named by the client")

    def test_the_last_code_removed_leaves_an_empty_list(self):
        self.change("code_add", code="ONLY", exp=1, validity="7d")
        self.assertTrue(self.remove_code("ONLY")["done"])
        self.assertEqual(self.codes()["codes"], [], "Roblox saves it as []: the bot reads it as no codes (test_game_sync)")

    # ---------- events ----------

    def test_an_event_starts_on_every_server_at_once(self):
        answer = self.change("event_start", name="Weekend Boost", duration="1h", currency="coins", currency_x="2")
        self.assertEqual((answer["key"], answer["args"]), ("eventStarted", ["Weekend Boost", {"duration": "1h"}]))
        saved = self.kit.store()["Events"]
        event = saved["events"][0]
        self.assertEqual((event["id"], event["multipliers"], event["origin"], event["by"]),
                         ("g1", {"currency:Coins": 2}, "game", "Player1"))
        self.assertEqual(event["ends_at"] - event["starts_at"], 3600)
        self.assertEqual(saved["next_id"], 2)
        self.assertEqual(event["starts_at"] - self.kit.run("return M.now"), 10, "the players see a 10 s countdown first")
        self.assertEqual(self.kit.run("return Live.GetMultiplier('Coins')"), 1, "not used during the countdown")
        self.kit.run("M.now = M.now + 10")
        self.assertEqual(self.kit.run("return Live.GetMultiplier('Coins')"), 2, "this server uses it after it")
        fired = [f["payload"]["type"] for f in self.kit.run("return M.fired") if f["target"] == "all"]
        self.assertIn("events", fired, "the players' screens show it")
        self.assertEqual(self.published("DiscordLive")[0][1]["type"], "events")
        self.change("event_start", name="Luck", duration="5m", luck_x="1.5")
        self.change("event_start", name="All", duration="10m", currency="", currency_x="3")
        self.change("event_start", name="Exp", duration="24h", exp_x="10")
        ids = [e["id"] for e in self.kit.store()["Events"]["events"]]
        self.assertEqual(ids, ["g1", "g2", "g3", "g4"])
        self.assertEqual(self.kit.store()["Events"]["events"][2]["multipliers"], {"currency:*": 3})

    def test_a_counting_down_event_tells_your_code_when_it_starts(self):
        self.kit.run("seen = {}; Live.EventsChanged:Connect(function(list) table.insert(seen, #list) end)")
        self.change("event_start", name="Soon", duration="1h", exp_x="2")
        self.assertEqual(self.kit.run("return seen[#seen]"), 0, "the list changed, the event isn't running yet")
        listed = self.invoke("events")["list"][0]
        self.assertEqual(listed["starts"] - self.kit.run("return M.now"), 10, "the Manager shows the start")
        self.kit.run("M.now = M.now + 10; M.flush()")
        self.assertEqual(self.kit.run("return seen[#seen]"), 1, "EventsChanged fires again at the start")

    def test_a_start_far_away_from_a_pc_clock_ahead_waits_only_the_countdown(self):
        now = self.kit.run("return M.now")
        self.kit.load_store({"Events": {"events": [{"id": 7, "name": "Ahead", "multipliers": {"exp": 2},
                                                    "starts_at": now + 300, "ends_at": now + 3900}], "updated_at": now}})
        self.kit.run("Live.RefreshEvents()")
        self.assertEqual(self.kit.run("return Live.GetEvents()[1].starts_at") - now, 10)
        self.kit.run("M.now = M.now + 5; Live.RefreshEvents()")
        self.assertEqual(self.kit.run("return Live.GetEvents()[1].starts_at") - now, 10, "it doesn't move on a refresh")
        self.kit.run("M.now = M.now + 5")
        self.assertEqual(self.kit.run("return Live.GetMultiplier('EXP')"), 2)

    def test_events_are_checked_like_on_discord(self):
        self.refused("event_start", "badValue", name="  ", duration="1h", exp_x="2")
        self.refused("event_start", "badValue", name="X", duration="2h", exp_x="2")
        self.refused("event_start", "badMultiplier", name="X", duration="1h", exp_x="7x")
        self.refused("event_start", "unknownName", name="X", duration="1h", currency="Coinz", currency_x="2")
        self.assertEqual(self.refused("event_start", "longText", name="x" * 51, duration="1h", exp_x="2")["args"],
                         [{"text": "name"}, "50"])
        for n in range(10):
            self.change("event_start", name=f"E{n}", duration="1h", exp_x="2")
        self.assertEqual(self.refused("event_start", "tooManyEvents", name="E11", duration="1h", exp_x="2")["args"], ["10"])

    def test_an_event_with_an_animation_a_typed_multiplier_and_only_this_server(self):
        answer = self.change("event_start", name="Gold Rush", duration="1h", currency="", currency_x="2.5", animation="coin_storm")
        self.assertTrue(answer["done"], answer)
        event = self.kit.store()["Events"]["events"][0]
        self.assertEqual((event["animation"], event["multipliers"]), ("coin_storm", {"currency:*": 2.5}))
        fired = [f["payload"] for f in self.kit.run("return M.fired") if f["payload"]["type"] == "events"][-1]["events"][0]
        self.assertEqual((fired["animation"], fired["id"]), ("coin_storm", "g1"), "the players' devices get the animation")
        self.assertGreater(fired["starts_at"], 0, "and the start, for the start show")
        here = self.change("event_start", name="Local", duration="5m", exp_x="3", scope="server")
        self.assertEqual((here["done"], here["key"]), (True, "eventStartedHere"))
        self.assertEqual(len(self.kit.store()["Events"]["events"]), 1, "this server only: never saved")
        self.kit.run("M.now = M.now + 10")
        self.assertEqual(self.kit.run("return Live.GetMultiplier('EXP')"), 3, "but it works here")
        listed = {e["name"]: e for e in self.invoke("events")["list"]}
        self.assertEqual((listed["Local"]["scope"], listed["Gold Rush"]["scope"]), ("server", "all"))
        self.assertEqual(listed["Gold Rush"]["animation"], "coin_storm")
        self.assertEqual(self.log()[-1]["data"]["scope"], "server", "the bot's log says it was one server")
        self.change("event_stop", id=listed["Local"]["id"])
        self.assertEqual(self.kit.run("return Live.GetMultiplier('EXP')"), 1)
        self.assertEqual(self.log()[-1]["data"], {"id": "s1", "name": "Local", "scope": "server"})

    def test_multipliers_and_animations_are_checked(self):
        for value in ("1", "0", "101", "abc", "-2", "nan"):
            self.refused("event_start", "badMultiplier", name="X", duration="1h", exp_x=value)
        self.assertTrue(self.change("event_start", name="Comma", duration="1h", luck_x="1,75")["done"])
        self.assertEqual(self.kit.store()["Events"]["events"][0]["multipliers"], {"luck": 1.75})
        self.refused("event_start", "badValue", name="X", duration="1h", exp_x="2", animation="laser_show")
        self.refused("event_start", "badValue", name="X", duration="1h", exp_x="2", scope="galaxy")
        self.assertEqual(self.invoke("preview", {"kind": "animation", "animation": "coin_storm"}), {"ok": True})
        shown = [f["payload"] for f in self.kit.run("return M.fired") if f["payload"]["type"] == "effect_preview"]
        self.assertEqual(shown, [{"type": "effect_preview", "animation": "coin_storm"}], "only on the owner's screen")
        self.assertEqual(self.invoke("forms")["animations"],
                         ["coin_storm", "aurora", "lucky_breeze", "meteor_shower", "sakura_festival"])

    def test_stopping_an_event_from_the_bot_or_the_panel(self):
        self.kit.load_store({"Events": {"version": 1, "events": [
            {"id": 7, "name": "From Discord", "multipliers": {"exp": 2}, "ends_at": self.kit.run("return os.time()") + 600}]}})
        self.change("event_start", name="Panel", duration="1h", exp_x="2")
        listed = self.invoke("events")["list"]
        self.assertEqual(sorted((str(e["id"]), e["origin"]) for e in listed), [("7", "discord"), ("g1", "game")])
        self.assertEqual(self.change("event_stop", id=7)["args"], ["From Discord"])
        self.assertEqual([e["id"] for e in self.kit.store()["Events"]["events"]], ["g1"])
        self.change("event_stop", id="g1")
        self.assertEqual(self.kit.store()["Events"]["events"], [])
        self.refused("event_stop", "notFound", id="g1")
        self.assertEqual([e["kind"] for e in self.log()], ["event_start", "event_stop", "event_stop"])

    def test_ended_events_leave_the_entry_when_the_game_saves(self):
        now = self.kit.run("return os.time()")
        self.kit.load_store({"Events": {"events": [{"id": 1, "name": "Old", "multipliers": {"exp": 2}, "ends_at": now - 1}]}})
        self.change("event_start", name="New", duration="1h", exp_x="2")
        self.assertEqual([e["name"] for e in self.kit.store()["Events"]["events"]], ["New"])

    # ---------- eggs ----------

    def test_an_egg_is_made_with_the_chances_in_percent(self):
        answer = self.change("egg_create", name="Lava Egg", price=250, currency="coins", pets="dog: 3, Cat=1,5%",
                             spot="Lobby", duration="3d")
        self.assertEqual((answer["key"], answer["args"]), ("eggCreated", ["Lava Egg", "250", "Coins"]))
        egg = self.kit.store()["Eggs"]["eggs"][0]
        self.assertEqual((egg["id"], egg["currency"], egg["spot"], egg["color"], egg["origin"]), ("g1", "Coins", "Lobby", "#F5F5F5", "game"))
        self.assertEqual(egg["pets"], [{"name": "Dog", "chance": 66.6667}, {"name": "Cat", "chance": 33.3333}],
                         "the catalog's spelling, chances in % like /egg-create")
        self.assertGreater(egg["ends_at"], 0)
        self.kit.run("M.flush()")
        self.assertIsNotNone(self.kit.lua.globals().stand("g1"), "the stand appears on this server")
        listed = self.invoke("eggs")["list"][0]
        self.assertEqual((listed["origin"], listed["by"], listed["spot"]), ("game", "Player1", "Lobby"))

    def test_eggs_are_checked_like_on_discord(self):
        good = {"name": "Basic", "price": 10, "currency": "Coins", "pets": "Dog:1"}
        self.refused("egg_create", "badPets", **dict(good, pets="Dog 50"))
        self.refused("egg_create", "badPets", **dict(good, pets=" , ; "))
        self.refused("egg_create", "badPets", **dict(good, pets="Dog:0"))
        self.refused("egg_create", "petTwice", **dict(good, pets="Dog:1, dog:2"))
        self.assertEqual(self.refused("egg_create", "unknownPets", **dict(good, pets="Dog:1, Unicorn:1, Ghost:2"))["args"],
                         ["Unicorn, Ghost"])
        self.refused("egg_create", "tooManyPets", **dict(good, pets=", ".join(f"P{i}:1" for i in range(26))))
        self.refused("egg_create", "badValue", **dict(good, price=0))
        self.refused("egg_create", "badValue", **dict(good, price=10 ** 13))
        self.refused("egg_create", "unknownName", **dict(good, currency="Rubies"))
        self.refused("egg_create", "unknownName", **dict(good, currency=""))
        self.refused("egg_create", "badSpot", **dict(good, spot="Nowhere"))
        self.change("egg_create", **good)
        self.refused("egg_create", "eggExists", **dict(good, name="BASIC"))
        for n in range(19):
            self.change("egg_create", **dict(good, name=f"Egg {n}"))
        self.assertEqual(self.refused("egg_create", "tooManyEggs", **dict(good, name="One more"))["args"], ["20"])

    def test_without_egg_spots_the_answer_says_so(self):
        self.start(spots=())
        answer = self.change("egg_create", name="Basic", price=10, currency="Coins", pets="Dog:1")
        self.assertEqual(answer["warns"], [{"key": "warnNoSpots", "args": []}])

    def test_a_new_id_never_repeats_one_the_entry_has(self):
        self.kit.load_store({"Eggs": {"eggs": [{"id": "g3", "name": "Old", "currency": "Coins", "price": 10,
                                                "pets": [{"name": "Dog", "chance": 100}], "ends_at": 0}]}})
        self.change("egg_create", name="New", price=10, currency="Coins", pets="Dog:1")
        self.assertEqual([e["id"] for e in self.kit.store()["Eggs"]["eggs"]], ["g3", "g4"])
        self.assertEqual(self.kit.store()["Eggs"]["next_id"], 5)

    def test_moving_and_removing_eggs_of_the_bot_and_of_the_panel(self):
        self.kit.load_store({"Eggs": {"version": 1, "eggs": [{"id": 5, "name": "Bot Egg", "currency": "Coins", "price": 10,
                                                             "pets": [{"name": "Dog", "chance": 100}], "spot": "", "ends_at": 0}]}})
        self.kit.run("Live.RefreshEggs()")
        answer = self.change("egg_move", id=5, spot="Spawn")
        self.assertEqual(answer["args"], ["Bot Egg", "Spawn"])
        self.assertEqual(self.kit.store()["Eggs"]["eggs"][0]["spot"], "Spawn")
        self.assertEqual(self.change("egg_move", id=5, spot="")["args"], ["Bot Egg", {"text": "anySpot"}])
        self.refused("egg_move", "badSpot", id=5, spot="Nowhere")
        self.change("egg_create", name="Panel Egg", price=10, currency="Coins", pets="Cat:1")
        self.change("egg_remove", id=5)
        self.assertEqual([e["id"] for e in self.kit.store()["Eggs"]["eggs"]], ["g1"])
        self.refused("egg_remove", "notFound", id=5)
        self.assertEqual([e["kind"] for e in self.log()], ["egg_move", "egg_move", "egg_create", "egg_remove"])

    # ---------- gifts and announcements ----------

    def test_a_gift_reaches_a_player_on_this_server_at_once(self):
        answer = self.change("gift", player="player101", currency="Coins", amount=500, message="Thanks!")
        self.assertEqual((answer["key"], answer["args"]), ("giftSent", ["Player101", "+500 Coins"]))
        coins = "return M.players[1]:FindFirstChild('leaderstats'):FindFirstChild('Coins').Value"
        self.assertEqual(self.kit.run(coins), 1500, "delivered right away")
        entry = self.log()[0]
        self.assertEqual((entry["kind"], entry["data"]["user_id"], entry["data"]["username"]), ("gift", 101, "Player101"))
        self.assertTrue(entry["data"]["key"].startswith("gift_101_"), "the bot keeps it under the same key")
        self.assertEqual(self.published("DiscordLive")[-1][1], {"type": "gift", "user_id": 101,
                                                                "from": self.published("DiscordLive")[-1][1]["from"]})

    def test_a_gift_for_someone_offline_waits_in_the_game(self):
        self.kit.run("M.accounts[555] = 'Sleeper'")
        self.change("gift", player="555", exp=100, message="")
        gifts = self.kit.store("DiscordGifts")
        key = next(iter(gifts))
        self.assertTrue(key.startswith("gift_555_"))
        self.assertEqual(gifts[key]["reward"], {"exp": 100})
        self.assertEqual(gifts[key]["from"], "Player1")

    def test_gifts_are_checked_like_on_discord(self):
        self.kit.run("M.accounts[555] = 'Bob'; M.accounts[777] = '555'")
        self.assertEqual(self.refused("gift", "ambiguous", player="555", exp=1)["args"], ["555"],
                         "the ID of one account and the name of another: never guessed")
        self.refused("gift", "noPlayer", player="nobody_here", exp=1)
        self.refused("gift", "noPlayer", player="", exp=1)
        self.refused("gift", "noReward", player="Bob")
        self.refused("gift", "longText", player="Bob", exp=1, message="x" * 151)
        answer = self.change("gift", player="Bob", exp=1, message="see youtube.com/abc")
        self.assertEqual(answer["warns"], [{"key": "warnLink", "args": []}], "sent, with a warning")

    def test_an_announcement_shows_here_and_goes_to_every_server(self):
        answer = self.change("announce", text="Double coins now!", seconds=15)
        self.assertEqual(answer["key"], "announced")
        shown = [f["payload"] for f in self.kit.run("return M.fired") if f["payload"]["type"] == "announce"]
        self.assertEqual(shown, [{"type": "announce", "text": "Double coins now!", "seconds": 15}])
        message = self.published("DiscordLive")[0][1]
        self.assertEqual((message["type"], message["text"], message["seconds"]), ("announce", "Double coins now!", 15))
        self.refused("announce", "hasLink", text="join discord.gg/abc", seconds=10)
        self.refused("announce", "hasLink", text="see www.site", seconds=10)
        self.refused("announce", "badValue", text="hi", seconds=7)
        self.refused("announce", "longText", text="x" * 201, seconds=10)

    def test_an_announcement_when_the_other_servers_cant_be_told(self):
        self.kit.run("M.publishError = 'MessagingService down'")
        answer = self.change("announce", text="Hello", seconds=10)
        self.assertEqual((answer["done"], answer["key"]), (True, "announcedHere"))
        self.assertEqual(answer["warns"][0]["key"], "warnNotTold")

    def test_the_own_notifications_are_not_read_again_but_other_servers_are(self):
        self.change("event_start", name="Here", duration="1h", exp_x="2")
        own = self.kit.run("return M.published[1].data")
        reads = self.kit.run("return M.reads['DiscordLiveContent/Events'] or 0")
        self.kit.lua.globals().ownMessage = own
        self.kit.run("M.subscriptions.DiscordLive({ Data = ownMessage }); M.flush()")
        self.assertEqual(self.kit.run("return M.reads['DiscordLiveContent/Events'] or 0"), reads, "this server has it already")
        self.kit.lua.globals().otherMessage = json.dumps({"type": "events", "at": 1, "from": "another server"})
        self.kit.run("M.subscriptions.DiscordLive({ Data = otherMessage }); M.flush()")
        self.assertGreater(self.kit.run("return M.reads['DiscordLiveContent/Events'] or 0"), reads)

    # ---------- bans ----------

    def test_a_ban_goes_through_roblox_for_the_whole_game(self):
        found = self.change("find_player", player="Player101")
        self.assertEqual((found["key"], found["args"], found["extra"]),
                         ("found", ["Player101", "101"], {"user_id": 101, "username": "Player101"}))
        answer = self.change("ban", user_id=101, duration="24h", reason="Exploiting")
        self.assertEqual((answer["key"], answer["args"]), ("banned", ["Player101", {"duration": "24h"}]))
        ban = self.kit.run("return M.bans[1]")
        self.assertEqual((ban["UserIds"], ban["Duration"], ban["ApplyToUniverse"], ban["DisplayReason"]),
                         ([101], 86400, True, "Exploiting"))
        self.assertIn("Player1", ban["PrivateReason"])
        self.change("ban", user_id=101, duration="permanent", reason="")
        ban = self.kit.run("return M.bans[2]")
        self.assertEqual((ban["Duration"], ban["DisplayReason"]), (-1, "Breaking the game's rules (permanent ban)"))
        self.assertEqual(self.change("unban", player="101")["args"], ["Player101"])
        self.assertEqual(self.kit.run("return M.unbans[1]")["UserIds"], [101])
        self.assertEqual([e["kind"] for e in self.log()], ["ban", "ban", "unban"], "an account check is not a change")

    def test_bans_are_checked(self):
        self.refused("ban", "banSelf", user_id=1, duration="24h")
        self.kit.run("M.accounts[202] = 'Someone'")
        self.refused("ban", "hasLink", user_id=202, duration="24h", reason="read rules at www.x")
        self.refused("ban", "badValue", user_id=202, duration="2d")
        self.refused("ban", "noPlayer", user_id=999999, duration="24h")
        self.kit.run("M.banError = 'Players:BanAsync() is not enabled: turn on Players.BanningEnabled'")
        self.refused("ban", "banOff", user_id=202, duration="24h")
        self.kit.run("M.banError = 'HTTP 503'")
        self.assertEqual(self.refused("unban", "robloxBusy", player="Someone")["args"], ["HTTP 503"])
        self.assertEqual(self.kit.run("return #M.bans"), 0)

    def test_in_studio_a_ban_is_only_checked(self):
        self.start(studio=True)
        answer = self.change("ban", user_id=101, duration="1h", reason="test")
        self.assertEqual(answer["warns"], [{"key": "warnStudioBan", "args": []}])

    # ---------- the log for the bot and saving problems ----------

    def test_the_log_keeps_the_newest_100_changes(self):
        for n in range(105):
            self.kit.run("M.clock = M.clock + 2")
            self.change("announce", text=f"News {n}", seconds=5)
        log = self.kit.store()["PanelLog"]
        self.assertEqual(len(log["entries"]), 100)
        self.assertEqual((log["entries"][0]["seq"], log["entries"][-1]["seq"], log["next"]), (6, 105, 106))

    def test_a_studio_without_api_access_and_other_save_errors(self):
        self.kit.lua.globals().studioError = STUDIO_ERROR
        self.kit.run("M.updateError = studioError")
        self.refused("code_add", "studioApi", code="X", exp=1, validity="7d")
        self.refused("event_start", "studioApi", name="X", duration="1h", exp_x="2")
        self.kit.run("M.updateError = 'DataStore request was rejected'")
        self.assertEqual(self.refused("egg_create", "saveFailed", name="X", price=1, currency="Coins", pets="Dog:1")["args"],
                         ["DataStore request was rejected"])

    def test_a_later_save_never_goes_back_in_time(self):
        future = self.kit.run("return os.time()") + 300
        self.kit.load_store({"Events": {"events": [], "updated_at": future}})
        self.change("event_start", name="Now", duration="1h", exp_x="2")
        self.assertGreater(self.kit.store()["Events"]["updated_at"], future)

    def test_a_broken_form_never_breaks_the_panel(self):
        for data in ({"code": {"x": 1}}, {"price": "lots"}, {"id": None}, {}):
            for kind in ("code_add", "egg_create", "egg_move", "event_stop", "gift", "ban", "unban", "announce"):
                answer = self.invoke("change", {"kind": kind, "data": data})
                self.assertTrue(answer["ok"] is False or answer["done"] is False, (kind, data, answer))


class AnimationLists(unittest.TestCase):
    """The animations the players' devices have (Effects.luau), the panel offers (Control.luau) and Discord offers
    (cogs/live_game.py) are the same list."""

    def test_the_three_lists_are_the_same(self):
        import re
        from cogs.live_game import ANIMATIONS
        effects = sorted(set(re.findall(r"^animations\.(\w+) = function", read(os.path.join(SOURCE, "Effects.luau")), re.M)))
        control = re.search(r"Control\.Animations = \{([^}]*)\}", read(os.path.join(SOURCE, "Control.luau"))).group(1)
        self.assertEqual(sorted(re.findall(r'"(\w+)"', control)), effects)
        self.assertEqual(sorted(ANIMATIONS), effects)
        self.assertTrue(effects)


@unittest.skipUnless(HAVE_LUA, "lupa is not installed (set BOTDC_LUPA_PATH): the kit server scripts were not run")
class LinksLikeTheBot(unittest.TestCase):
    """Control.HasLink is the same rule as has_link in cogs/live_game.py (Roblox shows a text with a link as ####)."""

    def test_the_same_answers_as_the_bot(self):
        from cogs.live_game import has_link
        kit = Kit()
        kit.lua.globals().Control = kit.lua.execute(read(os.path.join(SOURCE, "Control.luau")))
        texts = ["https://x.y", "http://a", "www.site", "discord.gg/abc", "discord . gg/abc", "youtu.be/abc", "roblox.com",
                 "Visit Roblox.COM now", "a.de.", "Awww.", "v1.2", "Super.To nowy event", "Wow.Co nowego?", "event.Fun",
                 "game.Fun/stuff", "a.com5", "abc.community", "my-site.pl", "x.gg", "plain text", "", "3.14 coins",
                 "hello.world/", "end.com"]
        for text in texts:
            kit.lua.globals().sample = text
            self.assertEqual(kit.run("return Control.HasLink(sample)"), has_link(text), text)


if __name__ == "__main__":
    unittest.main()
