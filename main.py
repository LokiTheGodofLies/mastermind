import logging
import asyncio
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters

# Import handlers from our modular folders
from modules.start.start_handler import start_command
from modules.help_menu.help_handler import help_command, help_button_callback
from modules.message.message_handler import handle_normal_text

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

if __name__ == '__main__':
    token = load_token()
    if not token:
        print("Please ensure your TELEGRAM_BOT_TOKEN is set inside env.txt")
        exit(1)

    # Build the application using the token
    application = ApplicationBuilder().token(token).build()

    # Register handlers
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CallbackQueryHandler(help_button_callback))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_normal_text))

    print("Mastermind bot is up and running...")
    
    # Fix for Python 3.14 event loop compatibility in Termux
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Start polling for messages safely
    application.run_polling()
