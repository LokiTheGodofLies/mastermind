from configs import log_topic
import os
import logging
import asyncio
import html
import re
from urllib.parse import quote_plus, urljoin
import aiohttp
from telegram import Update
from telegram.ext import ContextTypes
from modules.database.file_db import get_file_by_unique_id_db, save_indexed_file_db

logger = logging.getLogger(__name__)
SUPPORTED_EBOOK_EXTENSIONS = {".epub", ".pdf", ".mobi"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_BOOK_CACHE: dict[str, dict] = {}


def clean_filename_for_search(file_name: str) -> str:
    if not file_name:
        return ""
    name = re.sub(r"\.[a-zA-Z0-9]{2,5}$", "", file_name)
    name = re.sub(r"\[.*?\]|\(.*?\)", " ", name)
    noise = r"\b(z-lib\.org|z-library|annas-archive|libgen|epub|pdf|azw3|kfx|mp3|m4b|aax|audiobook|unabridged|64kbps|128kbps)\b"
    name = re.sub(noise, " ", name, flags=re.IGNORECASE)
    name = re.sub(r"[_\.\-]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _default_book_meta(clean_title: str) -> dict:
    return {
        "book_title": clean_title or "Unknown Title",
        "book_author": "N/A",
        "book_rating": "N/A",
        "book_ratings_count": "0",
        "book_genres": "N/A",
        "book_pages": "N/A",
        "book_isbn": "N/A",
        "book_language": "N/A",
        "book_published": "N/A",
        "book_description": "N/A",
        "book_url": "",
        "book_cover": "",
    }


async def fetch_goodreads_metadata(file_name: str) -> dict:
    clean_query = clean_filename_for_search(file_name)
    if not clean_query:
        return _default_book_meta(file_name)

    cache_key = clean_query.lower()
    if cache_key in _BOOK_CACHE:
        return _BOOK_CACHE[cache_key]

    timeout = aiohttp.ClientTimeout(total=8)
    try:
        async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout) as session:
            words = clean_query.split()
            candidate_queries = [clean_query]
            if len(words) > 5:
                candidate_queries.append(" ".join(words[:5]))

            stub_data = None
            for q in candidate_queries:
                auto_url = f"https://www.goodreads.com/book/auto_complete?format=json&q={quote_plus(q)}"
                async with session.get(auto_url) as resp:
                    if resp.status == 200:
                        items = await resp.json(content_type=None)
                        if isinstance(items, list) and len(items) > 0:
                            first = items[0]
                            book_path = first.get("bookUrl", "")
                            author_obj = first.get("author") or {}
                            stub_data = {
                                "book_title": first.get("title") or clean_query,
                                "book_author": author_obj.get("name") if isinstance(author_obj, dict) else "N/A",
                                "book_rating": str(first.get("avgRating") or "N/A"),
                                "book_ratings_count": str(first.get("ratingsCount") or "0"),
                                "book_genres": "N/A",
                                "book_pages": "N/A",
                                "book_isbn": "N/A",
                                "book_language": "N/A",
                                "book_published": "N/A",
                                "book_description": "N/A",
                                "book_url": urljoin("https://www.goodreads.com", book_path).split("?")[0],
                                "book_cover": first.get("imageUrl") or "",
                            }
                            break

            if not stub_data:
                return _default_book_meta(clean_query)

            if len(_BOOK_CACHE) >= 500:
                _BOOK_CACHE.clear()
            _BOOK_CACHE[cache_key] = stub_data
            return stub_data

    except Exception as e:
        print(f"[GOODREADS SCRAPER WARNING] Could not fetch '{clean_query}': {e}")
        return _default_book_meta(clean_query)


def format_index_channel_caption(
    file_name: str,
    file_size_str: str,
    extension: str,
    file_type: str,
    book_meta: dict,
) -> str:
    esc_file_name = html.escape(file_name or "Unknown")
    esc_title = html.escape(book_meta.get("book_title") or "Unknown")
    esc_author = html.escape(book_meta.get("book_author") or "N/A")
    esc_rating = html.escape(book_meta.get("book_rating") or "N/A")
    esc_ratings_count = html.escape(book_meta.get("book_ratings_count") or "0")
    esc_genres = html.escape(book_meta.get("book_genres") or "N/A")
    esc_pages = html.escape(book_meta.get("book_pages") or "N/A")
    esc_published = html.escape(book_meta.get("book_published") or "N/A")
    book_url = book_meta.get("book_url") or ""

    title_display = (
        f'<a href="{html.escape(book_url)}">{esc_title}</a>' if book_url else esc_title
    )

    lines = [
        f"📚 <b>Book:</b> {title_display}",
        f"✍️ <b>Author:</b> <code>{esc_author}</code>",
        f"⭐ <b>Rating:</b> <code>{esc_rating}</code> (<code>{esc_ratings_count}</code> ratings)",
        f"🏷 <b>Genres:</b> <code>{esc_genres}</code>",
        f"📄 <b>Pages:</b> <code>{esc_pages}</code> | 📅 <code>{esc_published}</code>",
        "",
        f"📁 <b>File Name:</b> <code>{esc_file_name}</code>",
        f"📦 <b>Size:</b> <code>{html.escape(file_size_str)}</code> | <b>Type:</b> <code>{html.escape(file_type)} (.{html.escape(extension)})</code>",
    ]

    caption = "\n".join(lines)
    return caption[:1020]


async def handle_book_indexing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    STORAGE_GROUP_ID = os.getenv("STORAGE_GROUP_ID")
    LOGGER_GROUP_ID = os.getenv("LOGGER_GROUP_ID")
    INDEX_LOG_TOPIC_ID = log_topic("INDEX")

    if not STORAGE_GROUP_ID:
        return

    message = update.message or update.channel_post or update.effective_message
    if not message or not message.document:
        return

    # Ignore messages posted inside the storage group itself
    if message.chat and str(message.chat.id) == str(STORAGE_GROUP_ID):
        return

    document = message.document
    file_id = document.file_id
    file_unique_id = document.file_unique_id
    file_name = document.file_name or "unknown_file"
    file_size = document.file_size or 0
    mime_type = document.mime_type or "document"
    _, ext = os.path.splitext(file_name.lower())

    if ext not in SUPPORTED_EBOOK_EXTENSIONS:
        if update.message and update.message.chat.type == "private":
            await update.message.reply_text("❌ Unsupported format!")
        return

    if get_file_by_unique_id_db(file_unique_id):
        if update.message and update.message.chat.type == "private":
            await update.message.reply_text("📚 Already indexed")
        return

    try:
        book_meta = await fetch_goodreads_metadata(file_name)

        size_mb = file_size / (1024 * 1024)
        file_size_str = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{file_size / 1024:.2f} KB"

        caption_html = format_index_channel_caption(
            file_name=file_name,
            file_size_str=file_size_str,
            extension=ext.lstrip("."),
            file_type=mime_type,
            book_meta=book_meta,
        )

        target_msg = await asyncio.wait_for(
            context.bot.send_document(
                chat_id=int(STORAGE_GROUP_ID),
                document=file_id,
                caption=caption_html,
                parse_mode="HTML",
            ),
            timeout=25.0,
        )

        user = message.from_user
        searchable_caption = f"{message.caption or ''} {book_meta.get('book_title', '')} {book_meta.get('book_author', '')}".strip()
        save_indexed_file_db(
            file_unique_id=file_unique_id,
            file_id=file_id,
            storage_message_id=target_msg.message_id,
            file_name=file_name,
            file_size=file_size,
            duration=0,
            user_id=user.id if user else 0,
            user_title=user.full_name or user.username or "Unknown" if user else "Channel",
            caption=searchable_caption,
            extension=ext,
            file_type=mime_type,
            category="book",
        )

        if LOGGER_GROUP_ID:
            try:
                log_text = (
                    f"📥 <b>File Indexed Successfully</b>\n\n"
                    f"📂 <b>Filename:</b> <code>{html.escape(file_name)}</code>\n"
                    f"🆔 <b>Unique ID:</b> <code>{file_unique_id}</code>\n"
                    f"👤 <b>Indexed By:</b> {html.escape(user.full_name) if user else 'Unknown'} (<code>{user.id if user else 'N/A'}</code>)"
                )
                log_kwargs = {
                    "chat_id": int(LOGGER_GROUP_ID),
                    "text": log_text,
                    "parse_mode": "HTML",
                }
                if INDEX_LOG_TOPIC_ID:
                    log_kwargs["message_thread_id"] = int(INDEX_LOG_TOPIC_ID)

                await context.bot.send_message(**log_kwargs)
            except Exception as e:
                print(f"Log send error: {e}")

        if update.message and update.message.chat.type == "private":
            await update.message.reply_text("✅ Ebook successfully indexed, enriched with Goodreads metadata, and stored!")

    except Exception as e:
        print(f"❌ [INDEXING ERROR] Failed to process document: {e}")
        if update.message and update.message.chat.type == "private":
            await update.message.reply_text(f"❌ Error: {e}")
