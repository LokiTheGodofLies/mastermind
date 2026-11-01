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
    topic_rows = []
    if thread_id:
        topic_name = "General" if thread_id == 1 else f"Topic #{thread_id}"
        reply_msg = message.reply_to_message
        if reply_msg and getattr(reply_msg, "forum_topic_created", None):
            topic_name = reply_msg.forum_topic_created.name
        topic_rows.append(f"<tr><td>🧵 <b>Topic ID</b></td><td><code>{thread_id}</code></td></tr>")
        topic_rows.append(f"<tr><td>📌 <b>Topic Name</b></td><td>{html.escape(topic_name)}</td></tr>")

    reply_to = message.reply_to_message
    args = context.args

    if args:
        target_username = args[0].lstrip("@")
        rows = [
            f"<tr><td>🎯 <b>Target Username</b></td><td><code>@{html.escape(target_username)}</code></td></tr>",
            f"<tr><td>💬 <b>Chat Name</b></td><td>{html.escape(chat_title)}{html.escape(chat_uname)}</td></tr>",
            f"<tr><td>🏷️ <b>Chat ID</b></td><td><code>{chat.id}</code></td></tr>",
            f"<tr><td>🌐 <b>Chat Type</b></td><td><code>{html.escape(chat_type)}</code></td></tr>",
            *topic_rows,
        ]
        table_html = "<table striped><tr><th>Field</th><th>Value</th></tr>" + "".join(rows) + "</table>"
        btns = tg_button_row_html([
            tg_button_html(f"👤 Open @{target_username}", url=f"https://t.me/{target_username}", style="success"),
            tg_button_html("📋 Copy Chat ID", copy_text=str(chat.id), style="danger"),
        ])
        await message.reply_text(f"ℹ️ <b>Username Lookup</b>\n\n{table_html}\n\n{btns}", parse_mode="HTML")
        return

    if reply_to and reply_to.from_user:
        replied_user = reply_to.from_user
        r_uname = f" (@{replied_user.username})" if replied_user.username else ""
        rows = [
            f"<tr><td>👤 <b>Name</b></td><td><a href=\"tg://user?id={replied_user.id}\">{html.escape(replied_user.full_name)}</a>{html.escape(r_uname)}</td></tr>",
            f"<tr><td>🆔 <b>User ID</b></td><td><code>{replied_user.id}</code></td></tr>",
            f"<tr><td>💬 <b>Chat Name</b></td><td>{html.escape(chat_title)}{html.escape(chat_uname)}</td></tr>",
            f"<tr><td>🏷️ <b>Chat ID</b></td><td><code>{chat.id}</code></td></tr>",
            f"<tr><td>🌐 <b>Chat Type</b></td><td><code>{html.escape(chat_type)}</code></td></tr>",
            *topic_rows,
        ]
        table_html = "<table striped><tr><th>Field</th><th>Value</th></tr>" + "".join(rows) + "</table>"
        btn_row = [tg_button_html("📋 Copy User ID", copy_text=str(replied_user.id), style="success")]
        if replied_user.username:
            btn_row.insert(0, tg_button_html(f"👤 @{replied_user.username}", url=f"https://t.me/{replied_user.username}", style="danger"))
        await message.reply_text(
            f"👤 <b>Replied User Details</b>\n\n{table_html}\n\n{tg_button_row_html(btn_row)}",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return

    rows = []
    # Only include User Name and User ID when a real sender user object is present.
    # In channels (or anonymous channel posts where user cannot be detected), omit User Name and User ID completely.
    if user:
        u_name = html.escape(user.full_name)
        u_uname = f" (@{user.username})" if user.username else ""
        rows.append(f"<tr><td>👤 <b>User Name</b></td><td>{u_name}{html.escape(u_uname)}</td></tr>")
        rows.append(f"<tr><td>🆔 <b>User ID</b></td><td><code>{user.id}</code></td></tr>")

    rows.extend([
        f"<tr><td>💬 <b>Chat Name</b></td><td>{html.escape(chat_title)}{html.escape(chat_uname)}</td></tr>",
        f"<tr><td>🏷️ <b>Chat ID</b></td><td><code>{chat.id}</code></td></tr>",
        f"<tr><td>🌐 <b>Chat Type</b></td><td><code>{html.escape(chat_type)}</code></td></tr>",
        *topic_rows,
    ])
    table_html = "<table striped><tr><th>Field</th><th>Value</th></tr>" + "".join(rows) + "</table>"

    copy_btns = [tg_button_html("📋 Copy Chat ID", copy_text=str(chat.id), style="danger")]
    if user:
        copy_btns.insert(0, tg_button_html("📋 Copy User ID", copy_text=str(user.id), style="success"))

    response_text = f"📊 <b>Identification</b>\n\n{table_html}\n\n{tg_button_row_html(copy_btns)}"
    try:
        await message.reply_text(response_text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        await context.bot.send_message(chat_id=chat.id, text=response_text, parse_mode="HTML", disable_web_page_preview=True)
