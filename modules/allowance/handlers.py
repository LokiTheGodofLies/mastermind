from telegram import Update
from telegram.ext import ContextTypes
from modules.allowance.allowance import get_user_quota_summary, gift_quota

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
