import os
import logging
import asyncio

logger = logging.getLogger(__name__)
GENERAL_TOPIC_ID = 1

async def send_startup_notification(application):
    STORAGE_GROUP_ID = os.getenv("STORAGE_GROUP_ID")
    if not STORAGE_GROUP_ID:
        print("⚠️ [STARTUP WARNING] STORAGE_GROUP_ID not set, skipping restart notification.")
        return

    try:
        startup_text = (
            "🔄 <b>Bot Restarted Successfully</b>\n\n"
            "🤖 Mastermind Bot is now online and polling for updates.\n"
            "⏱️ <i>System initialized and ready.</i>"
        )
        await application.bot.send_message(
            chat_id=int(STORAGE_GROUP_ID),
            text=startup_text,
            parse_mode="HTML",
            message_thread_id=GENERAL_TOPIC_ID
        )
        print("✅ [STARTUP] Restart notification sent to General topic (ID 1).")
    except Exception as e:
        print(f"❌ [STARTUP ERROR] Failed to send restart notification: {e}")
