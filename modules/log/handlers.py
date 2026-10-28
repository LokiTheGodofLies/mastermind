import os
import tempfile
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

ADMIN_PERM_MAP = {
    "can_post_messages": "Post Messages",
    "can_edit_messages": "Edit Messages",
    "can_delete_messages": "Delete Messages",
    "can_manage_topics": "Manage Topics",
    "can_invite_users": "Invite Users via Link",
    "can_restrict_members": "Restrict Members",
    "can_promote_members": "Add New Admins",
    "can_change_info": "Change Chat Info",
    "can_manage_chat": "Manage Chat",
    "can_manage_video_chats": "Manage Video Chats",
}


async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if not result:
        return

    chat = result.chat
    new_m, old_m = result.new_chat_member, result.old_chat_member
    new_st, old_st = new_m.status, old_m.status
    chat_type = chat.type
    is_channel = chat_type == "channel"
    actor = result.from_user
    actor_str = f"{actor.full_name} (<code>{actor.id}</code>)" if actor else "System"

    was_added = old_st in ("left", "kicked", "restricted") and new_st in ("member", "administrator")
    was_removed = old_st in ("member", "administrator") and new_st in ("left", "kicked")
    was_promoted = old_st == "member" and new_st == "administrator"
    was_demoted = old_st == "administrator" and new_st == "member"
    perm_changed = old_st == "administrator" and new_st == "administrator"

    if was_added:
        log_label = f"📢 <b>Bot Added to {'Channel' if is_channel else 'Group'} as Administrator</b>" if new_st == "administrator" else f"👥 <b>Bot Added to {'Channel' if is_channel else 'Group'}</b>"
    elif was_removed:
        log_label = f"❌ <b>Bot Removed from {'Channel' if is_channel else 'Group'}</b>"
    elif was_promoted:
        log_label = "👑 <b>Bot Promoted to Administrator</b>"
    elif was_demoted:
        log_label = "🔽 <b>Bot Demoted from Administrator</b>"
    elif perm_changed:
        log_label = "⚙️ <b>Bot Admin Permissions Updated</b>"
    else:
        log_label = f"📢 <b>Bot Status Updated in {'Channel' if is_channel else 'Group'}</b>"

    # Extract granular admin permissions
    perms_lines = []
    if new_st == "administrator":
        for attr, label in ADMIN_PERM_MAP.items():
            val = getattr(new_m, attr, None)
            if val is not None:
                icon = "✅" if val else "❌"
                perms_lines.append(f"  {icon} {label}")

    perms_block = "\n".join(perms_lines) if perms_lines else "  • Default / Restricted"

    topic_key = "channel_log_topic_id" if is_channel else "group_log_topic_id"
    msg = (
        f"{log_label}\n\n"
        f"🏷 <b>Title:</b> {chat.title or 'Private'}\n"
        f"🆔 <b>Chat ID:</b> <code>{chat.id}</code>\n"
        f"🌐 <b>Type:</b> <code>{chat_type.capitalize()}</code>\n"
        f"🛡 <b>Bot Role:</b> <code>{new_st.capitalize()}</code>\n"
        f"👤 <b>Action By:</b> {actor_str}\n\n"
        f"📋 <b>Permissions:</b>\n{perms_block}"
    )
    await send_log_with_fallback(context.bot, msg, "general_log_group_id", topic_key)


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
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not chat or not user or chat.type not in ("group", "supergroup"):
        return

    if not await _is_chat_or_bot_admin(update, context):
        await msg.reply_text("⛔ Only Group Admins or Bot Admins can use <code>/settopic</code>.", parse_mode="HTML")
        return

    arg = " ".join(context.args).strip().lower() if context.args else ""
    thread_id = msg.message_thread_id or 1
    log_group_id = str(get_config("general_log_group_id", fallback_env="LOGGER_GROUP_ID") or "")
    is_log_group = str(chat.id) == log_group_id

    if (arg in LOG_TOPIC_MAP or (is_log_group and arg == "request")) and get_user_role_db(user.id) in ("Admin", "Owner"):
        cfg_key, label = ("request_log_topic_id", "Request Logs Topic") if arg == "request" else LOG_TOPIC_MAP[arg]
        set_config(cfg_key, str(thread_id), "int", updated_by=user.id)
        set_config("general_log_group_id", str(chat.id), "channel", updated_by=user.id)
        await msg.reply_text(f"✅ <b>Log Topic Registered!</b>\n\n📌 <b>Assigned:</b> <code>{label}</code>\n🆔 <b>Topic ID:</b> <code>{thread_id}</code>", parse_mode="HTML")
        return

    if arg in ("search", "request"):
        set_group_topic_db(chat.id, chat.title or "Group", arg, thread_id, user.id)
        await msg.reply_text(f"✅ <b>Group {arg.capitalize()} Topic Registered!</b>\n\n🏷 <b>Group:</b> {chat.title}\n🧵 <b>Topic ID:</b> <code>{thread_id}</code>", parse_mode="HTML")
        return

    await msg.reply_text("⚙️ <b>Usage:</b>\n• <code>/settopic search</code> | <code>/settopic request</code>\n• <code>/settopic index logs</code> | <code>/settopic channel logs</code>", parse_mode="HTML")


async def enforce_group_topic_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    msg = update.effective_message
    if not chat or not msg or chat.type not in ("group", "supergroup"):
        return
    text = (msg.text or msg.caption or "").strip()
    cmd = text.split()[0].lstrip("/").split("@")[0].lower() if text.startswith("/") else ""
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
    if cur_tid == s_tid and (cmd in ("search", "searchebook", "searchaudiobook", "help") or len(text) >= 2):
        return
    if cur_tid == r_tid and (cmd in ("request", "req", "help") or context.user_data.get("manual_req_wizard")):
        return
    raise ApplicationHandlerStop()


async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    role = get_user_role_db(user_id)
    if role not in ("Admin", "Owner"):
        await update.effective_message.reply_text("⛔ Access denied.")
        return
    args = context.args
    count = min(1000, int(args[0])) if (args and args[0].isdigit()) else 20
    log_content = get_logs_by_count(count)
    temp_path = os.path.join(tempfile.gettempdir(), f"logs_{count}.txt")
    with open(temp_path, "w") as tf:
        tf.write(log_content)
    with open(temp_path, "rb") as tf:
        await update.effective_message.reply_document(document=tf, filename=f"logs_{count}.txt", caption=f"📋 <b>System Logs</b> ({role})", parse_mode="HTML")
    if os.path.exists(temp_path):
        os.remove(temp_path)
