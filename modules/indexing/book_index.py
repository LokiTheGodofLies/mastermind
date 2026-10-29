import asyncio
import html
import logging
import os
import re
from urllib.parse import quote_plus, urljoin
import aiohttp
from telegram import Update
from telegram.ext import ContextTypes

from config import (
    goodreads_base_url,
    goodreads_cache_max,
    log_topic,
    logger_group_id,
    scraper_user_agent,
    storage_group_id,
    supported_audiobook_extensions,
    supported_ebook_extensions,
    supported_extensions,
)
from modules.database.file_db import get_file_by_unique_id_db, save_indexed_file_db

logger = logging.getLogger(__name__)

# Backward-compatible module constants populated from config
SUPPORTED_EBOOK_EXTENSIONS = supported_ebook_extensions()
SUPPORTED_AUDIOBOOK_EXTENSIONS = supported_audiobook_extensions()
SUPPORTED_EXTENSIONS = supported_extensions()

MIME_EXTENSION_FALLBACK = {
    "application/epub+zip": ".epub",
    "application/pdf": ".pdf",
    "application/x-mobipocket-ebook": ".mobi",
    "application/vnd.amazon.ebook": ".azw",
    "application/x-cbr": ".cbr",
    "application/x-cbz": ".cbz",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4b",
    "audio/x-m4b": ".m4b",
    "audio/x-m4a": ".m4b",
    "audio/m4a": ".m4b",
    "audio/flac": ".flac",
    "audio/x-flac": ".flac",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/vnd.audible.aax": ".aax",
}

_BOOK_CACHE: dict[str, dict] = {}


def _headers() -> dict:
    return {
        "User-Agent": scraper_user_agent(),
        "Accept-Language": "en-US,en;q=0.9",
    }


