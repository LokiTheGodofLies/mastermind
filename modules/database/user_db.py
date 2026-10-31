from datetime import datetime
import sqlite3
from config import (
    admin_ids,
    creator_id,
    users_db_path,
    default_search_quota,
    default_request_quota,
    promoter_quota,
    volunteer_quota,
    moderator_quota,
    unlimited_quota_value,
)


def _db_file():
    return users_db_path()


def _initial_role(user_id: int) -> str:
    if int(user_id) == int(creator_id()):
        return "Creator"
    if int(user_id) in admin_ids():
        return "Admin"
    return "Normal User"


def _role_default_limits(role: str):
    if role in ("Creator", "Owner", "Admin"):
        u = unlimited_quota_value()
        return u, u
    if role == "Moderator":
        q = moderator_quota()
        return q, q
    if role == "Volunteer":
        q = volunteer_quota()
        return q, q
    if role == "Promoter":
        q = promoter_quota()
        return q, q
    return default_search_quota(), default_request_quota()


def init_user_db():
    """Initializes the SQLite database tables for users, quotas, referrals, and bans."""
    conn = sqlite3.connect(_db_file())
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            role TEXT DEFAULT 'Normal User',
            ban_status TEXT DEFAULT 'none',
            joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS quotas (
            user_id INTEGER PRIMARY KEY,
            searches_used INTEGER DEFAULT 0,
            searches_limit INTEGER DEFAULT {default_search_quota()},
            requests_used INTEGER DEFAULT 0,
            requests_limit INTEGER DEFAULT {default_request_quota()},
            last_reset_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            referred_id INTEGER PRIMARY KEY,
            referrer_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (referred_id) REFERENCES users (user_id),
            FOREIGN KEY (referrer_id) REFERENCES users (user_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bans (
            target_id INTEGER PRIMARY KEY,
            ban_type TEXT,
            reason TEXT
        )
    """)

    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY,
            chat_type TEXT,
            title TEXT,
            username TEXT,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_blocks (
            user_id INTEGER,
            bot_username TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, bot_username)
        )
    ''')

    # First-start tracker per bot (main bot = 'main', helper bots = 'helper:<bot_id>').
    # Independent from `users`, because a user row can already exist (search quota, gifts, ...)
    # before the person ever presses /start. Seeded once with every existing user for the main
    # bot so the first deploy does not log the whole user base as "new".
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bot_starts'")
    had_bot_starts = cursor.fetchone() is not None
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_starts (
            user_id INTEGER,
            bot_key TEXT,
            bot_username TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, bot_key)
        )
    ''')
    if not had_bot_starts:
        cursor.execute(
            "INSERT OR IGNORE INTO bot_starts (user_id, bot_key, bot_username) "
            "SELECT user_id, 'main', '' FROM users"
        )

    conn.commit()
    conn.close()


def ensure_user_quota_db(user_id, username="", full_name=""):
    """Ensures a user and their quota record exist in the database."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(_db_file())
    cursor = conn.cursor()

    cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        role = _initial_role(user_id)
        cursor.execute("""
            INSERT OR IGNORE INTO users (user_id, username, full_name, role, ban_status)
            VALUES (?, ?, ?, ?, 'none')
        """, (user_id, username or "", full_name or "", role))
    else:
        role = row[0] or _initial_role(user_id)

    cursor.execute("SELECT user_id FROM quotas WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        s_limit, r_limit = _role_default_limits(role)
        cursor.execute("""
            INSERT OR IGNORE INTO quotas (user_id, searches_used, searches_limit, requests_used, requests_limit, last_reset_date)
            VALUES (?, 0, ?, 0, ?, ?)
        """, (user_id, s_limit, r_limit, today_str))

    conn.commit()
    conn.close()


def add_or_update_user_db(user_id, username, full_name, today_str):
    """Inserts a new user or updates their username/full name. Returns True when the user was NOT in `users` yet."""
    conn = sqlite3.connect(_db_file())
    cursor = conn.cursor()

    cursor.execute("SELECT user_id, role FROM users WHERE user_id = ?", (user_id,))
    existing = cursor.fetchone()
    is_new = existing is None

    if not existing:
        role = _initial_role(user_id)
        s_limit, r_limit = _role_default_limits(role)

        cursor.execute("""
            INSERT INTO users (user_id, username, full_name, role, ban_status)
            VALUES (?, ?, ?, ?, 'none')
        """, (user_id, username, full_name, role))

        cursor.execute("""
            INSERT OR IGNORE INTO quotas (user_id, searches_used, searches_limit, requests_used, requests_limit, last_reset_date)
            VALUES (?, 0, ?, 0, ?, ?)
        """, (user_id, s_limit, r_limit, today_str))
    else:
        cursor.execute("""
            UPDATE users SET username = ?, full_name = ? WHERE user_id = ?
        """, (username, full_name, user_id))
        role = existing[1] or _initial_role(user_id)
        s_limit, r_limit = _role_default_limits(role)
        cursor.execute("""
            INSERT OR IGNORE INTO quotas (user_id, searches_used, searches_limit, requests_used, requests_limit, last_reset_date)
            VALUES (?, 0, ?, 0, ?, ?)
        """, (user_id, s_limit, r_limit, today_str))

    conn.commit()
    conn.close()
    return is_new


def record_bot_start_db(user_id: int, bot_key: str, bot_username: str = "") -> bool:
    """Records the first /start of `user_id` on a bot. Returns True only the first time (-> log it)."""
    try:
        conn = sqlite3.connect(_db_file())
        cur = conn.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO bot_starts (user_id, bot_key, bot_username) VALUES (?, ?, ?)",
            (int(user_id), str(bot_key), (bot_username or "").lstrip("@")),
        )
        first = cur.rowcount > 0
        conn.commit()
        conn.close()
        return first
    except Exception as exc:
        print(f"record_bot_start_db error: {exc}")
        return False


def get_user_info_db(user_id: int) -> dict | None:
    """Returns {'user_id', 'full_name', 'username'} for a known user, else None."""
    try:
        conn = sqlite3.connect(_db_file())
        row = conn.execute(
            "SELECT user_id, full_name, username FROM users WHERE user_id = ?", (int(user_id),)
        ).fetchone()
        conn.close()
        if not row:
            return None
        return {"user_id": row[0], "full_name": row[1] or "", "username": row[2] or ""}
    except Exception:
        return None


def get_user_role_db(user_id):
    """Retrieves a user's role from config or the database."""
    if int(user_id) == int(creator_id()):
        return "Creator"
    conn = sqlite3.connect(_db_file())
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result and result[0] and result[0] != "Normal User":
        return "Creator" if result[0] in ("Owner", "GOD") else result[0]
    if int(user_id) in admin_ids():
        return "Admin"
    if result and result[0]:
        return "Creator" if result[0] in ("Owner", "GOD") else result[0]
    return "Normal User"


def is_creator(user_id: int) -> bool:
    """Returns True if the user has the Creator role."""
    return get_user_role_db(user_id) in ("Creator", "Owner") or int(user_id) == int(creator_id())


def is_admin_or_creator(user_id: int) -> bool:
    """Returns True if the user has Admin or Creator role."""
    return get_user_role_db(user_id) in ("Admin", "Creator", "Owner") or int(user_id) in admin_ids()


is_admin_or_owner = is_admin_or_creator


def set_user_role_db(user_id: int, role: str):
    """Sets a user's role in the database and updates their default quota limits."""
    ensure_user_quota_db(user_id)
    s_limit, r_limit = _role_default_limits(role)
    conn = sqlite3.connect(_db_file())
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET role = ? WHERE user_id = ?", (role, int(user_id)))
    cursor.execute(
        "UPDATE quotas SET searches_limit = ?, requests_limit = ? WHERE user_id = ?",
        (s_limit, r_limit, int(user_id)),
    )
    conn.commit()
    conn.close()


def get_quota_record_db(user_id):
    """Retrieves raw quota tracking records for a user."""
    ensure_user_quota_db(user_id)
    conn = sqlite3.connect(_db_file())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT searches_used, searches_limit, requests_used, requests_limit, last_reset_date 
        FROM quotas WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def update_quota_counts_db(user_id, searches_used, requests_used, reset_date):
    """Updates used counts and reset timestamp."""
    ensure_user_quota_db(user_id)
    conn = sqlite3.connect(_db_file())
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE quotas 
        SET searches_used = ?, requests_used = ?, last_reset_date = ? 
        WHERE user_id = ?
    """, (searches_used, requests_used, reset_date, user_id))
    conn.commit()
    conn.close()


def increment_search_used_db(user_id):
    """Increments successful search usage by 1."""
    ensure_user_quota_db(user_id)
    conn = sqlite3.connect(_db_file())
    cursor = conn.cursor()
    cursor.execute("UPDATE quotas SET searches_used = searches_used + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def increment_request_used_db(user_id):
    """Increments successful request usage by 1."""
    ensure_user_quota_db(user_id)
    conn = sqlite3.connect(_db_file())
    cursor = conn.cursor()
    cursor.execute("UPDATE quotas SET requests_used = requests_used + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def add_quota_limits_db(target_user_id, search_bonus=0, request_bonus=0):
    """Increases a user's ceiling limits used for gift/referral bonuses."""
    ensure_user_quota_db(target_user_id)
    conn = sqlite3.connect(_db_file())
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE quotas 
        SET searches_limit = searches_limit + ?, requests_limit = requests_limit + ? 
        WHERE user_id = ?
    """, (search_bonus, request_bonus, target_user_id))
    conn.commit()
    conn.close()


def record_referral_db(referrer_id, referred_id):
    """Records a referral relationship. Returns True if successful, False if already referred."""
    ensure_user_quota_db(referrer_id)
    ensure_user_quota_db(referred_id)
    conn = sqlite3.connect(_db_file())
    cursor = conn.cursor()

    cursor.execute("SELECT referred_id FROM referrals WHERE referred_id = ?", (referred_id,))
    if cursor.fetchone():
        conn.close()
        return False

    cursor.execute("""
        INSERT INTO referrals (referred_id, referrer_id)
        VALUES (?, ?)
    """, (referred_id, referrer_id))

    conn.commit()
    conn.close()
    return True


def get_referred_users_db(referrer_id):
    """Retrieves a list of users referred by a specific user."""
    conn = sqlite3.connect(_db_file())
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.user_id, u.full_name, u.username, r.timestamp 
        FROM referrals r
        JOIN users u ON r.referred_id = u.user_id
        WHERE r.referrer_id = ?
        ORDER BY r.timestamp DESC
    """, (referrer_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def register_chat_db(chat_id: int, chat_type: str, title: str = "", username: str = ""):
    """Registers or updates a known group/channel in the database for broadcasts and permission auditing."""
    try:
        conn = sqlite3.connect(_db_file())
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO chats (chat_id, chat_type, title, username, last_seen)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE SET
                chat_type = excluded.chat_type,
                title = excluded.title,
                username = excluded.username,
                last_seen = CURRENT_TIMESTAMP
        ''', (chat_id, chat_type, title or "", username or ""))
        conn.commit()
        conn.close()
    except Exception as exc:
        print(f"register_chat_db error: {exc}")


def get_all_chats_db(chat_type: str | None = None) -> list[dict]:
    """Retrieves all registered chats, optionally filtered by type (group, supergroup, channel)."""
    try:
        conn = sqlite3.connect(_db_file())
        cursor = conn.cursor()
        if chat_type:
            cursor.execute("SELECT chat_id, chat_type, title, username FROM chats WHERE chat_type = ?", (chat_type,))
        else:
            cursor.execute("SELECT chat_id, chat_type, title, username FROM chats")
        rows = cursor.fetchall()
        conn.close()
        return [{"chat_id": r[0], "chat_type": r[1], "title": r[2], "username": r[3]} for r in rows]
    except Exception:
        return []


def get_all_users_for_broadcast_db() -> list[dict]:
    """Retrieves all unbanned users for broadcasting."""
    try:
        conn = sqlite3.connect(_db_file())
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, full_name, username FROM users WHERE ban_status = 'none'")
        rows = cursor.fetchall()
        conn.close()
        return [{"user_id": r[0], "full_name": r[1], "username": r[2]} for r in rows]
    except Exception:
        return []


def get_users_by_role_db(role: str) -> list[dict]:
    """Retrieves all users assigned a specific role (with profile formatting)."""
    try:
        conn = sqlite3.connect(_db_file())
        cursor = conn.cursor()
        if role in ("Admin", "Creator"):
            cursor.execute("SELECT user_id, full_name, username, role FROM users WHERE role IN ('Admin', 'Creator', 'GOD', 'Owner')")
        else:
            cursor.execute("SELECT user_id, full_name, username, role FROM users WHERE role = ?", (role,))
        rows = cursor.fetchall()
        conn.close()
        return [{"user_id": r[0], "full_name": r[1], "username": r[2], "role": r[3]} for r in rows]
    except Exception:
        return []


def record_user_blocked_bot_db(user_id: int, bot_username: str):
    """Records in database that user blocked a specific bot."""
    try:
        conn = sqlite3.connect(_db_file())
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO bot_blocks (user_id, bot_username) VALUES (?, ?)", (user_id, (bot_username or "").lstrip("@")))
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_db_stats_counts() -> dict:
    """Returns counts of users, groups, channels, and blocks for /stats."""
    try:
        conn = sqlite3.connect(_db_file())
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM chats WHERE chat_type IN ('group', 'supergroup')")
        total_groups = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM chats WHERE chat_type = 'channel'")
        total_channels = c.fetchone()[0]
        c.execute("SELECT COUNT(DISTINCT user_id) FROM bot_blocks")
        total_blocked_users = c.fetchone()[0]
        conn.close()
        return {
            "users": total_users,
            "groups": total_groups,
            "channels": total_channels,
            "blocked": total_blocked_users,
        }
    except Exception:
        return {"users": 0, "groups": 0, "channels": 0, "blocked": 0}


def record_user_last_file_db(user_id: int, file_id: int):
    """Records the last file row_id clicked by a user for instant helper re-delivery."""
    try:
        conn = sqlite3.connect(_db_file())
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS last_user_requests (
                user_id INTEGER PRIMARY KEY,
                file_id INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            INSERT INTO last_user_requests (user_id, file_id, timestamp)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET file_id = excluded.file_id, timestamp = CURRENT_TIMESTAMP
        """, (int(user_id), int(file_id)))
        conn.commit()
        conn.close()
    except Exception as exc:
        print(f"record_user_last_file_db error: {exc}")


def get_user_last_file_db(user_id: int) -> int | None:
    """Retrieves the last requested file row_id for a user."""
    try:
        conn = sqlite3.connect(_db_file())
        cursor = conn.cursor()
        cursor.execute("SELECT file_id FROM last_user_requests WHERE user_id = ?", (int(user_id),))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None
