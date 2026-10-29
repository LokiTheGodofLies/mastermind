import html
from telegram import Update
from telegram.ext import ContextTypes


async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat:
        return

    chat_title = chat.title if chat.title else (chat.full_name or "Private Chat")
    chat_uname = f" (@{chat.username})" if chat.username else ""
    chat_type = chat.type.capitalize()

    # Topic detection
    thread_id = getattr(message, "message_thread_id", None)
    topic_lines = []
    if thread_id:
        topic_name = "General" if thread_id == 1 else f"Topic #{thread_id}"
        reply_msg = message.reply_to_message
        if reply_msg and getattr(reply_msg, "forum_topic_created", None):
            topic_name = reply_msg.forum_topic_created.name
        topic_lines.append(f"• 🧵 <b>Topic ID:</b> <code>{thread_id}</code>")
        topic_lines.append(f"• 📌 <b>Topic Name:</b> {html.escape(topic_name)}")

    reply_to = message.reply_to_message
    args = context.args

    if args:
        target_username = args[0].lstrip("@")
        lines = [
            f"ℹ️ <b>Username Lookup</b>",
            f"• <b>Target Username:</b> @{html.escape(target_username)}",
            f"• 💬 <b>Chat Name:</b> {html.escape(chat_title)}{chat_uname}",
            f"• 🏷️ <b>Chat ID:</b> <code>{chat.id}</code>",
            f"• 🌐 <b>Chat Type:</b> {chat_type}",
        ]
        if topic_lines:
            lines.extend(topic_lines)
        await message.reply_text("\n".join(lines), parse_mode="HTML")
        return

    if reply_to and reply_to.from_user:
        replied_user = reply_to.from_user
        r_uname = f" (@{replied_user.username})" if replied_user.username else ""
        lines = [
            "👤 <b>Replied User Details</b>",
            f"• <b>Name:</b> <a href=\"tg://user?id={replied_user.id}\">{html.escape(replied_user.full_name)}</a>{r_uname}",
            f"• 🆔 <b>User ID:</b> <code>{replied_user.id}</code>",
            f"• 💬 <b>Chat Name:</b> {html.escape(chat_title)}{chat_uname}",
            f"• 🏷️ <b>Chat ID:</b> <code>{chat.id}</code>",
            f"• 🌐 <b>Chat Type:</b> {chat_type}",
        ]
        if topic_lines:
            lines.extend(topic_lines)
        await message.reply_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)
        return

    u_name = html.escape(user.full_name) if user else "Channel"
    u_uname = f" (@{user.username})" if user and user.username else ""
    user_id_str = f"<code>{user.id}</code>" if user else "<i>Channel Post</i>"
    lines = [
        "📊 <b>Identification</b>",
        f"• 👤 <b>User Name:</b> {u_name}{u_uname}",
        f"• 🆔 <b>User ID:</b> {user_id_str}",
        f"• 💬 <b>Chat Name:</b> {html.escape(chat_title)}{chat_uname}",
        f"• 🏷️ <b>Chat ID:</b> <code>{chat.id}</code>",
        f"• 🌐 <b>Chat Type:</b> {chat_type}",
    ]
    if topic_lines:
        lines.extend(topic_lines)

    response_text = "\n".join(lines)
    try:
        await message.reply_text(response_text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        await context.bot.send_message(chat_id=chat.id, text=response_text, parse_mode="HTML", disable_web_page_preview=True)
