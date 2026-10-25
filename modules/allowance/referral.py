from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.database.user_db import (
    record_referral_db,
    add_quota_limits_db,
    get_referred_users_db
)

def process_referral(referrer_id: int, new_user_id: int):
    """
    Processes a referral when a new user starts the bot via a referral link.
    Awards +10 search and +10 request limits to BOTH the referrer and the new user.
    """
    if referrer_id == new_user_id:
        return False, "⚠️ You cannot refer yourself."
        
    success = record_referral_db(referrer_id, new_user_id)
    if not success:
        return False, "⚠️ You have already claimed a referral bonus."
        
    # Reward both users
    add_quota_limits_db(referrer_id, search_bonus=10, request_bonus=10)
    add_quota_limits_db(new_user_id, search_bonus=10, request_bonus=10)
    
    return True, "Success"

def get_user_referral_stats(user_id: int):
    """Fetches total invite count and details of invited users for a given user ID."""
    referred_rows = get_referred_users_db(user_id)
    total_invites = len(referred_rows)
    return {
        "total_invites": total_invites,
        "referred_list": referred_rows
    }

async def process_referral_with_notification(context: ContextTypes.DEFAULT_TYPE, referrer_id: int, new_user_id: int, new_user_name: str = "A user"):
    """
    Processes the referral and dispatches notifications to both the referrer and the new user.
    """
    success, msg = process_referral(referrer_id, new_user_id)
    if not success:
        return

    # 1. Notify the Referrer
    referrer_text = (
        f"👤 **New Referral Joined!**\n\n"
        f"🔗 <b>{new_user_name}</b> joined using your referral link.\n"
        f"🎁 You have been awarded <b>+10 Search</b> and <b>+10 Request</b> allowance bonuses!"
    )
    referrer_keyboard = [
        [
            InlineKeyboardButton("📋 See my referrals", callback_data="my_referrals_callback"),
            InlineKeyboardButton("🔗 Refer more", callback_data="refer_more_callback")
        ]
    ]
    try:
        await context.bot.send_message(
            chat_id=referrer_id,
            text=referrer_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(referrer_keyboard)
        )
    except Exception:
        pass

    # 2. Notify the New User in a separate message
    new_user_text = (
        "🎁 <b>Referral Bonus Claimed!</b>\n\n"
        "Since you joined from a referral link, you got <b>+10 bonus search and request</b> allowances!"
    )
    new_user_keyboard = [
        [InlineKeyboardButton("🚀 Refer and earn more bonus", callback_data="refer_more_callback")]
    ]
    try:
        await context.bot.send_message(
            chat_id=new_user_id,
            text=new_user_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(new_user_keyboard)
        )
    except Exception:
        pass

async def refer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /refer - Generates and provides the user's personal referral link.
    """
    user_id = update.effective_user.id
    bot_username = context.bot.username
    referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    text = (
        "🔗 **Your Referral Link**\n\n"
        "Share this link with your friends. Whenever someone starts the bot using your link, "
        "both you and your friend will receive **+10 Search** and **+10 Request** bonuses!\n\n"
        f"📋 `{referral_link}`"
    )
    
    keyboard = [[InlineKeyboardButton("📋 Copy Link", url=referral_link)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

async def my_referrals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /myreferrals - Displays user's total invites and referral statistics.
    """
    user_id = update.effective_user.id
    stats = get_user_referral_stats(user_id)
    
    text = (
        "📋 **Your Referral Statistics**\n\n"
        f"• **Total Invites:** {stats['total_invites']} users\n"
        f"• **Total Bonus Earned:** +{stats['total_invites'] * 10} Searches & Requests\n\n"
        "Keep sharing your link using `/refer` to earn more allowances!"
    )
    
    await update.message.reply_text(text, parse_mode="Markdown")
