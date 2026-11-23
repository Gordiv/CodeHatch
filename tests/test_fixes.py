"""Unit tests of single fixes from the audit (B1, B2, B10, F9, F13, K3, L1, L4, L5, A2, A4, E3 and minor items)."""
import glob
import json
import os
import tempfile
import unittest
from unittest import mock

import discord

from tests.helpers import ROOT, TempBot


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class Eggs(unittest.TestCase):
    def test_pet_list_needs_a_separator_and_sane_numbers(self):
        from cogs import live_game
        with TempBot():
            pets = live_game.parse_pets("Cat:60, Robot 2000: 40")
            self.assertEqual([p["name"] for p in pets], ["Cat", "Robot 2000"])
            for bad in ("Dragon2", "Cat:" + "9" * 400, "Cat:0"):
                with self.assertRaises(live_game.RuleError, msg=bad):
                    live_game.parse_pets(bad)

    def test_events_multiply_up_to_100(self):
        from cogs import live_game
        rows = [{"multipliers": json.dumps({"exp": 10})}, {"multipliers": json.dumps({"exp": 20, "luck": 2})}]
        self.assertEqual(live_game.combined_multipliers(rows), {"exp": 100, "luck": 2})


class Catalog(unittest.TestCase):
    def test_untouched_template_blocks_nothing(self):
        from utils import catalog
        cat = {"currencies": ["Coins", "Gems"], "items": ["VIP Pass", "Speed Coil"], "pets": [], "eggs": [],
               "multipliers": [], "problems": [], "missing": False}
        self.assertTrue(catalog.is_template(cat))
        cat["template"] = True
        self.assertEqual(catalog.names(cat, "currencies"), [])
        with TempBot():
            self.assertEqual(catalog.resolve("currencies", "Diamonds", cat), ("Diamonds", ""))
        real = dict(cat, currencies=["Coins", "Diamonds"], template=False)
        self.assertFalse(catalog.is_template(real))

    def test_ai_prompt_cuts_names_not_instructions(self):
        from utils import catalog
        scan = {"values": [(f"leaderstats.Value{i:03d}", "IntValue") for i in range(200)], "attributes": []}
        with TempBot():
            text = catalog.ai_prompt(scan, max_length=1200)
        self.assertLessEqual(len(text), 1200)
        self.assertIn("return Catalog", text)
        self.assertIn("{", text, "Luau braces stay as written")


class Translations(unittest.IsolatedAsyncioTestCase):
    async def test_broken_placeholder_falls_back_to_english(self):
        from utils import i18n
        with TempBot(), mock.patch.dict(i18n._texts, {"pl": {"x.y": "Ala {wrong}"}, "en": {"x.y": "Hi {name}"}}):
            self.assertEqual(i18n.t("x.y", lang="pl", name="Bob"), "Hi Bob")

    async def test_translator_skips_too_long_texts(self):
        from discord import app_commands
        from utils import i18n
        translator = i18n.Translator()
        context = app_commands.TranslationContext(app_commands.TranslationContextLocation.command_description, None)
        with mock.patch.dict(i18n._texts, {"pl": {"cmd.x": "y" * 120}}):
            self.assertIsNone(await translator.translate(app_commands.locale_str("x", key="cmd.x"), discord.Locale.polish, context))


class ErrorReports(unittest.TestCase):
    def test_no_webhook_address_in_shipped_code(self):
        from utils import error_reports
        for folder in ("cogs", "utils", "scripts", "locales"):
            for path in glob.glob(os.path.join(ROOT, folder, "**", "*.*"), recursive=True):
                if path.endswith((".py", ".json", ".luau", ".html", ".rbxmx")):
                    with open(path, encoding="utf-8", errors="ignore") as f:
                        self.assertIsNone(error_reports.WEBHOOK_PATTERN.search(f.read()), path)

    def test_sanitize_hides_a_webhook(self):
        from utils import error_reports
        hook = "https://discord.com/api/webhooks/123/abcDEF_-x"  # secret-scan:allow
        self.assertNotIn("abcDEF", error_reports.sanitize(f"error at {hook}"))


class Updates(unittest.TestCase):
    def test_every_module_is_on_the_list_the_bot_loads(self):
        """Only the listed modules start (an old file left by an update must not), so a new cog must be listed."""
        import ast
        with open(os.path.join(ROOT, "main.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        listed = next(ast.literal_eval(node.value) for node in tree.body
                      if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "COGS")
        files = sorted(name[:-3] for name in os.listdir(os.path.join(ROOT, "cogs")) if name.endswith(".py"))
        self.assertEqual(sorted(listed), files)

    def test_the_changelog_has_this_version(self):
        from utils.version import VERSION
        with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
            self.assertIn(f"## {VERSION}", f.read(), "every release gets its CHANGELOG.md entry")


class FirstStart(unittest.TestCase):
    def test_a_missing_config_is_made_from_the_defaults(self):
        """The zip carries no config.json (an update never overwrites the owner's settings): the first start makes it."""
        from utils import config_store
        with tempfile.TemporaryDirectory() as folder:
            defaults = os.path.join(folder, "config.defaults.json")
            with open(defaults, "w", encoding="utf-8") as f:
                json.dump({"bot_settings": {"language": "en"}}, f)
            target = os.path.join(folder, "config.json")
            with mock.patch.object(config_store, "CONFIG_PATH", target), \
                    mock.patch.object(config_store, "DEFAULTS_PATH", defaults):
                data = config_store._read_config()
                self.assertEqual(data["bot_settings"]["language"], "en")
                self.assertTrue(os.path.exists(target))
                with open(target, "w", encoding="utf-8") as f:
                    json.dump({"bot_settings": {"language": "pl"}}, f)
                self.assertEqual(config_store._read_config()["bot_settings"]["language"], "pl", "an existing file is kept")


class EnvFile(unittest.TestCase):
    def test_line_without_equals_is_reported_without_the_secret(self):
        from utils import env_store
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, ".env")
            with open(path, "w", encoding="utf-8", newline="\r\n") as f:
                f.write("DISCORD_TOKEN=abc\n# comment\n\nREPORT_WEBHOOK_https://discord.com/api/webhooks/1/SECRETPART\n"  # secret-scan:allow
                        "export X=1\n")
            self.assertEqual(env_store.broken_lines(path), [(4, "REPORT_WEBHOOK_https")])
            self.assertEqual(env_store.broken_lines(os.path.join(tmp, "missing")), [])


if __name__ == "__main__":
    unittest.main()
