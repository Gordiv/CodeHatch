"""D1, D2, W3, F15, A5 and minor fixes: safe files, config cache, colors, background loops that survive errors, one bot."""
import json
import os
import tempfile
import time
import unittest
from unittest import mock

from tests.helpers import TempBot
from utils import config_store, env_store, instance_lock


class DataFiles(unittest.TestCase):
    def test_broken_file_is_kept_not_lost(self):
        with TempBot():
            config_store.write_json("game_economy.json", {"currencies": ["Coins"]})
            self.assertEqual(config_store.read_json("game_economy.json", {}), {"currencies": ["Coins"]})
            path = config_store.data_path("game_economy.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{"currencies": ["Co')  # a write cut in the middle
            time.sleep(0.01)
            os.utime(path)
            with self.assertLogs("config", level="ERROR"):
                self.assertEqual(config_store.read_json("game_economy.json", {"x": 1}), {"x": 1})
            kept = [n for n in os.listdir(config_store.DATA_DIR) if n.startswith("game_economy.json.broken-")]
            self.assertEqual(len(kept), 1, "a copy of the damaged file is kept")

    def test_write_leaves_no_temporary_files(self):
        with TempBot():
            for i in range(5):
                config_store.write_json("state.json", {"i": i})
            self.assertEqual(sorted(os.listdir(config_store.DATA_DIR)), ["state.json"])

    def test_returned_values_are_copies(self):
        with TempBot():
            config_store.write_json("a.json", {"list": [1]})
            config_store.read_json("a.json", {})["list"].append(2)
            self.assertEqual(config_store.read_json("a.json", {}), {"list": [1]})
            config_store.load()["roblox"]["universe_id"] = 99
            self.assertEqual(config_store.get("roblox")["universe_id"], 0)


class Config(unittest.TestCase):
    def test_defaults_and_null_sections(self):
        with TempBot({"guild_overrides": {"5": {"moderation": None, "ai_support": {"developer_bug_channel_id": 7}}},
                      "moderation": None, "bot_settings": {"embed_color": None}}):
            cfg = config_store.load()
            self.assertEqual(cfg["roblox"]["universe_id"], 0, "a section missing in config.json comes from the defaults")
            self.assertEqual(cfg["ai_support"]["developer_bug_channel_id"], 0, "a setting missing in config.json comes from the defaults")
            self.assertEqual(config_store.get("moderation"), {}, "a section written as null counts as empty")
            self.assertEqual(config_store.for_guild(cfg, 5, "moderation"), {})
            self.assertEqual(config_store.for_guild(cfg, 5, "ai_support")["developer_bug_channel_id"], 7)
            self.assertEqual(config_store.for_guild(cfg, 6, "ai_support")["developer_bug_channel_id"], 0)
            self.assertEqual(config_store.for_guild({"moderation": None}, 5, "moderation"), {})

    def test_edit_by_hand_is_seen_and_broken_edit_keeps_old_values(self):
        with TempBot():
            self.assertEqual(config_store.get("bot_settings")["language"], "en")
            cfg = json.load(open(config_store.CONFIG_PATH, encoding="utf-8"))
            cfg["bot_settings"]["language"] = "pl"
            with open(config_store.CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f)
            config_store._config["checked"] = 0  # don't wait the 1 s check interval
            self.assertEqual(config_store.get("bot_settings")["language"], "pl")
            with open(config_store.CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write("{ broken")
            config_store._config["checked"] = 0
            with self.assertLogs("config", level="ERROR"):
                self.assertEqual(config_store.get("bot_settings")["language"], "pl")
            self.assertTrue(config_store.last_error())

    def test_broken_config_at_start(self):
        with TempBot():
            with open(config_store.CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write("{ broken")
            config_store.reset_cache()
            with self.assertRaises(config_store.ConfigError):
                config_store.load()

    def test_embed_color(self):
        for value, expected in (("0x00A2FF", 0x00A2FF), ("#ff0000", 0xFF0000), ("00ff00", 0x00FF00), (255, 255),
                                ("nonsense", config_store.DEFAULT_COLOR), (None, config_store.DEFAULT_COLOR),
                                (-5, config_store.DEFAULT_COLOR), (True, config_store.DEFAULT_COLOR)):
            self.assertEqual(config_store.parse_color(value), expected, value)
        with TempBot({"bot_settings": {"embed_color": "#123456"}}):
            self.assertEqual(config_store.embed_color(), 0x123456)


class EnvFile(unittest.TestCase):
    def test_duplicates_export_and_placeholders(self):
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, ".env")
        with open(path, "w", encoding="utf-8") as f:
            f.write("A=1\nexport ROBLOX_API_KEY=old\nB=2\nROBLOX_API_KEY=older\n")
        with mock.patch.object(env_store, "ENV_PATH", path), mock.patch.dict(os.environ, {}, clear=False):
            env_store.set_env("ROBLOX_API_KEY", "new")
            with open(path, encoding="utf-8") as f:
                text = f.read()
            self.assertEqual(text.count("ROBLOX_API_KEY"), 1)
            self.assertIn("ROBLOX_API_KEY=new", text)
            self.assertIn("A=1", text)
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "your_gemini_api_key_here"}):
            self.assertEqual(env_store.secret("GEMINI_API_KEY"), "", "the example from .env.example is not a key")


class OneBot(unittest.TestCase):
    def test_second_copy_is_refused(self):
        path = os.path.join(tempfile.mkdtemp(), "bot.lock")
        first = instance_lock.InstanceLock(path)
        self.assertTrue(first.acquire())
        self.assertTrue(instance_lock.is_running(path))
        self.assertFalse(instance_lock.InstanceLock(path).acquire())
        first.release()
        self.assertFalse(instance_lock.is_running(path))


class BackgroundLoops(unittest.IsolatedAsyncioTestCase):
    """A loop must keep running after any error (tasks.loop stops for good on errors other than network ones)."""

    async def test_loops_survive_errors(self):
        from cogs import cloud_sync as cloud_cog, game_codes, live_game
        from utils import cloud_sync, database

        boom = mock.AsyncMock(side_effect=RuntimeError("database is locked"))
        cases = [
            (cloud_cog.CloudSync, "sync_loop", [mock.patch.object(cloud_sync, "status", lambda: "ready"),
                                                mock.patch.object(cloud_sync, "push_codes", boom)]),
            (live_game.LiveGame, "sync_loop", [mock.patch.object(cloud_sync, "status", lambda: "ready"),
                                               mock.patch.object(live_game, "push_live", boom)]),
            (game_codes.GameCodes, "clean_expired_codes", [mock.patch.object(database, "expire_old_codes", boom)]),
        ]
        with TempBot():
            for cog_class, loop_name, patches in cases:
                with mock.patch("discord.ext.tasks.Loop.start", lambda *a, **k: None):
                    cog = cog_class(mock.MagicMock())
                for patch in patches:
                    patch.start()
                try:
                    await getattr(cog, loop_name).coro(cog)  # must not raise
                finally:
                    for patch in patches:
                        patch.stop()


if __name__ == "__main__":
    unittest.main()
