import html
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
    scope_desc = "Last 10 lines"
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
                scope_desc = f"Last {mins} minutes"
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
                scope_desc = f"Last {count} lines"
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
            caption=(
                f"📋 <b>Memory Logs Generated Successfully</b>\n"
                f"• File: <code>{html.escape(filename)}</code>\n"
                f"• Scope: <code>{html.escape(scope_desc)}</code>\n"
                f"• Requested by: <code>{html.escape(str(role))}</code>"
            ),
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
    chat_title = chat.title or "Untitled Chat"
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
        log_label = "👥 <b>Bot Added to Group/Supergroup</b>" if chat_type != "channel" else "📢 <b>Bot Added to Channel</b>"
    elif was_removed:
        log_label = "❌ <b>Bot Removed / Left Chat</b>"
    elif was_promoted:
        log_label = "👑 <b>Bot Promoted to Administrator</b>"
    elif was_demoted:
        log_label = "🔽 <b>Bot Demoted from Administrator</b>"
    elif permission_changed:
        log_label = "⚙️ <b>Bot Admin Permissions Changed</b>"
    else:
        return
    role_description = "👑 Administrator" if new_status == "administrator" else "Regular Member"
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

    info_table = (
        "<table striped>"
        "<tr><th>Field</th><th>Details</th></tr>"
        f"<tr><td>🏷 <b>Title</b></td><td>{html.escape(chat_title)}</td></tr>"
        f"<tr><td>🆔 <b>Chat ID</b></td><td><code>{chat_id}</code></td></tr>"
        f"<tr><td>🔗 <b>Username</b></td><td>{html.escape(chat_username)}</td></tr>"
        f"<tr><td>🌐 <b>Type</b></td><td>{html.escape(chat_type.capitalize())}</td></tr>"
        f"<tr><td>🛡 <b>Bot Role</b></td><td>{html.escape(role_description)}</td></tr>"
        f"<tr><td>👤 <b>Triggered By</b></td><td>{html.escape(actor_name)} (<code>{actor_id}</code>)</td></tr>"
        "</table>"
    )
    parts = [log_label, "", info_table]

    if new_status == "administrator":
        perm_rows = []
        for attr, label in perm_mapping.items():
            val = "✅ Allowed" if getattr(new_member, attr, False) else "❌ Off"
            perm_rows.append(f"<tr><td>{label}</td><td>{val}</td></tr>")
        parts.extend([
            "",
            "📋 <b>Administrator Permissions</b>",
            "<table striped><tr><th>Permission</th><th>Status</th></tr>" + "".join(perm_rows) + "</table>",
        ])

    log_message = "\n".join(parts)
    try:
        kwargs = {
            "chat_id": int(log_group_id),
            "text": log_message,
            "parse_mode": "HTML",
            "message_thread_id": int(topic_id),
        }
        await context.bot.send_message(**kwargs)
    except Exception as e:
        print(f"❌ Log error: {e}")
