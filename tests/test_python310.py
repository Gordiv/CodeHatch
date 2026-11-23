"""The bot is supported on Python 3.10+ (start.bat / start.sh), but it is developed and tested on a newer Python.
This reads the production sources and refuses what only newer versions understand: f-strings that reuse their own
quote inside {...} or break a line there (Python 3.12+), and library calls added in 3.11 / 3.12."""
import ast
import glob
import io
import os
import re
import token
import tokenize
import unittest

from tests.helpers import ROOT

SOURCES = sorted(glob.glob(os.path.join(ROOT, "cogs", "*.py")) + glob.glob(os.path.join(ROOT, "utils", "*.py"))
                 + [os.path.join(ROOT, "main.py")])
# API that does not exist in Python 3.10 (pattern, since which version)
NEWER_API = {r"\btomllib\b": "3.11", r"\basyncio\.timeout\(": "3.11", r"\bTaskGroup\b": "3.11", r"\bdatetime\.UTC\b": "3.11",
             r"from datetime import [^\n]*\bUTC\b": "3.11", r"\bStrEnum\b": "3.11", r"\bExceptionGroup\b": "3.11",
             r"\bexcept\s*\*": "3.11", r"typing import [^\n]*\b(Self|override|LiteralString)\b": "3.11/3.12",
             r"\bitertools\.batched\b": "3.12", r"\basyncio\.Runner\b": "3.11", r"^\s*type \w+(\[.*\])? =": "3.12",
             r"\bPath\([^)]*\)\.walk\(": "3.12", r"\bmath\.cbrt\b": "3.11"}
# datetime.fromisoformat() does not read "Z" or every fraction before 3.11: only where a failure is caught
ISOFORMAT_OK = set()


def relative(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def fstring_problems(source: str, name: str) -> list:
    problems = []
    stack = []
    for tk in tokenize.generate_tokens(io.StringIO(source).readline):
        if tk.type == token.FSTRING_START:
            quote = tk.string.lstrip("fFrRbBuU")
            if stack and stack[-1]["expression"] and quote == stack[-1]["quote"]:
                problems.append(f"{name}:{tk.start[0]} an f-string inside an f-string with the same quotes")
            stack.append({"quote": quote, "depth": 0, "expression": False})
        elif tk.type == token.FSTRING_END:
            stack.pop()
        elif stack:
            top = stack[-1]
            if tk.type == token.OP and tk.string == "{":
                top["depth"] += 1
                top["expression"] = True
            elif tk.type == token.OP and tk.string == "}":
                top["depth"] -= 1
                top["expression"] = top["depth"] > 0
            elif top["expression"]:
                if tk.type == token.STRING and tk.string.lstrip("fFrRbBuU")[:len(top["quote"])] == top["quote"]:
                    problems.append(f"{name}:{tk.start[0]} the quote of the f-string is used inside {{...}}")
                if tk.type in (token.NL, token.NEWLINE) and len(top["quote"]) == 1:
                    problems.append(f"{name}:{tk.start[0]} a line break inside {{...}} of a one-line f-string")
                if tk.type == token.COMMENT:
                    problems.append(f"{name}:{tk.start[0]} a comment inside {{...}} of an f-string")
    return problems


class OlderPython(unittest.TestCase):
    @unittest.skipUnless(hasattr(token, "FSTRING_START"), "on Python before 3.12 the file would not even import")
    def test_f_strings_read_by_python_3_10(self):
        problems = []
        for path in SOURCES:
            with open(path, encoding="utf-8") as f:
                problems += fstring_problems(f.read(), relative(path))
        self.assertEqual(problems, [])

    @unittest.skipUnless(hasattr(token, "FSTRING_START"), "needs the tokenizer of Python 3.12+")
    def test_the_f_string_check_really_finds_newer_syntax(self):
        bad = ['x = f"{d["a"]}"\n', "x = f'{d['a']}'\n", 'x = f"{f"{y}"}"\n', 'x = f"{\n y}"\n', 'x = f"{y # c\n}"\n']
        for source in bad:
            self.assertTrue(fstring_problems(source, "sample"), source)
        good = ["x = f\"{d['a']}\"\n", 'x = f"""{d["a"]}"""\n', 'x = f"{y!r:>{w}}"\n', 'x = f"{{literal}} {y}"\n']
        for source in good:
            self.assertEqual(fstring_problems(source, "sample"), [], source)

    def test_no_library_calls_newer_than_python_3_10(self):
        problems = []
        for path in SOURCES:
            with open(path, encoding="utf-8") as f:
                for number, line in enumerate(f, 1):
                    code = line.split("#", 1)[0]
                    for pattern, version in NEWER_API.items():
                        if re.search(pattern, code):
                            problems.append(f"{relative(path)}:{number} needs Python {version}: {line.strip()[:80]}")
                    if "fromisoformat(" in code and relative(path) not in ISOFORMAT_OK:
                        problems.append(f"{relative(path)}:{number} datetime.fromisoformat() fails on Roblox times before 3.11")
        self.assertEqual(problems, [])

    def test_syntax_of_python_3_10(self):
        for path in SOURCES:
            with open(path, encoding="utf-8") as f:
                try:
                    ast.parse(f.read(), filename=path, feature_version=(3, 10))
                except SyntaxError as e:
                    self.fail(f"{relative(path)}:{e.lineno}: {e.msg}")


if __name__ == "__main__":
    unittest.main()
