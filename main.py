import os
import asyncio
import logging


def load_env():
    env_path = "env.txt"
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())
        print("✅ Environment variables loaded from env.txt successfully.")
    else:
        print("⚠️ env.txt not found, relying on system environment variables.")


# Load env and restore databases from Telegram backup BEFORE importing modules
# that initialize SQLite files on import.
load_env()
from modules.database import persistence  # noqa: E402
persistence.restore_if_fresh()

from configs import bot_name  # noqa: E402
from telegram.ext import (  # noqa: E402
    ApplicationBuilder,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from modules.start.start_handler import start_command, menu_callback_router  # noqa: E402
from modules.help.handlers import help_command  # noqa: E402
from modules.support.handlers import support_command, support_callback_handler  # noqa: E402
from modules.allowance.handlers import (  # noqa: E402
    quota_command,
    gift_command,
    refer_command,
    my_referrals_command,
)
from modules.ban.handlers import (  # noqa: E402
    ban_command,
    ban_pm_command,
    ban_support_command,
    unban_command,
    enforce_ban_middleware,
)
from modules.editscript.handlers import editscript_command, editscript_callback  # noqa: E402
from modules.log.logger import setup_in_memory_logger  # noqa: E402
from modules.log.handlers import log_command, handle_my_chat_member  # noqa: E402
from modules.database.config_db import init_config_db  # noqa: E402
from modules.database.file_db import init_file_db  # noqa: E402
from modules.database.user_db import init_user_db  # noqa: E402
from modules.request.handlers import request_command, request_callback_handler  # noqa: E402
from modules.id.handlers import id_command  # noqa: E402
from modules.stats.handlers import stats_command  # noqa: E402
from modules.search.handlers import search_command, search_callback_handler  # noqa: E402
from modules.indexing.book_index import handle_book_indexing  # noqa: E402
from modules.indexing.index_command import index_command, index_callback, index_flow_handler  # noqa: E402
from modules.message.message_handler import handle_normal_text  # noqa: E402
from modules.utility.ping import ping_command  # noqa: E402
from modules.log.startup_log import send_startup_notification, error_handler, report_fatal_sync  # noqa: E402

persistence.sync_startup_log()

logger = logging.getLogger(__name__)


def main():
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    load_env()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Please ensure your TELEGRAM_BOT_TOKEN is set inside env.txt or environment.")
        exit(1)

    logging.basicConfig(level=logging.INFO)
    setup_in_memory_logger()
    init_config_db()
    init_file_db()
    init_user_db()
    print("✅ Database and tables initialized successfully.")
    print(f"🔍 DEBUG: STORAGE_GROUP_ID from environment is -> {os.getenv('STORAGE_GROUP_ID')}")

    async def post_init(app):
        await send_startup_notification(app)
        app.bot_data["backup_task"] = asyncio.create_task(persistence.backup_loop())

    async def post_stop(app):
        try:
            ok, detail = await asyncio.to_thread(persistence.final_backup)
            print(f"💾 Shutdown backup: {'ok' if ok else 'FAILED'} - {detail}")
        except Exception as exc:
            print(f"💾 Shutdown backup error: {exc}")

    application = (
        ApplicationBuilder()
        .token(token)
        .post_init(post_init)
        .post_stop(post_stop)
        .build()
    )

    # Global ban check middleware
    application.add_handler(MessageHandler(filters.ALL, enforce_ban_middleware), group=-1)

    # Group/Channel membership & admin change logger
    application.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    # User & Admin Commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("support", support_command))
    application.add_handler(CommandHandler("quota", quota_command))
    application.add_handler(CommandHandler("gift", gift_command))
    application.add_handler(CommandHandler(["refer", "ref"], refer_command))
    application.add_handler(CommandHandler("myreferrals", my_referrals_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("ban_pm", ban_pm_command))
    application.add_handler(CommandHandler("ban_support", ban_support_command))
    application.add_handler(CommandHandler("unban", unban_command))
    application.add_handler(CommandHandler("editscript", editscript_command))
    application.add_handler(CommandHandler("log", log_command))
    application.add_handler(CommandHandler("id", id_command))
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler(["request", "req"], request_command))
    application.add_handler(CommandHandler("index", index_command))
    application.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.Regex(r"^/index(?:@\w+)?(?:\s|$)"), index_command))
    application.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.Regex(r"^/id(?:@\w+)?$"), id_command))

    # Callback Query Routers
    application.add_handler(CallbackQueryHandler(index_callback, pattern=r"^idx_(yes|no|apr|rej|cancel)_[0-9a-f]{8}$"))
    application.add_handler(
        CallbackQueryHandler(
            menu_callback_router,
            pattern=r"^(help_button|help_menu|search_menu|stats_menu|start_menu|quota|quota_menu|quota_shortcut|bot_owner|request_menu|my_referrals_callback|refer_more_callback)$",
        )
    )
    application.add_handler(CallbackQueryHandler(support_callback_handler, pattern=r"^(support_|quiz_ans_)"))
    application.add_handler(CallbackQueryHandler(search_callback_handler, pattern=r"^(file_dl_|search_page_|join_search_group_quiz|generate_group_invite|search_menu|noop)"))
    application.add_handler(CallbackQueryHandler(request_callback_handler, pattern=r"^req_"))
    application.add_handler(CallbackQueryHandler(editscript_callback, pattern=r"^es_"))

    # Direct file upload indexing, /index interactive flow, and private normal-text fallback
    application.add_handler(MessageHandler(filters.Document.ALL, handle_book_indexing))
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, index_flow_handler), group=1)
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, handle_normal_text), group=2)

    print(f"🤖 {bot_name()} bot is up and running...")

    application.add_error_handler(error_handler)

    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class _H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def do_HEAD(self):
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    threading.Thread(
        target=HTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), _H).serve_forever,
        daemon=True,
    ).start()
    try:
        application.run_polling()
    except Exception:
        import traceback
        report_fatal_sync(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
