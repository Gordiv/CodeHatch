"""The database opens without an error on COPIES of the real backups in data/backups (when there are any), and every row
stays. Only copies in a temporary folder are opened (shutil.copyfile): the real files, and the -wal/-shm files that
opening one would leave behind, are never touched. Skipped when the folder has no backup (a clean checkout)."""
import glob
import os
import shutil
import sqlite3
import unittest
import unittest.mock

from tests.helpers import ROOT, TempBot
from utils import database


def counts(path: str) -> dict:
    conn = sqlite3.connect(path)
    try:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
        return {name: conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in tables}
    finally:
        conn.close()


class RealBackups(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await database.close_db()

    async def test_every_backup_opens_and_keeps_its_rows(self):
        backups = sorted(glob.glob(os.path.join(ROOT, "data", "backups", "*.db")))
        if not backups:
            self.skipTest("data/backups has no database copy here")
        for source in backups:
            with TempBot():
                os.makedirs(os.path.dirname(database.DB_PATH), exist_ok=True)
                shutil.copyfile(source, database.DB_PATH)  # a copy: the real file is never opened
                before = counts(database.DB_PATH)
                await database.init_db()
                await database.close_db()
                after = counts(database.DB_PATH)
                name = os.path.basename(source)
                for table, rows in before.items():
                    self.assertIn(table, after, f"{name}: the table {table} is gone")
                    if table == "verified_users":  # one account per member: the older link is kept aside, never deleted
                        self.assertEqual(after[table] + after.get("verified_conflicts", 0), rows, f"{name}: {table}")
                    else:
                        self.assertGreaterEqual(after[table], rows, f"{name}: rows lost in {table}")
                conn = sqlite3.connect(database.DB_PATH)
                try:
                    self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], database.SCHEMA_VERSION, name)
                finally:
                    conn.close()
                await database.init_db()  # the second start changes nothing
                await database.close_db()
                self.assertEqual(counts(database.DB_PATH), after, f"{name}: a second start changed the data")

    async def test_an_empty_database_starts_and_has_every_table_the_panels_read(self):
        with TempBot():
            await database.init_db()
            tables = set(counts(database.DB_PATH)) - {"sqlite_sequence"}
            self.assertEqual(tables, set(database.USED_TABLES), "only what this bot uses, nothing of the full bot")
            conn = sqlite3.connect(database.DB_PATH)
            try:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], database.SCHEMA_VERSION)
                columns = [row[1] for row in conn.execute("PRAGMA table_info(game_codes)")]
                created = conn.execute("SELECT dflt_value FROM pragma_table_info('game_codes') WHERE name = 'created_at'")
                self.assertIn("strftime", created.fetchone()[0], "times in seconds, like an upgraded database")
            finally:
                conn.close()
            self.assertIn("created_by", columns)
            self.assertEqual(await database.get_active_game_codes(), [])
            self.assertEqual(list(await database.get_active_eggs()), [])
            self.assertEqual(list(await database.get_active_live_events()), [])
            await database.add_game_code("NEW", "Coins", 5, 0, None, "permanent", 0, 0, 0, 7)
            await database.close_db()
            await database.init_db()  # the second start keeps the new database as it is
            self.assertEqual([r["code"] for r in await database.get_active_game_codes()], ["NEW"])


    async def test_a_later_schema_step_keeps_a_new_database_small_and_backs_it_up_first(self):
        with TempBot():
            await database.init_db()
            await database.close_db()
            steps = []

            def next_step(conn):
                steps.append(sorted(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")))

            later = database.SCHEMA_VERSION + 1
            with unittest.mock.patch.object(database, "SCHEMA_VERSION", later),                     unittest.mock.patch.object(database, "MIGRATIONS", database.MIGRATIONS + [(later, next_step)]):
                await database.init_db()
            self.assertEqual(len(steps), 1)
            self.assertEqual(set(steps[0]) - {"sqlite_sequence"}, set(database.USED_TABLES),
                             "no tables of the full bot appear on the way")
            self.assertTrue(glob.glob(os.path.join(os.path.dirname(database.DB_PATH), "backups", f"bot-before-v{later}-*.db")))

    async def test_an_old_database_without_a_version_and_without_verified_users_is_still_upgraded(self):
        with TempBot():
            os.makedirs(os.path.dirname(database.DB_PATH), exist_ok=True)
            conn = sqlite3.connect(database.DB_PATH)
            conn.execute(next(s for s in database.SCHEMA_V1 if "EXISTS game_codes (" in s))
            conn.execute("INSERT INTO game_codes (code, created_at) VALUES ('OLD', '2026-10-05 12:00:00')")
            conn.commit()
            conn.close()
            await database.init_db()
            row = await database.get_game_code("OLD")
            self.assertIsInstance(row["created_at"], int, "the text time became seconds")


if __name__ == "__main__":
    unittest.main()
