import sqlite3
from config import support_chat_id, users_db_path
from modules.database.config_db import get_config


def get_support_chat_id():
    """Reads PUBLIC_/TESTING_SUPPORT_CHAT_ID via config.support_chat_id() (no fallback)."""
    cid = support_chat_id()
    if cid is not None:
        return cid
    return None


def set_ban_db(target_id: int, ban_type: str, reason: str):
    """Sets a ban record for a user or chat ID in the database."""
    conn = sqlite3.connect(users_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bans (
            target_id INTEGER PRIMARY KEY,
            ban_type TEXT,
            reason TEXT
        )
    """)
    cursor.execute("""
        INSERT OR REPLACE INTO bans (target_id, ban_type, reason) 
        VALUES (?, ?, ?)
    """, (int(target_id), ban_type, reason))
    cursor.execute(
        "UPDATE users SET ban_status = ? WHERE user_id = ?",
        (ban_type, int(target_id)),
    )
    conn.commit()
    conn.close()


def remove_ban_db(target_id: int):
    """Removes a single ban record without dropping the bans table."""
    conn = sqlite3.connect(users_db_path())
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bans (
            target_id INTEGER PRIMARY KEY,
            ban_type TEXT,
            reason TEXT
        )
    """)
    cursor.execute("DELETE FROM bans WHERE target_id = ?", (int(target_id),))
    cursor.execute(
        "UPDATE users SET ban_status = 'none' WHERE user_id = ?",
        (int(target_id),),
    )
    conn.commit()
    conn.close()


def get_ban_status(target_id: int):
    """Retrieves ban status for any user or chat ID."""
    try:
        conn = sqlite3.connect(users_db_path())
        cursor = conn.cursor()
        cursor.execute("SELECT ban_type, reason FROM bans WHERE target_id = ?", (int(target_id),))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"is_banned": True, "ban_type": row[0], "reason": row[1]}
    except Exception:
        pass
    return {"is_banned": False, "ban_type": "none", "reason": None}


def check_access(user_id: int, chat_id: int, chat_type: str):
    """
    Evaluates access based on ban rules:
    - /ban (type 'all'): Cannot access anywhere.
    - /ban_pm (type 'pm'): Cannot use in PM, but can use in groups & support chat.
    - /ban_support (type 'support'): Can ONLY use in support chat, blocked everywhere else.
    """
    support_id = get_support_chat_id()

    chat_status = get_ban_status(chat_id)
    if chat_status["is_banned"]:
        return False, f"This chat is banned from using the bot.\nReason: {chat_status['reason']}"

    user_status = get_ban_status(user_id)
    if not user_status["is_banned"]:
        return True, None

    ban_type = user_status["ban_type"]
    reason = user_status["reason"]

    if ban_type == "all":
        return False, f"🚫 You are banned from using this bot everywhere.\n📝 Reason: {reason}"

    if ban_type == "pm" and chat_type == "private":
        return False, f"🚫 You are banned from using this bot in Private Messages.\n📝 Reason: {reason}"

    if ban_type == "support":
        if support_id and chat_id == support_id:
            return True, None
        return False, f"🚫 You are restricted. You can only use the bot inside the support chat.\n📝 Reason: {reason}"

    return True, None


def check_user_access(user_id: int, chat_id: int, chat_type: str):
    """Backward-compatible alias used by main.py."""
    return check_access(user_id, chat_id, chat_type)
