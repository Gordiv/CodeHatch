"""The in-game event icons (scripts/DiscordCodes/LiveClient.client.luau) and the Studio files built from it.

1. Always run (plain Python, read only): the .rbxmx files hold exactly the current scripts, the version recorded in
   tools/roblox_kit_version.json is the one in Loader.server.luau (there is one kit file, with the Live module for eggs
   and events).
2. Run when the `lupa` package is installed (it is not in the project's .venv): the real LocalScript runs against a small
   Roblox mock (tests/live_client_mock.lua) and the icons are read back: the icon (own ones from EventIcons), the biggest
   multiplier and the time left, the card that tells what the event does, where the row is, and the timer counting down.
   Without lupa those tests are SKIPPED; point BOTDC_LUPA_PATH at a folder that holds it to run them."""
import json
import os
import sys
import unittest
import xml.etree.ElementTree as ET

from tests.helpers import ROOT

SCRIPTS = os.path.join(ROOT, "scripts")
SOURCE = os.path.join(SCRIPTS, "DiscordCodes")


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def sources_in(rbxmx: str) -> dict:
    """{name: source} of every script in a built .rbxmx."""
    result = {}
    for item in ET.parse(os.path.join(SCRIPTS, rbxmx)).getroot().iter("Item"):
        props = item.find("Properties")
        source = props.find("ProtectedString[@name='Source']") if props is not None else None
        if source is not None:
            result[props.find("string[@name='Name']").text] = source.text
    return result


class BuiltFilesAreCurrent(unittest.TestCase):
    def test_the_full_kit_holds_the_current_scripts(self):
        built = sources_in("DiscordCodes.rbxmx")
        for name, file in (("Core", "Core.luau"), ("Report", "Report.luau"), ("Live", "Live.luau"), ("DiscordCodesClient", "Client.client.luau"),
                           ("DiscordLiveClient", "LiveClient.client.luau"), ("DiscordCodes", "Loader.server.luau")):
            self.assertIn(name, built, f"{name} is in the kit")
            self.assertEqual(built[name], read(os.path.join(SOURCE, file)), f"{file}: the .rbxmx is older than the script: run tools/build_roblox_kit.py")

    def test_the_kit_file_has_the_live_module_and_there_is_no_beta_file(self):
        """Eggs and events are in the Live module and the event bar: they are in the one scripts/DiscordCodes.rbxmx."""
        self.assertFalse(os.path.exists(os.path.join(SCRIPTS, "DiscordCodes_beta.rbxmx")), "the old testers' file is gone")
        self.assertFalse(os.path.exists(os.path.join(SCRIPTS, "DiscordCatalog_beta.rbxmx")), "the beta catalog file is gone")
        built = sources_in("DiscordCodes.rbxmx")
        for name in ("Core", "Report", "Live", "DiscordLiveClient", "DiscordCodes"):
            self.assertIn(name, built, f"{name} is in the kit file")
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        try:
            import build_roblox_kit
        finally:
            sys.path.remove(os.path.join(ROOT, "tools"))
        self.assertFalse(hasattr(build_roblox_kit, "OUT_BETA"), "the build script makes no beta kit file")

    def test_the_recorded_version_and_hash_are_the_ones_of_the_scripts(self):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        try:
            import build_roblox_kit
        finally:
            sys.path.remove(os.path.join(ROOT, "tools"))
        record = json.loads(read(os.path.join(ROOT, "tools", "roblox_kit_version.json")))
        loader = read(os.path.join(SOURCE, "Loader.server.luau"))
        version = int(build_roblox_kit.KIT_LINE.search(loader).group(1))
        self.assertEqual(record["version"], version, "KIT_VERSION in Loader.server.luau is the recorded version")
        self.assertEqual(record["hash"], build_roblox_kit.sources_hash(), "the scripts changed after the last build: run tools/build_roblox_kit.py")

    def test_the_window_template_is_valid(self):
        root = ET.parse(os.path.join(SCRIPTS, "DiscordCodesWindow.rbxmx")).getroot()
        self.assertTrue(list(root.iter("Item")))

    def test_the_settings_template_names_every_setting_of_the_kit(self):
        """DiscordSettings.rbxmx (the owner's settings, outside DiscordCodes): the Loader copies a value only into a
        setting of the same name, so the template must use exactly the names of the kit's Settings folder."""
        from tools import build_roblox_kit
        top = ET.parse(os.path.join(SCRIPTS, "DiscordSettings.rbxmx")).getroot().find("Item")
        self.assertEqual(top.get("class"), "ModuleScript")
        source = top.find("Properties/ProtectedString").text
        self.assertEqual(source, build_roblox_kit.SETTINGS_SOURCE.read_text(encoding="utf-8").replace("\r\n", "\n"))
        for _cls, name, _xml_type, _value in build_roblox_kit.SETTINGS:
            self.assertIn(f"\t{name} = ", source)

    def test_the_event_icons_read_their_settings_in_the_source(self):
        source = read(os.path.join(SOURCE, "LiveClient.client.luau"))
        self.assertIn('live("EventPosition", "BottomRight")', source)
        self.assertIn('setting("EventIcons", "")', source)
        self.assertIn('live("AnnouncementPosition", "Top")', source)
        self.assertIn('live("NotificationPosition", "Bottom")', source)


