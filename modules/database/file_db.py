import os
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


def deduplicate_indexed_files_db(conn=None):
    """
    Enforces strict 1-to-1 uniqueness across `indexed_files` so that each file has:
      - ONLY ONE `file_unique_id`
      - ONLY ONE `file_id`
      - ONLY ONE `storage_message_id`
    If duplicate rows share the same `file_unique_id`, `file_id`, or `storage_message_id`,
    consolidates the latest `storage_message_id` and `file_id` onto the canonical row and
    deletes the stale duplicate rows.
    """
    own_conn = conn is None
    try:
        if own_conn:
            conn = get_connection()
        cursor = conn.cursor()

        # 1. Deduplicate by file_unique_id (keep highest id / most recent storage_message_id)
        cursor.execute("""
            DELETE FROM indexed_files
            WHERE file_unique_id IS NOT NULL AND file_unique_id != ''
              AND id NOT IN (
                  SELECT MAX(id) FROM indexed_files
                  WHERE file_unique_id IS NOT NULL AND file_unique_id != ''
                  GROUP BY file_unique_id
              )
        """)

        # 2. Deduplicate by file_id (each file_id must belong to at most one row)
        cursor.execute("""
            DELETE FROM indexed_files
            WHERE file_id IS NOT NULL AND file_id != ''
              AND id NOT IN (
                  SELECT MAX(id) FROM indexed_files
                  WHERE file_id IS NOT NULL AND file_id != ''
                  GROUP BY file_id
              )
        """)

        # 3. Deduplicate by storage_message_id (each Storage Group message ID belongs to at most one row)
        cursor.execute("""
            DELETE FROM indexed_files
            WHERE storage_message_id IS NOT NULL AND storage_message_id > 0
              AND id NOT IN (
                  SELECT MAX(id) FROM indexed_files
                  WHERE storage_message_id IS NOT NULL AND storage_message_id > 0
                  GROUP BY storage_message_id
              )
        """)

        # Create unique indexes to enforce 1-to-1 mapping going forward
        cursor.execute("DROP INDEX IF EXISTS idx_indexed_files_storage_msg")
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_indexed_files_unique_id "
            "ON indexed_files(file_unique_id) WHERE file_unique_id IS NOT NULL AND file_unique_id != ''"
        )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_indexed_files_file_id "
            "ON indexed_files(file_id) WHERE file_id IS NOT NULL AND file_id != ''"
        )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_indexed_files_storage_msg "
            "ON indexed_files(storage_message_id) WHERE storage_message_id IS NOT NULL AND storage_message_id > 0"
        )

        if own_conn:
            conn.commit()
    except Exception as e:
        print(f"⚠️ [DB WARN] deduplicate_indexed_files_db: {e}")
    finally:
        if own_conn and conn is not None:
            conn.close()


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

        # Migration check: add is_enriched if table existed without it
        cursor.execute("PRAGMA table_info(indexed_files)")
        columns = [row["name"] for row in cursor.fetchall()]
        if "is_enriched" not in columns:
            cursor.execute("ALTER TABLE indexed_files ADD COLUMN is_enriched INTEGER DEFAULT 0")

        deduplicate_indexed_files_db(conn)
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


def get_file_by_file_id_db(file_id: str):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM indexed_files WHERE file_id = ?", (file_id,))
        row = cursor.fetchone()
        conn.close()
        return row
    except Exception as e:
        print(f"❌ [DB ERROR] get_file_by_file_id_db failed: {e}")
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


def find_file_candidates_by_ids_db(
    file_unique_id: str | None = None,
    file_id: str | None = None,
    file_name: str | None = None,
) -> list:
    """
    Checks all records in `files.db` matching `file_unique_id`, `file_id`, or exact `file_name`
    (newest first) so that if a storage_message_id is missing, all candidate file_ids and
    storage_message_ids can be checked.
    """
    clauses = []
    params = []
    if file_unique_id:
        clauses.append("file_unique_id = ?")
        params.append(str(file_unique_id))
    if file_id:
        clauses.append("file_id = ?")
        params.append(str(file_id))
    if file_name:
        clauses.append("file_name = ? COLLATE NOCASE")
        params.append(str(file_name))
    if not clauses:
        return []
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT * FROM indexed_files WHERE {' OR '.join(clauses)} ORDER BY id DESC",
            params,
        )
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"❌ [DB ERROR] find_file_candidates_by_ids_db failed: {e}")
        return []