def clean_filename_for_search(file_name: str) -> str:
    if not file_name:
        return ""
    name = re.sub(r"\.[a-zA-Z0-9]{2,5}$", "", file_name)
    name = re.sub(r"\[.*?\]|\(.*?\)|\{.*?\}", " ", name)
    noise = (
        r"\b(z-lib\.org|z-library|annas-archive|libgen|epub|pdf|azw|azw3|mobi|cbz|cbr|"
        r"kfx|mp3|m4b|aax|aa|flac|wav|audiobook|unabridged|abridged|64kbps|128kbps)\b"
    )
    name = re.sub(noise, " ", name, flags=re.IGNORECASE)
    name = re.sub(r"[_\.\-]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _format_duration(seconds: int) -> str:
    if not seconds or seconds <= 0:
        return "N/A"
    hrs = seconds // 3600
    mins = (seconds % 3600) // 60
    if hrs > 0 and mins > 0:
        return f"{hrs} hrs {mins} mins"
    if hrs > 0:
        return f"{hrs} hrs"
    return f"{max(1, mins)} mins"


def parse_caption_metadata(caption: str) -> dict:
    """Extracts pre-existing structured fields from an audiobook or ebook caption if present."""
    if not caption:
        return {}
    meta = {}
    patterns = {
        "book_title": r"(?:🎧\s*Audiobook|📚\s*Book)\s*:\s*(.+)",
        "book_author": r"✍️\s*(?:By|Author)\s*:\s*(.+)",
        "narrator": r"🎙\s*Narrated by\s*:\s*(.+)",
        "length": r"⏱\s*Length\s*:\s*(.+)",
        "book_published": r"📅\s*(?:Release Date\s*:)?\s*(.+)",
        "publisher": r"🏢\s*Publisher\s*:\s*(.+)",
        "caption_file_name": r"📁\s*(?:File(?:\s*Name)?)\s*:\s*(.+)",
        "caption_type": r"Type\s*:\s*(?:[^(\n]*\()?(\.[a-zA-Z0-9]{2,5})\)?",
    }
    for key, pat in patterns.items():
        m = re.search(pat, caption, flags=re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if val:
                meta[key] = val
    return meta


def extract_media_info(message) -> dict | None:
    """Extracts unified media details from a Telegram message (supports both Document and Audio)."""
    if not message:
        return None

    media = message.document or getattr(message, "audio", None)
    if not media:
        return None

    media_kind = "document" if message.document else "audio"
    caption = message.caption or ""
    cap_meta = parse_caption_metadata(caption)

    raw_name = getattr(media, "file_name", None) or ""
    if not raw_name and cap_meta.get("caption_file_name"):
        raw_name = cap_meta["caption_file_name"]

    _, ext = os.path.splitext(raw_name.lower())
    if not ext and cap_meta.get("caption_type"):
        ext = cap_meta["caption_type"].lower()
    if not ext:
        mime = (getattr(media, "mime_type", None) or "").lower()
        ext = MIME_EXTENSION_FALLBACK.get(mime, "")
    if not raw_name:
        title_hint = cap_meta.get("book_title") or getattr(media, "title", None) or "unknown_file"
        raw_name = f"{title_hint}{ext}" if ext and not title_hint.lower().endswith(ext) else title_hint
    elif ext and not raw_name.lower().endswith(ext):
        raw_name = f"{raw_name}{ext}"

    ebook_exts = supported_ebook_extensions()
    audiobook_exts = supported_audiobook_extensions()
    all_exts = ebook_exts | audiobook_exts

    is_supported = ext in all_exts
    category = "audiobook" if ext in audiobook_exts else "ebook"

    return {
        "media_kind": media_kind,
        "file_id": media.file_id,
        "file_unique_id": media.file_unique_id,
        "file_name": raw_name,
        "file_size": getattr(media, "file_size", 0) or 0,
        "duration": getattr(media, "duration", 0) or 0,
        "mime_type": getattr(media, "mime_type", None) or media_kind,
        "extension": ext,
        "category": category,
        "is_supported": is_supported,
        "caption_meta": cap_meta,
    }


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
        "narrator": "N/A",
        "length": "N/A",
        "publisher": "Audible",
    }


async def fetch_goodreads_metadata(file_name: str) -> dict:
    clean_query = clean_filename_for_search(file_name)
    if not clean_query:
        return _default_book_meta(file_name)

    cache_key = clean_query.lower()
    if cache_key in _BOOK_CACHE:
        return dict(_BOOK_CACHE[cache_key])

    base_url = goodreads_base_url()
    timeout = aiohttp.ClientTimeout(total=8)
    try:
        async with aiohttp.ClientSession(headers=_headers(), timeout=timeout) as session:
            words = clean_query.split()
            candidate_queries = [clean_query]
            if len(words) > 5:
                candidate_queries.append(" ".join(words[:5]))

            stub_data = None
            for q in candidate_queries:
                auto_url = f"{base_url}/book/auto_complete?format=json&q={quote_plus(q)}"
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
                                "book_url": urljoin(base_url, book_path).split("?")[0],
                                "book_cover": first.get("imageUrl") or "",
                                "narrator": "N/A",
                                "length": "N/A",
                                "publisher": "Audible",
                            }
                            break

            if not stub_data:
                return _default_book_meta(clean_query)

            if len(_BOOK_CACHE) >= goodreads_cache_max():
                _BOOK_CACHE.clear()
            _BOOK_CACHE[cache_key] = stub_data
            return dict(stub_data)

    except Exception as e:
        print(f"[GOODREADS SCRAPER WARNING] Could not fetch '{clean_query}': {e}")
        return _default_book_meta(clean_query)


