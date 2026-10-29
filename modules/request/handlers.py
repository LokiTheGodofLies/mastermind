import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ApplicationHandlerStop
from modules.database.file_db import get_connection as get_db_connection
import os
import requests
from bs4 import BeautifulSoup
import html

logger = logging.getLogger(__name__)

def fetch_goodreads_metadata(query):
    try:
        search_url = f"https://www.goodreads.com/search?q={requests.utils.quote(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(search_url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, 'html.parser')
        results = []
        rows = soup.select("tr[itemtype='http://schema.org/Book']")[:5]
        for row in rows:
            title_tag = row.select_one("span[itemprop='name']")
            author_tag = row.select_one("span[itemprop='author']")
            link_tag = row.select_one("a.bookTitle")
            rating_tag = row.select_one("span.minirating")
            
            if title_tag and link_tag:
                title = title_tag.get_text(strip=True)
                author = author_tag.get_text(strip=True) if author_tag else "Unknown Author"
                url = "https://www.goodreads.com" + link_tag["href"]
                rating = rating_tag.get_text(strip=True) if rating_tag else ""
                results.append({"title": title, "author": author, "url": url, "rating": rating})
        return results
    except Exception as e:
        logger.error(f"Error fetching Goodreads metadata: {e}")
        return []

async def request_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    
    query = " ".join(context.args).strip()
    if not query:
        await message.reply_text("📖 Please provide a book title or keyword. Usage: <code>/request [book name]</code>", parse_mode="HTML")
        return
    
    q_esc = html.escape(query)
    status_msg = await message.reply_text(f"🔎 Searching local database for <i>\"{q_esc}\"</i>...", parse_mode="HTML")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT file_id, file_name FROM indexed_files WHERE file_name LIKE ? LIMIT 5", (f"%{query}%",))
    rows = cursor.fetchall()
    conn.close()
    
    if rows:
        header = f"📁 <b>Local Database Matches for:</b> <i>\"{q_esc}\"</i>\n"
        lines = [header]
        for row in rows:
            file_id, file_name = row
            lines.append(f"• {html.escape(file_name)}")
        text = "\n".join(lines)
        await status_msg.edit_text(text, parse_mode="HTML")
    else:
        await process_goodreads_or_request(status_msg, query, context)

async def process_goodreads_or_request(status_msg, query, context):
    q_esc = html.escape(query)
    await status_msg.edit_text(f"🔎 Not found in local database. Fetching Goodreads metadata for <i>\"{q_esc}\"</i>...", parse_mode="HTML")
    matches = fetch_goodreads_metadata(query)
    if matches:
        bot_username = context.bot.username or (await context.bot.get_me()).username
        if "goodreads_cache" not in context.bot_data:
            context.bot_data["goodreads_cache"] = {}
        context.bot_data["goodreads_cache"][status_msg.chat_id] = matches
        context.bot_data["goodreads_last_matches"] = matches
        context.bot_data["goodreads_last_query"] = query

        header = f"📖 <b>Goodreads Book Matches Found for:</b> <i>\"{q_esc}\"</i>"
        lines = [header, "", "Tap any book title below to select and request it:"]
        for idx, book in enumerate(matches):
            title = html.escape(book["title"])
            author = html.escape(book["author"])
            url = book["url"]
            rating = html.escape(book.get("rating", ""))
            cmd_link = f"https://t.me/{bot_username}?start=req_pick_{idx}"
            lines.append(f'{idx + 1}. <a href="{cmd_link}">📚 <b>{title}</b> ({author})</a> — {rating} [<a href="{url}">Goodreads</a>]')

        manual_link = f"https://t.me/{bot_username}?start=req_manual"
        lines.append("")
        lines.append(f'✍️ <a href="{manual_link}"><b>Request Manually (\"{html.escape(query[:35])}\")</b></a>')

        text = "\n".join(lines)
        await status_msg.edit_text(text, parse_mode="HTML", disable_web_page_preview=True)
    else:
        text = f"📖 <b>Book Request:</b> <i>\"{q_esc}\"</i>\n\nNo Goodreads matches found. Would you like to submit this request directly to the Request Channel?"
        keyboard = [
            [InlineKeyboardButton("📤 Submit Request", callback_data=f"req_sub_orig_{query[:40]}"),
             InlineKeyboardButton("❌ Cancel", callback_data="req_join_no")]
        ]
        await status_msg.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def request_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("req_sub_orig_") or data.startswith("req_sub_gb_"):
        book_query = data.split("_", 3)[-1]
        request_channel_id = os.getenv("REQUEST_CHANNEL_ID", "-1004447576324")
        user = query.from_user
        user_mention = f"<a href='tg://user?id={user.id}'>{user.full_name}</a>"
        bq_esc = html.escape(book_query)
        
        req_text = f"📥 <b>New Book Request</b>\n\n👤 <b>Requested By:</b> {user_mention}\n📖 <b>Book / Query:</b> <i>\"{bq_esc}\"</i>"
        try:
            await context.bot.send_message(
                chat_id=int(request_channel_id),
                text=req_text,
                parse_mode="HTML"
            )
            await query.edit_message_text(
                f"✅ <b>Request Submitted Successfully!</b>\n\nYour request for <i>\"{bq_esc}\"</i> has been forwarded to the Request Channel.",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to send request to channel: {e}")
            await query.edit_message_text("❌ Failed to submit request to channel. Please try again later.")
    elif data == "req_join_no":
        await query.edit_message_text("❌ Request cancelled.")

async def request_deeplink_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not context.args:
        return
    payload = context.args[0]
    if payload.startswith("req_pick_"):
        try:
            idx = int(payload.split("req_pick_")[1])
        except ValueError:
            return
        matches = context.bot_data.get("goodreads_cache", {}).get(
            message.chat_id,
            context.bot_data.get("goodreads_last_matches", [])
        )
        orig_query = context.bot_data.get("goodreads_last_query", "")
        if 0 <= idx < len(matches):
            book_data = matches[idx]
            title = html.escape(book_data["title"])
            author = html.escape(book_data["author"])
            rating = html.escape(book_data.get("rating", "No rating"))
            url = book_data["url"]
            text = f"📖 <b>Goodreads Book Selected</b>\n\n📌 <b>Title:</b> <a href=\"{url}\">{title}</a>\n✍️ <b>Author:</b> {author}\n⭐ <b>Rating:</b> {rating}\n\nIs this the book you are looking for?"
            encoded_title = book_data["title"][:40]
            fallback_q = (orig_query or book_data["title"])[:40]
            keyboard = [
                [InlineKeyboardButton("✅ Yes (Submit Goodreads)", callback_data=f"req_sub_gb_{encoded_title}")],
                [InlineKeyboardButton("❌ No (Submit Original)", callback_data=f"req_sub_orig_{fallback_q}")]
            ]
            await message.reply_text(
                text,
                parse_mode="HTML",
                disable_web_page_preview=False,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            raise ApplicationHandlerStop
    elif payload == "req_manual":
        orig_query = context.bot_data.get("goodreads_last_query", "Book Request")
        oq_esc = html.escape(orig_query)
        text = f"📖 <b>Book Request:</b> <i>\"{oq_esc}\"</i>\n\nWould you like to submit this request directly to the Request Channel?"
        keyboard = [
            [InlineKeyboardButton("📤 Submit Request", callback_data=f"req_sub_orig_{orig_query[:40]}"),
             InlineKeyboardButton("❌ Cancel", callback_data="req_join_no")]
        ]
        await message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        raise ApplicationHandlerStop
