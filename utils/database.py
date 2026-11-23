"""The bot's SQLite database (data/bot.db).

One connection is shared by the whole bot (WAL mode, waits up to 10 s for a lock), and every operation runs under
one lock, so two messages at the same moment can't mix their changes. The schema has a version (PRAGMA user_version):
init_db() brings an older database up to date with the steps in MIGRATIONS, after a backup copy in data/backups.
Times are stored as whole seconds since 1970 (UTC).
"""
import asyncio
import itertools
import logging
import os
import sqlite3
import time

import aiosqlite

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "bot.db")
SCHEMA_VERSION = 4
BACKUP_KEEP = 7
BACKUP_INTERVAL = 86400

log = logging.getLogger("database")

_state = {"db": None, "path": None, "lock": None, "lock_loop": None}


def _now() -> int:
    return int(time.time())


# ---------- Schema ----------

# Tables as version 1.1.0 created them (version 1). Older databases may lack some of them.
SCHEMA_V1 = [
    """CREATE TABLE IF NOT EXISTS verified_users (discord_id INTEGER PRIMARY KEY, roblox_id INTEGER NOT NULL,
        roblox_username TEXT NOT NULL, verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS pending_verifications (discord_id INTEGER PRIMARY KEY, roblox_id INTEGER NOT NULL,
        roblox_username TEXT NOT NULL, verification_code TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS tickets (id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id INTEGER UNIQUE,
        user_id INTEGER NOT NULL, category TEXT NOT NULL, status TEXT DEFAULT 'open',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, closed_at TIMESTAMP, closed_by INTEGER)""",
    """CREATE TABLE IF NOT EXISTS game_codes (code TEXT PRIMARY KEY, reward_currency TEXT, currency_amount INTEGER DEFAULT 0,
        exp_amount INTEGER DEFAULT 0, reward_item TEXT, item_duration_label TEXT, item_duration_seconds INTEGER DEFAULT 0,
        is_temporary_item INTEGER DEFAULT 0, expires_at INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_by INTEGER, is_active INTEGER DEFAULT 1)""",
    """CREATE TABLE IF NOT EXISTS giveaways (message_id INTEGER PRIMARY KEY, channel_id INTEGER NOT NULL, prize TEXT NOT NULL,
        winners_count INTEGER DEFAULT 1, end_timestamp INTEGER NOT NULL, require_verification INTEGER DEFAULT 1,
        require_group INTEGER DEFAULT 0, status TEXT DEFAULT 'active', created_by INTEGER)""",
    """CREATE TABLE IF NOT EXISTS giveaway_entries (giveaway_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (giveaway_id, user_id))""",
    """CREATE TABLE IF NOT EXISTS levels (guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, xp INTEGER DEFAULT 0,
        level INTEGER DEFAULT 0, messages INTEGER DEFAULT 0, last_xp_at INTEGER DEFAULT 0, PRIMARY KEY (guild_id, user_id))""",
    """CREATE TABLE IF NOT EXISTS level_roles (guild_id INTEGER NOT NULL, level INTEGER NOT NULL, role_id INTEGER NOT NULL,
        PRIMARY KEY (guild_id, level))""",
    """CREATE TABLE IF NOT EXISTS live_events (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, multipliers TEXT NOT NULL,
        starts_at INTEGER NOT NULL, ends_at INTEGER NOT NULL, active INTEGER DEFAULT 1, created_by INTEGER)""",
    """CREATE TABLE IF NOT EXISTS eggs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, currency TEXT NOT NULL,
        price INTEGER NOT NULL, pets TEXT NOT NULL, color TEXT DEFAULT '', spot TEXT DEFAULT '', template TEXT DEFAULT '',
        ends_at INTEGER DEFAULT 0, active INTEGER DEFAULT 1, created_by INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS gifts (id INTEGER PRIMARY KEY AUTOINCREMENT, gift_key TEXT NOT NULL, roblox_id INTEGER NOT NULL,
        roblox_username TEXT NOT NULL, reward TEXT NOT NULL, message TEXT DEFAULT '', created_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
]

NOW_SQL = "(CAST(strftime('%s','now') AS INTEGER))"


def _epoch(column: str) -> str:
    """SQL that turns an old text time ('2026-10-05 12:00:00', UTC) into seconds; numbers stay as they are."""
    return (f"CASE WHEN typeof({column}) IN ('integer', 'real') THEN CAST({column} AS INTEGER) "
            f"WHEN {column} IS NULL OR {column} = '' THEN NULL "
            f"ELSE CAST(strftime('%s', {column}) AS INTEGER) END")


# Version 2: times in seconds, guild_id in tickets and giveaways, one Discord account per Roblox account, index for /top
V2_TABLES = {
    "verified_users": (
        f"""CREATE TABLE verified_users (discord_id INTEGER PRIMARY KEY, roblox_id INTEGER NOT NULL,
            roblox_username TEXT NOT NULL, verified_at INTEGER NOT NULL DEFAULT {NOW_SQL})""",
        f"discord_id, roblox_id, roblox_username, COALESCE({_epoch('verified_at')}, {NOW_SQL})"),
    "pending_verifications": (
        f"""CREATE TABLE pending_verifications (discord_id INTEGER PRIMARY KEY, roblox_id INTEGER NOT NULL,
            roblox_username TEXT NOT NULL, verification_code TEXT NOT NULL, created_at INTEGER NOT NULL DEFAULT {NOW_SQL})""",
        f"discord_id, roblox_id, roblox_username, verification_code, COALESCE({_epoch('created_at')}, {NOW_SQL})"),
    "tickets": (
        f"""CREATE TABLE tickets (id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id INTEGER UNIQUE,
            guild_id INTEGER NOT NULL DEFAULT 0, user_id INTEGER NOT NULL, category TEXT NOT NULL, status TEXT DEFAULT 'open',
            created_at INTEGER NOT NULL DEFAULT {NOW_SQL}, closed_at INTEGER, closed_by INTEGER)""",
        f"id, channel_id, 0, user_id, category, status, COALESCE({_epoch('created_at')}, {NOW_SQL}), {_epoch('closed_at')}, "
        "closed_by"),
    "game_codes": (
        f"""CREATE TABLE game_codes (code TEXT PRIMARY KEY, reward_currency TEXT, currency_amount INTEGER DEFAULT 0,
            exp_amount INTEGER DEFAULT 0, reward_item TEXT, item_duration_label TEXT, item_duration_seconds INTEGER DEFAULT 0,
            is_temporary_item INTEGER DEFAULT 0, expires_at INTEGER DEFAULT 0, created_at INTEGER NOT NULL DEFAULT {NOW_SQL},
            created_by INTEGER, is_active INTEGER DEFAULT 1)""",
        "code, reward_currency, currency_amount, exp_amount, reward_item, item_duration_label, item_duration_seconds, "
        f"is_temporary_item, expires_at, COALESCE({_epoch('created_at')}, {NOW_SQL}), created_by, is_active"),
    "giveaways": (
        f"""CREATE TABLE giveaways (message_id INTEGER PRIMARY KEY, channel_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL DEFAULT 0, prize TEXT NOT NULL, winners_count INTEGER DEFAULT 1,
            end_timestamp INTEGER NOT NULL, require_verification INTEGER DEFAULT 1, require_group INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active', created_by INTEGER, created_at INTEGER NOT NULL DEFAULT {NOW_SQL})""",
        "message_id, channel_id, 0, prize, winners_count, end_timestamp, require_verification, require_group, status, "
        f"created_by, {NOW_SQL}"),
    "giveaway_entries": (
        f"""CREATE TABLE giveaway_entries (giveaway_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            joined_at INTEGER NOT NULL DEFAULT {NOW_SQL}, PRIMARY KEY (giveaway_id, user_id))""",
        f"giveaway_id, user_id, COALESCE({_epoch('joined_at')}, {NOW_SQL})"),
    "eggs": (
        f"""CREATE TABLE eggs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, currency TEXT NOT NULL,
            price INTEGER NOT NULL, pets TEXT NOT NULL, color TEXT DEFAULT '', spot TEXT DEFAULT '', template TEXT DEFAULT '',
            ends_at INTEGER DEFAULT 0, active INTEGER DEFAULT 1, created_by INTEGER,
            created_at INTEGER NOT NULL DEFAULT {NOW_SQL})""",
        "id, name, currency, price, pets, color, spot, template, ends_at, active, created_by, "
        f"COALESCE({_epoch('created_at')}, {NOW_SQL})"),
    "gifts": (
        f"""CREATE TABLE gifts (id INTEGER PRIMARY KEY AUTOINCREMENT, gift_key TEXT NOT NULL, roblox_id INTEGER NOT NULL,
            roblox_username TEXT NOT NULL, reward TEXT NOT NULL, message TEXT DEFAULT '', created_by INTEGER,
            created_at INTEGER NOT NULL DEFAULT {NOW_SQL})""",
        f"id, gift_key, roblox_id, roblox_username, reward, message, created_by, COALESCE({_epoch('created_at')}, {NOW_SQL})"),
}


