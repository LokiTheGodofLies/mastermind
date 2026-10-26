import os
import logging
import sqlite3
import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

def check_database_for_book(query: str) -> bool:
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

def fetch_goodreads_metadata(query: str):
    try:
        search_url = f"https://www.goodreads.com/search?q={requests.utils.quote(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(search_url, headers=headers, timeout=5)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            result_title = soup.find('a', class_='bookTitle')
            result_author = soup.find('a', class_='authorName')
            result_img = soup.find('img', class_='bookCover')
            result_rating = soup.find('span', class_='minirating')
            if result_title:
                title = result_title.get_text(strip=True)
                url = "https://www.goodreads.com" + result_title.get('href', '')
                author = result_author.get_text(strip=True) if result_author else "Unknown Author"
                img_url = result_img.get('src', '') if result_img else ""
                rating = result_rating.get_text(strip=True) if result_rating else "No rating"
                return {"title": title, "author": author, "url": url, "img_url": img_url, "rating": rating}
    except Exception as e:
        logger.error(f"Goodreads fetch error: {e}")
    return None

async def request_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    query = ""
    if context.args:
        query = " ".join(context.args)
    elif message.reply_to_message and message.reply_to_message.text:
        query = message.reply_to_message.text.strip()
    if not query:
        text = "📥 <b>Mastermind Request Center</b>\n\nTo keep requests orderly and spam-free, would you like to join our dedicated request group?"
        keyboard = [
            [InlineKeyboardButton("✅ Yes, Join", callback_data="req_join_yes"),
             InlineKeyboardButton("❌ No", callback_data="req_join_no")]
        ]
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return
    status_msg = await message.reply_text(f"🔍 Searching database for <i>\"{query}\"</i>...", parse_mode="HTML")
    if check_database_for_book(query):
        await status_msg.edit_text(
            f"📚 <b>Book Already Available!</b>\n\n<i>\"{query}\"</i> is already in our library. You can search and download it directly in our Search Group or via Bot PM.",
            parse_mode="HTML"
        )
        return
    await status_msg.edit_text(f"🔎 Not found in local database. Fetching Goodreads metadata for <i>\"{query}\"</i>...", parse_mode="HTML")
    book_data = fetch_goodreads_metadata(query)
    if book_data:
        text = f"📖 <b>Goodreads Book Match Found</b>\n\n📌 <b>Title:</b> <a href=\"{book_data['url']}\">{book_data['title']}</a>\n✍️ <b>Author:</b> {book_data['author']}\n⭐ <b>Rating:</b> {book_data['rating']}\n\nWould you like to submit this book request to the Request Group?"
        encoded_title = book_data['title'][:40]
        keyboard = [
            [InlineKeyboardButton("📤 Submit Request", callback_data=f"req_submit_{encoded_title}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="req_join_no")]
        ]
        await status_msg.edit_text(text, parse_mode="HTML", disable_web_page_preview=False, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        text = f"📖 <b>Book Request:</b> <i>{query}</i>\n\nWould you like to submit this request directly to the Request Group?"
        keyboard = [
            [InlineKeyboardButton("📤 Submit Request", callback_data=f"req_submit_{query[:40]}")],
            [InlineKeyboardButton("❌ Cancel", callback_data="req_join_no")]
        ]
        await status_msg.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def request_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "req_join_yes":
        REQUEST_CHAT_ID = os.getenv("REQUEST_CHAT_ID")
        try:
            invite = await context.bot.create_chat_invite_link(
                chat_id=int(REQUEST_CHAT_ID),
                member_limit=1,
                expire_date=int(query.message.date.timestamp()) + 3600
            )
            await query.edit_message_text(
                f"✅ <b>Verification Passed!</b>\n\nHere is your secure, single-use invite link to the Request Group:\n{invite.invite_link}",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to create invite link: {e}")
            await query.edit_message_text("❌ Failed to generate invite link. Please contact an admin.")
    elif data.startswith("req_submit_"):
        book_query = data.replace("req_submit_", "")
        user = query.from_user
        user_mention = f"@{user.username}" if user.username else user.full_name
        REQUEST_CHAT_ID = os.getenv("REQUEST_CHAT_ID")
        topic_id = os.getenv("CHANNEL_LOG_TOPIC_ID") or os.getenv("GROUP_LOG_TOPIC_ID")
        if REQUEST_CHAT_ID:
            try:
                request_notice = f"📢 <b>New Book Request!</b>\n\n👤 <b>Requested By:</b> {user_mention} (<code>{user.id}</code>)\n📚 <b>Book:</b> <code>{book_query}</code>"
                msg_kwargs = {
                    "chat_id": int(REQUEST_CHAT_ID),
                    "text": request_notice,
                    "parse_mode": "HTML"
                }
                if topic_id:
                    msg_kwargs["message_thread_id"] = int(topic_id)
                await context.bot.send_message(**msg_kwargs)
                await query.edit_message_text(
                    f"✅ <b>Request Submitted Successfully!</b>\n\nYour request for <i>\"{book_query}\"</i> has been sent to the Request Group/Channel.",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Failed to send to request group: {e}")
                await query.edit_message_text("❌ Failed to forward request to the Request Group. Please contact an admin.")
        else:
            await query.edit_message_text("❌ Request Group ID is not configured.")
    elif data == "req_join_no":
        await query.edit_message_text("❌ Request cancelled.")
