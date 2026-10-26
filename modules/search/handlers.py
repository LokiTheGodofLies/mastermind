import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.database.config_db import get_config

async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Fetch text script from config DB with default fallback
    default_text = "🔒 Please verify your access to use search."
    text_content = get_config("search_welcome_script", default=default_text)

    # Fetch media config
    media_type = get_config("search_media_type", default="none")
    media_url = get_config("search_media_url", default="")

    # Sample interactive buttons
    keyboard = [
        [InlineKeyboardButton("🔍 Start Search", url="https://t.me/"), InlineKeyboardButton("❓ Support", url="https://t.me/")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if media_type == "photo" and media_url:
        await message.reply_photo(photo=media_url, caption=text_content, reply_markup=reply_markup, parse_mode="HTML")
    elif media_type == "video" and media_url:
        await message.reply_video(video=media_url, caption=text_content, reply_markup=reply_markup, parse_mode="HTML")
    elif media_type == "animation" and media_url:
        await message.reply_animation(animation=media_url, caption=text_content, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await message.reply_text(text=text_content, reply_markup=reply_markup, parse_mode="HTML")


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await search_handler(update, context)

async def search_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("🔍 Search action processed.", parse_mode="HTML")
