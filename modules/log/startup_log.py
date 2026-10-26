import os
import logging
import asyncio

logger = logging.getLogger(__name__)

async def send_startup_notification(application):
    logger_group_id = os.getenv("LOGGER_GROUP_ID") or os.getenv("STORAGE_GROUP_ID")
    general_topic_id = int(os.getenv("GENERAL_TOPIC_ID", "1"))

    if not logger_group_id:
        print("⚠️ [STARTUP WARNING] LOGGER_GROUP_ID not set, skipping restart notification.")
        return

    try:
        # Give bot session a moment to bind
        await asyncio.sleep(1.5)
        startup_text = (
            "🔄 <b>Bot Restarted Successfully</b>\n\n"
            "🤖 Mastermind Bot is now online and polling for updates.\n"
            "⏱️ <i>System initialized and ready.</i>"
        )
        await application.bot.send_message(
            chat_id=int(logger_group_id),
            text=startup_text,
            parse_mode="HTML",
            message_thread_id=general_topic_id
        )
        print(f"✅ [STARTUP] Restart notification sent successfully to Logger Group (Topic ID {general_topic_id}).")
    except Exception as e:
        print(f"❌ [STARTUP ERROR] Failed to send restart notification: {e}")