def lua_runtime():
    try:
        import lupa
    except ImportError:
        extra = os.environ.get("BOTDC_LUPA_PATH")
        if not extra:
            return None
        sys.path.insert(0, extra)
        try:
            import lupa
        except ImportError:
            return None
        finally:
            sys.path.remove(extra)
    return lupa.LuaRuntime(unpack_returned_tuples=True)


LUA = lua_runtime()


@unittest.skipIf(LUA is None, "lupa is not installed (set BOTDC_LUPA_PATH): the Luau event icons were not run")
class EventIconsInTheGame(unittest.TestCase):
    def setUp(self):
        self.lua = LUA
        self.mock = self.lua.execute(read(os.path.join(ROOT, "tests", "live_client_mock.lua")))
        self.source = read(os.path.join(SOURCE, "LiveClient.client.luau"))

    def to_lua(self, value):
        if isinstance(value, dict):
            return self.lua.table_from({k: self.to_lua(v) for k, v in value.items()})
        if isinstance(value, list):
            return self.lua.table_from([self.to_lua(v) for v in value])
        return value

    def start(self, locale="en-us", setting="auto", touch=False, **extra):
        self.mock.start(self.source, locale, setting, self.to_lua(extra) if extra else None, touch)
        self.assertEqual(len(self.mock.warnings), 0, "the script started without a warning")

    def events(self, *events, now=None):
        now = now or self.mock.now
        self.mock.fire(self.to_lua({"type": "events", "server_time": now, "events": list(events)}))

    def badges(self):
        badges = self.mock.badges()
        return [(badges[i]["icon"], badges[i]["factor"], badges[i]["time"]) for i in range(1, len(badges) + 1)]

    def hover(self, index=0):
        badge = self.mock.badges()[index + 1]["object"]
        badge.MouseEnter.Fire(badge.MouseEnter)
        tip = self.mock.tip()
        return {k: tip[k] for k in ("visible", "title", "lines", "ends")}

    def test_an_event_is_an_icon_with_its_biggest_multiplier_and_the_time_left(self):
        self.start()
        now = self.mock.now
        self.events({"id": 1, "name": "Weekend", "multipliers": {"exp": 2, "luck": 3, "currency:Coins": 2}, "ends_at": now + 3700})
        self.assertEqual(self.badges(), [("💰", "3x", "1h 01m")], "the icon of its first multiplier (a currency), the biggest one")
        self.assertEqual(self.hover(), {"visible": True, "title": "Weekend", "ends": "Ends in 1h 01m",
                                        "lines": "2x more Coins\n2x more EXP\nRare pets 3x more often"})

    def test_the_timer_counts_down_and_the_icon_goes_when_the_event_ends(self):
        self.start()
        now = self.mock.now
        self.events({"id": 1, "name": "", "multipliers": {"currency:*": 5}, "ends_at": now + 90})
        self.assertEqual(self.badges(), [("💰", "5x", "1:30")])
        tip = self.hover()
        self.assertEqual((tip["title"], tip["lines"]), ("Event", "5x more of every currency"), "no name: the word Event")
        self.mock.tick(30)
        self.assertEqual(self.badges()[0][2], "1:00")
        self.assertEqual(self.mock.tip()["ends"], "Ends in 1:00", "an open card counts down too")
        self.mock.tick(30)
        self.assertEqual(self.badges()[0][2], "0:30")
        self.mock.tick(31)
        self.assertEqual(self.badges(), [], "the event ran out: its icon is gone")
        self.assertFalse(self.mock.tip()["visible"], "and its card")

    def test_a_new_event_counts_down_10_seconds_in_a_card_then_3_2_1_at_the_top(self):
        self.start()
        now = self.mock.now
        self.events({"id": "g1", "name": "Gold Rush", "multipliers": {"currency:Coins": 2}, "starts_at": now + 10,
                     "ends_at": now + 70, "animation": "coin_storm"})
        self.mock.tick(0)
        shown = self.mock.countdown()
        self.assertEqual((shown["card"], shown["title"], shown["line"], shown["note"], shown["big"]),
                         ("10", "Gold Rush", "2x more Coins", "Lasts 1 min", ""), "a small card with the seconds left")
        self.assertEqual(self.badges(), [], "no event icon before it starts")
        self.assertNotIn("announceNewEvents", self.source, "and no announcement banner: its own countdown")
        self.mock.tick(6)
        self.assertEqual(self.mock.countdown()["card"], "4")
        self.mock.tick(2)
        shown = self.mock.countdown()
        self.assertEqual((shown["card"], shown["big"], shown["text"]), ("", "2", "GOLD RUSH"), "the last 3 seconds: big, at the top")
        self.mock.tick(1)
        self.assertEqual(self.mock.countdown()["big"], "1")
        self.mock.tick(1)
        shown = self.mock.countdown()
        self.assertEqual((shown["big"], shown["text"]), ("", "START!"))
        self.assertEqual(self.badges(), [("💰", "2x", "1:00")], "now its icon is there")
        self.mock.runDelayed()
        self.assertEqual(self.mock.countdown()["text"], "", "the big text goes after a moment")
        self.mock.tick(1)
        shown = self.mock.countdown()
        self.assertEqual((shown["card"], shown["big"], shown["text"]), ("", "", ""), "and it does not come back")

    def test_an_event_that_already_runs_has_no_countdown(self):
        self.start(locale="pl-pl")
        now = self.mock.now
        self.events({"id": "g1", "name": "Old", "multipliers": {"exp": 2}, "starts_at": now - 100, "ends_at": now + 60},
                    {"id": "g2", "name": "Nowy", "multipliers": {"exp": 3}, "starts_at": now + 5, "ends_at": now + 60})
        self.mock.tick(0)
        shown = self.mock.countdown()
        self.assertEqual((shown["card"], shown["title"], shown["note"]), ("5", "Nowy", "Trwa 55 s"), "only the coming one")
        self.assertEqual([factor for _, factor, _ in self.badges()], ["2x"], "the running one is an icon")
        self.mock.tick(5)
        self.assertEqual(self.mock.countdown()["text"], "START!")
        self.assertEqual(len(self.badges()), 2)

    def test_an_event_stopped_during_its_3_2_1_leaves_nothing_on_the_screen(self):
        self.start()
        now = self.mock.now
        self.events({"id": "g1", "name": "Stop me", "multipliers": {"exp": 2}, "starts_at": now + 2, "ends_at": now + 60})
        self.mock.tick(0)
        self.assertEqual(self.mock.countdown()["big"], "2")
        self.events()
        self.mock.tick(0)
        shown = self.mock.countdown()
        self.assertEqual((shown["card"], shown["big"], shown["text"]), ("", "", ""))

    def test_a_start_missed_by_a_frozen_device_still_shows_the_icon(self):
        self.start()
        now = self.mock.now
        self.events({"id": "g1", "name": "Late", "multipliers": {"exp": 2}, "starts_at": now + 5, "ends_at": now + 60})
        self.mock.tick(0)
        self.mock.tick(8)
        self.assertEqual([factor for _, factor, _ in self.badges()], ["2x"])
        self.assertEqual(self.mock.countdown()["big"], "", "no late 3-2-1")

    def test_own_icons_from_the_settings_by_multiplier_or_event_name(self):
        self.start(EventIcons="Strength=💪, exp = ✨ ; Weekend Boost=🎉, Gems=rbxassetid://123, Speed=456, broken, =x")
        now = self.mock.now
        self.events({"id": 1, "name": "", "multipliers": {"currency:Strength": 2}, "ends_at": now + 60},
                    {"id": 2, "name": "Weekend Boost", "multipliers": {"exp": 2}, "ends_at": now + 60},
                    {"id": 3, "name": "", "multipliers": {"currency:Gems": 2}, "ends_at": now + 60},
                    {"id": 4, "name": "", "multipliers": {"currency:Speed": 3}, "ends_at": now + 60},
                    {"id": 5, "name": "", "multipliers": {"exp": 2}, "ends_at": now + 60},
                    {"id": 6, "name": "", "multipliers": {"luck": 2}, "ends_at": now + 60})
        self.assertEqual([icon for icon, _, _ in self.badges()],
                         ["💪", "🎉", "image:rbxassetid://123", "image:rbxassetid://456", "✨", "🍀"])

    def test_several_events_in_a_row_and_one_with_20_currencies(self):
        self.start()
        now = self.mock.now
        many = {f"currency:Currency number {i:02d}": 2 for i in range(20)}
        self.events({"id": 1, "name": "Everything", "multipliers": dict(many, exp=4, luck=2), "ends_at": now + 7200},
                    {"id": 2, "name": "Short", "multipliers": {"exp": 10}, "ends_at": now + 600})
        self.assertEqual(self.badges(), [("💰", "4x", "2h 00m"), ("⭐", "10x", "10:00")])
        lines = self.hover()["lines"].split("\n")
        self.assertEqual(len(lines), 22)
        self.assertEqual(lines[0], "2x more Currency number 00", "the named currencies first, by name")
        self.assertEqual(lines[-2:], ["4x more EXP", "Rare pets 2x more often"])

    def test_a_new_message_replaces_the_icons_and_the_server_clock_is_followed(self):
        self.start()
        now = self.mock.now
        self.events({"id": 1, "name": "Old", "multipliers": {"exp": 2}, "ends_at": now + 1000})
        self.events({"id": 2, "name": "New", "multipliers": {"luck": 2}, "ends_at": now + 1000 + 600}, now=now + 600)
        self.assertEqual(self.badges(), [("🍀", "2x", "16:40")], "the server clock is 600 s ahead: 1000 s are left, not 1600")
        self.events()
        self.assertEqual(self.badges(), [])

    def test_the_texts_in_polish_and_spanish(self):
        for locale, setting, lines, ends in (("pl-pl", "auto", "2x więcej: Coins\nRzadkie zwierzaki 2x częściej", "Koniec za 1h 00m"),
                                             ("es-es", "auto", "2x más de Coins\nMascotas raras 2x más a menudo", "Termina en 1h 00m"),
                                             ("en-us", "pl", "2x więcej: Coins\nRzadkie zwierzaki 2x częściej", "Koniec za 1h 00m")):
            self.start(locale, setting)
            now = self.mock.now
            self.events({"id": 1, "name": "X", "multipliers": {"luck": 2, "currency:Coins": 2}, "ends_at": now + 3600})
            tip = self.hover()
            self.assertEqual((tip["lines"], tip["ends"]), (lines, ends), (locale, setting))

    def test_where_the_icons_are(self):
        self.start()
        self.assertEqual(dict(self.mock.place()), {"ax": 1, "ay": 1, "xs": 1, "xo": -16, "ys": 1, "yo": -16}, "bottom right by default")
        self.start(EventPosition="TopLeft")
        self.assertEqual(dict(self.mock.place()), {"ax": 0, "ay": 0, "xs": 0, "xo": 16, "ys": 0, "yo": 16})
        self.start(EventPosition="nowhere")
        self.assertEqual(self.mock.place()["ax"], 1, "an unknown name: bottom right")
        self.start(ButtonPosition="BottomRight")
        self.assertEqual(self.mock.place()["yo"], -86, "the Codes button is in the same corner: the icons go above it")
        self.start(touch=True)
        self.assertEqual(self.mock.place()["yo"], -146, "a phone: above the jump button")

    def test_every_place_can_be_moved_by_pixels(self):
        self.start(EventPosition="BottomRight -20,-30")
        self.assertEqual(dict(self.mock.place()), {"ax": 1, "ay": 1, "xs": 1, "xo": -36, "ys": 1, "yo": -46})
        self.start(EventPosition="Center")
        self.assertEqual((self.mock.place()["ax"], self.mock.place()["ay"]), (0.5, 0.5))

    def test_announcements_and_notifications_go_where_the_settings_say(self):
        self.start()
        self.assertEqual(dict(self.mock.place("Toast")), {"ax": 0.5, "ay": 1, "xs": 0.5, "xo": 0, "ys": 1, "yo": -110},
                         "notifications: bottom center by default")
        banner = self.mock.place("AnnouncementHolder")
        self.assertEqual((banner["ax"], banner["ay"], banner["yo"]), (0.5, 0, 12 - 220), "announcements: hidden above the top")
        self.start(NotificationPosition="TopLeft 10,20", AnnouncementPosition="Bottom 0,-20")
        self.assertEqual(dict(self.mock.place("Toast")), {"ax": 0, "ay": 0, "xs": 0, "xo": 26, "ys": 0, "yo": 36})
        banner = self.mock.place("AnnouncementHolder")
        self.assertEqual((banner["ax"], banner["ay"], banner["yo"]), (0.5, 1, -110 - 20 + 220), "hidden below the bottom")
        self.start(NotificationPosition="BottomRight")
        self.assertEqual(self.mock.place("Toast")["yo"], -16 - 110, "the event icons are in that corner: the card goes above them")
        self.start(NotificationPosition="nowhere")
        self.assertEqual(self.mock.place("Toast")["yo"], -110, "an unknown place: bottom center")

    def test_the_manager_moves_things_while_the_game_runs(self):
        self.start()
        self.mock.remote.SetAttribute(self.mock.remote, "NotificationPosition", "Top")
        self.assertEqual((self.mock.place("Toast")["ay"], self.mock.place("Toast")["yo"]), (0, 90))
        self.mock.remote.SetAttribute(self.mock.remote, "EventPosition", "TopLeft")
        self.assertEqual((self.mock.place()["ax"], self.mock.place()["ay"]), (0, 0))
        self.mock.remote.SetAttribute(self.mock.remote, "AnnouncementPosition", "Center")
        banner = self.mock.place("AnnouncementHolder")
        self.assertEqual((banner["ax"], banner["ay"], banner["ys"], banner["yo"]), (0.5, 0.5, 0.5, -40), "in the middle it comes from 40 px above")

    def test_a_tap_shows_the_card_and_a_second_tap_hides_it(self):
        self.start()
        now = self.mock.now
        self.events({"id": 1, "name": "Tap", "multipliers": {"exp": 2}, "ends_at": now + 600})
        badge = self.mock.badges()[1]["object"]
        badge.Activated.Fire(badge.Activated)
        self.assertTrue(self.mock.tip()["visible"])
        badge.Activated.Fire(badge.Activated)
        self.assertFalse(self.mock.tip()["visible"])

    def test_odd_messages_do_not_break_the_script(self):
        self.start()
        now = self.mock.now
        for payload in ({"type": "events"}, {"type": "events", "events": "not a list"}, {"type": "events", "events": []},
                        {"type": "events", "events": [{"id": 1, "name": "", "multipliers": {}, "ends_at": now + 60}]},
                        {"type": "events", "events": [{"id": 1, "name": "N", "multipliers": {"unknown": 2}, "ends_at": now + 60}]}):
            self.mock.fire(self.to_lua(payload))
        self.assertEqual(self.badges(), [("⚡", "", "1:00")], "nothing it knows: a lightning icon without a multiplier")
        self.assertEqual(self.hover()["lines"], "")
        self.assertEqual(len(self.mock.warnings), 0)


