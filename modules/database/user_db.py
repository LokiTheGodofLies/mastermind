from datetime import datetime
import sqlite3
from config import (
    admin_ids,
    owner_id,
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
    if int(user_id) == int(owner_id()):
        return "GOD"
    if int(user_id) in admin_ids():
        return "Admin"
    return "Normal User"


def _role_default_limits(role: str):
    if role in ("GOD", "Owner", "Admin"):
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
    """Inserts a new user or updates their username/full name."""
    conn = sqlite3.connect(_db_file())
    cursor = conn.cursor()

    cursor.execute("SELECT user_id, role FROM users WHERE user_id = ?", (user_id,))
    existing = cursor.fetchone()

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


def get_user_role_db(user_id):
    """Retrieves a user's role from config or the database."""
    if int(user_id) == int(owner_id()):
        return "GOD"
    conn = sqlite3.connect(_db_file())
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result and result[0] and result[0] != "Normal User":
        return "GOD" if result[0] == "Owner" else result[0]
    if int(user_id) in admin_ids():
        return "Admin"
    if result and result[0]:
        return "GOD" if result[0] == "Owner" else result[0]
    return "Normal User"


def is_god(user_id: int) -> bool:
    """Returns True if the user has the GOD role."""
    return get_user_role_db(user_id) in ("GOD", "Owner") or int(user_id) == int(owner_id())


def is_admin_or_god(user_id: int) -> bool:
    """Returns True if the user has Admin or GOD role."""
    return get_user_role_db(user_id) in ("Admin", "GOD", "Owner") or int(user_id) in admin_ids()


is_admin_or_owner = is_admin_or_god


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
