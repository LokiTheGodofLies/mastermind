from configs import bot_name
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.database.config_db import get_config

ADMIN_IDS = [7261537212]


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    user_id = user.id
    is_admin = user_id in ADMIN_IDS

    default_help = (
        f"📖 <b>{bot_name()} Bot - Help & User Guide</b>\n\n"
        "Welcome! Here is a complete overview of available features and access tiers:\n\n"
        "👤 <b>User Hierarchy & Features:</b>\n"
        "• <b>Standard Users:</b>\n"
        "  - <code>/start</code>: Access the main interactive welcome menu.\n"
        "  - <code>/search</code>: Open verification and search features.\n"
        "  - <code>/request</code>: Request books not yet in the library.\n"
        "  - <code>/quota</code>: View your remaining daily search & request allowances.\n"
        "  - <code>/refer</code>: Invite friends to earn bonus allowances.\n"
        "  - <code>/support</code>: Take the verification quiz to join the support group.\n"
        "  - <code>/stats</code>: View bot uptime and public operation metrics.\n"
        "  - <code>/help</code>: Display this documentation guide.\n\n"
        "👑 <b>Administrators & Owner:</b>\n"
        "  - <code>/editscript</code>: Open the dynamic configuration hub (stored in <code>configuration.db</code>) to manage text templates, media URLs, and system variables live without restarts.\n"
        "  - <code>/index</code>: Batch index books from a source channel/group.\n"
        "  - <code>/ban</code>, <code>/ban_pm</code>, <code>/ban_support</code>, <code>/unban</code>: Manage user and chat restrictions.\n"
        "  - <code>/gift</code>: Grant bonus search/request allowances to a user.\n"
        "  - <code>/log</code>: Export recent in-memory system logs.\n"
        "  - <b>Admin Metrics:</b> Advanced server status and configuration tracking via <code>/stats</code>."
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
    from modules.start.start_handler import menu_callback_router
    await menu_callback_router(update, context)
