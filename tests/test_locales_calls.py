"""Texts and the code that uses them, checked by reading the source (no Discord, no network):
- every t("key", ...) call passes all {placeholders} of that text (a missing one shows English or raw braces),
- labels, titles and placeholders of forms and buttons fit Discord's limits in all three languages,
- the guide and the tutorial name buttons exactly as the buttons are called."""
import ast
import glob
import json
import os
import re
import unittest

from tests.helpers import ROOT

LANGS = ("en", "pl", "es")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
SOURCES = sorted(glob.glob(os.path.join(ROOT, "cogs", "*.py")) + glob.glob(os.path.join(ROOT, "utils", "*.py"))
                 + [os.path.join(ROOT, "main.py")])
# (call, keyword) -> Discord's limit
LIMITS = {("TextInput", "label"): 45, ("Label", "text"): 45, ("TextInput", "placeholder"): 100, ("Select", "placeholder"): 150,
          ("Button", "label"): 80, ("SelectOption", "label"): 100, ("SelectOption", "description"): 100,
          ("Label", "description"): 100, ("__init__", "title"): 45}


def texts(lang):
    with open(os.path.join(ROOT, "locales", f"{lang}.json"), encoding="utf-8") as f:
        return json.load(f)


def trees():
    for path in SOURCES:
        with open(path, encoding="utf-8") as f:
            yield os.path.basename(path), ast.parse(f.read())


def call_name(node):
    func = node.func
    return func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None


def text_key(node):
    """(key, cut): the key of t("key", ...) and the length it is cut to with [:n] (None when not cut)."""
    cut = None
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
        cut = node.slice.upper.value if isinstance(node.slice.upper, ast.Constant) else None
        node = node.value
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "t" and node.args \
            and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        return node.args[0].value, cut
    return None, None


class TextCalls(unittest.TestCase):
    def test_every_call_passes_the_placeholders_of_its_text(self):
        en = texts("en")
        problems = []
        for name, tree in trees():
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or call_name(node) not in ("t", "_t") or not node.args:
                    continue
                key = node.args[0]
                if not (isinstance(key, ast.Constant) and key.value in en) or any(k.arg is None for k in node.keywords):
                    continue
                given = {k.arg for k in node.keywords} - {"lang"}
                missing = set(PLACEHOLDER.findall(en[key.value])) - given
                if missing:
                    problems.append(f"{name}:{node.lineno} {key.value} lacks {sorted(missing)}")
        self.assertEqual(problems, [])

    def test_labels_titles_and_placeholders_fit_in_every_language(self):
        all_texts = {lang: texts(lang) for lang in LANGS}
        problems = []
        for name, tree in trees():
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                for keyword in node.keywords:
                    limit = LIMITS.get((call_name(node), keyword.arg))
                    key, cut = text_key(keyword.value)
                    if limit is None or key is None or (cut is not None and cut <= limit):
                        continue
                    for lang in LANGS:
                        if len(all_texts[lang].get(key, "")) > limit:
                            problems.append(f"{name}:{node.lineno} {key} [{lang}] is {len(all_texts[lang][key])} > {limit}")
        self.assertEqual(problems, [])

    def test_removed_keys_are_gone_everywhere(self):
        for key in ("codes.btn_remove_this", "codes.panel_footer"):
            for lang in LANGS:
                self.assertNotIn(key, texts(lang))
        for name, tree in trees():
            used = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
            self.assertFalse(used & {"codes.btn_remove_this", "codes.panel_footer"}, name)

    def test_guides_name_the_buttons_like_the_buttons_are_called(self):
        for lang in LANGS:
            t = texts(lang)
            with open(os.path.join(ROOT, "locales", f"tutorial_{lang}.json"), encoding="utf-8") as f:
                tutorial = {c["id"]: " ".join(f[1] for f in c["fields"]) for c in json.load(f)}
            with open(os.path.join(ROOT, "locales", f"guide_{lang}.json"), encoding="utf-8") as f:
                guide = {c["id"]: " ".join(f[1] for f in c["fields"]) for c in json.load(f)}
            save = f"✅ {t['codes.btn_save']}"
            self.assertIn(save, tutorial["codes"], lang)
            for key in ("codes.draft_description", "codes.draft_replaces", "codes.draft_footer"):
                self.assertIn(save, t[key], f"{lang}: {key} names the Save button")
            self.assertTrue(any(save in text for text in guide.values()), f"{lang}: the guide names ✅ {t['codes.btn_save']}")
            for key in ("rban.btn_confirm", "card.btn_unban", "rbx.btn_gift"):
                self.assertIn(f"**{t[key]}**", tutorial["gifts"], f"{lang}: tutorial 'gifts' chapter names {key}")
            self.assertIn(f"**👤 {t['rbx.btn_player']}**", tutorial["gifts"], lang)
            self.assertIn(f"⚙️ {t['codes.btn_extras']}", " ".join(guide.values()), f"{lang}: the guide names the ⚙️ button")

    def test_the_card_texts_exist_in_all_languages_with_a_name_placeholder(self):
        for lang in LANGS:
            t = texts(lang)
            for key in ("card.by_name", "card.by_id", "card.btn_unban_yes"):
                self.assertIn("{username}", t[key], f"{lang}: {key}")
            self.assertIn("{user_id}", t["card.by_id"])
            self.assertIn("{player}", t["card.ambiguous"])
            self.assertIn("{player}", t["give.ambiguous"])
            self.assertIn("{code}", t["codes.draft_title"])

    def test_documentation_page_matches_the_new_flow(self):
        """DOCS.html is built at the bot's start from these texts; the file lying in the folder may be older."""
        from utils import docs_site
        html = docs_site.render()
        for lang in LANGS:
            t = texts(lang)
            self.assertIn(t["codes.btn_save"], html, lang)
            for stale in ("under the finished code", "Remove this code", "Usuń ten kod", "pod gotowym kodem",
                          "Quitar este código", "bajo el código terminado"):
                self.assertNotIn(stale, html)
            self.assertIn(t["rbx.btn_player"], html, f"{lang}: the page describes the player card")


if __name__ == "__main__":
    unittest.main()
