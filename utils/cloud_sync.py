"""Game sync: the codes go into the game's DataStore and every game server is told to reload them. The game's own
⚙️ Manager changes the same entry: utils/game_sync.py makes the game and the bot's database agree.
The HTTP part (and the error texts) is in utils/open_cloud.py, shared with the other game features."""
import time
from dataclasses import dataclass

from utils import config_store, database, env_store, open_cloud
from utils.i18n import t

STATE_FILE = "cloud_sync_state.json"
# Files with data sent to (or read from) one game: they are cleared when the owner connects another game
GAME_STATE_FILES = (STATE_FILE, "live_sync_state.json", "roblox_kit_state.json")

DEFAULTS = {
    "enabled": False,
    "datastore_name": "DiscordCodeSync",
    "entry_key": "ActiveCodes",
    "topic": "DiscordCodes",
    # live game features (events, eggs, gifts, announcements); must match the Live module in the game
    "live_datastore": "DiscordLiveContent",
    "gifts_datastore": "DiscordGifts",
    "live_topic": "DiscordLive",
}

@dataclass
class SyncResult:
    ok: bool
    message: str
    warning: str = ""


class CloudSyncError(Exception):
    pass


def settings() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(config_store.get("cloud_sync"))
    except config_store.ConfigError:
        pass
    return cfg


def api_key() -> str:
    return env_store.secret("ROBLOX_API_KEY")


def universe_id() -> int:
    try:
        return int(config_store.get("roblox").get("universe_id", 0) or 0)
    except (config_store.ConfigError, TypeError, ValueError):
        return 0


def status() -> str:
    """off | no_key | no_universe | ready | config_error (config.json can't be read, so the state is unknown)"""
    if config_store.last_error() and not _config_loaded():
        return "config_error"
    if not settings()["enabled"]:
        return "off"
    if not api_key():
        return "no_key"
    if not universe_id():
        return "no_universe"
    return "ready"


def _config_loaded() -> bool:
    try:
        config_store.get("cloud_sync")
        return True
    except config_store.ConfigError:
        return False


def load_state() -> dict:
    return config_store.read_json(STATE_FILE, {})


def _save_state(**changes) -> None:
    state = load_state()
    state.update(changes)
    config_store.write_json(STATE_FILE, state)


async def reset_game_state() -> None:
    """Called when another game is connected: what was sent to (or read from) the old game says nothing about the new
    one, so the next sync sends everything again (and never takes a code missing there as removed)."""
    for name in GAME_STATE_FILES:
        config_store.write_json(name, {})
    await database.mark_all_pending()


def _error_text(status_code: int, body: str, what: str, kind: str = "datastore") -> str:
    """Kept for code that used the old name (open_cloud imports this module, so nothing of it is read at import)."""
    return open_cloud.error_text(status_code, body, what, kind)


async def push_codes(force: bool = True) -> SyncResult:
    """Makes the codes in the game and in the bot's database agree (utils/game_sync.py): the codes changed on Discord
    go to the game, the codes made or removed in the game's ⚙️ Manager come here. force: tell the game servers to read
    the codes again even when nothing changed (/sync-codes)."""
    from utils import game_sync  # it imports this module
    st = status()
    if st != "ready":
        return SyncResult(False, t(f"sync.{st}"))
    universe = universe_id()
    state = load_state()
    try:
        outcome = await game_sync.sync("codes", notify=force)
    except open_cloud.OpenCloudError as e:
        _save_state(last_error=str(e), last_error_at=int(time.time()), universe=universe,
                    failures=int(state.get("failures", 0)) + 1)
        return SyncResult(False, str(e))
    warning = (outcome.notify_error.rstrip(".") + ". " + t("sync.poll_fallback")) if outcome.notify_error else ""
    _save_state(universe=universe, last_ok=int(time.time()), last_error="", failures=0, count=outcome.count)
    return SyncResult(True, t("sync.success", count=outcome.count), warning)
