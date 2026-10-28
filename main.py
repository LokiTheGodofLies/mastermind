"""Mastermind Library Bot - entry point.

Start-up order matters:
  1. environment files are loaded,
  2. the Telegram-hosted database backup is restored (before any module opens SQLite),
  3. modules are imported and the databases initialised,
  4. handlers are registered (middlewares first) and polling starts.
"""
import asyncio
import fcntl
import logging
import os
import tempfile

from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from modules.utility.telegram_patches import apply_patches, global_error_handler

apply_patches()


def load_env() -> None:
    """Copy KEY=VALUE lines from env.txt / .env into os.environ (real env vars win)."""
    for env_path in ("env.txt", ".env"):
        if not os.path.exists(env_path):
            continue
        with open(env_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# Restore databases from the Telegram backup BEFORE any module below is imported:
# several of them open / create their SQLite files at import time.
load_env()
from modules.database import persistence  # noqa: E402

persistence.restore_if_fresh()

from server import start_server_in_background  # noqa: E402
from modules.database.config_db import init_config_db, reload_config_cache  # noqa: E402
from modules.database.user_db import init_user_db  # noqa: E402
from modules.database.file_db import init_file_db  # noqa: E402
from modules.log.logger import setup_in_memory_logger  # noqa: E402
from modules.log.startup_log import send_startup_notification  # noqa: E402
from modules.log.handlers import log_command, settopic_command, enforce_group_topic_middleware, handle_my_chat_member  # noqa: E402
from modules.ban.handlers import ban_command, ban_pm_command, ban_support_command, unban_command, enforce_ban_middleware  # noqa: E402
from modules.fsub.handlers import enforce_fsub_middleware, handle_chat_join_request, fsub_verify_callback  # noqa: E402
from modules.start.start_handler import start_command, menu_callback_router  # noqa: E402
from modules.help.handlers import help_command, adminhelp_command  # noqa: E402
from modules.roles.handlers import addvol_command, addprom_command, addmod_command, addadmin_command  # noqa: E402
from modules.allowance.allowance import quota_command, gift_command, refer_command  # noqa: E402
from modules.search.handlers import search_command, searchebook_command, searchaudiobook_command, search_callback_handler  # noqa: E402
from modules.request.handlers import request_command, request_callback_handler  # noqa: E402
from modules.indexing.book_index import handle_book_indexing, index_command, indexing_callback_handler  # noqa: E402
from modules.converter.handlers import convert_command, convert_callback_handler  # noqa: E402
from modules.editscript.handlers import (  # noqa: E402
    customize_command, editscript_callback, reloadconfig_command, restart_command, redeploy_command,
    setconfig_command, getconfig_command, template_cli_command,
)
from modules.broadcast.handlers import broadcast_command, broadcast_confirm_command, broadcast_callback_handler  # noqa: E402
from modules.stats.handlers import stats_command, backup_command  # noqa: E402
from modules.support.handlers import support_command, support_callback_handler  # noqa: E402
from modules.id.handlers import id_command  # noqa: E402
from modules.utility.ping import ping_command  # noqa: E402
from modules.message.message_handler import handle_normal_text  # noqa: E402


def _acquire_single_instance_lock():
    """Exit quietly if another instance of the bot is already running on this host."""
    lock_file = open(os.path.join(tempfile.gettempdir(), "mastermind_bot.lock"), "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("❌ Another bot instance is already running. Exiting.")
        raise SystemExit(0)
    return lock_file  # keep a reference so the lock lives as long as the process


def register_handlers(app) -> None:
    # --- Middlewares (lower group runs first): -3 ban check, -2 topic filter, -1 force-subscribe
    app.add_handler(MessageHandler(filters.ALL, enforce_ban_middleware), group=-3)
    app.add_handler(MessageHandler(filters.ALL, enforce_group_topic_middleware), group=-2)
    app.add_handler(CallbackQueryHandler(enforce_group_topic_middleware), group=-2)
    app.add_handler(MessageHandler(filters.ALL, enforce_fsub_middleware), group=-1)
    app.add_handler(ChatJoinRequestHandler(handle_chat_join_request))
    app.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    # --- User & group commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("searchebook", searchebook_command))
    app.add_handler(CommandHandler("searchaudiobook", searchaudiobook_command))
    app.add_handler(CommandHandler(["request", "req"], request_command))
    app.add_handler(CommandHandler("convert", convert_command))
    app.add_handler(CommandHandler("settopic", settopic_command))
    app.add_handler(CommandHandler("quota", quota_command))
    app.add_handler(CommandHandler(["refer", "ref"], refer_command))
    app.add_handler(CommandHandler("support", support_command))
    app.add_handler(CommandHandler("id", id_command))
    app.add_handler(CommandHandler("ping", ping_command))

    # --- Admin & role commands
    app.add_handler(CommandHandler(["adminhelp", "ownerhelp"], adminhelp_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(CommandHandler("log", log_command))
    app.add_handler(CommandHandler("gift", gift_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("ban_pm", ban_pm_command))
    app.add_handler(CommandHandler("ban_support", ban_support_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("addvol", addvol_command))
    app.add_handler(CommandHandler("addprom", addprom_command))
    app.add_handler(CommandHandler("addmod", addmod_command))
    app.add_handler(CommandHandler("addadmin", addadmin_command))
    app.add_handler(CommandHandler(["index", "Index"], index_command))

    # --- Config, customize, deploy & broadcast commands
    app.add_handler(CommandHandler(["customize", "editscript", "config", "showconfig"], customize_command))
    app.add_handler(CommandHandler("reloadconfig", reloadconfig_command))
    app.add_handler(CommandHandler("restart", restart_command))
    app.add_handler(CommandHandler("redeploy", redeploy_command))
    app.add_handler(CommandHandler("setconfig", setconfig_command))
    app.add_handler(CommandHandler("getconfig", getconfig_command))
    app.add_handler(CommandHandler(
        ["edittext", "setmedia", "removemedia", "addbutton", "removebutton", "listtemplates", "showtemplate"],
        template_cli_command,
    ))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("broadcast_confirm", broadcast_confirm_command))

    # --- Inline-button (callback) routers
    app.add_handler(CallbackQueryHandler(fsub_verify_callback, pattern=r"^fsub_"))
    app.add_handler(CallbackQueryHandler(
        menu_callback_router,
        pattern=r"^(help_button|help_menu|help_open_admin|help_sec_|adm_sec_|search_menu|stats_menu|start_menu|quota|quota_menu|bot_owner)",
    ))
    app.add_handler(CallbackQueryHandler(search_callback_handler, pattern=r"^(file_dl_|dl_|search_page_|spg\||sendall\||search_cancel|noop)"))
    app.add_handler(CallbackQueryHandler(request_callback_handler, pattern=r"^req_"))
    app.add_handler(CallbackQueryHandler(indexing_callback_handler, pattern=r"^idx_"))
    app.add_handler(CallbackQueryHandler(convert_callback_handler, pattern=r"^cv\|"))
    app.add_handler(CallbackQueryHandler(editscript_callback, pattern=r"^(cust_|es_)"))
    app.add_handler(CallbackQueryHandler(broadcast_callback_handler, pattern=r"^bcast_"))
    app.add_handler(CallbackQueryHandler(support_callback_handler, pattern=r"^support_|^quiz_ans_"))

    # --- File uploads (auto-indexing / convert hook) and conversational text
    app.add_handler(MessageHandler(filters.Document.ALL | filters.AUDIO, handle_book_indexing))
    app.add_handler(MessageHandler(
        filters.PHOTO | filters.VIDEO | filters.FORWARDED | (filters.TEXT & ~filters.COMMAND),
        handle_normal_text,
    ))


def main() -> None:
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    load_env()
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    if not token:
        print("❌ Please set TELEGRAM_BOT_TOKEN (environment variable or env.txt)")
        raise SystemExit(1)

    _lock = _acquire_single_instance_lock()  # noqa: F841

    logging.basicConfig(level=logging.INFO)
    setup_in_memory_logger()
    init_config_db()
    reload_config_cache()
    init_user_db()
    init_file_db()

    async def post_stop(application):
        # Final snapshot while Render is shutting the old instance down (deploy / restart).
        try:
            ok, detail = persistence.final_backup()
            print(f"💾 Shutdown backup: {'ok' if ok else 'FAILED'} - {detail}")
        except Exception as exc:  # never block shutdown
            print(f"💾 Shutdown backup error: {exc}")

    async def post_init(application):
        await send_startup_notification(application)
        # Keep the databases safe across Render redeploys (see modules/database/persistence.py)
        application.bot_data["backup_task"] = asyncio.create_task(persistence.backup_loop())

    app = ApplicationBuilder().token(token).pool_timeout(30).post_init(post_init).post_stop(post_stop).build()
    app.add_error_handler(global_error_handler)
    register_handlers(app)

    start_server_in_background()
    print("🤖 Mastermind Library Bot is online and polling...")
    app.run_polling(drop_pending_updates=True, allowed_updates=None)


if __name__ == "__main__":
    main()
