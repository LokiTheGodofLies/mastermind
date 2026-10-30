import html
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes



from configs import bot_name, referral_bonus_label, referral_earned_label
from modules.database.user_db import (
    get_user_role_db,
    get_quota_record_db,
    update_quota_counts_db,
    increment_search_used_db,
    increment_request_used_db,
    add_quota_limits_db,
)
from modules.allowance.referral import get_user_referral_stats


def check_and_reset_quota(user_id):
    """Checks if a new calendar day has started and resets daily usage counts to 0."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    row = get_quota_record_db(user_id)

    if row:
        _, _, _, _, last_reset = row
        if last_reset != today_str:
            update_quota_counts_db(user_id, 0, 0, today_str)


def can_user_search(user_id):
    """Validates if a user has remaining search quota for the day."""
    role = get_user_role_db(user_id)
    if role in ["Admin", "Creator", "Owner"]:
        return True

    check_and_reset_quota(user_id)
    row = get_quota_record_db(user_id)
    if not row:
        return True

    searches_used, searches_limit, _, _, _ = row
    return searches_used < searches_limit


def can_user_request(user_id):
    """Validates if a user has remaining request quota for the day."""
    role = get_user_role_db(user_id)
    if role in ["Admin", "Creator", "Owner"]:
        return True

    check_and_reset_quota(user_id)
    row = get_quota_record_db(user_id)
    if not row:
        return True

    _, _, requests_used, requests_limit, _ = row
    return requests_used < requests_limit


def deduct_search_quota(user_id):
    """Deducts 1 search allowance ONLY after a successful search."""
    role = get_user_role_db(user_id)
    if role in ["Admin", "Creator", "Owner"]:
        return
    check_and_reset_quota(user_id)
    increment_search_used_db(user_id)


def deduct_request_quota(user_id):
    """Deducts 1 request allowance ONLY after a successful request submission."""
    role = get_user_role_db(user_id)
    if role in ["Admin", "Creator", "Owner"]:
        return
    check_and_reset_quota(user_id)
    increment_request_used_db(user_id)


def get_user_quota_summary(user_id):
    """Retrieves and formats the user's role and remaining quotas for the /quota command."""
    check_and_reset_quota(user_id)
    role = get_user_role_db(user_id)
    row = get_quota_record_db(user_id)

    if role in ["Admin", "Creator", "Owner"]:
        return {
            "role": role,
            "unlimited": True,
            "searches_left": "Unlimited",
            "searches_limit": "Unlimited",
            "requests_left": "Unlimited",
            "requests_limit": "Unlimited",
        }

    if row:
        searches_used, searches_limit, requests_used, requests_limit, _ = row
        searches_left = max(0, searches_limit - searches_used)
        requests_left = max(0, requests_limit - requests_used)
        return {
            "role": role,
            "unlimited": False,
            "searches_left": searches_left,
            "searches_limit": searches_limit,
            "requests_left": requests_left,
            "requests_limit": requests_limit,
        }
    return None


def gift_quota(admin_user_id, target_user_id, search_bonus=0, request_bonus=0):
    """Allows Admins or Creator to increase a target user's quota limits via /gift."""
    admin_role = get_user_role_db(admin_user_id)
    if admin_role not in ["Admin", "Creator", "Owner"]:
        return False, "❌ You do not have permission to use the gift command."

    add_quota_limits_db(target_user_id, search_bonus, request_bonus)
    return True, f"🎁 Successfully added <b>+{search_bonus}</b> search limit and <b>+{request_bonus}</b> request limit to user <code>{target_user_id}</code>."


async def quota_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Telegram command handler for /quota and quota button callbacks."""
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return

    summary = get_user_quota_summary(user.id)
    if not summary:
        text = "⚠️ Could not retrieve your quota record."
    elif summary["unlimited"]:
        text = (
            f"👤 <b>Your Role:</b> {html.escape(str(summary['role']))}\n"
            f"♾️ <b>Status:</b> Unlimited searches and requests."
        )
    else:
        text = (
            f"👤 <b>Your Role:</b> {html.escape(str(summary['role']))}\n\n"
            f"🔍 <b>Searches Remaining:</b> <code>{summary['searches_left']} / {summary['searches_limit']}</code>\n"
            f"📥 <b>Requests Remaining:</b> <code>{summary['requests_left']} / {summary['requests_limit']}</code>\n\n"
            f"<i>(Quotas reset automatically every day)</i>"
        )

    if update.callback_query:
        await update.callback_query.answer()
    await msg.reply_text(text, parse_mode="HTML")


async def gift_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Telegram command handler for /gift <user_id> <searches> <requests>"""
    admin_id = update.effective_user.id
    args = context.args

    if len(args) < 3:
        await update.effective_message.reply_text(
            "⚠️ <b>Usage:</b> <code>/gift &lt;user_id&gt; &lt;search_bonus&gt; &lt;request_bonus&gt;</code>",
            parse_mode="HTML",
        )
        return

    try:
        target_id = int(args[0])
        search_bonus = int(args[1])
        request_bonus = int(args[2])
    except ValueError:
        await update.effective_message.reply_text(
            "⚠️ Invalid numbers provided.\n"
            "<b>Usage:</b> <code>/gift &lt;user_id&gt; &lt;search_bonus&gt; &lt;request_bonus&gt;</code>",
            parse_mode="HTML",
        )
        return

    _, message = gift_quota(admin_id, target_id, search_bonus, request_bonus)
    await update.effective_message.reply_text(message, parse_mode="HTML")


async def refer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Telegram command handler for /refer to generate link, view invite history, and share."""
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    bot_username = context.bot.username

    referral_link = f"https://t.me/{bot_username}?start=ref_{user.id}"
    stats = get_user_referral_stats(user.id)
    total_invites = stats["total_invites"]
    referred_list = stats["referred_list"]

    text = (
        f"🔗 <b>Your Referral Dashboard</b>\n\n"
        f"📌 <b>Your Link:</b>\n<code>{html.escape(referral_link)}</code>\n\n"
        f"📊 <b>Total Friends Invited:</b> <code>{total_invites}</code>\n"
        f"🎁 <b>Bonus Earned:</b> <code>{html.escape(str(referral_earned_label(total_invites)))}</code>\n\n"
    )

    if referred_list:
        text += "👥 <b>Invited Users:</b>\n"
        for r_id, r_name, r_uname, timestamp in referred_list[:10]:
            name_display = html.escape(r_name or f"User {r_id}")
            text += f"• {name_display} (ID: <code>{r_id}</code>)\n"
        if total_invites > 10:
            text += f"\n<i>(Showing latest 10 of {total_invites} invites)</i>\n"
    else:
        text += "💡 <i>You haven't invited anyone yet. Share your link to start earning bonuses!</i>"

    text += f"\n\n<i>When a new user starts via your link, both of you get {html.escape(str(referral_bonus_label()))}!</i>"

    share_text = f"Join {bot_name()} Bot and let's earn bonus searches & requests!"
    share_url = f"https://t.me/share/url?url={referral_link}&text={share_text}"

    keyboard = [
        [InlineKeyboardButton("📤 Refer More & Share Link", url=share_url)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
    await msg.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
