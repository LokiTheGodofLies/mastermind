import os
import logging
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from modules.database.file_db import get_file_by_unique_id_db, save_indexed_file_db

logger = logging.getLogger(__name__)
SUPPORTED_EBOOK_EXTENSIONS = {'.epub', '.pdf', '.mobi'}
INDEX_LOG_TOPIC_ID = 18

async def handle_book_indexing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    STORAGE_GROUP_ID = os.getenv('STORAGE_GROUP_ID')
    if not STORAGE_GROUP_ID: return
    message = update.message or update.channel_post or update.effective_message
    if not message or not message.document: return
    document = message.document
    file_id = document.file_id
    file_unique_id = document.file_unique_id
    file_name = document.file_name or 'unknown_file'
    file_size = document.file_size or 0
    mime_type = document.mime_type or 'document'
    _, ext = os.path.splitext(file_name.lower())
    if ext not in SUPPORTED_EBOOK_EXTENSIONS:
        if update.message: await update.message.reply_text('❌ Unsupported format!')
        return
    if get_file_by_unique_id_db(file_unique_id):
        if update.message: await update.message.reply_text('📚 Already indexed')
        return
    try:
        base_name = os.path.splitext(file_name)[0]
        target_msg = await asyncio.wait_for(context.bot.send_document(chat_id=int(STORAGE_GROUP_ID), document=file_id, caption=f"📖 **Title:** {base_name}\n📚 **Format:** Ebook", parse_mode='Markdown', message_thread_id=INDEX_LOG_TOPIC_ID), timeout=15.0)
        user = message.from_user
        save_indexed_file_db(file_unique_id=file_unique_id, file_id=file_id, storage_message_id=target_msg.message_id, file_name=file_name, file_size=file_size, duration=0, user_id=user.id if user else 0, user_title=user.full_name or user.username or 'Unknown', caption=message.caption or '', extension=ext, file_type=mime_type, category='book')
        try:
            log_text = f"📥 <b>File Indexed Successfully</b>\n\n📂 <b>Filename:</b> <code>{file_name}</code>\n🆔 <b>Unique ID:</b> <code>{file_unique_id}</code>\n👤 <b>Indexed By:</b> {user.full_name if user else 'Unknown'} (<code>{user.id if user else 'N/A'}</code>)"
            await context.bot.send_message(chat_id=int(STORAGE_GROUP_ID), text=log_text, parse_mode='HTML', message_thread_id=INDEX_LOG_TOPIC_ID)
        except Exception as e: print(e)
        if update.message: await update.message.reply_text('✅ Ebook successfully indexed and stored in the library!')
    except Exception as e:
        if update.message: await update.message.reply_text(f"❌ Error: {e}")
