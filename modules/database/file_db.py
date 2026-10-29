import sqlite3
import os

DB_PATH = "database/files.db"


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_indexed_files_name ON indexed_files(file_name)")
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


def search_files_db(search_term: str, limit: int = 200):
    """Searches indexed_files in SQL using tokenized LIKE queries instead of scanning in Python."""
    cleaned = (search_term or "").strip()
    if not cleaned:
        return []
    tokens = [t for t in cleaned.split() if t]
    if not tokens:
        return []

    where_clauses = []
    params = []
    for tok in tokens:
        pattern = f"%{tok}%"
        where_clauses.append("(file_name LIKE ? COLLATE NOCASE OR caption LIKE ? COLLATE NOCASE)")
        params.extend([pattern, pattern])

    sql = (
        f"SELECT id, file_name, caption, extension "
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
):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO indexed_files (
                file_unique_id, file_id, storage_message_id, file_name, file_size, 
                duration, user_id, user_title, caption, extension, file_type, category
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            file_unique_id, file_id, storage_message_id, file_name, file_size,
            duration, user_id, user_title, caption, extension, file_type, category
        ))
        conn.commit()
        conn.close()
        print("✅ [DB SUCCESS] Record saved to database.")
    except Exception as e:
        print(f"❌ [DB ERROR] save_indexed_file_db failed: {e}")
