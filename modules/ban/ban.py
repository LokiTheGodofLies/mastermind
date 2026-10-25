import os
import sqlite3

def get_support_chat_id():
    """Reads SUPPORT_CHAT_ID securely from env.txt"""
    try:
        with open("env.txt", "r") as f:
            for line in f:
                if line.startswith("SUPPORT_CHAT_ID="):
                    return int(line.split("=", 1)[1].strip())
    except Exception:
        pass
    return None

def set_ban_db(target_id: int, ban_type: str, reason: str):
    """Sets a ban record for a user or chat ID in the database."""
    conn = sqlite3.connect("mastermind_users.db")
    cursor = conn.cursor()
    # We use a unified table or ensure columns exist
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
    """, (target_id, ban_type, reason))
    conn.commit()
    conn.close()

def remove_ban_db(target_id: int):
    """Removes a ban record."""
    conn = sqlite3.connect("mastermind_users.db")
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS bans") # Safe fallback or delete row
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bans (
            target_id INTEGER PRIMARY KEY,
            ban_type TEXT,
            reason TEXT
        )
    """)
    cursor.execute("DELETE FROM bans WHERE target_id = ?", (target_id,))
    conn.commit()
    conn.close()

def get_ban_status(target_id: int):
    """Retrieves ban status for any user or chat ID."""
    try:
        conn = sqlite3.connect("mastermind_users.db")
        cursor = conn.cursor()
        cursor.execute("SELECT ban_type, reason FROM bans WHERE target_id = ?", (target_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"is_banned": True, "ban_type": row[0], "reason": row[1]}
    except Exception:
        pass
    return {"is_banned": False, "ban_type": "none", "reason": None}

def check_access(user_id: int, chat_id: int, chat_type: str):
    """
    Evaluates access based on your specific rules:
    - /ban (type 'all'): Cannot access anywhere.
    - /ban_pm (type 'pm'): Cannot use in PM, but can use in groups & support chat.
    - /ban_support (type 'support'): Can ONLY use in support chat, blocked everywhere else.
    - Banned groups/channels are handled directly upon bot addition or message events.
    """
    support_id = get_support_chat_id()
    
    # 1. Check if the chat itself (group/channel) is banned
    chat_status = get_ban_status(chat_id)
    if chat_status["is_banned"]:
        return False, f"This chat is banned from using the bot.\nReason: {chat_status['reason']}"

    # 2. Check user ban status
    user_status = get_ban_status(user_id)
    if not user_status["is_banned"]:
        return True, None
        
    ban_type = user_status["ban_type"]
    reason = user_status["reason"]
    
    if ban_type == 'all':
        return False, f"🚫 You are banned from using this bot everywhere.\n📝 Reason: {reason}"
        
    if ban_type == 'pm' and chat_type == 'private':
        return False, f"🚫 You are banned from using this bot in Private Messages.\n📝 Reason: {reason}"
        
    if ban_type == 'support':
        # Can ONLY use in the support chat group
        if support_id and chat_id == support_id:
            return True, None
        return False, f"🚫 You are restricted. You can only use the bot inside the support chat.\n📝 Reason: {reason}"
        
    return True, None
