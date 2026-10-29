from configs import default_search_quota, default_request_quota
import sqlite3

DB_FILE = "mastermind_users.db"
ADMIN_IDS = {7261537212}


def init_user_db():
    """Initializes the SQLite database tables for users, quotas, and referrals."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            role TEXT DEFAULT 'Normal User',
            ban_status TEXT DEFAULT 'none',
            joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS quotas (
            user_id INTEGER PRIMARY KEY,
            searches_used INTEGER DEFAULT 0,
            searches_limit INTEGER DEFAULT {default_search_quota()},
            requests_used INTEGER DEFAULT 0,
            requests_limit INTEGER DEFAULT {default_request_quota()},
            last_reset_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            referred_id INTEGER PRIMARY KEY,
            referrer_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (referred_id) REFERENCES users (user_id),
            FOREIGN KEY (referrer_id) REFERENCES users (user_id)
        )
    ''')

    conn.commit()
    conn.close()


def add_or_update_user_db(user_id, username, full_name, today_str):
    """Inserts a new user or updates their username/full name."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
    existing = cursor.fetchone()

    if not existing:
        role = 'Owner' if user_id in ADMIN_IDS else 'Normal User'
        if role == 'Owner':
            s_limit, r_limit = 999999, 999999
        else:
            s_limit, r_limit = default_search_quota(), default_request_quota()

        cursor.execute('''
            INSERT INTO users (user_id, username, full_name, role, ban_status)
            VALUES (?, ?, ?, ?, 'none')
        ''', (user_id, username, full_name, role))

        cursor.execute('''
            INSERT OR IGNORE INTO quotas (user_id, searches_used, searches_limit, requests_used, requests_limit, last_reset_date)
            VALUES (?, 0, ?, 0, ?, ?)
        ''', (user_id, s_limit, r_limit, today_str))
    else:
        cursor.execute('''
            UPDATE users SET username = ?, full_name = ? WHERE user_id = ?
        ''', (username, full_name, user_id))

    conn.commit()
    conn.close()


def get_user_role_db(user_id):
    """Retrieves a user's role from the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT role FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result and result[0]:
        return result[0]
    if user_id in ADMIN_IDS:
        return 'Owner'
    return 'Normal User'


def get_quota_record_db(user_id):
    """Retrieves raw quota tracking records for a user."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT searches_used, searches_limit, requests_used, requests_limit, last_reset_date 
        FROM quotas WHERE user_id = ?
    ''', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def update_quota_counts_db(user_id, searches_used, requests_used, reset_date):
    """Updates used counts and reset timestamp."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE quotas 
        SET searches_used = ?, requests_used = ?, last_reset_date = ? 
        WHERE user_id = ?
    ''', (searches_used, requests_used, reset_date, user_id))
    conn.commit()
    conn.close()


def increment_search_used_db(user_id):
    """Increments successful search usage by 1."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE quotas SET searches_used = searches_used + 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()


def increment_request_used_db(user_id):
    """Increments successful request usage by 1."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE quotas SET requests_used = requests_used + 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()


def add_quota_limits_db(target_user_id, search_bonus=0, request_bonus=0):
    """Increases a user's ceiling limits used for gift/referral bonuses."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE quotas 
        SET searches_limit = searches_limit + ?, requests_limit = requests_limit + ? 
        WHERE user_id = ?
    ''', (search_bonus, request_bonus, target_user_id))
    conn.commit()
    conn.close()


def record_referral_db(referrer_id, referred_id):
    """Records a referral relationship. Returns True if successful, False if already referred."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute('SELECT referred_id FROM referrals WHERE referred_id = ?', (referred_id,))
    if cursor.fetchone():
        conn.close()
        return False

    cursor.execute('''
        INSERT INTO referrals (referred_id, referrer_id)
        VALUES (?, ?)
    ''', (referred_id, referrer_id))

    conn.commit()
    conn.close()
    return True


def get_referred_users_db(referrer_id):
    """Retrieves a list of users referred by a specific user."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.user_id, u.full_name, u.username, r.timestamp 
        FROM referrals r
        JOIN users u ON r.referred_id = u.user_id
        WHERE r.referrer_id = ?
        ORDER BY r.timestamp DESC
    ''', (referrer_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows
