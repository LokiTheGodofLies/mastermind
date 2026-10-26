import os
import sqlite3

DB_DIR = "database"
DB_PATH = os.path.join(DB_DIR, "config.db")


def _ensure_db_dir():
    os.makedirs(DB_DIR, exist_ok=True)


def get_connection():
    _ensure_db_dir()
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_config_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT,
            type TEXT DEFAULT 'text'
        )
        """
    )
    conn.commit()
    conn.close()


def get_config(key, default=None, fallback_env=None):
    init_config_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()

    if row is not None:
        return row["value"]

    if fallback_env and os.getenv(fallback_env):
        return os.getenv(fallback_env)

    if default is not None:
        return default

    return None


def set_config(key, value, value_type="text"):
    init_config_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO config (key, value, type)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, type = excluded.type
        """,
        (key, str(value), value_type),
    )
    conn.commit()
    conn.close()
    return True


def get_all_configs():
    init_config_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, type, value FROM config ORDER BY key ASC")
    rows = cursor.fetchall()
    conn.close()
    return [(row["key"], row["type"], row["value"]) for row in rows]


init_config_db()
