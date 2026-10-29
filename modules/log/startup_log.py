import os
import html
import sqlite3
import logging
import datetime
from zoneinfo import ZoneInfo

from telegram import Bot
from modules.database.config_db import get_config

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")

# Set by the Telegram backup/restore module (when present) at boot, e.g.
#   startup_log.DB_STATUS = "restored from Telegram backup"
DB_STATUS = "initialized (no backup restored)"
DB_STATUS_OK = True

# (label, config key / env var holding the chat id, default)
CHAT_SLOTS = [
    ("Storage", "STORAGE_GROUP_ID", "Storage group"),
    ("Posting", "POSTING_CHANNEL_ID", "Posting channel"),
    ("Logs Group", "LOGGER_GROUP_ID", "Logs group"),
    ("Index Ch", "INDEX_CHANNEL_ID", "Index channel"),
    ("Request Ch", "REQUEST_CHANNEL_ID", "Request channel"),
    ("Support", "SUPPORT_CHAT_ID", "Support chat"),
]

# (short label, env var)
TOPIC_SLOTS = [
    ("Gen", "GENERAL_LOG_TOPIC_ID"),
    ("Usr", "USER_LOG_TOPIC_ID"),
    ("Idx", "INDEX_LOG_TOPIC_ID"),
    ("Grp", "GROUP_LOG_TOPIC_ID"),
    ("Ch", "CHANNEL_LOG_TOPIC_ID"),
    ("Req", "REQUEST_LOG_TOPIC_ID"),
    ("Err", "ERROR_LOG_TOPIC_ID"),
]


def _esc(text):
    return html.escape(str(text or ""), quote=False)


def _cfg(env_name):
    return get_config(env_name.lower(), fallback_env=env_name)


def _count(db_path, query):
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        n = conn.execute(query).fetchone()[0]
        conn.close()
        return n
    except Exception:
        return 0


def _db_counts():
    return (
        _count("database/files.db", "SELECT COUNT(*) FROM indexed_files"),
        _count("mastermind_users.db", "SELECT COUNT(*) FROM users"),
        _count("database/config.db", "SELECT COUNT(*) FROM config"),
    )


def _bot_line(bot_info):
    uname = f"@{bot_info.username}" if bot_info.username else "no username"
    return f"{_esc(bot_info.first_name)} ({uname}) | {bot_info.id}"


async def _helper_lines():
    raw = os.getenv("HELPER_BOT_TOKENS", "")
    tokens = [t.strip() for t in raw.split(",") if t.strip()]
    lines = []
    for i, token in enumerate(tokens, 1):
        try:
            async with Bot(token) as hb:
                me = await hb.get_me()
            lines.append(f"  {i}. ✅ {_bot_line(me)}")
        except Exception as e:
            logger.warning("Helper bot %d check failed: %s", i, e)
            lines.append(f"  {i}. ❌ Unreachable (token ends …{token[-4:]})")
    return lines


async def _chat_line(bot, label, chat_id_raw, default_name):
    if not chat_id_raw:
        return f"• {label}: ⚠️ Not set"
    try:
        chat_id = int(chat_id_raw)
    except ValueError:
        return f"• {label}: ❌ Invalid ID ({_esc(chat_id_raw)})"
    try:
        chat = await bot.get_chat(chat_id)
        name = chat.title or default_name
        link = chat.invite_link or (f"https://t.me/{chat.username}" if chat.username else None)
        if not link:
            try:
                link = await bot.export_chat_invite_link(chat_id)
            except Exception:
                link = None
        line = f"• {label}: ✅ {_esc(name)} ({chat_id})"
        if link:
            line += f' — <a href="{html.escape(link, quote=True)}">Invite Link</a>'
        return line
    except Exception as e:
        logger.warning("Startup check for %s (%s) failed: %s", label, chat_id, e)
        return f"• {label}: ❌ Not accessible ({chat_id})"


async def build_startup_text(application):
    bot = application.bot
    me = await bot.get_me()

    parts = ["🔄 <b>Bot Restarted Successfully</b>", ""]
    parts.append(f"🤖 <b>Main Bot:</b> {_bot_line(me)}")

    helpers = await _helper_lines()
    if helpers:
        parts += ["", "🤝 <b>Helper Bots:</b>", *helpers]

    chat_lines = [
        await _chat_line(bot, label, _cfg(env), default)
        for label, env, default in CHAT_SLOTS
    ]
    parts += ["", "📡 <b>Groups &amp; Channels:</b>", *chat_lines]

    topics = " | ".join(f"{label}:{_cfg(env) or '—'}" for label, env in TOPIC_SLOTS)
    parts += ["", f"🧵 <b>Topics:</b> {topics}"]

    files, users, templates = _db_counts()
    icon = "✅" if DB_STATUS_OK else "⚠️"
    parts += [
        "",
        f"💾 <b>Database:</b> {icon} {_esc(DB_STATUS)} "
        f"(📚 files: {files} | 👥 users: {users} | 🧩 templates: {templates})",
    ]

    now = datetime.datetime.now(IST).strftime("%d-%m-%Y | %I:%M:%S %p IST")
    parts += ["", f"⏱ <b>Timestamp:</b> {now}"]
    return "\n".join(parts)


async def send_startup_notification(application):
    logger_group_id = _cfg("LOGGER_GROUP_ID") or _cfg("STORAGE_GROUP_ID")
    if not logger_group_id:
        print("⚠️ [STARTUP WARNING] Logger Group ID not set.")
        return
    try:
        text = await build_startup_text(application)
        kwargs = dict(
            chat_id=int(logger_group_id),
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        topic = _cfg("GENERAL_LOG_TOPIC_ID")
        if topic:
            kwargs["message_thread_id"] = int(topic)
        await application.bot.send_message(**kwargs)
        print("✅ [STARTUP] Restart notification sent successfully!")
    except Exception as e:
        print(f"❌ [STARTUP ERROR]: {e}")
