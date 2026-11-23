"""Texts: the same keys and {placeholders} in 3 languages, every key the code uses exists, Discord's limits."""
import glob
import json
import os
import re
import unittest

from tests.helpers import ROOT

LANGS = ("en", "pl", "es")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
KEY = re.compile(r"""["']([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)["']""")
DYNAMIC = re.compile(r"""f["']([a-z][a-z0-9_.]*?)\{""")


def load(name):
    with open(os.path.join(ROOT, "locales", name), encoding="utf-8") as f:
        return json.load(f)


class Texts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texts = {lang: load(f"{lang}.json") for lang in LANGS}

    def test_same_keys_and_placeholders(self):
        en = self.texts["en"]
        for lang in ("pl", "es"):
            self.assertEqual(set(self.texts[lang]), set(en), f"{lang}.json has other keys than en.json")
            for key, text in self.texts[lang].items():
                self.assertEqual(set(PLACEHOLDER.findall(text)), set(PLACEHOLDER.findall(en[key])), f"{lang}: {key}")

    def test_every_key_used_in_code_exists(self):
        prefixes = {k.split(".")[0] for k in self.texts["en"]}
        missing = set()
        for path in glob.glob(os.path.join(ROOT, "cogs", "*.py")) + glob.glob(os.path.join(ROOT, "utils", "*.py")) \
                + [os.path.join(ROOT, "main.py")]:
            with open(path, encoding="utf-8") as f:
                source = f.read()
            for key in KEY.findall(source):
                if key.split(".")[0] in prefixes and key not in self.texts["en"] and not key.endswith((".json", ".com")):
                    missing.add(f"{os.path.basename(path)}: {key}")
        self.assertEqual(missing, set())

    def test_no_unused_keys(self):
        literal, prefixes = set(), set()
        for path in glob.glob(os.path.join(ROOT, "cogs", "*.py")) + glob.glob(os.path.join(ROOT, "utils", "*.py")) \
                + glob.glob(os.path.join(ROOT, "tools", "*.py")) + [os.path.join(ROOT, "main.py")]:
            with open(path, encoding="utf-8") as f:
                source = f.read()
            literal |= set(KEY.findall(source))
            prefixes |= set(DYNAMIC.findall(source))
        unused = [k for k in self.texts["en"] if k not in literal and not any(p and k.startswith(p) for p in prefixes)]
        self.assertEqual(unused, [])

    def test_slash_command_texts_fit(self):
        for lang, texts in self.texts.items():
            for key, text in texts.items():
                if key.startswith("cmd.") or key.startswith("duration.choice.") or key.startswith("eggs.color."):
                    self.assertLessEqual(len(text), 100, f"{lang}: {key}")

    def test_buttons_fit(self):
        for lang, texts in self.texts.items():
            for key, text in texts.items():
                if ".btn" in key or key.startswith("tut.act_"):
                    self.assertLessEqual(len(text), 80, f"{lang}: {key}")
                labels = {"servers.add_label"} | {f"setup.kb_{k}" for k in ("name", "desc", "updates", "support", "faq")} \
                    | {f"setup.eco_{k}" for k in ("currencies", "stats", "items", "pets")}
                if key.startswith("protect.f_") or key in labels:
                    self.assertLessEqual(len(text), 45, f"{lang}: {key} is a form label")

    def test_menu_placeholders_fit_one_line(self):
        # a select menu shows its placeholder on one line: a longer one is cut off and can't be read
        menus = re.compile(r"^(alerts[.](channel|role)_placeholder|codes[.]remove_placeholder|levels[.][a-z_]+_placeholder|"
                           r"protect[.][a-z_]+_placeholder|roles[.]allowed_placeholder|setup[.]ph_[a-z_]+|setup[.]gp_hide_ph|"
                           r"guide[.]placeholder|rbx[.]names_pick_[a-z]+|tickets[.]select_placeholder|tut[.]placeholder|"
                           r"servers[.]remove_ph)$")
        too_long = [f"{lang}:{key}" for lang, texts in self.texts.items() for key, text in texts.items()
                    if menus.match(key) and len(text) > 34]
        self.assertEqual(too_long, [])

    def test_no_license_like_examples(self):
        # no text may hold something that looks like a license number
        pattern = re.compile(r"BDC-[A-Z0-9]{4}-[A-Z0-9]{4}")
        for path in glob.glob(os.path.join(ROOT, "locales", "*.json")):
            with open(path, encoding="utf-8") as f:
                self.assertIsNone(pattern.search(f.read()), path)


class Guides(unittest.TestCase):
    def test_guide_and_tutorial_match_in_every_language(self):
        for kind in ("guide", "tutorial"):
            files = {lang: load(f"{kind}_{lang}.json") for lang in LANGS}
            shape = [(item["id"], len(item["fields"])) for item in files["en"]]
            for lang in ("pl", "es"):
                self.assertEqual([(item["id"], len(item["fields"])) for item in files[lang]],
                                 shape, f"{kind}_{lang}.json")
            for lang, items in files.items():
                for item in items:
                    size = len(item["title"]) + len(item["intro"]) + sum(len(f[0]) + len(f[1]) for f in item["fields"])
                    self.assertLessEqual(size, 4500, f"{kind}_{lang}: {item['id']} (an embed holds 6000 characters)")
                    for field in item["fields"]:
                        self.assertLessEqual(len(field[1]), 1024, f"{kind}_{lang}: {item['id']} / {field[0]}")

    def test_docs_match_in_every_language(self):
        files = {lang: load(f"docs_{lang}.json") for lang in LANGS}
        shape = [(s["id"], len(s["fields"])) for s in files["en"]["sections"]]
        for lang in ("pl", "es"):
            self.assertEqual([(s["id"], len(s["fields"])) for s in files[lang]["sections"]], shape)
            self.assertEqual(set(files[lang]["ui"]), set(files["en"]["ui"]))
            self.assertEqual(set(files[lang]["quests"]), set(files["en"]["quests"]))

    def test_tutorial_actions_and_checks_exist(self):
        from cogs import tutorial
        for chapter in load("tutorial_en.json"):
            for action in chapter.get("actions", []):
                self.assertIn(action, tutorial.ACTIONS, chapter["id"])


if __name__ == "__main__":
    unittest.main()