def _migrate_v2(conn: sqlite3.Connection) -> None:
    for table, (create, select) in V2_TABLES.items():
        conn.execute(create.replace(f"CREATE TABLE {table} ", f"CREATE TABLE {table}__new ", 1))
        conn.execute(f"INSERT INTO {table}__new SELECT {select} FROM {table}")
        conn.execute(f"DROP TABLE {table}")
        conn.execute(f"ALTER TABLE {table}__new RENAME TO {table}")
    # One Roblox account = one Discord account. Earlier versions could link it twice: the newest link stays, the others
    # are kept in verified_conflicts (nothing is deleted) and these members simply verify again.
    conn.execute("""CREATE TABLE IF NOT EXISTS verified_conflicts (discord_id INTEGER, roblox_id INTEGER,
        roblox_username TEXT, verified_at INTEGER, moved_at INTEGER)""")
    newer = ("EXISTS (SELECT 1 FROM verified_users o WHERE o.roblox_id = {t}.roblox_id AND (o.verified_at > {t}.verified_at "
             "OR (o.verified_at = {t}.verified_at AND o.discord_id > {t}.discord_id)))")
    conn.execute(f"""INSERT INTO verified_conflicts SELECT v.discord_id, v.roblox_id, v.roblox_username, v.verified_at, {NOW_SQL}
        FROM verified_users v WHERE {newer.format(t="v")}""")
    # The newest link of each Roblox account never matches, so it always stays
    conn.execute(f"DELETE FROM verified_users WHERE {newer.format(t='verified_users')}")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_verified_roblox ON verified_users (roblox_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_levels_xp ON levels (guild_id, xp DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets (user_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_giveaways_status ON giveaways (status, guild_id)")


#  Version 3: the game's ⚙️ Manager makes codes, events and eggs by itself, and the bot keeps a copy of them here.
# origin: "discord" or "game"; author: the Roblox name of who made it in the game; uid: the id an event or egg has in
# the game when it isn't the row's own id ("g5" for one made in the game); pending > 0: a change made here that the
# game doesn't have yet (the next sync sends it). Existing rows start pending, so the first sync checks every one.
V3_COLUMNS = {
    "game_codes": (("origin", "TEXT DEFAULT 'discord'"), ("author", "TEXT DEFAULT ''"), ("pending", "INTEGER DEFAULT 1")),
    "live_events": (("uid", "TEXT"), ("origin", "TEXT DEFAULT 'discord'"), ("author", "TEXT DEFAULT ''"),
                    ("pending", "INTEGER DEFAULT 1")),
    "eggs": (("uid", "TEXT"), ("origin", "TEXT DEFAULT 'discord'"), ("author", "TEXT DEFAULT ''"),
             ("pending", "INTEGER DEFAULT 1")),
    "gifts": (("author", "TEXT DEFAULT ''"),),
}


def _migrate_v3(conn: sqlite3.Connection) -> None:
    for table, columns in V3_COLUMNS.items():
        if not _table_exists(conn, table):
            continue
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, declaration in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
    for table in ("live_events", "eggs"):
        if _table_exists(conn, table):
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_uid ON {table} (uid)")


# Version 4: an event can have an animation the players see (scripts/DiscordCodes/Effects.luau), e.g. "coin_storm"
V4_COLUMNS = {"live_events": (("animation", "TEXT DEFAULT ''"),)}


def _migrate_v4(conn: sqlite3.Connection) -> None:
    for table, columns in V4_COLUMNS.items():
        if not _table_exists(conn, table):
            continue
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, declaration in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")


MIGRATIONS = [(2, _migrate_v2), (3, _migrate_v3), (4, _migrate_v4)]

# The tables this bot uses. A new database gets only these, already in the newest schema; the other tables above
# (verification, tickets, giveaways, levels) belong to the full bot and stay only in databases it made, with their rows.
# A later migration must therefore not expect those tables in every database.
USED_TABLES = ("game_codes", "live_events", "eggs", "gifts")


def _create_new(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        for table in USED_TABLES:
            if table in V2_TABLES:
                create = V2_TABLES[table][0].replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1)
            else:  # the same in both versions
                create = next(s for s in SCHEMA_V1 if f"EXISTS {table} (" in s)
            conn.execute(create)
        _migrate_v3(conn)
        _migrate_v4(conn)
        conn.execute(f"PRAGMA user_version = {int(SCHEMA_VERSION)}")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone() is not None


def backup_now(reason: str = "daily") -> str:
    """A consistent copy of bot.db in data/backups (the SQLite backup API also copies data still in the WAL file).
    Keeps the newest BACKUP_KEEP copies of each kind. Returns the path ("" when there is no database yet)."""
    if not os.path.exists(DB_PATH):
        return ""
    folder = os.path.join(os.path.dirname(DB_PATH), "backups")
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, f"bot-{reason}-{time.strftime('%Y%m%d-%H%M%S')}.db")
    source = sqlite3.connect(DB_PATH, timeout=10)
    try:
        copy = sqlite3.connect(target)
        try:
            source.backup(copy)
        finally:
            copy.close()
    finally:
        source.close()
    old = sorted(f for f in os.listdir(folder) if f.startswith(f"bot-{reason}-") and f.endswith(".db"))
    for name in old[:-BACKUP_KEEP]:
        try:
            os.remove(os.path.join(folder, name))
        except OSError:
            pass
    return target


def _upgrade(path: str) -> int:
    """Creates or updates the schema (synchronously, before the bot connects). Returns the schema version."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new_database = not os.path.exists(path)
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    try:
        conn.execute("PRAGMA busy_timeout = 10000")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            log.warning("bot.db has schema version %s, newer than this bot (%s). It was made by a newer version of "
                        "the bot; the bot keeps working, but update it again to be safe.", version, SCHEMA_VERSION)
            return version
        if version == SCHEMA_VERSION:
            return version
        old_tables = [s.split("EXISTS ", 1)[1].split(" ", 1)[0] for s in SCHEMA_V1]
        if version == 0 and not new_database and any(_table_exists(conn, name) for name in old_tables):
            version = 1  # made before the schema had a version
        if version == 0:  # a new (or empty) database
            _create_new(conn)
            return SCHEMA_VERSION
        conn.close()
        conn = None
        saved = backup_now(f"before-v{SCHEMA_VERSION}")
        log.warning("Updating the database to version %s (backup: %s)", SCHEMA_VERSION, saved)
        conn = sqlite3.connect(path, timeout=10, isolation_level=None)
        conn.execute("PRAGMA busy_timeout = 10000")
        if version < 2:  # the version 1 tables an old database may lack, so that the step to version 2 finds them all
            for statement in SCHEMA_V1:
                conn.execute(statement)
        for target, step in MIGRATIONS:
            if version < target:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    step(conn)
                    conn.execute(f"PRAGMA user_version = {int(target)}")
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
                version = target
        return version
    finally:
        if conn is not None:
            conn.close()


async def init_db():
    await close_db()
    await asyncio.to_thread(_upgrade, DB_PATH)
    await _db()


async def _db() -> aiosqlite.Connection:
    """The shared connection, opened on first use (and again if DB_PATH was changed, e.g. by tests)."""
    if _state["db"] is not None and _state["path"] == DB_PATH:
        return _state["db"]
    if _state["db"] is not None:
        await close_db()
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    pending = aiosqlite.connect(DB_PATH, timeout=10)
    thread = getattr(pending, "_thread", None)
    if thread is not None:
        thread.daemon = True  # a connection left open must never keep the process alive after the bot stops
    db = await pending
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode = WAL")
    await db.execute("PRAGMA synchronous = NORMAL")
    await db.execute("PRAGMA busy_timeout = 10000")
    await db.execute("PRAGMA foreign_keys = ON")
    _state.update(db=db, path=DB_PATH)
    return db


def _lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    if _state["lock"] is None or _state["lock_loop"] is not loop:
        _state.update(lock=asyncio.Lock(), lock_loop=loop)
    return _state["lock"]


async def close_db() -> None:
    db = _state["db"]
    _state.update(db=None, path=None)
    if db is not None:
        try:
            await db.close()
        except Exception as e:  # closing must never stop the shutdown
            log.warning("Could not close the database cleanly: %s", e)


async def _fetchone(sql: str, params=()):
    async with _lock():
        db = await _db()
        async with db.execute(sql, params) as cursor:
            return await cursor.fetchone()


async def _fetchall(sql: str, params=()):
    async with _lock():
        db = await _db()
        async with db.execute(sql, params) as cursor:
            return await cursor.fetchall()


async def _write(*statements) -> int:
    """Runs (sql, params) pairs in one transaction. Returns the rowcount of the last one."""
    async with _lock():
        db = await _db()
        rowcount = 0
        try:
            for sql, params in statements:
                cursor = await db.execute(sql, params)
                rowcount = cursor.rowcount
                await cursor.close()
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return rowcount


async def _insert(sql: str, params) -> int:
    async with _lock():
        db = await _db()
        try:
            cursor = await db.execute(sql, params)
            row_id = cursor.lastrowid
            await cursor.close()
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return row_id


async def backup_loop() -> None:
    """Makes a copy of bot.db once a day (data/backups, the last BACKUP_KEEP days are kept)."""
    while True:
        folder = os.path.join(os.path.dirname(DB_PATH), "backups")
        try:
            newest = max((os.path.getmtime(os.path.join(folder, f)) for f in os.listdir(folder)
                          if f.startswith("bot-daily-")), default=0)
        except OSError:
            newest = 0
        wait = BACKUP_INTERVAL - (time.time() - newest)
        if wait > 0:
            await asyncio.sleep(min(wait, BACKUP_INTERVAL))
            continue
        try:
            await asyncio.to_thread(backup_now, "daily")
        except Exception as e:
            log.error("Daily database backup failed: %s", e)
            await asyncio.sleep(3600)


# A change made on Discord gets a new number in "pending" (never used before, so a sync that sent an older version of
# the row leaves it pending); the sync sets it back to 0 only when the game has exactly that version.
_pending_numbers = itertools.count(int(time.time() * 1_000_000))


def new_pending() -> int:
    return next(_pending_numbers)


# --- GAME CODES ---
async def add_game_code(code: str, currency: str, currency_amount: int, exp_amount: int,
                        item: str, item_duration_label: str, item_duration_sec: int,
                        is_temporary: int, expires_at: int, created_by: int):
    await _write(("""INSERT OR REPLACE INTO game_codes (code, reward_currency, currency_amount, exp_amount, reward_item,
                     item_duration_label, item_duration_seconds, is_temporary_item, expires_at, created_at, created_by, is_active,
                     origin, author, pending)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'discord', '', ?)""",
                  (code.upper(), currency, currency_amount, exp_amount, item, item_duration_label, item_duration_sec,
                   is_temporary, expires_at, _now(), created_by, new_pending())))


async def get_active_game_codes():
    # A code is active when is_active=1 and (expires_at=0 OR expires_at > now)
    return await _fetchall("SELECT * FROM game_codes WHERE is_active = 1 AND (expires_at = 0 OR expires_at > ?) "
                           "ORDER BY created_at DESC", (_now(),))


async def get_game_code(code: str):
    return await _fetchone("SELECT * FROM game_codes WHERE code = ?", (code.upper(),))


async def delete_game_code(code: str):
    await _write(("UPDATE game_codes SET is_active = 0, pending = ? WHERE code = ?", (new_pending(), code.upper())))


async def expire_old_codes():
    await _write(("UPDATE game_codes SET is_active = 0 WHERE expires_at > 0 AND expires_at <= ? AND is_active = 1", (_now(),)))


# --- LIVE EVENTS (multipliers in the game) ---
async def add_live_event(name: str, multipliers: str, starts_at: int, ends_at: int, created_by: int,
                         animation: str = "") -> int:
    return await _insert("INSERT INTO live_events (name, multipliers, starts_at, ends_at, active, created_by, origin, author, "
                         "pending, animation) VALUES (?, ?, ?, ?, 1, ?, 'discord', '', ?, ?)",
                         (name, multipliers, starts_at, ends_at, created_by, new_pending(), animation or ""))


async def get_active_live_events():
    return await _fetchall("SELECT * FROM live_events WHERE active = 1 AND ends_at > ? ORDER BY ends_at", (_now(),))


async def stop_live_event(event_id: int) -> bool:
    """Ends a running event; False when it was ended already or ran out by itself."""
    return await _write(("UPDATE live_events SET active = 0, pending = ? WHERE id = ? AND active = 1 AND ends_at > ?",
                         (new_pending(), event_id, _now()))) > 0


async def get_live_event(event_id: int):
    return await _fetchone("SELECT * FROM live_events WHERE id = ?", (event_id,))


# --- EGGS ---
async def add_egg(name: str, currency: str, price: int, pets: str, color: str, spot: str, template: str,
                  ends_at: int, created_by: int) -> int:
    return await _insert("""INSERT INTO eggs (name, currency, price, pets, color, spot, template, ends_at, active, created_by,
                            created_at, origin, author, pending) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 'discord', '', ?)""",
                         (name, currency, price, pets, color, spot, template, ends_at, created_by, _now(), new_pending()))


async def get_egg(egg_id: int):
    return await _fetchone("SELECT * FROM eggs WHERE id = ?", (egg_id,))


async def get_active_eggs():
    return await _fetchall("SELECT * FROM eggs WHERE active = 1 AND (ends_at = 0 OR ends_at > ?) ORDER BY id", (_now(),))


async def update_egg(egg_id: int, **fields) -> bool:
    """Changes an ACTIVE egg; False when there was none to change (removed meanwhile)."""
    allowed = {k: v for k, v in fields.items() if k in ("name", "currency", "price", "pets", "color", "spot", "template", "ends_at")}
    if not allowed:
        return False
    sets = ", ".join(f"{k} = ?" for k in allowed)
    return await _write((f"UPDATE eggs SET {sets}, pending = ? WHERE id = ? AND active = 1",
                         (*allowed.values(), new_pending(), egg_id))) > 0


async def remove_egg(egg_id: int) -> bool:
    return await _write(("UPDATE eggs SET active = 0, pending = ? WHERE id = ? AND active = 1", (new_pending(), egg_id))) > 0


# --- GIFTS (log of /give and of the gifts sent from the game's ⚙️ Manager) ---
async def add_gift(gift_key: str, roblox_id: int, roblox_username: str, reward: str, message: str, created_by: int,
                   author: str = ""):
    await _write(("INSERT INTO gifts (gift_key, roblox_id, roblox_username, reward, message, created_by, created_at, author) "
                  "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (gift_key, roblox_id, roblox_username, reward, message, created_by, _now(), author)))


async def has_gift(gift_key: str) -> bool:
    return await _fetchone("SELECT 1 FROM gifts WHERE gift_key = ?", (gift_key,)) is not None


# --- WHAT THE GAME HAS (utils/game_sync.py) ---
# The game's DataStore holds the codes, events and eggs; this database keeps a copy, so Discord can list them and
# change them. A row is in the game when pending = 0; a sync sends the pending ones and copies what the game's
# ⚙️ Manager made or changed. The key of a row: the code for codes, the id for events and eggs.
SYNC_TABLES = {"codes": ("game_codes", "code", "is_active"), "events": ("live_events", "id", "active"),
               "eggs": ("eggs", "id", "active")}


async def sync_rows(kind: str, uids=()) -> list:
    """The rows a sync looks at: active ones, pending ones, and those the game has (uids: the game's ids or codes)."""
    table, key, active = SYNC_TABLES[kind]
    rows = {}
    for row in await _fetchall(f"SELECT * FROM {table} WHERE {active} = 1 OR pending > 0"):
        rows[row[key]] = row
    uids = [str(u) for u in uids]
    for start in range(0, len(uids), 400):
        chunk = uids[start:start + 400]
        marks = ", ".join("?" * len(chunk))
        if kind == "codes":
            sql, params = f"SELECT * FROM game_codes WHERE code IN ({marks})", chunk
        else:
            numbers = [int(u) for u in chunk if u.isdigit()] or [-1]
            sql = f"SELECT * FROM {table} WHERE uid IN ({marks}) OR id IN ({', '.join('?' * len(numbers))})"
            params = chunk + numbers
        for row in await _fetchall(sql, params):
            rows[row[key]] = row
    return list(rows.values())


async def apply_sync(kind: str, imports=(), updates=(), deactivate=(), done=()) -> None:
    """Saves what one sync found, in one transaction. imports: new rows from the game (column -> value); updates:
    (row key, column -> value) for rows the game changed; deactivate: keys of rows the game no longer has; done:
    (row key, pending) of the rows the game now has. Rows changed on Discord meanwhile (pending > 0) are left alone:
    the next sync sends that newer change."""
    table, key, _ = SYNC_TABLES[kind]
    statements = []
    for values in imports:
        # OR IGNORE: a code (or an id) saved on Discord in the meantime stays; the next sync sends it to the game
        values = dict(values)
        columns = ", ".join(values)
        statements.append((f"INSERT OR IGNORE INTO {table} ({columns}) VALUES ({', '.join('?' * len(values))})",
                           tuple(values.values())))
    for row_key, values in updates:
        sets = ", ".join(f"{column} = ?" for column in values)
        statements.append((f"UPDATE {table} SET {sets} WHERE {key} = ? AND pending = 0", (*values.values(), row_key)))
    active = SYNC_TABLES[kind][2]
    for row_key in deactivate:
        statements.append((f"UPDATE {table} SET {active} = 0 WHERE {key} = ? AND pending = 0", (row_key,)))
    for row_key, pending in done:
        statements.append((f"UPDATE {table} SET pending = 0 WHERE {key} = ? AND pending = ?", (row_key, pending)))
    if statements:
        await _write(*statements)


async def id_taken(kind: str, row_id: int) -> bool:
    table = SYNC_TABLES[kind][0]
    return await _fetchone(f"SELECT 1 FROM {table} WHERE id = ?", (row_id,)) is not None


async def mark_all_pending() -> None:
    """Another game was connected. What was made on Discord and still runs is sent to it again (nothing there is taken
    as removed); what the old game's ⚙️ Manager made stays with the old game (ended here, never sent); ended and removed
    rows are left alone, so they never remove anything from the new game."""
    now = _now()
    pending = new_pending()
    await _write(
        ("UPDATE game_codes SET is_active = 0 WHERE origin = 'game'", ()),
        ("UPDATE game_codes SET pending = ? WHERE pending = 0 AND is_active = 1 AND (expires_at = 0 OR expires_at > ?)",
         (pending, now)),
        ("UPDATE live_events SET active = 0 WHERE origin = 'game' OR uid IS NOT NULL", ()),
        ("UPDATE live_events SET pending = ? WHERE pending = 0 AND active = 1 AND ends_at > ?", (pending, now)),
        ("UPDATE eggs SET active = 0 WHERE origin = 'game' OR uid IS NOT NULL", ()),
        ("UPDATE eggs SET pending = ? WHERE pending = 0 AND active = 1 AND (ends_at = 0 OR ends_at > ?)", (pending, now)),
        ("UPDATE game_codes SET pending = 0 WHERE is_active = 0", ()),
        ("UPDATE live_events SET pending = 0 WHERE active = 0", ()),
        ("UPDATE eggs SET pending = 0 WHERE active = 0", ()))


async def get_recent_gifts(roblox_id: int, limit: int = 3):
    """The newest gifts sent to one player (the player card in /setup-roblox)."""
    return await _fetchall("SELECT * FROM gifts WHERE roblox_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
                           (roblox_id, limit))
