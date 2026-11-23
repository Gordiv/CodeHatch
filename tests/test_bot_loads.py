"""The bot loads: every module, every command. It runs in a TEMPORARY COPY of the project in a subprocess, so the real
config.json, data/ and bot.db are never touched and nothing connects to Discord."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.helpers import ROOT

COPIED = ("cogs", "utils", "locales", "scripts", "main.py", "config.defaults.json")
# The commands of the game: eggs, events, gifts, bans, the leaderboard
GAME_COMMANDS = ("egg-create", "egg-edit", "egg-remove", "eggs", "event-start", "event-stop", "events")
ADMIN_COMMANDS = ("give", "announce-game", "roblox-ban", "roblox-unban", "roblox-ban-check", "leaderboard",
                  "leaderboard-setup")


def copy_project() -> str:
    target = tempfile.mkdtemp(prefix="botdc-load-")
    for name in COPIED:
        source = os.path.join(ROOT, name)
        if os.path.isdir(source):
            shutil.copytree(source, os.path.join(target, name), ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(source, os.path.join(target, name))
    shutil.copy2(os.path.join(ROOT, "config.defaults.json"), os.path.join(target, "config.json"))
    shutil.copy2(os.path.join(ROOT, "tests", "load_driver.py"), os.path.join(target, "load_driver.py"))
    os.makedirs(os.path.join(target, "tests"))
    for name in ("__init__.py", "fakes.py"):
        shutil.copy2(os.path.join(ROOT, "tests", name), os.path.join(target, "tests", name))
    return target


def run_driver() -> dict:
    target = copy_project()
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=target)
        env.pop("BOT_LAUNCHER", None)
        done = subprocess.run([sys.executable, "load_driver.py"], cwd=target, env=env,
                              capture_output=True, text=True, encoding="utf-8", timeout=180)
        lines = [line for line in done.stdout.splitlines() if line.startswith("RESULT ")]
        if not lines:
            raise AssertionError(f"the driver printed no result (exit {done.returncode}):\n{done.stdout[-1500:]}\n{done.stderr[-1500:]}")
        return json.loads(lines[-1][len("RESULT "):])
    finally:
        shutil.rmtree(target, ignore_errors=True)


class BotLoads(unittest.TestCase):
    def test_the_bot_loads_every_module(self):
        result = run_driver()
        self.assertEqual(result["failed"], [], "no module may fail to load")
        self.assertEqual(result["problems"], [])
        for module in ("cogs.live_game", "cogs.roblox_admin", "cogs.game_codes", "cogs.setup_roblox", "cogs.tutorial", "cogs.help"):
            self.assertIn(module, result["extensions"])
        for command in ("help", "code-add", "setup-roblox") + GAME_COMMANDS + ADMIN_COMMANDS:
            self.assertIn(command, result["commands"])
        for removed in ("verify", "whois", "ticket", "giveaway", "rank", "ban", "kick", "clear", "game", "ask"):
            self.assertNotIn(removed, result["commands"], "a command of a removed Discord-only feature came back")
        self.assertLessEqual(len(result["commands"]), 100)
        self.assertLessEqual(result["panel_rows"], 5)
        self.assertEqual(result["click_errors"], [], "every button of /setup-roblox opens without a missing name or module")
        self.assertTrue(result["draft_shown"] and result["code_saved"] and result["command_saved"])
        self.assertEqual(result["network_attempts"], 0, "no click reaches for the network without an API key")


if __name__ == "__main__":
    unittest.main()
