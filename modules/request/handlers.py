import os
import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

def check_database_for_book(query: str) -> bool:
    """Checks if the book exists in database/files.db"""
    db_path = "database/files.db"
    if not os.path.exists(db_path):
        return False
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [t[0] for t in cursor.fetchall()]
        
        for table in tables:
            cursor.execute(f"PRAGMA table_info({table});")
            columns = [col[1] for col in cursor.fetchall()]
            for col in columns:
                if any(k in col.lower() for k in ['title', 'name', 'filename']):
                    cursor.execute(f"SELECT 1 FROM {table} WHERE {col} LIKE ? LIMIT 1;", (f"%{query}%",))
                    if cursor.fetchone():
                        conn.close()
                        return True
        conn.close()
    except Exception as e:
        logger.error(f"Database check error: {e}")
    return False

async def request_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Extract query from args or reply
    query = ""
    if context.args:
        query = " ".join(context.args)
    elif message.reply_to_message and message.reply_to_message.text:
        query = message.reply_to_message.text.strip()

    # IF SENT ALONE (No query and no reply): Trigger Verification / Join Request Flow
    if not query:
        text = (
            "📥 <b>Mastermind Request Center</b>\n\n"
            "To keep requests orderly and spam-free, would you like to join our dedicated request group?"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Yes, Join", callback_data="req_join_yes"),
             InlineKeyboardButton("❌ No", callback_data="req_join_no")]
        ]
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return

    # IF SENT WITH A QUERY: Run Database -> Goodreads -> Interactive Flow
    await message.reply_text(f"🔍 Searching database for <i>\"{query}\"</i>...", parse_mode='HTML')

    if check_database_for_book(query):
        await message.reply_text(
            f"📚 <b>Book Already Available!</b>\n\n"
            f"<i>\"{query}\"</i> is already in our library. You can search and download it directly in our Search Group or via Bot PM.",
            parse_mode='HTML'
        )
        return

    # TODO: Integrate your existing Goodreads fetch & preview buttons here
    await message.reply_text(
        f"🔎 Not found in local database. Fetching Goodreads metadata for <i>\"{query}\"</i>...",
        parse_mode='HTML'
    )

async def request_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "req_join_yes":
        REQUEST_CHAT_ID = os.getenv('REQUEST_CHAT_ID')
        try:
            invite = await context.bot.create_chat_invite_link(
                chat_id=int(REQUEST_CHAT_ID),
                member_limit=1,
                expire_date=int(query.message.date.timestamp()) + 3600
            )
            await query.edit_message_text(
                f"✅ <b>Verification Passed!</b>\n\nHere is your secure, single-use invite link to the Request Group:\n{invite.invite_link}",
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Failed to create invite link: {e}")
            await query.edit_message_text("❌ Failed to generate invite link. Please contact an admin.")
    elif data == "req_join_no":
        await query.edit_message_text("❌ Request cancelled.")
