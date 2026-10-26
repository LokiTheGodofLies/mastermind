import os
import logging
import datetime
from modules.database.config_db import get_config

logger = logging.getLogger(__name__)

async def send_startup_notification(application):
    logger_group_id = get_config("logger_group_id", fallback_env="LOGGER_GROUP_ID") or get_config("storage_group_id", fallback_env="STORAGE_GROUP_ID")
    if not logger_group_id:
        print("⚠️ [STARTUP WARNING] Logger Group ID not set.")
        return
    try:
        bot_info = await application.bot.get_me()
        bot_title = bot_info.first_name or "Mastermind Bot"
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        default_template = "🔄 <b>ʙᴏᴛ ʀᴇꜱᴛᴀʀᴛᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ</b>\n\n🤖 <b>{bot_title}</b> ɪꜱ ɴᴏᴡ ᴏɴʟɪɴᴇ\n⏱️ ʀᴇꜱᴛᴀʀᴛᴇᴅ ᴀᴛ {deploy_time}\n🤞ꜱᴇᴇ /stats"
        template = get_config("startup_log_script", default=default_template)
        startup_text = template.format(bot_title=bot_title, deploy_time=current_time)

        media_type = get_config("startup_log_media_type", default="none")
        media_url = get_config("startup_log_media_url", default="")
        chat_id = int(logger_group_id)

        if media_type == "photo" and media_url:
            await application.bot.send_photo(chat_id=chat_id, photo=media_url, caption=startup_text, parse_mode="HTML")
        elif media_type == "video" and media_url:
            await application.bot.send_video(chat_id=chat_id, video=media_url, caption=startup_text, parse_mode="HTML")
        elif media_type == "animation" and media_url:
            await application.bot.send_animation(chat_id=chat_id, animation=media_url, caption=startup_text, parse_mode="HTML")
        else:
            await application.bot.send_message(chat_id=chat_id, text=startup_text, parse_mode="HTML")
        print("✅ [STARTUP] Restart notification sent successfully!")
    except Exception as e:
        print(f"❌ [STARTUP ERROR]: {e}")