@unittest.skipIf(LUA is None, "lupa is not installed (set BOTDC_LUPA_PATH): the Luau toasts were not run")
class ToastsAndFloatingEggs(unittest.TestCase):
    setUp = EventIconsInTheGame.setUp
    to_lua = EventIconsInTheGame.to_lua
    start = EventIconsInTheGame.start

    def fire(self, payload):
        self.mock.fire(self.to_lua(payload))
        toast = self.mock.toast()
        return {k: toast[k] for k in ("visible", "title", "line", "note")}

    def test_a_hatched_pet_shows_its_chance_and_a_rare_one_says_so(self):
        for locale, title, rare in (("en-us", "You hatched Fox!", "Rare!"), ("pl-pl", "Nowy zwierzak: Fox!", "Rzadki!"),
                                    ("es-es", "¡Has sacado Fox!", "¡Rara!")):
            self.start(locale)
            self.assertEqual(self.fire({"type": "hatch", "pet": "Fox", "chance": 1, "rare": True}),
                             {"visible": True, "title": title, "line": f"{rare} · 1%", "note": ""}, locale)
            self.assertEqual(self.fire({"type": "hatch", "pet": "Fox", "chance": 40, "rare": False})["line"], "40%")

    def test_a_gift_shows_the_reward_and_its_message_on_its_own_line(self):
        self.start()
        shown = self.fire({"type": "gift", "reward": {"currency": {"name": "Coins", "amount": 5000}, "item": {"name": "Golden Sword"}},
                           "message": "Thanks for reporting the bug!"})
        self.assertEqual(shown, {"visible": True, "title": "Gift from the developers", "line": "+5,000 Coins, Golden Sword",
                                 "note": "Thanks for reporting the bug!"})
        self.assertEqual(self.fire({"type": "gift", "reward": {"exp": 10}})["note"], "", "no message: no empty line")

    def test_an_egg_error_is_the_whole_title_and_wraps_instead_of_being_cut(self):
        self.start()
        shown = self.fire({"type": "egg_error", "key": "poor", "currency": "Coins", "price": 1000})
        self.assertEqual(shown["title"], "Not enough Coins (you need 1,000).")
        self.assertEqual(shown["line"], "")
        self.assertEqual(self.fire({"type": "egg_error", "key": "restricted"})["title"],
                         "Eggs aren't available for your account (Roblox rules in your country).")

    def test_a_floating_egg_moves_up_and_its_pedestal_stays(self):
        self.start()
        model, egg, base = self.mock.addStand(True)
        self.mock.tick(1)  # the script looks for stands every second
        self.mock.renderStepped.Fire(self.mock.renderStepped)
        moved = self.mock.moved
        self.assertIsNotNone(moved, "the egg was moved")
        parts = [moved.parts[i] for i in range(1, len(moved.parts) + 1)]
        self.assertEqual([p.Name for p in parts], ["Egg"], "only the egg, not the pedestal")
        self.assertGreaterEqual(moved.cframes[1].Position.Y, 5, "up from its place, never into the pedestal")

    def test_an_egg_without_the_mark_stays_still(self):
        self.start()
        self.mock.addStand(False)
        self.mock.tick(1)
        self.mock.renderStepped.Fire(self.mock.renderStepped)
        self.assertIsNone(self.mock.moved)


if __name__ == "__main__":
    unittest.main()
