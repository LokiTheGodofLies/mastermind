import logging
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    filters, 
    ContextTypes, 
    ApplicationHandlerStop
)

# Import ban access check and middleware
from modules.ban.ban import check_user_access
from modules.database.user_db import init_user_db, get_user_role_db

# Import handlers from our modular folders
from modules.start.start import start_command
from modules.help_menu.help_handler import help_command, help_button_callback
from modules.ban.handlers import ban_command, ban_pm_command, ban_support_command, unban_command
from modules.allowance.handlers import quota_command, gift_command, refer_command

# Set logging level to WARNING to keep your terminal clean and quiet
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING
)

def load_token():
    """Reads the bot token securely from env.txt"""
    try:
        with open("env.txt", "r") as f:
            for line in f:
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        print("Error: env.txt file not found! Please create it.")
    return None

async def enforce_ban_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Global middleware that intercepts messages and blocks banned users/chats."""
    if not update.effective_user or not update.effective_chat:
        return
        
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type  # 'private', 'group', 'supergroup', etc.
    
    # Skip check for Owner (Owner can never be blocked)
    if get_user_role_db(user_id) == 'Owner':
        return

    is_allowed, warning_message = check_user_access(user_id, chat_id, chat_type)
    
    if not is_allowed:
        # Send warning and stop propagation to other handlers
        await update.message.reply_text(warning_message)
        raise ApplicationHandlerStop # Stops python-telegram-bot from running subsequent handlers

if __name__ == '__main__':
    token = load_token()
    if not token:
        print("Please ensure your TELEGRAM_BOT_TOKEN is set inside env.txt")
        exit(1)

    # Initialize SQLite databases & tables on startup
    init_user_db()
    print("✅ Database and tables initialized successfully.")

    # Build the application using the token
    application = ApplicationBuilder().token(token).build()

    # Register the ban enforcement middleware FIRST (group -1 ensures it intercepts before any command handlers)
    application.add_handler(MessageHandler(filters.ALL & ~filters.StatusUpdate.ALL, enforce_ban_middleware), group=-1)

    # Register Command Handlers & Callbacks
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CallbackQueryHandler(help_button_callback))
    application.add_handler(CommandHandler('quota', quota_command))
    application.add_handler(CommandHandler('gift', gift_command))
    application.add_handler(CommandHandler('refer', refer_command))
    application.add_handler(CommandHandler('ban', ban_command))
    application.add_handler(CommandHandler('ban_pm', ban_pm_command))
    application.add_handler(CommandHandler('ban_support', ban_support_command))
    application.add_handler(CommandHandler('unban', unban_command))

    # Optional message handlers
    # application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_normal_text))

    print("🤖 Mastermind bot is up and running...")
    
    # Fix for Python 3.14 event loop compatibility in Termux
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Start polling for messages safely
    application.run_polling()
    
