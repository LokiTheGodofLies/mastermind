from configs import bot_name, referral_bonus_label
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from modules.database.user_db import add_or_update_user_db
from modules.allowance.referral import process_referral_with_notification


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Telegram command handler for /start, handles registration, referrals, and welcome UI."""
    user = update.effective_user
    if not user:
        return

    target_message = update.message or (update.callback_query.message if update.callback_query else None)
    if not target_message:
        return

    user_name = user.first_name
    today_str = datetime.now().strftime('%Y-%m-%d')
    bot_username = context.bot.username

    add_or_update_user_db(user.id, user.username, user.full_name, today_str)

    referral_notice = ""
    args = context.args
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
        "I am your modular assistant. Tap the buttons below to see my help menu or reach out to my owner."
        f"{referral_notice}"
    )

    my_referral_link = f"https://t.me/{bot_username}?start=ref_{user.id}"
    share_text = "try this amazing bot and let's earn bonus searches and requests !"
    share_url = f"https://t.me/share/url?url={my_referral_link}&text={share_text}"

    keyboard = [
        [
            InlineKeyboardButton("📖 Help Menu", callback_data='help_button'),
            InlineKeyboardButton("👑 Bot Owner", callback_data='bot_owner')
        ],
        [
            InlineKeyboardButton("📤 Refer & Earn Bonus", url=share_url)
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(message, parse_mode='HTML', reply_markup=reply_markup)
    else:
        await target_message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)


async def menu_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    data = query.data

    if data in ("help_button", "help_menu"):
        from modules.help.handlers import help_command
        update.message = query.message
        await help_command(update, context)
    elif data == "bot_owner":
        await query.message.edit_text(
            "👑 <b>Bot Owner & Administrator:</b>\n\n• Owner ID: <code>7261537212</code>\n• For support or inquiries, contact the administrator.",
            parse_mode="HTML"
        )
    elif data in ("search_menu", "stats_menu"):
        if data == "search_menu":
            from modules.search.handlers import search_command
            update.message = query.message
            await search_command(update, context)
        else:
            from modules.stats.handlers import stats_command
            update.message = query.message
            await stats_command(update, context)
    elif data == "start_menu":
        update.message = query.message
        await start_command(update, context)
    elif data in ("quota", "quota_menu"):
        await query.message.edit_text(
            "📊 <b>Your Quota Status:</b>\n\n• Remaining Searches: Unlimited\n• API Status: Active",
            parse_mode="HTML"
        )


start_handler = start_command
