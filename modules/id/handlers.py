from telegram import Update
from telegram.ext import ContextTypes

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    chat = message.chat
    user = message.from_user
    reply_to = message.reply_to_message

    # Check if a username argument was passed (e.g. /id @username or /id username)
    args = context.args
    if args:
        target_username = args[0].lstrip("@")
        # Try finding user via context or mention if available, else inform user
        await message.reply_text(
            f"ℹ️ <b>Username Lookup</b>\n"
            f"• <b>Target Username:</b> @{target_username}\n"
            f"<i>Note: Telegram bots can only resolve usernames if the user has interacted with the bot before or via cached chats.</i>",
            parse_mode="HTML"
        )
        return

    # Case 1: Replied to another user's message
    if reply_to and reply_to.from_user:
        replied_user = reply_to.from_user
        response_text = (
            f"👤 <b>Replied User Details</b>\n"
            f"• <b>Name:</b> {replied_user.full_name}\n"
            f"• <b>Username:</b> @{replied_user.username if replied_user.username else 'None'}\n"
            f"• <b>User ID:</b> <code>{replied_user.id}</code>\n"
            f"• <b>Message ID:</b> <code>{reply_to.message_id}</code>\n"
            f"• <b>Chat ID:</b> <code>{chat.id}</code>"
        )
        if message.is_topic_message:
            response_text += f"\n• <b>Topic ID:</b> <code>{message.message_thread_id}</code>"
        
        await message.reply_text(response_text, parse_mode="HTML")
        return

    # Case 2: Standard /id command (no args, no reply)
    response_text = (
        f"📊 <b>Chat & User Identification</b>\n\n"
        f"👤 <b>Your User ID:</b> <code>{user.id}</code>\n"
        f"💬 <b>Chat ID:</b> <code>{chat.id}</code>\n"
        f"🏷️ <b>Chat Type:</b> {chat.type.capitalize()}"
    )

    if message.is_topic_message and message.message_thread_id:
        response_text += f"\n🧵 <b>Topic ID:</b> <code>{message.message_thread_id}</code>"

    if reply_to:
        response_text += f"\n📌 <b>Replied Message ID:</b> <code>{reply_to.message_id}</code>"

    await message.reply_text(response_text, parse_mode="HTML")
