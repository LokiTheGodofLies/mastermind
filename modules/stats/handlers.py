from config import bot_name
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.database.config_db import get_config
from modules.database.user_db import is_admin_or_owner, get_user_role_db


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    role = get_user_role_db(user.id)
    is_admin = is_admin_or_owner(user.id)

    default_header = f"📊 <b>{bot_name()} Bot Statistics</b>"
    header_text = get_config("stats_header_script", default=default_header)

    if is_admin:
        stats_text = (
            f"{header_text}\n\n"
            "👑 <b>Admin System Metrics:</b>\n"
            "• Bot Status: 🟢 Online (Configuration DB Active)\n"
            "• Active Database: config.db / files.db / mastermind_users.db\n"
            f"• Access Level: {role}"
        )
    else:
        stats_text = (
            f"{header_text}\n\n"
            "👥 <b>Public User Metrics:</b>\n"
            "• Bot is fully operational and serving requests!"
        )

    media_type = get_config("stats_media_type", default="none")
    media_url = get_config("stats_media_url", default="")

    keyboard = [[InlineKeyboardButton("« Back to Start", callback_data="start_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if media_type == "photo" and media_url:
        await message.reply_photo(photo=media_url, caption=stats_text, reply_markup=reply_markup, parse_mode="HTML")
    elif media_type == "video" and media_url:
        await message.reply_video(video=media_url, caption=stats_text, reply_markup=reply_markup, parse_mode="HTML")
    elif media_type == "animation" and media_url:
        await message.reply_animation(animation=media_url, caption=stats_text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await message.reply_text(text=stats_text, reply_markup=reply_markup, parse_mode="HTML")
