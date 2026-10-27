import os
from telegram import Update
from telegram.ext import ContextTypes, ApplicationHandlerStop
from modules.database.user_db import get_user_role_db
from modules.database.config_db import get_config, get_config_int, set_config, set_group_topic_db, get_group_topics_db
from modules.log.logger import get_logs_by_count, get_logs_by_time, setup_in_memory_logger
from modules.log.startup_log import send_log_with_fallback

setup_in_memory_logger()

LOG_TOPIC_MAP = {
    "general": ("general_topic_id", "General Logs Topic"),
    "general logs": ("general_topic_id", "General Logs Topic"),
    "index": ("index_log_topic_id", "Index Logs Topic"),
    "index logs": ("index_log_topic_id", "Index Logs Topic"),
    "user": ("user_log_topic_id", "User Logs Topic"),
    "user logs": ("user_log_topic_id", "User Logs Topic"),
    "group": ("group_log_topic_id", "Group Logs Topic"),
    "group logs": ("group_log_topic_id", "Group Logs Topic"),
    "channel": ("channel_log_topic_id", "Channel Logs Topic"),
    "channel logs": ("channel_log_topic_id", "Channel Logs Topic"),
    "channels": ("channel_log_topic_id", "Channel Logs Topic"),
    "channels logs": ("channel_log_topic_id", "Channel Logs Topic"),
    "request logs": ("request_log_topic_id", "Request Logs Topic"),
    "error": ("error_log_topic_id", "Errors Topic"),
    "errors": ("error_log_topic_id", "Errors Topic"),
    "error logs": ("error_log_topic_id", "Errors Topic"),
}


async def _is_chat_or_bot_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return False
    if get_user_role_db(user.id) in ("Admin", "Owner"):
        return True
    if chat.type in ("group", "supergroup"):
        try:
            m = await context.bot.get_chat_member(chat.id, user.id)
            return m.status in ("administrator", "creator")
        except Exception:
            pass
    return False


async def settopic_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows Bot Admins or Group Chat Admins to assign search/request topics in groups, or log topics in the Log Group."""
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not chat or not user:
        return

    if chat.type not in ("group", "supergroup"):
        await msg.reply_text("⚠️ <code>/settopic</code> can only be used inside a group topic thread.", parse_mode="HTML")
        return

    if not await _is_chat_or_bot_admin(update, context):
        await msg.reply_text("⛔ Only Group Admins or Bot Admins can use <code>/settopic</code>.", parse_mode="HTML")
        return

    arg = " ".join(context.args).strip().lower() if context.args else ""
    thread_id = msg.message_thread_id or 1
    log_group_id = str(get_config("general_log_group_id", fallback_env="LOGGER_GROUP_ID") or "")
    is_log_group = str(chat.id) == log_group_id

    # 1. If used in Log Group (or with explicit log topic names) by Bot Admin/Owner
    if (arg in LOG_TOPIC_MAP or (is_log_group and arg == "request")) and get_user_role_db(user.id) in ("Admin", "Owner"):
        cfg_key, label = ("request_log_topic_id", "Request Logs Topic") if arg == "request" else LOG_TOPIC_MAP[arg]
        set_config(cfg_key, str(thread_id), "int", updated_by=user.id)
        set_config("general_log_group_id", str(chat.id), "channel", updated_by=user.id)
        await msg.reply_text(
            f"✅ <b>Log Topic Registered!</b>\n\n"
            f"📌 <b>Assigned:</b> <code>{label}</code>\n"
            f"🆔 <b>Chat ID:</b> <code>{chat.id}</code> | <b>Topic ID:</b> <code>{thread_id}</code>",
            parse_mode="HTML",
        )
        return

    # 2. Group Search / Request Topic assignment (available to any Group Admin!)
    if arg in ("search", "request"):
        set_group_topic_db(chat.id, chat.title or "Group", arg, thread_id, user.id)
        await msg.reply_text(
            f"✅ <b>Group {arg.capitalize()} Topic Registered!</b>\n\n"
            f"🏷 <b>Group:</b> {chat.title}\n"
            f"🧵 <b>{arg.capitalize()} Topic ID:</b> <code>{thread_id}</code>\n\n"
            f"<i>The bot will now handle {arg} commands in this topic and stay silent in non-designated topics.</i>",
            parse_mode="HTML",
        )
        return

    await msg.reply_text(
        "⚙️ <b>Usage of /settopic:</b>\n\n"
        "👥 <b>For Group Admins (Book Groups):</b>\n"
        "• <code>/settopic search</code> — Set current topic for book/audiobook searches\n"
        "• <code>/settopic request</code> — Set current topic for book requests\n\n"
        "📋 <b>For Bot Admins (inside Log Group):</b>\n"
        "• <code>/settopic general</code> | <code>/settopic index logs</code>\n"
        "• <code>/settopic user logs</code> | <code>/settopic group logs</code>\n"
        "• <code>/settopic channel logs</code> | <code>/settopic request logs</code>\n"
        "• <code>/settopic errors</code>",
        parse_mode="HTML",
    )


async def enforce_group_topic_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Restricts bot responses in multi-topic groups to only the registered Search Topic and Request Topic."""
    chat = update.effective_chat
    msg = update.effective_message
    if not chat or not msg or chat.type not in ("group", "supergroup"):
        return

    text = (msg.text or msg.caption or "").strip()
    cmd = text.split()[0].lstrip("/").split("@")[0].lower() if text.startswith("/") else ""

    # Always allow /settopic and /id so admins can configure topics
    if cmd in ("settopic", "id"):
        return

    g_cfg = get_group_topics_db(chat.id)
    if not g_cfg:
        return

    s_tid = int(g_cfg.get("search_topic_id") or 0)
    r_tid = int(g_cfg.get("request_topic_id") or 0)
    if s_tid == 0 and r_tid == 0:
        return

    cur_tid = msg.message_thread_id or 1

    if update.callback_query:
        data = update.callback_query.data or ""
        if cur_tid == s_tid and data.startswith(("file_dl_", "search_", "noop", "help_sec_search")):
            return
        if cur_tid == r_tid and data.startswith(("req_", "help_sec_requests")):
            return
        if cur_tid not in (s_tid, r_tid):
            raise ApplicationHandlerStop()
        return

    # In Search Topic: only allow search commands, search help, or plain search queries
    if cur_tid == s_tid:
        if cmd in ("search", "searchebook", "searchaudiobook", "help"):
            return
        if not cmd and len(text) >= 2:
            return
        raise ApplicationHandlerStop()

    # In Request Topic: only allow request commands or request help
    if cur_tid == r_tid:
        if cmd in ("request", "req", "help"):
            return
        if context.user_data.get("manual_req_wizard"):
            return
        raise ApplicationHandlerStop()

    # Any other topic in a configured multi-topic group -> stay completely silent
    raise ApplicationHandlerStop()


