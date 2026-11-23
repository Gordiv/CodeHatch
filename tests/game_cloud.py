"""The game's DataStore as Open Cloud shows it to the bot, for tests of utils/game_sync.py and the game's log: entries
with versions, and a save with an older version answered like Roblox does (412 with the entry as it is now)."""
import copy
import json
from unittest import mock

from utils import cloud_sync, open_cloud

LIVE = "DiscordLiveContent"
CODES = "DiscordCodeSync"


class FakeCloud:
    def __init__(self):
        self.entries = {}  # (datastore, key) -> [value, version number]
        self.published = []  # (topic, message)
        self.writes = []  # (datastore, key) of every save that went through
        self.conflicts = 0
        self.before_write = []  # functions run before the next saves: a game server saving in that very moment

    # --- what the game does (UpdateAsync in a game server)
    def game_saves(self, datastore: str, key: str, change) -> None:
        value = copy.deepcopy(self.value(datastore, key))
        value = change(value) if value is not None else change(None)
        version = self.entries.get((datastore, key), [None, 0])[1]
        self.entries[(datastore, key)] = [json.loads(json.dumps(value)), version + 1]

    def value(self, datastore: str, key: str):
        return copy.deepcopy(self.entries.get((datastore, key), [None, 0])[0])

    # --- Open Cloud as utils/open_cloud.py uses it
    async def read_entry_versioned(self, datastore, key, what=None):
        value, version = self.entries.get((datastore, key), [None, 0])
        return copy.deepcopy(value), (f"v{version}" if version else None)

    async def write_entry_if(self, datastore, key, value, version, what=None):
        if self.before_write:
            self.before_write.pop(0)(self)
        current, number = self.entries.get((datastore, key), [None, 0])
        if version != (f"v{number}" if number else None):
            self.conflicts += 1
            raise open_cloud.VersionConflict(copy.deepcopy(current), f"v{number}" if number else None)
        self.entries[(datastore, key)] = [json.loads(json.dumps(value)), number + 1]
        self.writes.append((datastore, key))

    async def read_entry(self, datastore, key):
        return copy.deepcopy(self.entries.get((datastore, key), [None, 0])[0])

    async def write_entry(self, datastore, key, value):
        number = self.entries.get((datastore, key), [None, 0])[1]
        self.entries[(datastore, key)] = [json.loads(json.dumps(value)), number + 1]
        self.writes.append((datastore, key))

    async def publish(self, message):
        self.published.append(("DiscordLive", dict(message)))

    async def messaging_publish(self, universe, topic, message, what=None):
        self.published.append((topic, dict(message)))

    def patches(self) -> list:
        names = ("read_entry_versioned", "write_entry_if", "read_entry", "write_entry", "publish", "messaging_publish")
        return [mock.patch.object(open_cloud, name, getattr(self, name)) for name in names] + [
            mock.patch.object(open_cloud, "require_live", return_value=123),
            mock.patch.object(open_cloud, "require_key", return_value=123),
            mock.patch.object(cloud_sync, "status", return_value="ready"),
            mock.patch.object(cloud_sync, "universe_id", return_value=123)]
