import os
import asyncio
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

# Import from exact module paths
from modules.start.start_handler import start_command
from modules.help.handlers import help_command, help_button_callback
from modules.support.handlers import support_command, support_callback_handler
from modules.allowance.handlers import quota_command, gift_command, refer_command
from modules.ban.handlers import ban_command, ban_pm_command, enforce_ban_middleware
from modules.log.logger import setup_in_memory_logger
from modules.database.user_db import init_user_db
from modules.request.handlers import request_command, request_callback_handler, request_deeplink_handler
from modules.id.handlers import id_command
from modules.stats.handlers import stats_command
from modules.search.handlers import search_command, search_callback_handler

logger = logging.getLogger(__name__)

def load_env():
    env_path = "env.txt"
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key.strip()] = value.strip()
        print("✅ Environment variables loaded from env.txt successfully.")
    else:
        print("⚠️ env.txt not found, relying on system environment variables.")

async def send_startup_log(application):
    logger_group_id = os.getenv("LOGGER_GROUP_ID")
    if logger_group_id:
        try:
            restart_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_text = "🔄 Bot Restarted Successfully\n\n🤖 Mastermind is now online.\n⏱️ Restarted at " + restart_time
            await application.bot.send_message(
                chat_id=int(logger_group_id),
                text=log_text,
                parse_mode="HTML"
            )
            print("✅ Restart log sent to log group successfully.")
        except Exception as e:
            print(f"Failed to send startup log: {e}")

def main():
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    load_env()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Please ensure your TELEGRAM_BOT_TOKEN is set inside env.txt")
        exit(1)

    logging.basicConfig(level=logging.INFO)
    setup_in_memory_logger()
    init_user_db()
    print("✅ Database and tables initialized successfully.")
    print(f"🔍 DEBUG: STORAGE_GROUP_ID from environment is -> {os.getenv('STORAGE_GROUP_ID')}")

    # Build application
    application = ApplicationBuilder().token(token).build()

    # Register middleware and handlers inside main() scope
    application.add_handler(MessageHandler(filters.ALL, enforce_ban_middleware), group=-1)

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("support", support_command))
    application.add_handler(CallbackQueryHandler(help_button_callback, pattern="^(quota|bot_owner|help_menu|search_menu|stats_menu|start_menu)$"))
    application.add_handler(CallbackQueryHandler(support_callback_handler, pattern="^support_"))
    application.add_handler(CommandHandler("quota", quota_command))
    application.add_handler(CommandHandler("gift", gift_command))
    application.add_handler(CommandHandler("refer", refer_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("ban_pm", ban_pm_command))
    
    # ID module handler
    # ID module handlers for standard chats and channels
    application.add_handler(CommandHandler("id", id_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CallbackQueryHandler(search_callback_handler, pattern="^(file_dl_|search_page_|join_search_group_quiz|generate_group_invite)"))
    application.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.Regex(r"^/id(?:@\w+)?$"), id_command))

    # Request module handlers
    application.add_handler(CommandHandler("request", request_command))
    
    application.add_handler(CommandHandler("req", request_command))
    application.add_handler(CallbackQueryHandler(request_callback_handler, pattern="^req_"))

    print("🤖 Mastermind bot is up and running...")

    # Send startup log upon booting
    if application.job_queue:
        application.job_queue.run_once(lambda ctx: asyncio.create_task(send_startup_log(application)), when=1)
    else:
        # Fallback if job_queue isn't active
        async def post_init(app):
            await send_startup_log(app)
        application.post_init = post_init
    
            # Ensure only a single active polling loop runs
    if not application.updater or not application.updater.running:
            application.add_handler(CommandHandler("start", request_deeplink_handler), group=-2)
    application.run_polling()


if __name__ == "__main__":
    main()
