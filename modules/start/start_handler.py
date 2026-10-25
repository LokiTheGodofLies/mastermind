from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    
    message = (
        f"Hi <b>{user_name}</b>, I am just a simple telegram bot! 👋\n\n"
        "Tap the buttons below to see my help menu or reach out to my owner."
    )
    
    # Replace 12345678 with your actual numeric Telegram user ID
    keyboard = [
        [
            InlineKeyboardButton("📖 Help Menu", callback_data='help_button'),
            InlineKeyboardButton("👑 Bot Owner", url='tg://user?id=12345678')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
