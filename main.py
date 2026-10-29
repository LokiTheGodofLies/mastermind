import os
import asyncio
import logging

from config import (
    bot_name,
    bot_token,
    env_file_path,
    helper_bot_tokens,
    port,
    storage_group_id,
)


def load_env():
    env_path = env_file_path()
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())
        print(f"✅ Environment variables loaded from {env_path} successfully.")
    else:
        print(f"⚠️ {env_path} not found, relying on system environment variables.")


# Load env and restore databases from Telegram backup BEFORE importing modules
# that initialize SQLite files on import.
load_env()
from modules.database import persistence  # noqa: E402
persistence.restore_if_fresh()

from telegram.error import Conflict  # noqa: E402
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
    addadmin_command,
    removeadmin_command,
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
from modules.search.delivery import handle_deeplink_file_delivery  # noqa: E402
from modules.indexing.book_index import handle_book_indexing  # noqa: E402
from modules.indexing.index_command import index_command, index_callback, index_flow_handler  # noqa: E402
from modules.message.message_handler import handle_normal_text  # noqa: E402
from modules.utility.ping import ping_command  # noqa: E402
from modules.log.startup_log import send_startup_notification, error_handler, report_fatal_sync  # noqa: E402

persistence.sync_startup_log()

logger = logging.getLogger(__name__)


async def _helper_start_command(update, context):
    """Handles /start on Helper Bots so users starting a helper bot receive their requested file in PM."""
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    if context.args and context.args[0].startswith("dl_"):
        await handle_deeplink_file_delivery(update, context, context.args[0])
        return
    await msg.reply_text(
        f"👋 Hi <b>{user.first_name}</b>! I am a {bot_name()} helper delivery bot.\n\n"
        "✅ You have started me — now whenever you click a search result in the main bot, "
        "I can send the files directly to your PM as well as the posting channel!",
        parse_mode="HTML",
    )


async def _helper_error_handler(update, context):
    if isinstance(context.error, Conflict):
        return
    logger.warning("Helper bot error: %s", context.error)


async def _start_helper_apps() -> list:
    """Starts lightweight polling on configured helper bots so /start deep-links deliver files in PM."""
    apps = []
    for tok in helper_bot_tokens():
        try:
            happ = ApplicationBuilder().token(tok).build()
            happ.add_handler(CommandHandler("start", _helper_start_command))
            happ.add_error_handler(_helper_error_handler)
            await happ.initialize()
            await happ.start()
            await happ.updater.start_polling(drop_pending_updates=True)
            apps.append(happ)
        except Exception as exc:
            logger.warning("Could not start helper bot polling (token …%s): %s", tok[-4:], exc)
    return apps


async def _stop_helper_apps(apps: list):
    for happ in apps:
        try:
            if happ.updater and happ.updater.running:
                await happ.updater.stop()
            await happ.stop()
            await happ.shutdown()
        except Exception:
            pass


def main():
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    load_env()
    token = bot_token()
    if not token:
        print("Please ensure your TELEGRAM_BOT_TOKEN is set inside env.txt or environment.")
        exit(1)

    logging.basicConfig(level=logging.INFO)
    setup_in_memory_logger()
    init_config_db()
    init_file_db()
    init_user_db()
    print("✅ Database and tables initialized successfully.")
    print(f"🔍 DEBUG: STORAGE_GROUP_ID from environment is -> {storage_group_id()}")

    async def post_init(app):
        await send_startup_notification(app)
        app.bot_data["backup_task"] = asyncio.create_task(persistence.backup_loop())
        app.bot_data["helper_apps"] = await _start_helper_apps()

    async def post_stop(app):
        await _stop_helper_apps(app.bot_data.get("helper_apps") or [])
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
    application.add_handler(CommandHandler("addadmin", addadmin_command))
    application.add_handler(CommandHandler("removeadmin", removeadmin_command))
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

    # Direct file upload indexing (supports both Document and Audio attachments), /index interactive flow, and private normal-text fallback
    application.add_handler(MessageHandler(filters.Document.ALL | filters.AUDIO, handle_book_indexing))
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
        target=HTTPServer(("0.0.0.0", port()), _H).serve_forever,
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
