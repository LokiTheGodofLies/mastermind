from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# Import database and referral logic
from modules.database.user_db import add_or_update_user_db
from modules.allowance.referral import process_referral_with_notification

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Telegram command handler for /start, handles registration, referrals, and welcome UI."""
    user = update.effective_user
    user_name = user.first_name
    today_str = datetime.now().strftime('%Y-%m-%d')
    bot_username = context.bot.username
    
    # 1. Register or update user in the database
    add_or_update_user_db(user.id, user.username, user.full_name, today_str)
    
    # 2. Check for referral deep link (e.g., /start ref_<referrer_id>)
    referral_notice = ""
    args = context.args
    if args and args[0].startswith("ref_"):
        try:
            referrer_id = int(args[0].split("_")[1])
            success, msg = process_referral_with_notification(referrer_id, user.id, context)
            if success:
                referral_notice = "\n\n🎉 <b>Referral Bonus Applied!</b> You and your referrer received +10 searches & requests."
        except ValueError:
            pass
            
    # 3. Construct welcome message
    message = (
        f"Hi <b>{user_name}</b>, welcome to Mastermind Bot! 👋\n\n"
        "I am your modular assistant. Tap the buttons below to see my help menu or reach out to my owner."
        f"{referral_notice}"
    )
    
    # 4. Interactive Keyboards including Help, Owner, and Refer More
    my_referral_link = f"https://t.me/{bot_username}?start=ref_{user.id}"
    share_text = "try this amazing bot and let's earn bonus searches and requests !"
    share_url = f"https://t.me/share/url?url={my_referral_link}&text={share_text}"

    keyboard = [
        [
            InlineKeyboardButton("📖 Help Menu", callback_data='help_button'),
            InlineKeyboardButton("👑 Bot Owner", url='tg://user?id=7261537212')
        ],
        [
            InlineKeyboardButton("📤 Refer & Earn Bonus", url=share_url)
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)


async def menu_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data

    if data == "search_menu":
        from modules.search.handlers import search_handler
        update.message = query.message
        await search_handler(update, context)
    elif data == "stats_menu":
        from modules.stats.handlers import stats_command
        update.message = query.message
        await stats_command(update, context)
    elif data == "help_menu":
        from modules.help.handlers import help_command
        update.message = query.message
        await help_command(update, context)
    elif data == "start_menu":
        await start_handler(update, context)
    elif data == "quota" or data == "quota_menu":
        await query.message.reply_text("📊 <b>Your Quota Status:</b>\n\n• Remaining Searches: Unlimited\n• API Status: Active", parse_mode="HTML")
