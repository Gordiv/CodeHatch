"""A9, B5, B8: schema version and migration of an old database (the tables of removed features stay and keep their rows)."""
from datetime import datetime, timezone
import os
import sqlite3
import unittest

from tests.helpers import TempBot
from utils import database

OLD_ROWS = [
    "INSERT INTO verified_users VALUES (1, 500, 'Alice', '2026-10-01 10:00:00')",
    "INSERT INTO verified_users VALUES (2, 500, 'Alice', '2026-10-03 10:00:00')",  # the same Roblox account twice
    "INSERT INTO verified_users VALUES (3, 600, 'Bob', '2026-10-02 10:00:00')",
    "INSERT INTO tickets (channel_id, user_id, category, status, created_at) VALUES (77, 3, 'bug', 'open', '2026-10-02 11:00:00')",
    "INSERT INTO game_codes (code, reward_currency, currency_amount, created_at) VALUES ('ABC', 'Coins', 5, '2026-10-02 12:00:00')",
    "INSERT INTO giveaways (message_id, channel_id, prize, end_timestamp) VALUES (88, 99, 'Robux', 2000000000)",
    "INSERT INTO giveaway_entries (giveaway_id, user_id, joined_at) VALUES (88, 3, '2026-10-02 13:00:00')",
    "INSERT INTO levels VALUES (1, 3, 120, 1, 10, 1790000000)",
]


class Migration(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await database.close_db()

    async def test_old_database_is_upgraded_without_losing_data(self):
        with TempBot():
            os.makedirs(os.path.dirname(database.DB_PATH), exist_ok=True)
            conn = sqlite3.connect(database.DB_PATH)
            for statement in database.SCHEMA_V1:
                conn.execute(statement)
            for statement in OLD_ROWS:
                conn.execute(statement)
            conn.commit()
            conn.close()

            await database.init_db()
            conn = sqlite3.connect(database.DB_PATH)
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], database.SCHEMA_VERSION)
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            # the newest link of Roblox account 500 stays, the older one is kept aside (never deleted)
            self.assertEqual(sorted(r[0] for r in conn.execute("SELECT discord_id FROM verified_users")), [2, 3])
            self.assertEqual(conn.execute("SELECT discord_id FROM verified_conflicts").fetchall(), [(1,)])
            self.assertEqual(conn.execute("SELECT typeof(verified_at), verified_at FROM verified_users WHERE discord_id = 3")
                             .fetchone(), ("integer", int(datetime(2026, 10, 2, 10, tzinfo=timezone.utc).timestamp())))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM levels").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT guild_id FROM giveaways").fetchone()[0], 0)
            conn.close()
            backups = os.listdir(os.path.join(os.path.dirname(database.DB_PATH), "backups"))
            self.assertTrue(any(name.startswith(f"bot-before-v{database.SCHEMA_VERSION}") for name in backups), "a copy is made before migrating")

            await database.close_db()
            await database.init_db()  # a second start changes nothing
            self.assertEqual(len(await database.get_active_game_codes()), 1)


if __name__ == "__main__":
    unittest.main()
