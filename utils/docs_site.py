"""The documentation page DOCS.html: one file in the bot folder, opened with a double-click, in English, Polish
and Spanish.

The texts are the same ones the bot shows on Discord: the chapters of /tutorial (locales/tutorial_*.json) and the
topics of /setup-guide (locales/guide_*.json). locales/docs_*.json adds the page's own labels, the texts of the quests
and the chapters only the page has (installing from zero, glossary, updates...). Fix a text there and the page follows:
the bot writes DOCS.html again at every start.
"""
import json
from pathlib import Path

from utils import config_store
from utils.version import VERSION

ROOT = Path(config_store.ROOT)
LOCALES = ROOT / "locales"
TEMPLATE = Path(__file__).with_name("docs_template.html")
OUTPUT = ROOT / "DOCS.html"
LANGUAGES = ("en", "pl", "es")
DATA_MARK = "__DOCS_DATA__"

# Quests: goal-based paths through the chapters. A step is "<tutorial|guide|docs>:<id>"; "optional" steps are shown
# but not needed for the badge; "needs" is the quest to finish first. Minutes are for a first-timer, not an expert,
# from a clean install from the zip (26.10.2026): the bot in 10–15 minutes, everything set up in about an hour.
# Texts (title, goal, badge) are in locales/docs_*.json under "quests".
QUESTS = [
    {"id": "from_zero", "emoji": "🐣", "color": "green", "minutes": 15,
     "steps": ["docs:prepare", "docs:discord_app", "docs:first_start", "docs:invite"],
     "help": ["docs:start_problems", "tutorial:permissions", "guide:bot_server", "docs:glossary"]},
    {"id": "server", "emoji": "🏠", "color": "blue", "minutes": 5, "needs": "from_zero",
     "steps": ["tutorial:language", "tutorial:channels"],
     "help": ["guide:troubleshooting"]},
    {"id": "codes", "emoji": "🎟️", "color": "yellow", "minutes": 40, "needs": "from_zero",
     "steps": ["tutorial:roblox", "tutorial:studio", "tutorial:names", "tutorial:codes", "tutorial:window",
               "tutorial:control_panel"],
     "optional": ["tutorial:window", "tutorial:control_panel"],
     "help": ["guide:codes_problems", "guide:names_look", "docs:codes_rules", "docs:rewards"]},
    {"id": "catalog", "emoji": "📒", "color": "orange", "minutes": 15, "needs": "codes",
     "steps": ["tutorial:names", "tutorial:catalog", "guide:catalog"],
     "optional": ["guide:catalog"],
     "help": ["guide:names_look", "guide:codes_problems", "docs:rewards"]},
    {"id": "update", "emoji": "🔄", "color": "teal", "minutes": 10, "needs": "from_zero",
     "steps": ["docs:updates", "guide:studio_update"],
     "optional": ["guide:studio_update"],  # only when the update changes the Studio file
     "help": ["guide:troubleshooting"]},
    {"id": "hosting", "emoji": "🌙", "color": "violet", "minutes": 20, "needs": "from_zero",
     "steps": ["tutorial:hosting", "guide:hosting", "guide:hosting_panel", "docs:vps"],
     "optional": ["guide:hosting_panel", "docs:vps"],
     "help": ["docs:hosting_more", "guide:hosting_vps", "guide:troubleshooting"]},
    {"id": "live", "emoji": "🥚", "color": "red", "minutes": 30, "needs": "codes",
     "steps": ["tutorial:eggs", "tutorial:events", "tutorial:gifts", "guide:game_live"],
     "optional": ["guide:game_live"],
     "help": ["docs:live_more", "guide:setup_roblox", "guide:catalog"]},
]
# The "Something doesn't work?" block on the start page (the first one is for a bot that doesn't start at all)
HELP = ["docs:start_problems", "guide:troubleshooting", "guide:codes_problems"]
# Chapters shown in a special way: "terms" = word and meaning side by side, "faq" = problem and fix as cards
LAYOUTS = {"docs:glossary": "terms", "docs:start_problems": "faq", "guide:troubleshooting": "faq",
           "guide:codes_problems": "faq"}


def _read(name: str):
    with open(LOCALES / name, "r", encoding="utf-8") as f:
        return json.load(f)


def _sections(kind: str, items: list) -> list:
    out = []
    for item in items:
        key = f"{kind}:{item['id']}"
        section = {"key": key, "emoji": item["emoji"], "title": item["title"], "menu": item.get("menu", ""),
                   "intro": item.get("intro", ""), "fields": [[field[0], field[1]] for field in item["fields"]]}
        if kind in ("tutorial", "guide"):
            section["n"] = len(out) + 1  # its number in /tutorial or /setup-guide
        if key in LAYOUTS:
            section["layout"] = LAYOUTS[key]
        out.append(section)
    return out


def language_data(lang: str) -> dict:
    docs = _read(f"docs_{lang}.json")
    groups = [
        {"id": "tutorial", "sections": _sections("tutorial", _read(f"tutorial_{lang}.json"))},
        {"id": "guide", "sections": _sections("guide", _read(f"guide_{lang}.json"))},
        {"id": "docs", "sections": _sections("docs", docs["sections"])},
    ]
    known = {section["key"] for group in groups for section in group["sections"]}
    quests = []
    for quest in QUESTS:
        missing = [key for key in quest["steps"] + quest.get("help", []) if key not in known]
        if missing:
            raise ValueError(f"quest {quest['id']} ({lang}): unknown chapters {missing}")
        optional = set(quest.get("optional", []))
        steps = [{"key": key, "optional": key in optional} for key in quest["steps"] if key in known]
        quests.append({"id": quest["id"], "emoji": quest["emoji"], "color": quest["color"], "minutes": quest.get("minutes", 0),
                       "needs": quest.get("needs", ""), **docs["quests"][quest["id"]], "steps": steps,
                       "help": [key for key in quest.get("help", []) if key in known]})
    return {"ui": docs["ui"], "quests": quests, "groups": groups, "help": [key for key in HELP if key in known]}


def build_data() -> dict:
    return {"version": VERSION, "languages": {lang: language_data(lang) for lang in LANGUAGES}}


def render() -> str:
    """The whole page as text."""
    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count(DATA_MARK) != 1:
        raise ValueError(f"{TEMPLATE.name} must contain {DATA_MARK} exactly once")
    # "<" escaped so no text can close the <script> tag that holds the data
    payload = json.dumps(build_data(), ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return template.replace(DATA_MARK, payload)


def write(path: Path = None) -> bool:
    """Writes the page (default: DOCS.html in the bot folder) if its content changed. Returns True when it was written."""
    content = render()
    path = Path(path or OUTPUT)
    try:
        if path.read_text(encoding="utf-8") == content:
            return False
    except (OSError, UnicodeDecodeError):
        pass
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)
    return True


def refresh() -> None:
    """Called at every bot start: a broken text file or a read-only folder must never stop the bot."""
    try:
        if write():
            print(f"📖 Documentation page updated: {OUTPUT.name} (open it with a double-click)")
    except Exception as e:  # noqa: BLE001 - the page is a convenience, the bot must start anyway
        print(f"⚠️ Could not write {OUTPUT.name}: {type(e).__name__}: {e}")


if __name__ == "__main__":
    print("written" if write() else "no changes", OUTPUT)