def get_storage_message_id_bounds_db() -> tuple[int, int]:
    """Returns (min_storage_msg_id, max_storage_msg_id) currently recorded in files.db."""
    try:
        conn = get_connection()
        row = conn.execute(
            "SELECT MIN(storage_message_id), MAX(storage_message_id) FROM indexed_files WHERE storage_message_id > 0"
        ).fetchone()
        conn.close()
        if row and row[1]:
            return int(row[0] or 1), int(row[1])
    except Exception:
        pass
    return 1, 0


def sync_unique_file_storage_db(
    row_id: int | None,
    file_unique_id: str | None,
    file_id: str | None,
    storage_message_id: int,
) -> int | None:
    """
    Updates the canonical file record in `files.db` with the verified `storage_message_id` and `file_id`,
    and removes any duplicate/conflicting rows that held the same `file_unique_id`, `file_id`, or
    `storage_message_id` so each file has strictly ONE unique `file_unique_id`, ONE `file_id`, and
    ONE `storage_message_id`.
    """
    if not storage_message_id or int(storage_message_id) <= 0:
        return None
    smid = int(storage_message_id)
    fuid = (file_unique_id or "").strip() or None
    fid = (file_id or "").strip() or None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Locate the canonical row to keep
        target_id = int(row_id) if row_id else None
        if target_id:
            chk = cursor.execute("SELECT id FROM indexed_files WHERE id = ?", (target_id,)).fetchone()
            if not chk:
                target_id = None
        if not target_id and fuid:
            r = cursor.execute("SELECT id FROM indexed_files WHERE file_unique_id = ? ORDER BY id DESC LIMIT 1", (fuid,)).fetchone()
            if r:
                target_id = int(r["id"])
        if not target_id and fid:
            r = cursor.execute("SELECT id FROM indexed_files WHERE file_id = ? ORDER BY id DESC LIMIT 1", (fid,)).fetchone()
            if r:
                target_id = int(r["id"])
        if not target_id:
            conn.close()
            return None

        # Remove any other rows that conflict with (fuid, fid, smid) so uniqueness is guaranteed
        del_clauses = ["storage_message_id = ?"]
        del_params: list = [smid]
        if fuid:
            del_clauses.append("file_unique_id = ?")
            del_params.append(fuid)
        if fid:
            del_clauses.append("file_id = ?")
            del_params.append(fid)
        del_params.append(target_id)
        cursor.execute(
            f"DELETE FROM indexed_files WHERE ({' OR '.join(del_clauses)}) AND id != ?",
            del_params,
        )

        # Update the canonical row with the verified storage_message_id (and file_id / file_unique_id)
        if fuid and fid:
            cursor.execute(
                "UPDATE indexed_files SET storage_message_id = ?, file_id = ?, file_unique_id = ? WHERE id = ?",
                (smid, fid, fuid, target_id),
            )
        elif fid:
            cursor.execute(
                "UPDATE indexed_files SET storage_message_id = ?, file_id = ? WHERE id = ?",
                (smid, fid, target_id),
            )
        else:
            cursor.execute(
                "UPDATE indexed_files SET storage_message_id = ? WHERE id = ?",
                (smid, target_id),
            )

        conn.commit()
        conn.close()
        return target_id
    except Exception as e:
        print(f"❌ [DB ERROR] sync_unique_file_storage_db failed: {e}")
        return None


