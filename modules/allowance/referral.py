from configs import referral_search_bonus, referral_request_bonus
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.database.user_db import (
    record_referral_db,
    add_quota_limits_db,
    get_referred_users_db,
)


def process_referral(referrer_id: int, new_user_id: int):
    """Processes a referral when a new user starts the bot via a referral link."""
    if referrer_id == new_user_id:
        return False, "⚠️ You cannot refer yourself."

    success = record_referral_db(referrer_id, new_user_id)
    if not success:
        return False, "⚠️ You have already claimed a referral bonus."

    add_quota_limits_db(referrer_id, search_bonus=referral_search_bonus(), request_bonus=referral_request_bonus())
    add_quota_limits_db(new_user_id, search_bonus=referral_search_bonus(), request_bonus=referral_request_bonus())
    return True, "Success"


def get_user_referral_stats(user_id: int):
    """Fetches total invite count and details of invited users for a given user ID."""
    referred_rows = get_referred_users_db(user_id)
    total_invites = len(referred_rows)
    return {"total_invites": total_invites, "referred_list": referred_rows}


async def process_referral_with_notification(*args, **kwargs):
    """Compatibility wrapper for both older and newer referral call patterns."""
    context = None
    referrer_id = None
    new_user_id = None
    new_user_name = "A user"

    if args and hasattr(args[0], "bot"):
        context = args[0]
        args = args[1:]

    if len(args) >= 2 and isinstance(args[0], int) and isinstance(args[1], int):
        referrer_id, new_user_id = args[:2]

    if len(args) >= 3 and hasattr(args[2], "bot"):
        context = args[2]

    if kwargs:
        referrer_id = kwargs.get("referrer_id", referrer_id)
        new_user_id = kwargs.get("new_user_id", new_user_id)
        new_user_name = kwargs.get("new_user_name", new_user_name)
        context = kwargs.get("context", context)

    if referrer_id is None or new_user_id is None:
        return False, "⚠️ Missing referral arguments."

    success, msg = process_referral(referrer_id, new_user_id)
    if not success:
        return False, msg

    if context is not None and hasattr(context, "bot"):
        referrer_text = (
            f"👤 **New Referral Joined!**\n\n"
            f"🔗 <b>{new_user_name}</b> joined using your referral link.\n"
            f"🎁 You have been awarded <b>+{referral_search_bonus()} Search</b> and <b>+{referral_request_bonus()} Request</b> allowance bonuses!"
        )
        referrer_keyboard = [[
            InlineKeyboardButton("📋 See my referrals", callback_data="my_referrals_callback"),
            InlineKeyboardButton("🔗 Refer more", callback_data="refer_more_callback")
        ]]
        try:
            await context.bot.send_message(
                chat_id=referrer_id,
                text=referrer_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(referrer_keyboard),
            )
        except Exception:
            pass

        new_user_text = (
            "🎁 <b>Referral Bonus Claimed!</b>\n\n"
            f"Since you joined from a referral link, you got <b>+{referral_search_bonus()} bonus search and +{referral_request_bonus()} bonus request</b> allowances!"
        )
        new_user_keyboard = [[InlineKeyboardButton("🚀 Refer and earn more bonus", callback_data="refer_more_callback")]]
        try:
            await context.bot.send_message(
                chat_id=new_user_id,
                text=new_user_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(new_user_keyboard),
            )
        except Exception:
            pass

    return True, msg


async def refer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generates and provides the user's personal referral link."""
    user_id = update.effective_user.id
    bot_username = context.bot.username
    referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    text = (
        "🔗 **Your Referral Link**\n\n"
        "Share this link with your friends. Whenever someone starts the bot using your link, "
        f"both you and your friend will receive **+{referral_search_bonus()} Search** and **+{referral_request_bonus()} Request** bonuses!\n\n"
        f"📋 `{referral_link}`"
    )

    keyboard = [[InlineKeyboardButton("📋 Copy Link", url=referral_link)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


async def my_referrals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the user's referral statistics."""
    user_id = update.effective_user.id
    stats = get_user_referral_stats(user_id)

    text = (
        "📋 **Your Referral Statistics**\n\n"
        f"• **Total Invites:** {stats['total_invites']} users\n"
        f"• **Total Bonus Earned:** +{stats['total_invites'] * 10} Searches & Requests\n\n"
        "Keep sharing your link using `/refer` to earn more allowances!"
    )
    await update.message.reply_text(text, parse_mode="Markdown")
