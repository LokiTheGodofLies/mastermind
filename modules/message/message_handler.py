from configs import bot_name
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes


async def handle_normal_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    # Do not interrupt interactive /index setup flow in private chat
    if (context.user_data or {}).get("idx_flow"):
        return

    message = (
        "<blockquote expandable>"
        f"🤖 <b>{bot_name()} Notice</b>\n\n"
        "I am just a Telegram bot and cannot chat freely!\n\n"
        "• <b>Want to search?</b> Use the /search command and join our search group.\n"
        "• <b>Want to request?</b> Use the /request command and join our request group.\n"
        "• <b>Need help?</b> Use the /support command to contact support.\n\n"
        "Tap the buttons below to see options or view the help menu."
        "</blockquote>"
    )

    keyboard = [
        [
            InlineKeyboardButton("🔍 Search Group", callback_data="search_menu"),
            InlineKeyboardButton("📥 Request Group", callback_data="request_menu"),
        ],
        [
            InlineKeyboardButton("🛡️ Support", callback_data="support_start_quiz"),
            InlineKeyboardButton("📖 Help Menu", callback_data="help_button"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(message, parse_mode="HTML", reply_markup=reply_markup)
