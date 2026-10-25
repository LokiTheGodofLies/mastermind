import sqlite3
import os

DB_PATH = "database/files.db"


def init_file_db():
    """Initializes the separate files database and creates the indexed files table."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS indexed_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT UNIQUE NOT NULL,
            storage_message_id INTEGER NOT NULL,
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
    conn.commit()
    conn.close()


def save_indexed_file_db(
    file_id: str,
    storage_message_id: int,
    file_name: str,
    file_size: int,
    duration: int,
    user_id: int,
    user_title: str,
    caption: str,
    extension: str,
    file_type: str,
    category: str = "book"
):
    """Saves a fully detailed file record into the files database."""
    init_file_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO indexed_files (
                file_id, storage_message_id, file_name, file_size, 
                duration, user_id, user_title, caption, extension, file_type, category
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            file_id, storage_message_id, file_name, file_size, 
            duration, user_id, user_title, caption, extension, file_type, category
        ))
        conn.commit()
    finally:
        conn.close()


def get_file_by_file_id_db(file_id: str):
    """Retrieves an indexed file record by its unique file_id."""
    init_file_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM indexed_files WHERE file_id = ?", (file_id,))
    row = cursor.fetchone()
    conn.close()
    return row
