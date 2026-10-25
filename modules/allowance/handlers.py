from telegram import Update
from telegram.ext import ContextTypes
from modules.allowance.allowance import get_user_quota_summary, gift_quota
from modules.allowance.referral import get_user_referral_stats

async def quota_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Telegram command handler for /quota"""
    user_id = update.effective_user.id
    summary = get_user_quota_summary(user_id)
    
    if not summary:
        await update.message.reply_text("⚠️ Could not retrieve your quota record.")
        return
        
    if summary["unlimited"]:
        await update.message.reply_text(
            f"👤 **Your Role:** {summary['role']}\n"
            f"♾️ **Status:** Unlimited searches and requests."
        )
    else:
        await update.message.reply_text(
            f"👤 **Your Role:** {summary['role']}\n\n"
            f"🔍 **Searches Remaining:** {summary['searches_left']} / {summary['searches_limit']}\n"
            f"📥 **Requests Remaining:** {summary['requests_left']} / {summary['requests_limit']}\n\n"
            f"*(Quotas reset automatically every day)*",
            parse_mode="Markdown"
        )

async def gift_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Telegram command handler for /gift <user_id> <searches> <requests>"""
    admin_id = update.effective_user.id
    args = context.args
    
    if len(args) < 3:
        await update.message.reply_text(
            "⚠️ **Usage:** `/gift <user_id> <search_bonus> <request_bonus>`",
            parse_mode="Markdown"
        )
        return
        
    try:
        target_id = int(args[0])
        search_bonus = int(args[1])
        request_bonus = int(args[2])
    except ValueError:
        await update.message.reply_text(
            "⚠️ Invalid numbers provided.\n"
            "**Usage:** `/gift <user_id> <search_bonus> <request_bonus>`",
            parse_mode="Markdown"
        )
        return
        
    success, message = gift_quota(admin_id, target_id, search_bonus, request_bonus)
    await update.message.reply_text(message, parse_mode="Markdown")

async def refer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Telegram command handler for /refer to generate link and view invite history."""
    user = update.effective_user
    bot_username = context.bot.username
    
    # Generate personal referral link
    referral_link = f"https://t.me/{bot_username}?start=ref_{user.id}"
    
    # Fetch user's referral stats
    stats = get_user_referral_stats(user.id)
    total_invites = stats["total_invites"]
    referred_list = stats["referred_list"]
    
    # Build response message
    text = (
        f"🔗 **Your Referral Dashboard**\n\n"
        f"📌 **Your Link:**\n`{referral_link}`\n\n"
        f"📊 **Total Friends Invited:** `{total_invites}`\n"
        f"🎁 **Bonus Earned:** `+{total_invites * 10}` Searches & Requests\n\n"
    )
    
    if referred_list:
        text += "👥 **Invited Users:**\n"
        # Show up to the last 10 invited users for cleanliness
        for r_id, r_name, r_uname, timestamp in referred_list[:10]:
            name_display = r_name or f"User {r_id}"
            text += f"• {name_display} (ID: `{r_id}`)\n"
        if total_invites > 10:
            text += f"\n*(Showing latest 10 of {total_invites} invites)*\n"
    else:
        text += "💡 *You haven't invited anyone yet. Share your link to start earning bonuses!*"
        
    text += f"\n\n*When a new user starts via your link, both of you get +10 searches & requests!*"
    
    await update.message.reply_text(text, parse_mode="Markdown")