def update_storage_message_id_db(row_id: int, storage_message_id: int, file_id: str | None = None, file_unique_id: str | None = None):
    sync_unique_file_storage_db(row_id, file_unique_id, file_id, int(storage_message_id))


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

        # Support number prefixes (e.g. #8 vs 8 vs Book 8 vs Book #8)
        if tok.isdigit():
            tok_patterns.append(f"%#{tok}%")
            tok_patterns.append(f"%Book {tok}%")
            tok_patterns.append(f"%Book #{tok}%")

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
) -> bool:
    """
    Saves or updates an indexed file record in files.db while enforcing 1-to-1 uniqueness across
    `file_unique_id`, `file_id`, and `storage_message_id` (preserving existing primary key `id`
    and deep-link `dl_<id>`).
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        smid = int(storage_message_id) if storage_message_id else None
        fuid = (file_unique_id or "").strip()
        fid = (file_id or "").strip()

        # Find if a canonical row already exists by file_unique_id, file_id, or storage_message_id
        existing = None
        if fuid:
            existing = cursor.execute(
                "SELECT id FROM indexed_files WHERE file_unique_id = ? LIMIT 1", (fuid,)
            ).fetchone()
        if not existing and fid:
            existing = cursor.execute(
                "SELECT id FROM indexed_files WHERE file_id = ? LIMIT 1", (fid,)
            ).fetchone()
        if not existing and smid:
            existing = cursor.execute(
                "SELECT id FROM indexed_files WHERE storage_message_id = ? LIMIT 1", (smid,)
            ).fetchone()

        if existing:
            keep_id = int(existing["id"])
            # Delete any other rows that would collide with (fuid, fid, smid)
            conflict_clauses = []
            conflict_params: list = []
            if fuid:
                conflict_clauses.append("file_unique_id = ?")
                conflict_params.append(fuid)
            if fid:
                conflict_clauses.append("file_id = ?")
                conflict_params.append(fid)
            if smid:
                conflict_clauses.append("storage_message_id = ?")
                conflict_params.append(smid)
            if conflict_clauses:
                conflict_params.append(keep_id)
                cursor.execute(
                    f"DELETE FROM indexed_files WHERE ({' OR '.join(conflict_clauses)}) AND id != ?",
                    conflict_params,
                )

            cursor.execute("""
                UPDATE indexed_files SET
                    file_unique_id = ?,
                    file_id = ?,
                    storage_message_id = ?,
                    file_name = ?,
                    file_size = ?,
                    duration = ?,
                    user_id = CASE WHEN ? != 0 THEN ? ELSE user_id END,
                    user_title = CASE WHEN ? != '' AND ? != 'Unknown' THEN ? ELSE user_title END,
                    caption = ?,
                    extension = ?,
                    file_type = ?,
                    category = ?,
                    is_enriched = ?
                WHERE id = ?
            """, (
                fuid, fid, smid, file_name, file_size, duration,
                user_id, user_id,
                user_title, user_title, user_title,
                caption, extension, file_type, category, int(is_enriched),
                keep_id,
            ))
        else:
            cursor.execute("""
                INSERT INTO indexed_files (
                    file_unique_id, file_id, storage_message_id, file_name, file_size,
                    duration, user_id, user_title, caption, extension, file_type, category, is_enriched
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fuid, fid, smid, file_name, file_size,
                duration, user_id, user_title, caption, extension, file_type, category, int(is_enriched)
            ))

        conn.commit()
        conn.close()
        print("✅ [DB SUCCESS] Record saved/updated in database.")
        return True
    except Exception as e:
        print(f"❌ [DB ERROR] save_indexed_file_db failed: {e}")
        return False


def get_file_stats_counts_db() -> dict:
    """Returns counts of total files, ebooks, and audiobooks for /stats."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM indexed_files")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM indexed_files WHERE category IN ('ebook', 'book', 'archive')")
        ebooks = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM indexed_files WHERE category = 'audiobook'")
        audiobooks = c.fetchone()[0]
        conn.close()
        return {"total": total, "ebooks": ebooks, "audiobooks": audiobooks}
    except Exception:
        return {"total": 0, "ebooks": 0, "audiobooks": 0}
