import os
import logging
from telegram import Update
from telegram.ext import ContextTypes

# Placeholder for database functions (to be implemented in user_db or index_db)
from modules.database.user_db import (
    get_file_by_file_id_db,
    save_file_db,
)

logger = logging.getLogger(__name__)

# Allowed ebook extensions
SUPPORTED_EBOOK_EXTENSIONS = {'.epub', '.pdf', '.mobi'}

# Storage group ID (configure via config or env)
STORAGE_GROUP_ID = os.getenv("STORAGE_GROUP_ID", "-100123456789")


async def fetch_and_format_book_caption(file_name: str) -> str:
    """
    Placeholder for the upcoming Book Caption Module.
    Fetches book metadata and returns a formatted caption.
    """
    # Will be expanded in the next step
    base_name = os.path.splitext(file_name)[0]
    return f"📖 **Title:** {base_name}\n📚 **Format:** Ebook"


async def handle_book_indexing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Core indexing function for books:
    1. Checks if file is sent/uploaded.
    2. Validates unique file_id against the database.
    3. Handles storage group synchronization (DB vs Storage).
    4. Step 3: Checks ebook extensions (.epub, .pdf, .mobi) and triggers metadata/caption update.
    """
    message = update.message or update.channel_post
    if not message or not message.document:
        return

    document = message.document
    file_id = document.file_id
    file_name = document.file_name or "unknown_file"
    _, ext = os.path.splitext(file_name.lower())

    # Step 1 & 2: Check database and storage existence
    db_record = get_file_by_file_id_db(file_id)
    exists_in_db = db_record is not None
    
    # Check if message is coming from or being sent to the storage group
    is_in_storage_group = str(message.chat_id) == str(STORAGE_GROUP_ID)

    # Logic: Syncing DB and Storage Group
    if is_in_storage_group and not exists_in_db:
        # File exists in storage group but not in DB -> Save to DB
        logger.info(f"File found in storage group but missing in DB. Saving: {file_name}")
        save_file_db(file_id=file_id, file_name=file_name, chat_id=message.chat_id, message_id=message.message_id, category="book")
        exists_in_db = True

    elif not is_in_storage_group and not exists_in_db:
        # File sent to bot directly -> Forward/Copy to storage group, then save to DB
        logger.info(f"Forwarding new book to storage group: {file_name}")
        forwarded_msg = await context.bot.forward_message(
            chat_id=STORAGE_GROUP_ID,
            from_chat_id=message.chat_id,
            message_id=message.message_id
        )
        save_file_db(
            file_id=file_id,
            file_name=file_name,
            chat_id=STORAGE_GROUP_ID,
            message_id=forwarded_msg.message_id,
            category="book"
        )

    # Step 3: Check extension and update caption
    if ext in SUPPORTED_EBOOK_EXTENSIONS:
        logger.info(f"Processing supported ebook extension ({ext}): {file_name}")
        
        # Generate new caption using the book info fetcher hook
        new_caption = await fetch_and_format_book_caption(file_name)
        
        # Determine target message to update caption on
        target_chat_id = STORAGE_GROUP_ID if not is_in_storage_group else message.chat_id
        target_message_id = forwarded_msg.message_id if not is_in_storage_group else message.message_id

        try:
            await context.bot.edit_message_caption(
                chat_id=target_chat_id,
                message_id=target_message_id,
                caption=new_caption,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to update book caption for {file_name}: {e}")
    else:
        logger.info(f"File extension {ext} is not a supported ebook format.")
