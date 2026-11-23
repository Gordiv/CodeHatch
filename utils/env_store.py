import os
import re
import stat

from utils import config_store

ENV_PATH = os.path.join(config_store.ROOT, ".env")
_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
# Example values from .env.example: they mean "not filled in yet", never a working key
PLACEHOLDERS = {"your_bot_token_here", "twoj_token_bota_tutaj", "your_gemini_api_key_here", "twoj_klucz_gemini_tutaj",
                "your_roblox_api_key_here", "paste_here", ""}


def is_placeholder(value) -> bool:
    text = str(value or "").strip()
    return text.lower() in PLACEHOLDERS or (text.startswith("<") and text.endswith(">"))


def broken_lines(path: str = ENV_PATH) -> list[tuple[int, str]]:
    """Lines of .env without "=" (e.g. a pasted address that replaced "URL=" in REPORT_WEBHOOK_URL=): dotenv skips
    them silently. Returns (line number, start of the line up to the first character that can't be in a name),
    never the value, so the warning shows no secret."""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    broken = []
    for number, line in enumerate(lines, start=1):
        text = line.strip()
        if text and not text.startswith("#") and "=" not in text:
            broken.append((number, re.match(r"[A-Za-z0-9_]{0,30}", text).group() or "?"))
    return broken


def secret(name: str) -> str:
    """A key from the environment (.env), or "" when it is missing or still the example value from .env.example."""
    value = (os.getenv(name) or "").strip()
    return "" if is_placeholder(value) else value


def set_env(name: str, value: str) -> None:
    """Writes NAME=value to .env (keeping the rest of the file) and sets the variable in this process.
    A name written several times (or as "export NAME=...") is replaced everywhere, so the file never has two values."""
    if not _NAME.match(name):
        raise ValueError("Invalid variable name.")
    if re.search(r"[\r\n]", value):
        raise ValueError("Value must not contain line breaks.")

    lines = []
    mode = None
    if os.path.exists(ENV_PATH):
        mode = stat.S_IMODE(os.stat(ENV_PATH).st_mode)
        with open(ENV_PATH, "r", encoding="utf-8-sig") as f:
            lines = f.read().splitlines()

    entry = f"{name}={value}"
    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(name)}\s*=")
    result, replaced = [], False
    for line in lines:
        if pattern.match(line):
            if not replaced:
                result.append(entry)
                replaced = True
            continue
        result.append(line)
    if not replaced:
        result.append(entry)

    tmp = ENV_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(result) + "\n")
    # Keep who may read the file (on Linux .env is often readable only by its owner); a new file gets that by default
    try:
        os.chmod(tmp, mode if mode is not None else 0o600)
    except OSError:
        pass
    config_store._replace(tmp, ENV_PATH)
    os.environ[name] = value