def format_index_channel_caption(
    file_name: str,
    file_size_str: str,
    extension: str,
    file_type: str,
    book_meta: dict,
    category: str = "ebook",
) -> str:
    esc_file_name = html.escape(file_name or "Unknown")
    esc_title = html.escape(book_meta.get("book_title") or "Unknown")
    esc_author = html.escape(book_meta.get("book_author") or "N/A")
    esc_published = html.escape(book_meta.get("book_published") or "N/A")
    book_url = book_meta.get("book_url") or ""
    ext_clean = html.escape(extension.lstrip("."))

    title_display = (
        f'<a href="{html.escape(book_url)}">{esc_title}</a>' if book_url else esc_title
    )

    if category == "audiobook" or f".{extension.lstrip('.').lower()}" in supported_audiobook_extensions():
        esc_narrator = html.escape(book_meta.get("narrator") or "N/A")
        esc_length = html.escape(book_meta.get("length") or "N/A")
        esc_publisher = html.escape(book_meta.get("publisher") or "Audible")
        lines = [
            f"🎧 <b>Audiobook:</b> {title_display}",
            f"✍️ <b>By:</b> <code>{esc_author}</code>",
            f"🎙 <b>Narrated by:</b> <code>{esc_narrator}</code>",
            f"⏱ <b>Length:</b> <code>{esc_length}</code>",
            f"📅 <b>Release Date:</b> <code>{esc_published}</code>",
            f"🏢 <b>Publisher:</b> <code>{esc_publisher}</code>",
            "",
            f"📁 <b>File:</b> <code>{esc_file_name}</code>",
            f"📦 <b>Size:</b> <code>{html.escape(file_size_str)}</code> | <b>Type:</b> <code>.{ext_clean}</code>",
        ]
    else:
        esc_rating = html.escape(book_meta.get("book_rating") or "N/A")
        esc_ratings_count = html.escape(book_meta.get("book_ratings_count") or "0")
        esc_genres = html.escape(book_meta.get("book_genres") or "N/A")
        esc_pages = html.escape(book_meta.get("book_pages") or "N/A")
        lines = [
            f"📚 <b>Book:</b> {title_display}",
            f"✍️ <b>Author:</b> <code>{esc_author}</code>",
            f"⭐ <b>Rating:</b> <code>{esc_rating}</code> (<code>{esc_ratings_count}</code> ratings)",
            f"🏷 <b>Genres:</b> <code>{esc_genres}</code>",
            f"📄 <b>Pages:</b> <code>{esc_pages}</code> | 📅 <code>{esc_published}</code>",
            "",
            f"📁 <b>File Name:</b> <code>{esc_file_name}</code>",
            f"📦 <b>Size:</b> <code>{html.escape(file_size_str)}</code> | <b>Type:</b> <code>{html.escape(file_type)} (.{ext_clean})</code>",
        ]

    caption = "\n".join(lines)
    return caption[:1020]


async def send_media_to_storage(bot, storage_chat_id: int, info: dict, caption_html: str):
    """Sends either an audio or document attachment to the storage group."""
    if info["media_kind"] == "audio":
        try:
            return await asyncio.wait_for(
                bot.send_audio(
                    chat_id=int(storage_chat_id),
                    audio=info["file_id"],
                    caption=caption_html,
                    parse_mode="HTML",
                ),
                timeout=25.0,
            )
        except Exception:
            pass
    return await asyncio.wait_for(
        bot.send_document(
            chat_id=int(storage_chat_id),
            document=info["file_id"],
            caption=caption_html,
            parse_mode="HTML",
        ),
        timeout=25.0,
    )


