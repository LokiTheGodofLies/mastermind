import os
import re
import sqlite3
from config import files_db_path


def _db_path():
    return files_db_path()


def get_connection():
    path = _db_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_file_db():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS indexed_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_unique_id TEXT UNIQUE,
                file_id TEXT,
                storage_message_id INTEGER,
                file_name TEXT,
                file_size INTEGER,
                duration INTEGER,
                user_id INTEGER,
                user_title TEXT,
                caption TEXT,
                extension TEXT,
                file_type TEXT,
                category TEXT,
                is_enriched INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_indexed_files_name ON indexed_files(file_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_indexed_files_unique_id ON indexed_files(file_unique_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_indexed_files_storage_msg ON indexed_files(storage_message_id)")

        # Migration check: add is_enriched if table existed without it
        cursor.execute("PRAGMA table_info(indexed_files)")
        columns = [row["name"] for row in cursor.fetchall()]
        if "is_enriched" not in columns:
            cursor.execute("ALTER TABLE indexed_files ADD COLUMN is_enriched INTEGER DEFAULT 0")

        conn.commit()
        conn.close()
        print("✅ Database tables verified/initialized successfully.")
    except Exception as e:
        print(f"❌ [DB ERROR] init_file_db failed: {e}")


def get_file_by_unique_id_db(file_unique_id: str):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM indexed_files WHERE file_unique_id = ?", (file_unique_id,))
        row = cursor.fetchone()
        conn.close()
        return row
    except Exception as e:
        print(f"❌ [DB ERROR] get_file_by_unique_id_db failed: {e}")
        return None


def get_file_by_id_db(row_id: int):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM indexed_files WHERE id = ?", (int(row_id),))
        row = cursor.fetchone()
        conn.close()
        return row
    except Exception as e:
        print(f"❌ [DB ERROR] get_file_by_id_db failed: {e}")
        return None


def get_file_by_storage_message_id_db(storage_message_id: int):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM indexed_files WHERE storage_message_id = ?", (int(storage_message_id),))
        row = cursor.fetchone()
        conn.close()
        return row
    except Exception as e:
        print(f"❌ [DB ERROR] get_file_by_storage_message_id_db failed: {e}")
        return None


def update_storage_message_id_db(row_id: int, storage_message_id: int):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE indexed_files SET storage_message_id = ? WHERE id = ?",
            (int(storage_message_id), int(row_id)),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ [DB ERROR] update_storage_message_id_db failed: {e}")


def update_file_caption_db(storage_message_id: int, new_caption: str, is_enriched: int = 1):
    """Updates the caption in files.db when edited in storage group or during enrichment."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE indexed_files SET caption = ?, is_enriched = ? WHERE storage_message_id = ?",
            (new_caption, int(is_enriched), int(storage_message_id)),
        )
        conn.commit()
        conn.close()
        print(f"✅ [DB SUCCESS] Updated caption for storage message {storage_message_id}")
    except Exception as e:
        print(f"❌ [DB ERROR] update_file_caption_db failed: {e}")


def update_caption_by_unique_id_db(file_unique_id: str, new_caption: str, is_enriched: int = 1):
    """Updates the caption in files.db using file_unique_id."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE indexed_files SET caption = ?, is_enriched = ? WHERE file_unique_id = ?",
            (new_caption, int(is_enriched), file_unique_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ [DB ERROR] update_caption_by_unique_id_db failed: {e}")


def search_files_db(search_term: str, limit: int = 200):
    """
    Enhanced search across file_name and caption with:
    1. Dual-matching for apostrophe variations (Suggestion C: Ender's matches Enders and vice-versa).
    2. Punctuation tolerance and series/volume number matching.
    3. Tokenized matching across both filename and enriched caption fields.
    """
    cleaned = (search_term or "").strip()
    if not cleaned:
        return []

    cleaned = cleaned.replace("’", "'").replace("‘", "'").replace("`", "'")
    raw_tokens = [t.strip("'") for t in cleaned.split() if t.strip("'")]
    if not raw_tokens:
        return []

    where_clauses = []
    params = []

    for tok in raw_tokens:
        tok_patterns = [f"%{tok}%"]
        if "'" in tok:
            clean_tok = tok.replace("'", "")
            tok_patterns.append(f"%{clean_tok}%")
            if tok.endswith("'s"):
                tok_patterns.append(f"%{tok[:-2]}%")
                tok_patterns.append(f"%{tok[:-2]}s%")
        else:
            tok_patterns.append(f"%{tok}'s%")
            if tok.endswith("s") and len(tok) > 2:
                tok_patterns.append(f"%{tok[:-1]}'s%")
                tok_patterns.append(f"%{tok[:-1]}%")

        # Support number prefixes (e.g. #8 vs 8 vs Book 8)
        if tok.isdigit():
            tok_patterns.append(f"%#{tok}%")
            tok_patterns.append(f"%Book {tok}%")

        sub_clauses = []
        for pat in tok_patterns:
            sub_clauses.append("(file_name LIKE ? COLLATE NOCASE OR caption LIKE ? COLLATE NOCASE)")
            params.extend([pat, pat])

        where_clauses.append(f"({' OR '.join(sub_clauses)})")

    sql = (
        f"SELECT id, file_unique_id, file_id, storage_message_id, file_name, file_size, duration, user_id, user_title, caption, extension, file_type, category, is_enriched "
        f"FROM indexed_files "
        f"WHERE {' AND '.join(where_clauses)} "
        f"ORDER BY id DESC LIMIT ?"
    )
    params.append(limit)

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"❌ [DB ERROR] search_files_db failed: {e}")
        return []


def save_indexed_file_db(
    file_unique_id,
    file_id,
    storage_message_id,
    file_name,
    file_size,
    duration,
    user_id,
    user_title,
    caption,
    extension,
    file_type,
    category,
    is_enriched=0,
):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO indexed_files (
                file_unique_id, file_id, storage_message_id, file_name, file_size, 
                duration, user_id, user_title, caption, extension, file_type, category, is_enriched
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            file_unique_id, file_id, storage_message_id, file_name, file_size,
            duration, user_id, user_title, caption, extension, file_type, category, int(is_enriched)
        ))
        conn.commit()
        conn.close()
        print("✅ [DB SUCCESS] Record saved to database.")
    except Exception as e:
        print(f"❌ [DB ERROR] save_indexed_file_db failed: {e}")


def get_file_stats_counts_db() -> dict:
    """Returns counts of total files, ebooks, and audiobooks for /stats."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM indexed_files")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM indexed_files WHERE category = 'ebook'")
        ebooks = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM indexed_files WHERE category = 'audiobook'")
        audiobooks = c.fetchone()[0]
        conn.close()
        return {"total": total, "ebooks": ebooks, "audiobooks": audiobooks}
    except Exception:
        return {"total": 0, "ebooks": 0, "audiobooks": 0}