async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    role = get_user_role_db(user_id)
    if role not in ("Admin", "Owner"):
        await update.effective_message.reply_text("⛔ Access denied.")
        return

    args = context.args
    if not args:
        log_content, filename = get_logs_by_count(20), "logs_last_20.txt"
    else:
        param = args[0].lower()
        if param.endswith("m") and param[:-1].isdigit():
            mins = int(param[:-1])
            log_content, filename = get_logs_by_time(mins), f"logs_last_{mins}_min.txt"
        elif param.isdigit():
            count = min(1000, int(param))
            log_content, filename = get_logs_by_count(count), f"logs_last_{count}.txt"
        else:
            await update.effective_message.reply_text("⚠️ Usage: <code>/log</code>, <code>/log 50</code>, or <code>/log 15m</code>", parse_mode="HTML")
            return

    temp_path = f"/tmp/{filename}"
    with open(temp_path, "w") as tf:
        tf.write(log_content)
    with open(temp_path, "rb") as tf:
        await update.effective_message.reply_document(document=tf, filename=filename, caption=f"📋 <b>System Logs</b> ({role})", parse_mode="HTML")
    if os.path.exists(temp_path):
        os.remove(temp_path)


async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if not result:
        return
    chat = result.chat
    new_st, old_st = result.new_chat_member.status, result.old_chat_member.status
    actor = result.from_user
    actor_str = f"{actor.full_name} (<code>{actor.id}</code>)" if actor else "System"
    topic_key = "group_log_topic_id" if chat.type in ("group", "supergroup") else ("channel_log_topic_id" if chat.type == "channel" else "general_topic_id")
    msg = (
        f"📢 <b>Bot Status Changed in {chat.type.capitalize()}</b>\n\n"
        f"🏷 <b>Title:</b> {chat.title or 'Private'}\n"
        f"🆔 <b>Chat ID:</b> <code>{chat.id}</code>\n"
        f"🔄 <b>Status:</b> <code>{old_st} -> {new_st}</code>\n"
        f"👤 <b>By:</b> {actor_str}"
    )
    await send_log_with_fallback(context.bot, msg, "general_log_group_id", topic_key)
