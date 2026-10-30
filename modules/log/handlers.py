from modules.database.user_db import register_chat_db
import os
import tempfile
from telegram import Update
from telegram.ext import ContextTypes
from config import log_topic, logger_group_id, max_log_lines
from modules.database.user_db import get_user_role_db, is_admin_or_creator
from modules.log.logger import get_logs_by_count, get_logs_by_time, setup_in_memory_logger

setup_in_memory_logger()


async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin_or_creator(user_id):
        await update.message.reply_text("⛔ You do not have permission to access system logs.")
        return
    role = get_user_role_db(user_id)
    args = context.args
    log_content = ""
    filename = "mastermind_logs.txt"
    if not args:
        log_content = get_logs_by_count(10)
        filename = "logs_last_10.txt"
    else:
        param = args[0].lower()
        if param.endswith("m"):
            try:
                mins = int(param[:-1])
                log_content = get_logs_by_time(mins)
                filename = f"logs_last_{mins}_min.txt"
            except ValueError:
                await update.message.reply_text("⚠️ Invalid time format. Use e.g., `/log 10m`", parse_mode="Markdown")
                return
        else:
            try:
                count = int(param)
                cap = max_log_lines()
                if count > cap:
                    count = cap
                log_content = get_logs_by_count(count)
                filename = f"logs_last_{count}.txt"
            except ValueError:
                await update.message.reply_text("⚠️ Invalid argument. Use a number (e.g., `/log 50`) or duration (e.g., `/log 10m`).", parse_mode="Markdown")
                return
    temp_file_path = os.path.join(tempfile.gettempdir(), filename)
    with open(temp_file_path, "w", encoding="utf-8") as tf:
        tf.write(log_content)
    with open(temp_file_path, "rb") as tf:
        await update.message.reply_document(
            document=tf,
            filename=filename,
            caption=f"📋 <b>Memory Logs Generated Successfully</b>\nRequested by: <code>{role}</code>",
            parse_mode="HTML",
        )
    if os.path.exists(temp_file_path):
        os.remove(temp_file_path)


async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if not result:
        return
    chat = result.chat
    new_status = result.new_chat_member.status
    old_status = result.old_chat_member.status
    log_group_id = logger_group_id()
    if not log_group_id:
        return
    chat_type = chat.type
    chat_title = chat.title
    chat_username = f"@{chat.username}" if chat.username else "No Username"
    chat_id = chat.id
    actor_user = result.from_user
    actor_name = actor_user.full_name if actor_user else "Unknown / System"
    actor_id = actor_user.id if actor_user else "N/A"
    topic_id = log_topic("GROUP") if chat_type in ["group", "supergroup"] else (log_topic("CHANNEL") if chat_type == "channel" else None)
    if not topic_id:
        return
    was_added = old_status in ["left", "restricted", "kicked"] and new_status in ["member", "administrator"]
    was_removed = old_status in ["member", "administrator"] and new_status in ["left", "kicked"]
    was_promoted = old_status == "member" and new_status == "administrator"
    was_demoted = old_status == "administrator" and new_status == "member"
    permission_changed = old_status == "administrator" and new_status == "administrator"
    if not (was_added or was_removed or was_promoted or was_demoted or permission_changed):
        return
    if was_added:
        log_label = "👥 **Bot Added to Group/Supergroup**" if chat_type != "channel" else "📢 **Bot Added to Channel**"
    elif was_removed:
        log_label = "❌ **Bot Removed / Left Chat**"
    elif was_promoted:
        log_label = "👑 **Bot Promoted to Administrator**"
    elif was_demoted:
        log_label = "🔽 **Bot Demoted from Administrator**"
    elif permission_changed:
        log_label = "⚙️ **Bot Admin Permissions Changed**"
    else:
        return
    role_description = "👑 Administrator" if new_status == "administrator" else "Regular Member"
    permissions_list = []
    # Register chat in database for broadcasts
    register_chat_db(chat_id, chat_type, chat_title, chat.username)

    perm_mapping = {
        "can_post_messages": "📝 Post Messages",
        "can_edit_messages": "✏️ Edit Messages",
        "can_delete_messages": "🗑 Delete Messages",
        "can_pin_messages": "📌 Pin Messages",
        "can_invite_users": "🔗 Invite Users",
        "can_change_info": "ℹ️ Change Info",
        "can_manage_topics": "🧵 Manage Topics",
        "can_manage_video_chats": "🎙 Manage Video Chats",
        "can_promote_members": "👑 Add Admins",
    }
    new_member = result.new_chat_member
    perms_lines = []
    if new_status == "administrator":
        for attr, label in perm_mapping.items():
            val = "✅" if getattr(new_member, attr, False) else "❌"
            perms_lines.append(f"• {label}: {val}")

    perms_str = "\n".join(perms_lines) if perms_lines else "None / Default"
    log_message = (
        f"{log_label}\n\n"
        f"🏷 **Title:** {chat_title}\n"
        f"🆔 **Chat ID:** `{chat_id}`\n"
        f"🔗 **Username:** {chat_username}\n"
        f"🌐 **Type:** {chat_type.capitalize()}\n"
        f"🛡 **Bot Role:** {role_description}\n"
        f"👤 **Triggered By:** {actor_name} (`{actor_id}`)\n"
    )
    if new_status == "administrator":
        log_message += f"\n📋 **Permissions:**\n{perms_str}\n"
    try:
        kwargs = {
            "chat_id": int(log_group_id),
            "text": log_message,
            "parse_mode": "Markdown",
            "message_thread_id": int(topic_id),
        }
        await context.bot.send_message(**kwargs)
    except Exception as e:
        print(f"❌ Log error: {e}")
