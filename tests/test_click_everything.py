"""The bot loads, then every
button and menu of the game control panel, of /setup-roblox and of the windows they open is clicked, every form they
open is filled in and sent, and ✖️ Close is pressed on every window, in English, Polish and Spanish.

Runs in a TEMPORARY COPY of the project in a subprocess (tests/click_driver.py): the real config.json, data/ and bot.db
are never touched, and nothing connects to Discord, Roblox or Gemini (a network attempt is refused and counted)."""
import json
import os
import shutil
import subprocess
import sys
import unittest

from tests.helpers import ROOT
from tests.test_bot_loads import copy_project

LANGS = ("en", "pl", "es")
KEYS = ("codes", "player", "gift", "announce", "events", "eggs")
GAME_WINDOWS = {"PlayerCardView", "UnbanConfirmView", "GiftsView", "BansView", "RankingView", "EggsView", "EventsView"}
OTHER_WINDOWS = {"GamePanelView", "CodesView", "CodeDraftView", "CodeRemoveView", "OverwriteView", "CloseView", "RobloxPanelView",
                 "GamePanelManager", "CloudSyncView", "CatalogView", "GameNamesView", "TutorialView",
                 # the windows of /setup
                 "PanelView", "ChannelsView", "ServersView", "GuideView"}
ALL_WINDOWS = OTHER_WINDOWS | GAME_WINDOWS | {"StaffView"}


def run_clicks(lang: str) -> dict:
    target = copy_project()
    try:
        shutil.copy2(os.path.join(ROOT, "tests", "click_driver.py"), os.path.join(target, "click_driver.py"))
        shutil.copy2(os.path.join(ROOT, "tests", "panel_fakes.py"), os.path.join(target, "tests", "panel_fakes.py"))
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=target)
        env.pop("BOT_LAUNCHER", None)
        done = subprocess.run([sys.executable, "click_driver.py", lang], cwd=target, env=env,
                              capture_output=True, text=True, encoding="utf-8", timeout=240)
        lines = [line for line in done.stdout.splitlines() if line.startswith("RESULT ")]
        if not lines:
            raise AssertionError(f"the driver printed no result (exit {done.returncode}):\n{done.stdout[-1500:]}\n{done.stderr[-2500:]}")
        return json.loads(lines[-1][len("RESULT "):])
    finally:
        shutil.rmtree(target, ignore_errors=True)


class ClickEverything(unittest.TestCase):
    def check_common(self, result: dict, label: str, lang: str) -> set:
        self.assertEqual(result["failed"], [], f"{label}: every module loads")
        self.assertEqual(result["errors"], [], f"{label}: no click, form or ✖️ fails")
        self.assertEqual(result["refused"], [], f"{label}: nobody who may use the panel was turned away")
        self.assertEqual(result["other_exceptions"], {}, f"{label}: no unexpected exception ({result.get('other_where')})")
        self.assertEqual(result["network_attempts"], 0, f"{label}: nothing reached for the network")
        self.assertEqual(result["registered_views"], 1, f"{label}: the posted panel is registered for restarts once")
        self.assertEqual(result["registered_ids"], sorted(f"gpanel:{k}" for k in KEYS),
                         f"{label}: the registered copy answers every button an old panel may have")
        self.assertGreater(result["clicks"], 400, f"{label}: the crawl really went deep")
        self.assertTrue(result["forms"], label)
        self.assertEqual(result["language"], lang, label)
        self.assertIn("CloseView", set(result["closed"]), label)
        return set(result["windows"])

    def test_every_window_and_click(self):
        for lang in LANGS:
            label = f"[{lang}]"
            result = run_clicks(lang)
            windows = self.check_common(result, label, lang)
            self.assertEqual(sorted(ALL_WINDOWS - windows), [], f"{label}: windows never reached")
            self.assertEqual(result["posted_ids"], [f"gpanel:{k}" for k in KEYS])
            self.assertEqual(result["modules"], ["cogs.live_game", "cogs.roblox_admin"])
            for key in KEYS:
                answer = result["old_buttons"][f"gpanel:{key}"]  # None: it opened a window or a form without a message
                self.assertFalse(str(answer or "").startswith("❌"), f"{label}: the button {key} of an old panel opens something, not an error: {answer}")
            # (the code draft, its "replace?" question and the remove-codes window close with their own Cancel instead)
            for kind in ("PlayerCardView", "CodesView", "EggsView", "EventsView", "StaffView", "GamePanelManager", "CloseView"):
                self.assertIn(kind, result["closed"], f"{label}: ✖️ Close pressed on {kind}")


if __name__ == "__main__":
    unittest.main()