async def handle_book_indexing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    storage_id = storage_group_id()
    log_group_id = logger_group_id()
    index_log_topic_id = log_topic("INDEX")

    if not storage_id:
        return

    message = update.message or update.channel_post or update.effective_message
    if not message:
        return

    # Ignore messages posted inside the storage group itself
    if message.chat and str(message.chat.id) == str(storage_id):
        return

    info = extract_media_info(message)
    if not info:
        return

    if not info["is_supported"]:
        if update.message and update.message.chat.type == "private":
            ebook_list = ", ".join(sorted(supported_ebook_extensions()))
            audio_list = ", ".join(sorted(supported_audiobook_extensions()))
            await update.message.reply_text(
                f"❌ <b>Unsupported format!</b>\n\n"
                f"📚 <b>Supported Ebooks:</b> <code>{ebook_list}</code>\n"
                f"🎧 <b>Supported Audiobooks:</b> <code>{audio_list}</code>",
                parse_mode="HTML",
            )
        return

    file_unique_id = info["file_unique_id"]
    file_id = info["file_id"]
    file_name = info["file_name"]
    file_size = info["file_size"]
    duration = info["duration"]
    mime_type = info["mime_type"]
    ext = info["extension"]
    category = info["category"]

    if get_file_by_unique_id_db(file_unique_id):
        if update.message and update.message.chat.type == "private":
            await update.message.reply_text("📚 Already indexed")
        return

    try:
        book_meta = await fetch_goodreads_metadata(file_name)
        # Preserve any richer fields present in the original caption
        for k, v in (info.get("caption_meta") or {}).items():
            if v and k in ("book_title", "book_author", "narrator", "length", "book_published", "publisher"):
                book_meta[k] = v
        if category == "audiobook" and book_meta.get("length in ('', 'N/A', None)"):
            pass
        if category == "audiobook" and (not book_meta.get("length") or book_meta.get("length") == "N/A") and duration > 0:
            book_meta["length"] = _format_duration(duration)

        size_mb = file_size / (1024 * 1024)
        file_size_str = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{file_size / 1024:.2f} KB"

        caption_html = format_index_channel_caption(
            file_name=file_name,
            file_size_str=file_size_str,
            extension=ext.lstrip("."),
            file_type=mime_type,
            book_meta=book_meta,
            category=category,
        )

        target_msg = await send_media_to_storage(context.bot, int(storage_id), info, caption_html)

        user = message.from_user
        searchable_caption = (
            f"{message.caption or ''} {book_meta.get('book_title', '')} "
            f"{book_meta.get('book_author', '')} {book_meta.get('narrator', '')}"
        ).strip()

        save_indexed_file_db(
            file_unique_id=file_unique_id,
            file_id=file_id,
            storage_message_id=target_msg.message_id,
            file_name=file_name,
            file_size=file_size,
            duration=duration,
            user_id=user.id if user else 0,
            user_title=user.full_name or user.username or "Unknown" if user else "Channel",
            caption=searchable_caption,
            extension=ext,
            file_type=mime_type,
            category=category,
        )

        if log_group_id:
            try:
                label = "Audiobook" if category == "audiobook" else "Ebook"
                log_text = (
                    f"📥 <b>{label} Indexed Successfully</b>\n\n"
                    f"📂 <b>Filename:</b> <code>{html.escape(file_name)}</code>\n"
                    f"🏷 <b>Format:</b> <code>{html.escape(ext)}</code> ({label})\n"
                    f"🆔 <b>Unique ID:</b> <code>{file_unique_id}</code>\n"
                    f"👤 <b>Indexed By:</b> {html.escape(user.full_name) if user else 'Unknown'} (<code>{user.id if user else 'N/A'}</code>)"
                )
                log_kwargs = {
                    "chat_id": int(log_group_id),
                    "text": log_text,
                    "parse_mode": "HTML",
                }
                if index_log_topic_id:
                    log_kwargs["message_thread_id"] = int(index_log_topic_id)

                await context.bot.send_message(**log_kwargs)
            except Exception as e:
                print(f"Log send error: {e}")

        if update.message and update.message.chat.type == "private":
            label = "Audiobook" if category == "audiobook" else "Ebook"
            await update.message.reply_text(f"✅ {label} successfully indexed, enriched with metadata, and stored!")

    except Exception as e:
        print(f"❌ [INDEXING ERROR] Failed to process media: {e}")
        if update.message and update.message.chat.type == "private":
            await update.message.reply_text(f"❌ Error: {e}")
