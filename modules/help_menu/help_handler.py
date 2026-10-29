from configs import default_search_quota, default_request_quota
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.database.user_db import get_user_role_db

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    role = get_user_role_db(user_id)

    help_text = (
        "<b>🤖 Bot Help Menu</b>\n\n"
        "Here are my modules and functions I can perform:\n"
        "• <b>/start</b> - Greets you with a simple welcome message and quick buttons.\n"
        "• <b>/help</b> - Shows this list of all available modules and functions.\n"
        "• <b>/quota</b> - Checks your current daily limits and role status.\n"
        "• <b>/refer</b> - Opens your referral dashboard to invite friends and earn bonus allowances.\n"
        "• <b>/log</b> - View system memory logs (Admin/Owner only: <code>/log</code>, <code>/log 50</code>, <code>/log 15m</code>).\n"
        "• <b>Normal Text</b> - Reminds you that I can't chat and gives you a quick help button.\n\n"
        f"👤 <b>Your Current Role:</b> <code>{role}</code>\n\n"
        "📊 <b>Hierarchy & Quota Tiers:</b>\n"
        f"• <b>Normal User:</b> {default_search_quota()} searches & {default_request_quota()} requests\n"
        "• <b>Promoter:</b> 20 searches & 20 requests\n"
        "• <b>Moderator:</b> 30 searches & 30 requests\n"
        "• <b>Admin / Owner:</b> Unlimited searches & requests (Plus management powers)"
    )

    keyboard = [
        [
            InlineKeyboardButton("📊 My Quota", callback_data='quota_shortcut'),
            InlineKeyboardButton("👑 Bot Owner", url='tg://user?id=7261537212')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(help_text, parse_mode='HTML', reply_markup=reply_markup)

async def help_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'help_button':
        user_id = update.effective_user.id
        role = get_user_role_db(user_id)

        help_text = (
            "<b>🤖 Bot Help Menu</b>\n\n"
            "Here are my modules and functions I can perform:\n"
            "• <b>/start</b> - Greets you with a simple welcome message and quick buttons.\n"
            "• <b>/help</b> - Shows this list of all available modules and functions.\n"
            "• <b>/log</b> - View system memory logs (Admin/Owner).\n"
            "• <b>Normal Text</b> - Reminds you that I can't chat and gives you a quick help button.\n\n"
            f"👤 <b>Your Current Role:</b> <code>{role}</code>\n\n"
            "📊 <b>Hierarchy & Quotas:</b>\n"
            "• Normal User: 10/10\n"
            "• Promoter: 20/20\n"
            "• Moderator: 30/30\n"
            "• Admin / Owner: Unlimited"
        )
        await query.message.reply_text(help_text, parse_mode='HTML')
