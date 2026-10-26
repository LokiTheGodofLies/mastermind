from modules.start.start_handler import menu_callback_router
from modules.help.handlers import help_command
from modules.editscript.handlers import editscript_command, editscript_callback
from telegram.request import HTTPXRequest
from modules.log.startup_log import send_startup_notification
from modules.stats.handlers import stats_command
from modules.id.handlers import id_command
from modules.search.handlers import search_command, search_callback_handler
from modules.request.handlers import request_command, request_callback_handler
import os
import logging
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ChatMemberHandler,
    filters,
    ContextTypes,
    ApplicationHandlerStop
)

def load_env():
    try:
        with open("env.txt", "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()
        print("✅ Environment variables loaded from env.txt successfully.")
    except FileNotFoundError:
        print("❌ Error: env.txt file not found!")

load_env()

from modules.ban.ban import check_user_access
from modules.database.user_db import init_user_db, get_user_role_db
from modules.start.start_handler import start_command
from modules.help_menu.help_handler import help_command, help_button_callback
from modules.ban.handlers import ban_command, ban_pm_command, ban_support_command, unban_command
from modules.allowance.allowance import quota_command, gift_command, refer_command
from modules.log.handlers import log_command, handle_my_chat_member
from modules.log.logger import setup_in_memory_logger
from modules.support.support import support_command, support_callback_handler
from modules.indexing.book_index import handle_book_indexing

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

async def enforce_ban_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.effective_chat:
        return
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type

    if get_user_role_db(user_id) == "Owner":
        return

    is_allowed, warning_message = check_user_access(user_id, chat_id, chat_type)
    if not is_allowed:
        if update.message:
            await update.message.reply_text(warning_message)
        elif update.callback_query:
            await update.callback_query.answer(warning_message, show_alert=True)
        raise ApplicationHandlerStop

if __name__ == "__main__":
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Please ensure your TELEGRAM_BOT_TOKEN is set inside env.txt")
        exit(1)

    setup_in_memory_logger()
    init_user_db()
    print("✅ Database and tables initialized successfully.")
    print(f"🔍 DEBUG: STORAGE_GROUP_ID from environment is -> {os.getenv("STORAGE_GROUP_ID")}")

    application = ApplicationBuilder().token(token).post_init(send_startup_notification).build()
    application.add_handler(MessageHandler(filters.ALL, enforce_ban_middleware), group=-1)

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("support", support_command))
    application.add_handler(CallbackQueryHandler(help_button_callback))
    application.add_handler(CallbackQueryHandler(support_callback_handler))
    application.add_handler(CommandHandler("quota", quota_command))
    application.add_handler(CommandHandler("gift", gift_command))
    application.add_handler(CommandHandler("refer", refer_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("ban_pm", ban_pm_command))
    application.add_handler(CommandHandler("ban_support", ban_support_command))
    application.add_handler(CommandHandler("unban", unban_command))
    application.add_handler(CommandHandler("log", log_command))
    application.add_handler(CommandHandler(["stats", "stat", "sysinfo"], stats_command))
    application.add_handler(CommandHandler("id", id_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("request", request_command))
    
    # Callback query handlers for search and request quizzes
    application.add_handler(CallbackQueryHandler(search_callback_handler, pattern="^(search_start_quiz|search_ans_)"))
    application.add_handler(CallbackQueryHandler(request_callback_handler, pattern="^(request_start_quiz|request_ans_)"))

    application.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_book_indexing))

    print("🤖 Mastermind bot is up and running...")

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        application.add_handler(CommandHandler("editscript", editscript_command))
    application.add_handler(CallbackQueryHandler(editscript_callback, pattern="^es_"))

    application.run_polling()
