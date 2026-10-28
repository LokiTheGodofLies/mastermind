from server import start_server_in_background
import os
import asyncio
import logging
import fcntl

import telegram
from telegram.error import BadRequest

# --- Global patch: silently ignore "Message is not modified" everywhere ---
_orig_msg_edit_text = telegram.Message.edit_text
_orig_msg_edit_rm = telegram.Message.edit_reply_markup
_orig_bot_edit_text = telegram.Bot.edit_message_text


async def _safe_msg_edit_text(self, *args, **kwargs):
    try:
        return await _orig_msg_edit_text(self, *args, **kwargs)
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            return self
        raise


async def _safe_msg_edit_rm(self, *args, **kwargs):
    try:
        return await _orig_msg_edit_rm(self, *args, **kwargs)
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            return self
        raise


async def _safe_bot_edit_text(self, *args, **kwargs):
    try:
        return await _orig_bot_edit_text(self, *args, **kwargs)
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            return None
        raise


telegram.Message.edit_text = _safe_msg_edit_text
telegram.Message.edit_reply_markup = _safe_msg_edit_rm
telegram.Bot.edit_message_text = _safe_bot_edit_text


async def global_telegram_error_handler(update, context):
    err = context.error
    if isinstance(err, BadRequest) and "message is not modified" in str(err).lower():
        return
    logging.getLogger(__name__).error(f"Unhandled exception: {err}", exc_info=err)


from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    ChatJoinRequestHandler,
    filters,
)

from modules.database.config_db import init_config_db, reload_config_cache
from modules.database.user_db import init_user_db
from modules.database.file_db import init_file_db
from modules.log.logger import setup_in_memory_logger
from modules.log.startup_log import send_startup_notification
from modules.log.handlers import log_command, settopic_command, enforce_group_topic_middleware, handle_my_chat_member
from modules.ban.handlers import ban_command, ban_pm_command, ban_support_command, unban_command, enforce_ban_middleware
from modules.fsub.handlers import enforce_fsub_middleware, handle_chat_join_request, fsub_verify_callback
from modules.start.start_handler import start_command, menu_callback_router
from modules.help.handlers import help_command, adminhelp_command
from modules.roles.handlers import addvol_command, addprom_command, addmod_command, addadmin_command
from modules.allowance.allowance import quota_command, gift_command, refer_command
from modules.search.handlers import search_command, searchebook_command, searchaudiobook_command, search_callback_handler
from modules.request.handlers import request_command, request_callback_handler
from modules.indexing.book_index import handle_book_indexing, index_command, indexing_callback_handler
from modules.editscript.handlers import (
    customize_command, editscript_callback, reloadconfig_command, restart_command, redeploy_command,
    setconfig_command, getconfig_command, template_cli_command,
)
from modules.broadcast.handlers import broadcast_command, broadcast_confirm_command, broadcast_callback_handler
from modules.stats.handlers import stats_command
from modules.support.handlers import support_command, support_callback_handler
from modules.id.handlers import id_command
from modules.utility.ping import ping_command
from modules.message.message_handler import handle_normal_text


def load_env():
    for env_path in ("env.txt", ".env"):
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                for line in f:
                    if "=" in line and not line.strip().startswith("#"):
                        k, v = line.strip().split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())


def main():
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    load_env()
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    if not token:
        print("❌ Please set TELEGRAM_BOT_TOKEN in env.txt")
        raise SystemExit(1)

    # Prevent duplicate bot instances for the same app environment.
    lock_path = "/tmp/mastermind_bot.lock"
    lock_file = open(lock_path, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("❌ Another bot instance is already running. Exiting.")
        raise SystemExit(0)

    logging.basicConfig(level=logging.INFO)
    setup_in_memory_logger()
    init_config_db()
    reload_config_cache()
    init_user_db()
    init_file_db()

    app = ApplicationBuilder().token(token).build()
    app.add_error_handler(global_telegram_error_handler)

    # Middlewares: Group -3 Ban check, Group -2 Group Topic filter, Group -1 Force Subscribe
    app.add_handler(MessageHandler(filters.ALL, enforce_ban_middleware), group=-3)
    app.add_handler(MessageHandler(filters.ALL, enforce_group_topic_middleware), group=-2)
    app.add_handler(CallbackQueryHandler(enforce_group_topic_middleware), group=-2)
    app.add_handler(MessageHandler(filters.ALL, enforce_fsub_middleware), group=-1)
    app.add_handler(ChatJoinRequestHandler(handle_chat_join_request))
    app.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))

    # User & Group Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("searchebook", searchebook_command))
    app.add_handler(CommandHandler("searchaudiobook", searchaudiobook_command))
    app.add_handler(CommandHandler(["request", "req"], request_command))
    app.add_handler(CommandHandler("settopic", settopic_command))
    app.add_handler(CommandHandler("quota", quota_command))
    app.add_handler(CommandHandler(["refer", "ref"], refer_command))
    app.add_handler(CommandHandler("support", support_command))
    app.add_handler(CommandHandler("id", id_command))
    app.add_handler(CommandHandler("ping", ping_command))

    # Admin & Role Commands
    app.add_handler(CommandHandler(["adminhelp", "ownerhelp"], adminhelp_command))
    app.add_handler(CommandHandler("stats", stats_command))
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

    # Config, Customize & Broadcast Commands
    app.add_handler(CommandHandler(["customize", "editscript", "config", "showconfig"], customize_command))
    app.add_handler(CommandHandler("reloadconfig", reloadconfig_command))
    app.add_handler(CommandHandler("restart", restart_command))
    app.add_handler(CommandHandler("redeploy", redeploy_command))
    app.add_handler(CommandHandler("setconfig", setconfig_command))
    app.add_handler(CommandHandler("getconfig", getconfig_command))
    app.add_handler(CommandHandler(["edittext", "setmedia", "removemedia", "addbutton", "removebutton", "listtemplates", "showtemplate"], template_cli_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("broadcast_confirm", broadcast_confirm_command))

    # Callback Routers
    app.add_handler(CallbackQueryHandler(fsub_verify_callback, pattern=r"^fsub_"))
    app.add_handler(CallbackQueryHandler(menu_callback_router, pattern=r"^(help_button|help_menu|help_open_admin|help_sec_|adm_sec_|search_menu|stats_menu|start_menu|quota|quota_menu|bot_owner)"))
    app.add_handler(CallbackQueryHandler(search_callback_handler, pattern=r"^(file_dl_|dl_|search_page_|spg\||sendall\||search_cancel|noop)"))
    app.add_handler(CallbackQueryHandler(request_callback_handler, pattern=r"^req_"))
    app.add_handler(CallbackQueryHandler(indexing_callback_handler, pattern=r"^idx_"))
    app.add_handler(CallbackQueryHandler(editscript_callback, pattern=r"^(cust_|es_)"))
    app.add_handler(CallbackQueryHandler(broadcast_callback_handler, pattern=r"^bcast_"))
    app.add_handler(CallbackQueryHandler(support_callback_handler, pattern=r"^support_|^quiz_ans_"))

    # File Upload / Auto-Indexing & Conversational / Text Handlers
    app.add_handler(MessageHandler(filters.Document.ALL | filters.AUDIO, handle_book_indexing))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.FORWARDED | (filters.TEXT & ~filters.COMMAND), handle_normal_text))

    async def post_init(application):
        await send_startup_notification(application)

    app.post_init = post_init
    start_server_in_background()
    print("🤖 Mastermind Library Bot is online and polling...")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=None,
        read_timeout=30,
        write_timeout=30,
        connect_timeout=30,
        pool_timeout=30,
    )


if __name__ == "__main__":
    main()
