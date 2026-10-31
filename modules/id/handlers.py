import html
from telegram import Update
from telegram.ext import ContextTypes
from modules.utility.rich_ui import tg_button_html, tg_button_row_html

_SEEN_CHANNEL_IDS: set[tuple[int, int]] = set()


async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat:
        return

    # Deduplicate when both Main Bot and Helper Bot are in the same channel
    if chat.type == "channel":
        key = (int(chat.id), int(message.message_id))
        if key in _SEEN_CHANNEL_IDS:
            return
        _SEEN_CHANNEL_IDS.add(key)
        if len(_SEEN_CHANNEL_IDS) > 500:
            _SEEN_CHANNEL_IDS.clear()

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
        topic_lines.append(f"• 🧵 <b>Topic ID:</b> <mark>{thread_id}</mark>")
        topic_lines.append(f"• 📌 <b>Topic Name:</b> {html.escape(topic_name)}")

    reply_to = message.reply_to_message
    args = context.args

    if args:
        target_username = args[0].lstrip("@")
        lines = [
            "ℹ️ <b>Username Lookup</b>",
            f"• <b>Target Username:</b> <mark>@{html.escape(target_username)}</mark>",
            f"• 💬 <b>Chat Name:</b> {html.escape(chat_title)}{chat_uname}",
            f"• 🏷️ <b>Chat ID:</b> <code>{chat.id}</code>",
            f"• 🌐 <b>Chat Type:</b> <mark>{chat_type}</mark>",
        ]
        if topic_lines:
            lines.extend(topic_lines)
        lines.append("")
        lines.append(
            tg_button_row_html([
                tg_button_html(f"👤 Open @{target_username}", url=f"https://t.me/{target_username}", style="primary"),
                tg_button_html("📋 Copy Chat ID", copy_text=str(chat.id), style="success"),
            ])
        )
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
            f"• 🌐 <b>Chat Type:</b> <mark>{chat_type}</mark>",
        ]
        if topic_lines:
            lines.extend(topic_lines)
        btn_row = [tg_button_html("📋 Copy User ID", copy_text=str(replied_user.id), style="success")]
        if replied_user.username:
            btn_row.insert(0, tg_button_html(f"👤 @{replied_user.username}", url=f"https://t.me/{replied_user.username}", style="primary"))
        lines.append("")
        lines.append(tg_button_row_html(btn_row))
        await message.reply_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)
        return

    lines = ["📊 <b>Identification</b>"]
    # Only include User Name and User ID when a real sender user object is present.
    # In channels (or anonymous channel posts where user cannot be detected), omit User Name and User ID completely.
    if user:
        u_name = html.escape(user.full_name)
        u_uname = f" (@{user.username})" if user.username else ""
        lines.append(f"• 👤 <b>User Name:</b> {u_name}{u_uname}")
        lines.append(f"• 🆔 <b>User ID:</b> <code>{user.id}</code>")

    lines.extend([
        f"• 💬 <b>Chat Name:</b> {html.escape(chat_title)}{chat_uname}",
        f"• 🏷️ <b>Chat ID:</b> <code>{chat.id}</code>",
        f"• 🌐 <b>Chat Type:</b> <mark>{chat_type}</mark>",
    ])
    if topic_lines:
        lines.extend(topic_lines)

    copy_btns = [tg_button_html("📋 Copy Chat ID", copy_text=str(chat.id), style="primary")]
    if user:
        copy_btns.insert(0, tg_button_html("📋 Copy User ID", copy_text=str(user.id), style="success"))
    lines.append("")
    lines.append(tg_button_row_html(copy_btns))

    response_text = "\n".join(lines)
    try:
        await message.reply_text(response_text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        await context.bot.send_message(chat_id=chat.id, text=response_text, parse_mode="HTML", disable_web_page_preview=True)
