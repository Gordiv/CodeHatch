"""database.get_recent_gifts (the gift lines of the player card) on a new database, on a migrated old one and on a
plain file copy of a real old backup (skipped when data/backups has none: private data is not part of the repository)."""
import glob
import json
import os
import shutil
import sqlite3
import unittest
from datetime import datetime, timezone

from tests.helpers import ROOT, TempBot
from utils import database

OLD_BACKUPS = sorted(glob.glob(os.path.join(ROOT, "data", "backups", "bot-before-v2-*.db")))


def epoch(text: str) -> int:
    return int(datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp())


class RecentGifts(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await database.close_db()

    async def test_new_database(self):
        with TempBot():
            await database.init_db()
            self.assertEqual(await database.get_recent_gifts(5, 3), [])
            for index in range(5):
                await database.add_gift(f"k{index}", 5, "Five", json.dumps({"exp": index + 1}), "", 7)
            await database.add_gift("other", 6, "Six", json.dumps({"exp": 1}), "", 7)
            rows = await database.get_recent_gifts(5, 3)
            self.assertEqual([r["gift_key"] for r in rows], ["k4", "k3", "k2"], "same second: the newest first, at most 3")
            self.assertEqual(len(await database.get_recent_gifts(5, 50)), 5)
            self.assertEqual(await database.get_recent_gifts(404, 3), [])
            self.assertEqual(await database.get_recent_gifts(5, 0), [])

    async def test_old_database_keeps_its_gifts_and_orders_them(self):
        with TempBot():
            os.makedirs(os.path.dirname(database.DB_PATH), exist_ok=True)
            conn = sqlite3.connect(database.DB_PATH)
            for statement in database.SCHEMA_V1:
                conn.execute(statement)
            for key, roblox_id, when in (("old1", 5, "2026-10-01 10:00:00"), ("old2", 5, "2026-10-03 10:00:00"),
                                         ("old3", 5, "2026-10-02 10:00:00"), ("else", 9, "2026-10-04 10:00:00")):
                conn.execute("INSERT INTO gifts (gift_key, roblox_id, roblox_username, reward, message, created_by, created_at) "
                             "VALUES (?, ?, 'Five', '{\"exp\": 1}', '', 7, ?)", (key, roblox_id, when))
            conn.commit()
            conn.close()
            await database.init_db()
            rows = await database.get_recent_gifts(5, 3)
            self.assertEqual([r["gift_key"] for r in rows], ["old2", "old3", "old1"])
            self.assertEqual([r["created_at"] for r in rows], [epoch("2026-10-03 10:00:00"), epoch("2026-10-02 10:00:00"),
                                                               epoch("2026-10-01 10:00:00")], "times became seconds")
            self.assertEqual(len(await database.get_recent_gifts(9, 3)), 1)
            await database.close_db()
            await database.init_db()  # a second start changes nothing
            self.assertEqual(len(await database.get_recent_gifts(5, 3)), 3)

    @unittest.skipUnless(OLD_BACKUPS, "no data/backups/bot-before-v2-*.db: the real old database is not in the repository")
    async def test_copy_of_a_real_old_backup(self):
        with TempBot():
            os.makedirs(os.path.dirname(database.DB_PATH), exist_ok=True)
            shutil.copyfile(OLD_BACKUPS[-1], database.DB_PATH)  # a plain file copy: the backup itself is never opened
            copy = sqlite3.connect(database.DB_PATH)
            tables = [r[0] for r in copy.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
            before = {name: copy.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in tables}
            ids = [r[0] for r in copy.execute("SELECT DISTINCT roblox_id FROM gifts")]
            copy.close()
            await database.init_db()
            conn = sqlite3.connect(database.DB_PATH)
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], database.SCHEMA_VERSION)
            for name, count in before.items():
                if name != "verified_users":  # a double link of one Roblox account is moved aside on purpose
                    self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0], count, name)
            conn.close()
            for roblox_id in ids:
                rows = await database.get_recent_gifts(roblox_id, 3)
                self.assertTrue(rows)
                self.assertEqual([r["created_at"] for r in rows], sorted((r["created_at"] for r in rows), reverse=True))


if __name__ == "__main__":
    unittest.main()
