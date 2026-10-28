import os
import sqlite3
import logging
from modules.log.logger import get_ist_str

logger = logging.getLogger(__name__)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
DB_PATH = os.path.join(BASE_DIR, "database", "files.db")

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_file_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS indexed_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_unique_id TEXT UNIQUE,
            file_id TEXT,
            storage_message_id INTEGER,
            file_name TEXT,
            file_size INTEGER DEFAULT 0,
            duration INTEGER DEFAULT 0,
            user_id INTEGER DEFAULT 0,
            user_title TEXT DEFAULT '',
            caption TEXT DEFAULT '',
            extension TEXT DEFAULT '',
            file_type TEXT DEFAULT '',
            category TEXT DEFAULT 'book',
            title TEXT DEFAULT '',
            author TEXT DEFAULT '',
            narrator TEXT DEFAULT '',
            series TEXT DEFAULT '',
            publisher TEXT DEFAULT '',
            release_date TEXT DEFAULT '',
            length_str TEXT DEFAULT '',
            description TEXT DEFAULT '',
            keywords TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("PRAGMA table_info(indexed_files)")
    fcols = {r["name"] for r in c.fetchall()}
    for col in ["title", "author", "narrator", "series", "publisher", "release_date", "length_str", "description", "keywords"]:
        if col not in fcols:
            c.execute(f"ALTER TABLE indexed_files ADD COLUMN {col} TEXT DEFAULT ''")
    conn.commit()
    conn.close()

def search_books_by_mode_db(keyword: str, mode: str = "all", limit: int = 80) -> list:
    cleaned = (keyword or "").strip()
    if not cleaned:
        return []

    tokens = [t.strip() for t in cleaned.split() if len(t.strip()) > 0]
    if not tokens:
        return []

    audio_exts = (".mp3", ".m4b", ".aax", "mp3", "m4b", "aax")
    where_clauses, params = [], []

    for tok in tokens:
        p = f"%{tok}%"
        where_clauses.append("(title LIKE ? OR author LIKE ? OR series LIKE ? OR file_name LIKE ? OR keywords LIKE ? OR description LIKE ? OR caption LIKE ?)")
        params.extend([p] * 7)

    sql = f"SELECT * FROM indexed_files WHERE {' AND '.join(where_clauses)} ORDER BY id DESC LIMIT ?"
    params.append(limit)

    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    results = []
    for r in rows:
        d = dict(r)
        ext = (d.get("extension") or "").lower()
        cat = (d.get("category") or "").lower()
        is_audio = ext in audio_exts or cat == "audiobook"
        if mode == "ebook" and is_audio:
            continue
        if mode == "audiobook" and not is_audio:
            continue
        results.append(d)
    return results

