import os
import logging
import asyncio
from telegram import Update
from telegram.ext import ContextTypes

from modules.database.file_db import (
    get_file_by_unique_id_db,
    save_indexed_file_db,
)

logger = logging.getLogger(__name__)

SUPPORTED_EBOOK_EXTENSIONS = {'.epub', '.pdf', '.mobi'}

async def handle_book_indexing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("🔥 [DEBUG] handle_book_indexing triggered!")
    
    STORAGE_GROUP_ID = os.getenv("STORAGE_GROUP_ID")
    if not STORAGE_GROUP_ID:
        print("❌ [LOG ERROR] STORAGE_GROUP_ID is missing from environment!")
        return

    message = update.message or update.channel_post or update.effective_message
    if not message or not message.document:
        print("❌ [LOG ERROR] No message or document found in update!")
        return

    document = message.document
    file_id = document.file_id
    file_unique_id = document.file_unique_id
    file_name = document.file_name or "unknown_file"
    file_size = document.file_size or 0
    mime_type = document.mime_type or "document"
    _, ext = os.path.splitext(file_name.lower())

    print(f"📄 [LOG INFO] Document received: {file_name} | Ext: {ext} | Size: {file_size}")

    if ext not in SUPPORTED_EBOOK_EXTENSIONS:
        print(f"❌ [LOG ERROR] Unsupported extension: {ext}")
        if update.message:
            await update.message.reply_text("❌ Unsupported format! Please send a valid ebook (.epub, .pdf, or .mobi).")
        return

    print("🔍 [DEBUG] Checking database for file_unique_id...")
    db_record = get_file_by_unique_id_db(file_unique_id)
    if db_record:
        print("📚 [LOG INFO] File already exists in database. Skipping duplicate.")
        if update.message:
            await update.message.reply_text("📚 This ebook is already indexed and stored in the library!")
        return

    print(f"🚀 [LOG INFO] Attempting to send document with 15s timeout to chat ID: {STORAGE_GROUP_ID}")
    print("⏳ [DEBUG] About to invoke asyncio.wait_for(context.bot.send_document)")
    
    try:
        base_name = os.path.splitext(file_name)[0]
        formatted_caption = f"📖 **Title:** {base_name}\n📚 **Format:** Ebook"
        
        # Wrapped with asyncio.wait_for to prevent infinite hanging
        target_msg = await asyncio.wait_for(
            context.bot.send_document(
                chat_id=STORAGE_GROUP_ID,
                document=file_id,
                caption=formatted_caption,
                parse_mode="Markdown"
            ),
            timeout=15.0
        )
        print(f"✅ [LOG SUCCESS] Successfully sent to storage group! Storage Message ID: {target_msg.message_id}")
        
        user = message.from_user
        save_indexed_file_db(
            file_unique_id=file_unique_id,
            file_id=file_id,
            storage_message_id=target_msg.message_id,
            file_name=file_name,
            file_size=file_size,
            duration=0,
            user_id=user.id if user else 0,
            user_title=user.full_name or user.username or "Unknown",
            caption=message.caption or "",
            extension=ext,
            file_type=mime_type,
            category="book"
        )
        print("✅ [LOG SUCCESS] File recorded into SQLite database.")
        
        if update.message:
            await update.message.reply_text("✅ Ebook successfully indexed and stored in the library!")
            
    except asyncio.TimeoutError:
        print("❌ [LOG CRITICAL ERROR] send_document timed out after 15 seconds! Check your network or bot permissions in the storage group.")
        if update.message:
            await update.message.reply_text("❌ Error: Request to storage group timed out. Is the bot an admin in the storage group?")
    except Exception as e:
        print(f"❌ [LOG CRITICAL ERROR] Failed to send document via Telegram API: {e}")
        if update.message:
            await update.message.reply_text(f"❌ Error forwarding to storage group: {e}")
