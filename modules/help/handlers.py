from configs import bot_name
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.database.config_db import get_config

ADMIN_IDS = [7261537212]


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.from_user:
        return

    user_id = message.from_user.id
    is_admin = user_id in ADMIN_IDS

    default_help = (
        f"📖 <b>{bot_name()} Bot - Help & User Guide</b>\n\n"
        "Welcome! Here is a complete overview of available features and access tiers:\n\n"
        "👤 <b>User Hierarchy & Features:</b>\n"
        "• <b>Standard Users:</b>\n"
        "  - <code>/start</code>: Access the main interactive welcome menu.\n"
        "  - <code>/search</code>: Open verification and search features.\n"
        "  - <code>/stats</code>: View bot uptime and public operation metrics.\n"
        "  - <code>/help</code>: Display this documentation guide.\n\n"
        "👑 <b>Administrators & Owner:</b>\n"
        "  - <code>/editscript</code>: Open the dynamic configuration hub (stored in <code>configuration.db</code>) to manage text templates, media URLs, and system variables live without restarts.\n"
        "  - <b>Admin Metrics:</b> Advanced server status and configuration tracking via <code>/stats</code>.\n"
        "  - <b>Startup Logging:</b> Automated deployment notifications sent directly to the configured logger group."
    )

    help_text = get_config("help_script", default=default_help)

    keyboard = [
        [InlineKeyboardButton("🔍 Search", callback_data="search_menu"), InlineKeyboardButton("📊 Stats", callback_data="stats_menu")],
        [InlineKeyboardButton("📊 My Quota", callback_data="quota"), InlineKeyboardButton("👑 Bot Owner", callback_data="bot_owner")],
    ]

    if is_admin:
        keyboard.append([InlineKeyboardButton("🛠️ Admin Hub (/editscript)", callback_data="es_menu_main")])

    keyboard.append([InlineKeyboardButton("« Back to Start", callback_data="start_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.reply_text(text=help_text, reply_markup=reply_markup, parse_mode="HTML")


async def help_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data

    if data in ("help_button", "help_menu"):
        from modules.start.start_handler import start_command
        update.message = query.message
        await start_command(update, context)
    elif data == "quota":
        await query.message.reply_text("📊 <b>Your Quota Status:</b>\n\n• Remaining Searches: Unlimited\n• Status: Active", parse_mode="HTML")
    elif data == "bot_owner":
        await query.message.reply_text(
            "👑 <b>Bot Owner & Administrator:</b>\n\n• Owner ID: <code>7261537212</code>\n• For support or inquiries, contact the administrator.",
            parse_mode="HTML"
        )
    elif data == "stats_menu":
        from modules.stats.handlers import stats_command
        update.message = query.message
        await stats_command(update, context)
    elif data == "search_menu":
        from modules.search.handlers import search_command
        update.message = query.message
        await search_command(update, context)
    elif data == "start_menu":
        from modules.start.start_handler import start_command
        update.message = query.message
        await start_command(update, context)
