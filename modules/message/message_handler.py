from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

async def handle_normal_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = (
        "<blockquote expandable>"
        "🤖 <b>Mastermind Notice</b>\n\n"
        "I am just a telegram bot, I can't chat with you! "
        "Tap the button below to see what I can do."
        "</blockquote>"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("📖 Help Menu", callback_data='help_button')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
