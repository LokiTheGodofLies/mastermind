import html
from configs import referral_search_bonus, referral_request_bonus, referral_earned_label
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.database.user_db import (
    record_referral_db,
    add_quota_limits_db,
    get_referred_users_db,
)
from modules.utility.rich_ui import styled_button


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
            f"👤 <b>New Referral Joined!</b>\n\n"
            f"🔗 <b>{html.escape(str(new_user_name))}</b> joined using your referral link.\n"
            f"🎁 You have been awarded <mark>+{referral_search_bonus()} Search</mark> and <mark>+{referral_request_bonus()} Request</mark> allowance bonuses!"
        )
        referrer_keyboard = [[
            styled_button("📋 See my referrals", callback_data="my_referrals_callback", style="primary"),
            styled_button("🔗 Refer more", callback_data="refer_more_callback", style="success"),
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
            f"Since you joined from a referral link, you got <mark>+{referral_search_bonus()} bonus search and +{referral_request_bonus()} bonus request</mark> allowances!"
        )
        new_user_keyboard = [[styled_button("🚀 Refer and earn more bonus", callback_data="refer_more_callback", style="success")]]
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
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    user_id = user.id
    bot_username = context.bot.username
    referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    text = (
        "🔗 <b>Your Referral Link</b>\n\n"
        "Share this link with your friends. Whenever someone starts the bot using your link, "
        f"both you and your friend will receive <mark>+{referral_search_bonus()} Search</mark> and <mark>+{referral_request_bonus()} Request</mark> bonuses!\n\n"
        f"📋 <code>{html.escape(referral_link)}</code>"
    )

    keyboard = [
        [styled_button("📋 Copy Referral Link", copy_text=referral_link, style="success")],
        [styled_button("🔗 Open Link", url=referral_link, style="primary")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.answer()
    await msg.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)


async def my_referrals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the user's referral statistics."""
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    user_id = user.id
    stats = get_user_referral_stats(user_id)

    text = (
        "📋 <b>Your Referral Statistics</b>\n\n"
        f"• <b>Total Invites:</b> <mark>{stats['total_invites']}</mark> users\n"
        f"• <b>Total Bonus Earned:</b> <mark>{html.escape(str(referral_earned_label(stats['total_invites'])))}</mark>\n\n"
        "Keep sharing your link using <code>/refer</code> to earn more allowances!"
    )
    markup = InlineKeyboardMarkup([
        [styled_button("📤 Refer More Friends", callback_data="refer_more_callback", style="success")],
        [styled_button("« Back to Start", callback_data="start_menu", style="primary")],
    ])
    if update.callback_query:
        await update.callback_query.answer()
    await msg.reply_text(text, parse_mode="HTML", reply_markup=markup)