def get_file_by_id_db(row_id: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM indexed_files WHERE id = ?", (int(row_id),)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_file_by_unique_id_db(file_unique_id: str):
    conn = get_connection()
    row = conn.execute("SELECT * FROM indexed_files WHERE file_unique_id = ?", (file_unique_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def save_indexed_file_db(
    file_unique_id, file_id, storage_message_id, file_name, file_size, duration,
    user_id, user_title, caption, extension, file_type, category,
    title="", author="", narrator="", series="", publisher="", release_date="", length_str="", description="", keywords=""
):
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO indexed_files (
            file_unique_id, file_id, storage_message_id, file_name, file_size,
            duration, user_id, user_title, caption, extension, file_type, category,
            title, author, narrator, series, publisher, release_date, length_str, description, keywords
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        file_unique_id, file_id, storage_message_id, file_name, file_size,
        duration, user_id, user_title, caption, extension, file_type, category,
        title, author, narrator, series, publisher, release_date, length_str, description, keywords
    ))
    conn.commit()
    conn.close()

def log_file_delivery_db(file_id, file_name, sender_bot, receiver_id, channel_link, message_link, posting_msg_id, status="delivered"):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS delivery_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            file_name TEXT,
            sender_bot TEXT,
            receiver_id INTEGER,
            channel_link TEXT,
            message_link TEXT,
            posting_message_id INTEGER DEFAULT 0,
            delivery_status TEXT DEFAULT 'delivered',
            deleted_at TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        INSERT INTO delivery_logs (file_id, file_name, sender_bot, receiver_id, channel_link, message_link, posting_message_id, delivery_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (file_id, file_name, sender_bot, receiver_id, channel_link, message_link, posting_msg_id, status))
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    return rid

def mark_delivery_deleted_db(log_id: int):
    conn = get_connection()
    now_str = get_ist_str("%Y-%m-%d %H:%M:%S IST")
    conn.execute("UPDATE delivery_logs SET deleted_at = ?, delivery_status = 'auto_deleted' WHERE id = ?", (now_str, int(log_id)))
    conn.commit()
    conn.close()
    return now_str

init_file_db()


def _init_queue_tables():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS indexing_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            file_unique_id TEXT,
            file_name TEXT,
            file_size INTEGER DEFAULT 0,
            mime_type TEXT DEFAULT '',
            caption TEXT DEFAULT '',
            channel_id INTEGER DEFAULT 0,
            message_id INTEGER DEFAULT 0,
            user_id INTEGER DEFAULT 0,
            user_title TEXT DEFAULT '',
            source TEXT DEFAULT 'upload',
            priority INTEGER DEFAULT 1,
            status TEXT DEFAULT 'queued',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TEXT DEFAULT ''
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS requests_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            user_name TEXT,
            request_type TEXT DEFAULT 'Book/Audiobook',
            title TEXT,
            author TEXT DEFAULT '',
            series TEXT DEFAULT '',
            format TEXT DEFAULT 'Any',
            source TEXT DEFAULT 'Manual',
            audible_url TEXT DEFAULT '',
            status TEXT DEFAULT 'Pending',
            log_chat_id INTEGER DEFAULT 0,
            log_message_id INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT ''
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS delivery_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT,
            file_name TEXT,
            sender_bot TEXT,
            receiver_id INTEGER,
            channel_link TEXT,
            message_link TEXT,
            posting_message_id INTEGER DEFAULT 0,
            delivery_status TEXT DEFAULT 'delivered',
            deleted_at TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def reset_file_db():
    _init_queue_tables()
    conn = get_connection()
    for t in ("indexed_files", "indexing_queue", "requests_queue", "delivery_logs"):
        conn.execute(f"DELETE FROM {t}")
    conn.commit()
    conn.close()


_init_queue_tables()

def build_file_start_param(row: dict, storage_id: str = "") -> str:
    st_cid = str(storage_id or "0").strip()
    fid = (row.get("file_id") or "").strip()
    fuid = (row.get("file_unique_id") or "").strip()
    if fid and fuid:
        token = f"{fid[:16]}_{fuid}"
    elif fuid:
        token = fuid
    else:
        token = str(row.get("id", 0))
    return f"file_{st_cid}_{token}"[:64]

def get_file_by_start_payload_db(payload: str):
    if not payload:
        return None
    if payload.startswith("dl_"):
        try:
            return get_file_by_id_db(int(payload.replace("dl_", "")))
        except ValueError:
            return None
    if payload.startswith("file_"):
        parts = payload.split("_", 2)
        if len(parts) < 3:
            return None
        token = parts[2]
        conn = get_connection()
        try:
            if "_" in token:
                prefix, fuid = token.split("_", 1)
                row = conn.execute("SELECT * FROM indexed_files WHERE file_unique_id = ?", (fuid,)).fetchone()
                if row:
                    return dict(row)
                row = conn.execute("SELECT * FROM indexed_files WHERE file_id LIKE ?", (f"{prefix}%",)).fetchone()
                if row:
                    return dict(row)
            row = conn.execute(
                "SELECT * FROM indexed_files WHERE file_unique_id = ? OR file_id LIKE ?",
                (token, f"{token}%"),
            ).fetchone()
            if row:
                return dict(row)
            if token.isdigit():
                row = conn.execute("SELECT * FROM indexed_files WHERE id = ?", (int(token),)).fetchone()
                if row:
                    return dict(row)
        finally:
            conn.close()
    return None
