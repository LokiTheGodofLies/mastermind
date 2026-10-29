import os
import asyncio
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

from modules.start.start_handler import start_command, menu_callback_router
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
from modules.indexing.index_command import index_command, index_callback, index_flow_handler
from modules.log.startup_log import send_startup_notification, error_handler, report_fatal_sync

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

    application = ApplicationBuilder().token(token).build()

    application.add_handler(MessageHandler(filters.ALL, enforce_ban_middleware), group=-1)

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("support", support_command))
    application.add_handler(CommandHandler("quota", quota_command))
    application.add_handler(CommandHandler("gift", gift_command))
    application.add_handler(CommandHandler("refer", refer_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("ban_pm", ban_pm_command))
    application.add_handler(CommandHandler("id", id_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("request", request_command))
    application.add_handler(CommandHandler("req", request_command))
    application.add_handler(CommandHandler("index", index_command))
    application.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.Regex(r"^/index(?:@\w+)?(?:\s|$)"), index_command))
    application.add_handler(CallbackQueryHandler(index_callback, pattern=r"^idx_(yes|no|apr|rej|cancel)_[0-9a-f]{8}$"))
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, index_flow_handler), group=1)

    application.add_handler(
        CallbackQueryHandler(
            menu_callback_router,
            pattern=r"^(help_button|help_menu|search_menu|stats_menu|start_menu|quota|quota_menu|bot_owner)$"
        )
    )
    application.add_handler(CallbackQueryHandler(support_callback_handler, pattern="^support_"))
    application.add_handler(CallbackQueryHandler(search_callback_handler, pattern="^(file_dl_|search_page_|join_search_group_quiz|generate_group_invite)"))
    application.add_handler(CallbackQueryHandler(request_callback_handler, pattern="^req_"))
    application.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.Regex(r"^/id(?:@\w+)?$"), id_command))

    print("🤖 Mastermind bot is up and running...")

    application.add_error_handler(error_handler)

    async def post_init(app):
        await send_startup_notification(app)
    application.post_init = post_init

    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    class _H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
        def do_HEAD(self):
            self.send_response(200); self.end_headers()
        def log_message(self, *a): pass
    threading.Thread(target=HTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), _H).serve_forever, daemon=True).start()
    try:
        application.run_polling()
    except Exception as e:
        import traceback
        report_fatal_sync(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
