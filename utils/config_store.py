"""config.json and the files in data/: one copy in memory, safe writes.

The configuration is read from disk only when the file changed (checked at most once a second), so the code that runs
for every message never touches the disk. load() returns a copy that the caller may change and pass to save().
Writes go through a temporary file and a rename, so a power cut or a crash can never leave half a file behind.
"""
import copy
import json
import logging
import os
import shutil
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.json")
DEFAULTS_PATH = os.path.join(ROOT, "config.defaults.json")
DATA_DIR = os.path.join(ROOT, "data")
DEFAULT_COLOR = 0x00A2FF
CHECK_INTERVAL = 1.0  # seconds between checks whether config.json was changed by hand

log = logging.getLogger("config")
_lock = threading.RLock()
_config = {"path": None, "stamp": None, "checked": 0.0, "data": None, "error": ""}
_files = {}  # data file name -> (stamp, parsed value)


class ConfigError(Exception):
    """config.json can't be read (broken JSON or no access)."""


def _stamp(path: str):
    try:
        info = os.stat(path)
    except OSError:
        return None
    return info.st_mtime_ns, info.st_size


def _merge_missing(cfg: dict, defaults: dict) -> None:
    """Adds settings that appeared in a newer version (config.defaults.json) without touching the owner's values."""
    for key, value in defaults.items():
        if key not in cfg:
            cfg[key] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(cfg[key], dict):
            _merge_missing(cfg[key], value)


def _defaults() -> dict:
    try:
        with open(DEFAULTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _create_from_defaults() -> None:
    """The first start: config.json is made from config.defaults.json (the zip doesn't carry the owner's settings, so an
    update never overwrites them)."""
    if not os.path.exists(CONFIG_PATH) and os.path.exists(DEFAULTS_PATH):
        try:
            with open(DEFAULTS_PATH, "r", encoding="utf-8") as src, open(CONFIG_PATH, "x", encoding="utf-8") as dst:
                dst.write(src.read())
        except FileExistsError:
            pass
        except OSError as e:
            raise ConfigError(f"config.json can't be created from config.defaults.json: {e}")


def _read_config() -> dict:
    _create_from_defaults()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ConfigError(f"{CONFIG_PATH} was not found")
    except ValueError as e:
        raise ConfigError(f"config.json is not valid JSON: {e}")
    except OSError as e:
        raise ConfigError(f"config.json can't be read: {e}")
    if not isinstance(data, dict):
        raise ConfigError("config.json must contain a JSON object { ... }")
    _merge_missing(data, _defaults())
    return data


def _current() -> dict:
    """The cached configuration (never change it in place: use load() for a copy)."""
    with _lock:
        now = time.monotonic()
        fresh = _config["data"] is not None and _config["path"] == CONFIG_PATH
        if fresh and now - _config["checked"] < CHECK_INTERVAL:
            return _config["data"]
        _config["checked"] = now
        stamp = _stamp(CONFIG_PATH)
        if fresh and stamp == _config["stamp"]:
            return _config["data"]
        try:
            data = _read_config()
        except ConfigError as e:
            if fresh:
                # Keep working with the last good settings; the owner sees the problem in the log
                if _config["error"] != str(e):
                    log.error("%s. The bot keeps the settings it had before; fix the file or undo the change.", e)
                _config["error"] = str(e)
                _config["stamp"] = stamp
                return _config["data"]
            _config["error"] = str(e)
            raise
        _config.update(path=CONFIG_PATH, stamp=stamp, data=data, error="")
        return data


def load() -> dict:
    """A copy of the configuration (with missing settings from config.defaults.json filled in)."""
    return copy.deepcopy(_current())


def get(section: str) -> dict:
    """A copy of one section, e.g. get("roblox"). An empty dict when the section is missing or not an object."""
    value = _current().get(section)
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def last_error() -> str:
    """Why config.json can't be read right now ("" = it is fine)."""
    try:
        _current()
    except ConfigError:
        pass
    return _config["error"]


def _replace(tmp: str, path: str) -> None:
    """os.replace with a few retries: on Windows an antivirus or indexer may hold the file for a moment."""
    for attempt in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.1 * (attempt + 1))


