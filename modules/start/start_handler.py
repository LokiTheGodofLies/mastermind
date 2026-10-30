import html
from config import bot_name, owner_id, referral_bonus_label
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from modules.database.user_db import add_or_update_user_db
from modules.allowance.referral import process_referral_with_notification


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Telegram command handler for /start, handles registration, referrals, request deep links, and welcome UI."""
    user = update.effective_user
    if not user:
        return

    target_message = update.effective_message
    if not target_message:
        return

    user_name = html.escape(user.first_name or "Friend")
    today_str = datetime.now().strftime("%Y-%m-%d")
    bot_username = context.bot.username

    add_or_update_user_db(user.id, user.username, user.full_name, today_str)

    args = context.args
    if args and (args[0].startswith("req_pick_") or args[0] == "req_manual"):
        from modules.request.handlers import request_deeplink_handler
        await request_deeplink_handler(update, context)
        return

    if args and args[0].startswith("dl_"):
        from modules.search.delivery import handle_deeplink_file_delivery
        await handle_deeplink_file_delivery(update, context, args[0])
        return

    referral_notice = ""
    if args and args[0].startswith("ref_"):
        try:
            referrer_id = int(args[0].split("_")[1])
            success, _ = await process_referral_with_notification(context, referrer_id, user.id, user.full_name)
            if success:
                referral_notice = f"\n\n🎉 <b>Referral Bonus Applied!</b> You and your referrer received {referral_bonus_label()}."
        except ValueError:
            pass

    message = (
        f"Hi <b>{user_name}</b>, welcome to {bot_name()} Bot! 👋\n\n"
        "I am your modular assistant. Tap the buttons below to see my help menu or reach out to GOD."
        f"{referral_notice}"
    )

    my_referral_link = f"https://t.me/{bot_username}?start=ref_{user.id}"
    share_text = "try this amazing bot and let's earn bonus searches and requests !"
    share_url = f"https://t.me/share/url?url={my_referral_link}&text={share_text}"

    keyboard = [
        [
            InlineKeyboardButton("📖 Help Menu", callback_data="help_button"),
            InlineKeyboardButton("👑 GOD", callback_data="bot_owner"),
        ],
        [
            InlineKeyboardButton("📤 Refer & Earn Bonus", url=share_url),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(message, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await target_message.reply_text(message, parse_mode="HTML", reply_markup=reply_markup)


async def menu_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return
    data = query.data

    if data in ("help_button", "help_menu"):
        await query.answer()
        from modules.help.handlers import help_command
        await help_command(update, context)
    elif data == "bot_owner":
        await query.answer()
        oid = owner_id()
        await query.message.edit_text(
            f"👑 <b>Bot Owner & Administrator:</b>\n\n• Owner ID: <code>{oid}</code>\n• For support or inquiries, contact the administrator.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Start", callback_data="start_menu")]]),
        )
    elif data == "search_menu":
        from modules.search.handlers import search_command
        await search_command(update, context)
    elif data == "request_menu":
        await query.answer()
        from modules.request.handlers import REQUEST_GUIDE_TEXT
        await query.message.reply_text(
            REQUEST_GUIDE_TEXT,
            parse_mode="HTML",
        )
    elif data == "stats_menu":
        await query.answer()
        from modules.stats.handlers import stats_command
        await stats_command(update, context)
    elif data == "start_menu":
        await start_command(update, context)
    elif data in ("quota", "quota_menu", "quota_shortcut"):
        from modules.allowance.allowance import quota_command
        await quota_command(update, context)
    elif data == "my_referrals_callback":
        from modules.allowance.referral import my_referrals_command
        await my_referrals_command(update, context)
    elif data == "refer_more_callback":
        from modules.allowance.allowance import refer_command
        await refer_command(update, context)


start_handler = start_command
