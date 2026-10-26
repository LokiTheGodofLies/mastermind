import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.database.config_db import get_config

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.from_user:
        return

    user_id = message.from_user.id
    admin_ids = [7261537212]
    is_admin = user_id in admin_ids

    # Fetch stats header script from configuration DB
    default_header = "📊 <b>Mastermind Bot Statistics</b>"
    header_text = get_config("stats_header_script", default=default_header)

    if is_admin:
        stats_text = (
            f"{header_text}\n\n"
            "👑 <b>Admin System Metrics:</b>\n"
            "• Bot Status: 🟢 Online (Configuration DB Active)\n"
            "• Active Database: configuration.db\n"
            "• Access Level: Administrator"
        )
    else:
        stats_text = (
            f"{header_text}\n\n"
            "👥 <b>Public User Metrics:</b>\n"
            "• Bot is fully operational and serving requests!"
        )

    # Fetch optional media config for stats
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