def _write_atomic(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        _replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def save(cfg: dict) -> None:
    with _lock:
        _write_atomic(CONFIG_PATH, cfg)
        data = copy.deepcopy(cfg)
        _merge_missing(data, _defaults())
        _config.update(path=CONFIG_PATH, stamp=_stamp(CONFIG_PATH), data=data, error="", checked=time.monotonic())


def set_values(updates: list) -> dict:
    """updates: list of (section, key, value) tuples. Returns the saved config."""
    with _lock:
        cfg = load()
        for section, key, value in updates:
            if not isinstance(cfg.get(section), dict):
                cfg[section] = {}
            cfg[section][key] = value
        save(cfg)
        return cfg


def for_guild(cfg: dict, guild_id: int, section: str) -> dict:
    """Config section with per-server values from "guild_overrides" (e.g. the bot's official support server) applied.
    A section written as null (or anything that isn't an object) counts as empty."""
    base = cfg.get(section)
    merged = dict(base) if isinstance(base, dict) else {}
    overrides = cfg.get("guild_overrides")
    server = overrides.get(str(guild_id)) if isinstance(overrides, dict) else None
    extra = server.get(section) if isinstance(server, dict) else None
    if isinstance(extra, dict):
        merged.update(extra)
    return merged


def guild_section(guild_id: int, section: str) -> dict:
    """for_guild() on the cached configuration, for code that runs often (e.g. for every message)."""
    return for_guild(_current(), guild_id, section)


def set_guild_values(guild_id: int, section: str, values: dict) -> dict:
    """Saves values of a config section for one server only ("guild_overrides"). Returns the saved config."""
    with _lock:
        cfg = load()
        overrides = cfg.get("guild_overrides") if isinstance(cfg.get("guild_overrides"), dict) else {}
        cfg["guild_overrides"] = overrides
        server = overrides.get(str(guild_id)) if isinstance(overrides.get(str(guild_id)), dict) else {}
        overrides[str(guild_id)] = server
        if not isinstance(server.get(section), dict):
            server[section] = {}
        server[section].update(values)
        save(cfg)
        return cfg


def parse_color(value, default: int = DEFAULT_COLOR) -> int:
    """A color written as "0x00A2FF", "#00A2FF", "00A2FF" or a number; the default when it can't be read."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value if 0 <= value <= 0xFFFFFF else default
    text = str(value or "").strip().lower()
    for prefix in ("0x", "#"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    try:
        number = int(text, 16)
    except ValueError:
        return default
    return number if 0 <= number <= 0xFFFFFF else default


def embed_color() -> int:
    """The embed color from config.json (bot_settings.embed_color), never an error."""
    try:
        return parse_color(_current().get("bot_settings", {}).get("embed_color"))
    except (ConfigError, AttributeError):
        return DEFAULT_COLOR


# ---------- Files in data/ ----------

def data_path(name: str) -> str:
    return os.path.join(DATA_DIR, name)


def _keep_broken(path: str) -> str:
    """Keeps a copy of a file that can't be read (instead of silently treating it as empty)."""
    copy_path = f"{path}.broken-{time.strftime('%Y%m%d-%H%M%S')}"
    try:
        shutil.copy2(path, copy_path)
    except OSError:
        return ""
    return copy_path


def read_json(name: str, default):
    """A file from data/ (a copy, safe to change), or `default` when it doesn't exist. A damaged file is never read
    as empty without a trace: it is copied to <name>.broken-<time> and the problem is written to the log."""
    path = data_path(name)
    with _lock:
        stamp = _stamp(path)
        if stamp is None:
            _files.pop(path, None)
            return copy.deepcopy(default)
        cached = _files.get(path)
        if cached and cached[0] == stamp:
            return copy.deepcopy(cached[1])
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                value = json.load(f)
        except ValueError as e:
            kept = _keep_broken(path)
            log.error("data/%s is damaged (%s). A copy was kept as %s; the bot uses empty values for it.",
                      name, e, os.path.basename(kept) or "(no copy)")
            _files[path] = (stamp, default)
            return copy.deepcopy(default)
        except OSError as e:
            log.error("data/%s can't be read: %s", name, e)
            return copy.deepcopy(default)
        _files[path] = (stamp, value)
        return copy.deepcopy(value)


def write_json(name: str, data) -> None:
    path = data_path(name)
    with _lock:
        _write_atomic(path, data)
        _files[path] = (_stamp(path), copy.deepcopy(data))


def reset_cache() -> None:
    """Forgets the cached files (used by tests that point CONFIG_PATH or DATA_DIR somewhere else)."""
    with _lock:
        _config.update(path=None, stamp=None, checked=0.0, data=None, error="")
        _files.clear()
