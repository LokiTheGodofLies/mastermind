from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# Import database and referral logic
from modules.database.user_db import add_or_update_user_db
from modules.allowance.referral import process_referral

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Telegram command handler for /start, handles registration, referrals, and welcome UI."""
    user = update.effective_user
    user_name = user.first_name
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    # 1. Register or update user in the database
    add_or_update_user_db(user.id, user.username, user.full_name, today_str)
    
    # 2. Check for referral deep link (e.g., /start ref_<referrer_id>)
    referral_notice = ""
    args = context.args
    if args and args[0].startswith("ref_"):
        try:
            referrer_id = int(args[0].split("_")[1])
            success, msg = process_referral(referrer_id, user.id)
            if success:
                referral_notice = "\n\n🎉 <b>Referral Bonus Applied!</b> You and your referrer received +10 searches & requests."
            else:
                # Optional: Handle self-referral or duplicate claim notice quietly or explicitly
                pass
        except ValueError:
            pass
            
    # 3. Construct welcome message
    message = (
        f"Hi <b>{user_name}</b>, welcome to Mastermind Bot! 👋\n\n"
        "I am your modular assistant. Tap the buttons below to see my help menu or reach out to my owner."
        f"{referral_notice}"
    )
    
    # 4. Interactive Keyboard (Using your owner ID: 7261537212)
    keyboard = [
        [
            InlineKeyboardButton("📖 Help Menu", callback_data='help_button'),
            InlineKeyboardButton("👑 Bot Owner", url='tg://user?id=7261537212')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
