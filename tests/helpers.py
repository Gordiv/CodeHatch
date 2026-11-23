"""Shared test helpers: a temporary bot folder, so tests never touch the real config.json, data/ or bot.db."""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from utils import config_store, database  # noqa: E402


class TempBot:
    """Points config.json, data/ and bot.db at a temporary folder (and back on exit)."""

    def __init__(self, config: dict = None):
        self.config = config

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="botdc-test-")
        self.saved = (config_store.CONFIG_PATH, config_store.DATA_DIR, database.DB_PATH)
        config_store.CONFIG_PATH = os.path.join(self.dir, "config.json")
        config_store.DATA_DIR = os.path.join(self.dir, "data")
        database.DB_PATH = os.path.join(self.dir, "data", "bot.db")
        with open(os.path.join(ROOT, "config.defaults.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        if self.config:
            for section, values in self.config.items():
                if isinstance(values, dict):
                    cfg.setdefault(section, {}).update(values)
                else:
                    cfg[section] = values
        with open(config_store.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        config_store.reset_cache()
        return self

    def __exit__(self, *exc):
        config_store.CONFIG_PATH, config_store.DATA_DIR, database.DB_PATH = self.saved
        config_store.reset_cache()
        shutil.rmtree(self.dir, ignore_errors=True)
        return False
