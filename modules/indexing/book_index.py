import asyncio
import html
import json
import logging
import os
import re
from datetime import datetime
from urllib.parse import quote_plus, urljoin
import urllib.request
import urllib.error

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    from telegram import Update
    from telegram.error import TelegramError
    from telegram.ext import ContextTypes
except ImportError:
    Update = object
    TelegramError = Exception
    class ContextTypes:
        DEFAULT_TYPE = object

from config import (
    admin_ids,
    creator_id,
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
from modules.database.file_db import (
    get_file_by_storage_message_id_db,
    get_file_by_unique_id_db,
    save_indexed_file_db,
    update_file_caption_db,
)
from modules.database.user_db import is_admin_or_creator

logger = logging.getLogger(__name__)

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

_METADATA_CACHE: dict[str, dict] = {}


def _headers() -> dict:
    return {
        "User-Agent": scraper_user_agent(),
        "Accept": "application/json, text/html, application/xhtml+xml, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }


def _ist_now_str() -> str:
    """Returns current timestamp string."""
    return datetime.now().strftime("%d %b %Y, %H:%M IST")


def _format_duration(seconds: int) -> str:
    if not seconds:
        return ""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}h {m}m"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


# ---------------------------------------------------------------------------
# Filename Tokenization & Cleaning (Suggestions A + B + C + Watermark Stripping)
# ---------------------------------------------------------------------------
def clean_filename_for_search(file_name: str) -> str:
    if not file_name:
        return ""

    name = re.sub(r"\.[a-zA-Z0-9]{2,5}$", "", file_name)
    name = name.replace("’", "'").replace("‘", "'").replace("`", "'")
    name = re.sub(r"(^|\s)'([^']*)'(\s|$)", r"\1 \2 \3", name)

    name = re.sub(
        r"\b(z-lib\.org|z-library|annas-archive|libgen|oceanofpdf|audiobookbay|mobilism|epub|pdf|azw|azw3|mobi|cbz|cbr|mp3|m4b|aax|flac|wav)\b",
        " ",
        name,
        flags=re.IGNORECASE,
    )

    name = re.sub(r"[^a-zA-Z0-9\s']", " ", name)
    name = re.sub(r"\s+'+\s+", " ", name)
    name = re.sub(r"^'+\s*|\s*'+$", "", name)

    return re.sub(r"\s+", " ", name).strip()


def parse_title_and_series(raw_title: str) -> tuple[str, str]:
    if not raw_title:
        return "Unknown Title", "Standalone"

    series_pattern = r"\s*\(([^)]*?(?:#\s*\d+|Book\s+\d+|Vol(?:ume)?\.?\s*\d+)[^)]*)\)"
    m = re.search(series_pattern, raw_title, re.IGNORECASE)
    if m:
        series_str = m.group(1).strip()
        clean_t = (raw_title[: m.start()] + raw_title[m.end() :]).strip(" -_")
        if "#" in series_str and not series_str.endswith(")"):
            series_str = re.sub(r"#\s*(\d+)", r"(#\1)", series_str)
        return clean_t or raw_title.strip(), series_str or "Standalone"

    m2 = re.search(r"\s*\(([^)]+)\)$", raw_title)
    if m2:
        inside = m2.group(1).strip()
        if any(c.isdigit() for c in inside) or "series" in inside.lower():
            clean_t = raw_title[: m2.start()].strip(" -_")
            return clean_t or raw_title.strip(), inside

    return raw_title.strip(), "Standalone"


def is_derivative_work(title: str, query: str) -> bool:
    q_low = query.lower()
    t_low = title.lower()
    indicators = [
        "study guide:",
        "study guide :",
        "summary of",
        "summary & analysis",
        "summary and analysis",
        "book analysis:",
        "companion guide",
        "supersummary",
        "instaread",
        "quicklet",
    ]
    for ind in indicators:
        if ind in t_low and ind not in q_low:
            return True
    return False


def _normalize_tokens(text: str) -> set[str]:
    text = text.replace("’", "'").replace("‘", "'").replace("`", "'")
    words = re.findall(r"[a-zA-Z0-9']+", text.lower())
    tokens = set()
    for w in words:
        clean_w = w.strip("'")
        if len(clean_w) > 1 or clean_w.isdigit():
            tokens.add(clean_w)
            if "'" in w:
                tokens.add(w.replace("'", ""))
    return tokens


def match_parameters(
    filename_query: str,
    item_title: str,
    item_author: str,
    item_series: str = "",
) -> int:
    fn_tokens = _normalize_tokens(filename_query)
    title_tokens = _normalize_tokens(item_title)
    author_tokens = _normalize_tokens(item_author)
    series_tokens = _normalize_tokens(item_series) if item_series and item_series != "Standalone" else set()

    matches = 0
    author_matched = False
    if author_tokens and fn_tokens:
        overlap = author_tokens.intersection(fn_tokens)
        if overlap:
            matches += 1
            author_matched = True

    if title_tokens and fn_tokens:
        overlap = title_tokens.intersection(fn_tokens)
        if len(overlap) >= min(2, len(title_tokens)):
            matches += 1

    if series_tokens and fn_tokens:
        overlap = series_tokens.intersection(fn_tokens)
        if overlap:
            matches += 1

    if author_tokens and not author_matched and len(author_tokens) > 0:
        matches = max(0, matches - 1)

    return matches


# ---------------------------------------------------------------------------
# Multi-Site HTTP Request Dispatcher
# ---------------------------------------------------------------------------
async def _async_get_json(url: str, timeout_sec: int = 6) -> dict | list | None:
    headers = _headers()
    if aiohttp is not None:
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout_sec)) as resp:
                    if resp.status == 200:
                        return await resp.json(content_type=None)
        except Exception as e:
            logger.debug("aiohttp get_json error for %s: %s", url, e)
            return None
    else:
        def _sync_fetch():
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=timeout_sec) as response:
                    if response.status == 200:
                        return json.loads(response.read().decode("utf-8", "ignore"))
            except Exception as e:
                logger.debug("urllib get_json error for %s: %s", url, e)
                return None
        return await asyncio.to_thread(_sync_fetch)


async def _fetch_goodreads(query: str) -> list[dict]:
    url = f"https://www.goodreads.com/book/auto_complete?format=json&q={quote_plus(query)}"
    try:
        data = await _async_get_json(url, timeout_sec=6)
        if isinstance(data, list):
            candidates = []
            for item in data[:8]:
                title = item.get("bookTitleBare") or item.get("title") or ""
                raw_title = item.get("title") or title
                author_obj = item.get("author") or {}
                author_name = author_obj.get("name", "") if isinstance(author_obj, dict) else ""
                book_id = str(item.get("bookId") or "")
                book_url = f"https://www.goodreads.com/book/show/{book_id}" if book_id else ""
                if item.get("bookUrl"):
                    book_url = urljoin("https://www.goodreads.com", item["bookUrl"]).split("?")[0]

                clean_t, series = parse_title_and_series(raw_title)
                rating = str(item.get("avgRating") or "")
                ratings_count = str(item.get("ratingsCount") or "")

                candidates.append({
                    "title": clean_t,
                    "raw_title": raw_title,
                    "author": author_name,
                    "series": series,
                    "rating": rating,
                    "ratings_count": ratings_count,
                    "url": book_url,
                    "provider": "Goodreads",
                })
            return candidates
    except Exception as e:
        logger.debug("Goodreads error: %s", e)
    return []


async def _fetch_audible(query: str) -> list[dict]:
    for tld in ("com", "in", "co.uk"):
        url = (
            f"https://api.audible.{tld}/1.0/catalog/products"
            f"?title={quote_plus(query)}&num_results=6&products_plan=all"
        )
        try:
            data = await _async_get_json(url, timeout_sec=5)
            if isinstance(data, dict):
                products = data.get("products") or []
                candidates = []
                for prod in products:
                    asin = prod.get("asin") or ""
                    title = prod.get("title") or ""
                    authors = [a.get("name", "") for a in (prod.get("authors") or []) if a.get("name")]
                    narrators = [n.get("name", "") for n in (prod.get("narrators") or []) if n.get("name")]
                    series_list = prod.get("series") or []
                    series_name = "Standalone"
                    if series_list:
                        s = series_list[0]
                        stitle = s.get("title") or ""
                        seq = s.get("sequence") or ""
                        series_name = f"{stitle} (#{seq})" if seq else stitle

                    runtime = prod.get("runtime_length_min") or 0
                    length_str = f"{runtime // 60}h {runtime % 60}m" if runtime else ""
                    pub_date = prod.get("release_date") or prod.get("issue_date") or ""

                    rating_obj = (prod.get("rating") or {}).get("overall_distribution") or {}
                    rating = str(rating_obj.get("display_average_rating") or "")
                    ratings_count = str(rating_obj.get("num_ratings") or "")

                    genres = []
                    for ladder in prod.get("category_ladders") or []:
                        for cat in ladder.get("ladder") or []:
                            if cat.get("name") and cat["name"] not in genres:
                                genres.append(cat["name"])

                    book_url = f"https://www.audible.{tld}/pd/{asin}" if asin else ""

                    clean_t, parsed_s = parse_title_and_series(title)
                    if series_name == "Standalone" and parsed_s != "Standalone":
                        series_name = parsed_s

                    candidates.append({
                        "title": clean_t,
                        "raw_title": title,
                        "author": ", ".join(authors),
                        "narrator": ", ".join(narrators),
                        "series": series_name,
                        "length": length_str,
                        "published": pub_date,
                        "rating": rating,
                        "ratings_count": ratings_count,
                        "genres": ", ".join(genres[:3]),
                        "url": book_url,
                        "provider": "Audible",
                    })
                if candidates:
                    return candidates
        except Exception as e:
            logger.debug("Audible %s error: %s", tld, e)
    return []


async def _fetch_google_books(query: str) -> list[dict]:
    url = f"https://www.googleapis.com/books/v1/volumes?q={quote_plus(query)}&maxResults=6"
    try:
        data = await _async_get_json(url, timeout_sec=5)
        if isinstance(data, dict):
            items = data.get("items") or []
            candidates = []
            for item in items:
                info = item.get("volumeInfo") or {}
                title = info.get("title") or ""
                subtitle = info.get("subtitle") or ""
                full_title = f"{title}: {subtitle}" if subtitle else title
                authors = info.get("authors") or []
                pages = str(info.get("pageCount") or "")
                pub_date = info.get("publishedDate") or ""
                categories = info.get("categories") or []
                rating = str(info.get("averageRating") or "")
                ratings_count = str(info.get("ratingsCount") or "")
                info_link = info.get("infoLink") or ""

                clean_t, series = parse_title_and_series(full_title)

                candidates.append({
                    "title": clean_t,
                    "raw_title": full_title,
                    "author": ", ".join(authors),
                    "series": series,
                    "pages": pages,
                    "published": pub_date,
                    "genres": ", ".join(categories[:3]),
                    "rating": rating,
                    "ratings_count": ratings_count,
                    "url": info_link,
                    "provider": "Google Books",
                })
            return candidates
    except Exception as e:
        logger.debug("Google Books error: %s", e)
    return []


async def _fetch_openlibrary(query: str) -> list[dict]:
    url = f"https://openlibrary.org/search.json?q={quote_plus(query)}&limit=6"
    try:
        data = await _async_get_json(url, timeout_sec=5)
        if isinstance(data, dict):
            docs = data.get("docs") or []
            candidates = []
            for doc in docs:
                title = doc.get("title") or ""
                authors = doc.get("author_name") or []
                year = str(doc.get("first_publish_year") or "")
                pages = str(doc.get("number_of_pages_median") or "")
                subjects = doc.get("subject") or []
                key = doc.get("key") or ""
                url_link = f"https://openlibrary.org{key}" if key else ""

                clean_t, series = parse_title_and_series(title)

                candidates.append({
                    "title": clean_t,
                    "raw_title": title,
                    "author": ", ".join(authors[:3]),
                    "series": series,
                    "pages": pages,
                    "published": year,
                    "genres": ", ".join(subjects[:3]),
                    "url": url_link,
                    "provider": "OpenLibrary",
                })
            return candidates
    except Exception as e:
        logger.debug("OpenLibrary error: %s", e)
    return []


async def _fetch_apple_books(query: str, is_audiobook: bool = False) -> list[dict]:
    entity = "audiobook" if is_audiobook else "ebook"
    url = f"https://itunes.apple.com/search?term={quote_plus(query)}&entity={entity}&limit=6"
    try:
        data = await _async_get_json(url, timeout_sec=5)
        if isinstance(data, dict):
            results = data.get("results") or []
            candidates = []
            for item in results:
                title = item.get("trackName") or ""
                author = item.get("artistName") or ""
                track_url = item.get("trackViewUrl") or ""
                release_date = (item.get("releaseDate") or "")[:10]
                genres = item.get("genres") or []
                rating = str(item.get("averageUserRating") or "")
                ratings_count = str(item.get("userRatingCount") or "")

                clean_t, series = parse_title_and_series(title)

                entry = {
                    "title": clean_t,
                    "raw_title": title,
                    "author": author,
                    "series": series,
                    "published": release_date,
                    "genres": ", ".join(genres[:3]),
                    "rating": rating,
                    "ratings_count": ratings_count,
                    "url": track_url,
                    "provider": "Apple Books",
                }
                if is_audiobook:
                    duration_ms = item.get("trackTimeMillis") or 0
                    if duration_ms > 0:
                        mins = duration_ms // 60000
                        entry["length"] = f"{mins // 60}h {mins % 60}m"
                candidates.append(entry)
            return candidates
    except Exception as e:
        logger.debug("Apple Books error: %s", e)
    return []


# ---------------------------------------------------------------------------
# Metadata Enrichment Pipeline
# ---------------------------------------------------------------------------
async def enrich_book_metadata(file_name: str, category: str = "ebook") -> dict:
    clean_query = clean_filename_for_search(file_name)
    if not clean_query:
        return {"is_matched": False, "clean_query": file_name}

    cache_key = f"{category}:{clean_query.lower()}"
    if cache_key in _METADATA_CACHE:
        return dict(_METADATA_CACHE[cache_key])

    is_audio = (category == "audiobook")

    if is_audio:
        primary_sequence = ["audible", "apple", "goodreads", "google", "openlibrary"]
    else:
        primary_sequence = ["goodreads", "google", "openlibrary", "apple", "audible"]

    matched_item = None
    matched_provider = None

    try:
        for prov in primary_sequence:
            candidates = []
            if prov == "goodreads":
                candidates = await _fetch_goodreads(clean_query)
            elif prov == "audible":
                candidates = await _fetch_audible(clean_query)
            elif prov == "google":
                candidates = await _fetch_google_books(clean_query)
            elif prov == "openlibrary":
                candidates = await _fetch_openlibrary(clean_query)
            elif prov == "apple":
                candidates = await _fetch_apple_books(clean_query, is_audiobook=is_audio)

            for cand in candidates:
                if is_derivative_work(cand.get("raw_title", "") or cand.get("title", ""), clean_query):
                    continue

                score = match_parameters(
                    filename_query=clean_query,
                    item_title=cand.get("title", ""),
                    item_author=cand.get("author", ""),
                    item_series=cand.get("series", ""),
                )

                if score >= 2:
                    matched_item = dict(cand)
                    matched_provider = prov
                    break

            if matched_item:
                break

        if matched_item:
            v_title = matched_item.get("title") or ""
            v_author = matched_item.get("author") or ""
            cross_query = f"{v_title} {v_author}".strip()
            check_series = (matched_item.get("series") in (None, "", "Standalone"))

            for prov in primary_sequence:
                if prov == matched_provider:
                    continue
                cross_cands = []
                if prov == "goodreads":
                    cross_cands = await _fetch_goodreads(cross_query)
                elif prov == "audible":
                    cross_cands = await _fetch_audible(cross_query)
                elif prov == "google":
                    cross_cands = await _fetch_google_books(cross_query)
                elif prov == "openlibrary":
                    cross_cands = await _fetch_openlibrary(cross_query)
                elif prov == "apple":
                    cross_cands = await _fetch_apple_books(cross_query, is_audiobook=is_audio)

                for cc in cross_cands:
                    if is_derivative_work(cc.get("raw_title", "") or cc.get("title", ""), cross_query):
                        continue
                    if _normalize_tokens(v_title).intersection(_normalize_tokens(cc.get("title", ""))):
                        for field in ("pages", "published", "rating", "ratings_count", "genres", "narrator", "length"):
                            if not matched_item.get(field) and cc.get(field):
                                matched_item[field] = cc[field]
                        if check_series and cc.get("series") and cc["series"] != "Standalone":
                            matched_item["series"] = cc["series"]
                            check_series = False
                        break

            matched_item["is_matched"] = True
            if not matched_item.get("series"):
                matched_item["series"] = "Standalone"

            if len(_METADATA_CACHE) >= goodreads_cache_max():
                _METADATA_CACHE.clear()
            _METADATA_CACHE[cache_key] = matched_item
            return dict(matched_item)

    except Exception as e:
        logger.warning("Metadata enrichment warning for '%s': %s", clean_query, e)

    return {
        "is_matched": False,
        "clean_query": clean_query,
        "title": "",
        "author": "",
        "series": "",
        "url": "",
    }


# Backward-compatible alias
async def fetch_goodreads_metadata(file_name: str) -> dict:
    meta = await enrich_book_metadata(file_name, category="ebook")
    return {
        "book_title": meta.get("title") or file_name,
        "book_author": meta.get("author") or "",
        "book_series": meta.get("series") or "Standalone",
        "book_rating": meta.get("rating") or "",
        "book_ratings_count": meta.get("ratings_count") or "",
        "book_genres": meta.get("genres") or "",
        "book_pages": meta.get("pages") or "",
        "book_published": meta.get("published") or "",
        "book_url": meta.get("url") or "",
        "narrator": meta.get("narrator") or "",
        "length": meta.get("length") or "",
        "is_matched": meta.get("is_matched", False),
    }


# ---------------------------------------------------------------------------
# Caption & Log Formatters (Zero N/A)
# ---------------------------------------------------------------------------
def format_index_channel_caption(
    file_name: str,
    file_size_str: str,
    extension: str,
    file_type: str,
    book_meta: dict,
    category: str = "ebook",
) -> str:
    """
    Constructs clean, structured storage group caption:
    1. If metadata was matched:
       - Hyperlinks title with matched website book info URL.
       - Series tag S (if not Standalone).
       - Zero N/A: omits any missing optional field entirely.
    2. If enrichment failed (<2 parameters):
       - Leaves T and A empty with clean placeholders so search does not index false info.
    """
    esc_file_name = html.escape(file_name or "Unknown")
    ext_clean = html.escape(extension.lstrip("."))
    is_matched = book_meta.get("is_matched", False)

    if not is_matched:
        # Failure placeholder caption
        if category == "audiobook" or f".{ext_clean.lower()}" in supported_audiobook_extensions():
            lines = [
                "🎧 <b>Audiobook:</b> ",
                "✍️ <b>By:</b> ",
                f"📁 <b>File Name:</b> <code>{esc_file_name}</code>",
                f"📦 <b>Size:</b> <code>{html.escape(file_size_str)}</code> | <b>Type:</b> <code>{html.escape(file_type)} (.{ext_clean})</code>",
            ]
        else:
            lines = [
                "📚 <b>Book:</b> ",
                "✍️ <b>Author:</b> ",
                f"📁 <b>File Name:</b> <code>{esc_file_name}</code>",
                f"📦 <b>Size:</b> <code>{html.escape(file_size_str)}</code> | <b>Type:</b> <code>{html.escape(file_type)} (.{ext_clean})</code>",
            ]
        return "\n".join(lines)[:1020]

    raw_title = book_meta.get("title") or book_meta.get("book_title") or ""
    esc_title = html.escape(raw_title)
    book_url = book_meta.get("url") or book_meta.get("book_url") or ""
    title_display = f'<a href="{html.escape(book_url)}">{esc_title}</a>' if book_url else esc_title

    esc_author = html.escape(book_meta.get("author") or book_meta.get("book_author") or "")
    esc_series = html.escape(book_meta.get("series") or book_meta.get("book_series") or "Standalone")
    esc_published = html.escape(book_meta.get("published") or book_meta.get("book_published") or "")

    lines = []
    if category == "audiobook" or f".{ext_clean.lower()}" in supported_audiobook_extensions():
        lines.append(f"🎧 <b>Audiobook:</b> {title_display}")
        if esc_author:
            lines.append(f"✍️ <b>By:</b> <code>{esc_author}</code>")
        if esc_series and esc_series != "Standalone":
            lines.append(f"📚 <b>Series:</b> <code>{esc_series}</code>")
        esc_narrator = html.escape(book_meta.get("narrator") or "")
        if esc_narrator:
            lines.append(f"🎙 <b>Narrated by:</b> <code>{esc_narrator}</code>")
        esc_length = html.escape(book_meta.get("length") or "")
        if esc_length:
            lines.append(f"⏱ <b>Length:</b> <code>{esc_length}</code>")
        if esc_published:
            lines.append(f"📅 <b>Release Date:</b> <code>{esc_published}</code>")
        lines.append("")
        lines.append(f"📁 <b>File:</b> <code>{esc_file_name}</code>")
        lines.append(f"📦 <b>Size:</b> <code>{html.escape(file_size_str)}</code> | <b>Type:</b> <code>.{ext_clean}</code>")
    else:
        lines.append(f"📚 <b>Book:</b> {title_display}")
        if esc_author:
            lines.append(f"✍️ <b>Author:</b> <code>{esc_author}</code>")
        if esc_series and esc_series != "Standalone":
            lines.append(f"📚 <b>Series:</b> <code>{esc_series}</code>")
        esc_rating = html.escape(book_meta.get("rating") or book_meta.get("book_rating") or "")
        esc_ratings_count = html.escape(book_meta.get("ratings_count") or book_meta.get("book_ratings_count") or "")
        if esc_rating:
            rc_str = f" ({esc_ratings_count} ratings)" if esc_ratings_count else ""
            lines.append(f"⭐ <b>Rating:</b> <code>{esc_rating}</code>{rc_str}")
        esc_genres = html.escape(book_meta.get("genres") or book_meta.get("book_genres") or "")
        if esc_genres:
            lines.append(f"🏷 <b>Genres:</b> <code>{esc_genres}</code>")
        esc_pages = html.escape(book_meta.get("pages") or book_meta.get("book_pages") or "")
        if esc_pages and esc_published:
            lines.append(f"📄 <b>Pages:</b> <code>{esc_pages}</code> | 📅 <code>{esc_published}</code>")
        elif esc_pages:
            lines.append(f"📄 <b>Pages:</b> <code>{esc_pages}</code>")
        elif esc_published:
            lines.append(f"📅 <b>Release Date:</b> <code>{esc_published}</code>")
        lines.append("")
        lines.append(f"📁 <b>File Name:</b> <code>{esc_file_name}</code>")
        lines.append(f"📦 <b>Size:</b> <code>{html.escape(file_size_str)}</code> | <b>Type:</b> <code>{html.escape(file_type)} (.{ext_clean})</code>")

    return "\n".join(lines)[:1020]


def format_index_log_message(
    file_name: str,
    file_size_str: str,
    file_unique_id: str,
    storage_link: str,
    user_id: int,
    user_title: str,
    db_badge: str,
    storage_badge: str,
    caption_badge: str,
    source_info: str | None = None,
) -> str:
    """Standardized new file index log format."""
    esc_fn = html.escape(file_name)
    esc_user = html.escape(user_title or "Unknown")
    user_link = f'<a href="tg://user?id={user_id}">{esc_user}</a>' if user_id else esc_user
    ts = _ist_now_str()

    lines = [
        "📥 <b>File Index Log</b>\n",
        f"📁 <b>File Name:</b> <code>{esc_fn}</code>",
        f"📦 <b>File Size:</b> <code>{html.escape(file_size_str)}</code>",
        f"🔑 <b>Unique ID:</b> <code>{html.escape(file_unique_id)}</code>",
        f"🔗 <b>Storage Link:</b> <a href=\"{storage_link}\">{storage_link}</a>",
        f"👤 <b>Sent By:</b> {user_link}",
    ]
    if source_info:
        lines.append(f"🌐 <b>Source:</b> {source_info}")

    lines.extend([
        "",
        f"🗄 <b>Database Check:</b> {db_badge}",
        f"📦 <b>Storage Check:</b> {storage_badge}",
        f"📝 <b>Caption Check:</b> {caption_badge}",
        f"⏰ <b>Timestamp:</b> <code>{ts}</code>",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Telegram Extraction & Upload Utilities
# ---------------------------------------------------------------------------
def _parse_caption_meta(raw_caption: str) -> dict:
    if not raw_caption:
        return {}
    meta = {}
    m = re.search(r"(?:Book|Audiobook):\s*([^\n]+)", raw_caption, re.IGNORECASE)
    if m:
        meta["book_title"] = m.group(1).strip()
    m = re.search(r"(?:Author|By):\s*([^\n]+)", raw_caption, re.IGNORECASE)
    if m:
        meta["book_author"] = m.group(1).strip()
    m = re.search(r"Narrated by:\s*([^\n]+)", raw_caption, re.IGNORECASE)
    if m:
        meta["narrator"] = m.group(1).strip()
    m = re.search(r"Length:\s*([^\n]+)", raw_caption, re.IGNORECASE)
    if m:
        meta["length"] = m.group(1).strip()
    m = re.search(r"Release Date:\s*([^\n]+)", raw_caption, re.IGNORECASE)
    if m:
        meta["book_published"] = m.group(1).strip()
    m = re.search(r"Series:\s*([^\n]+)", raw_caption, re.IGNORECASE)
    if m:
        meta["book_series"] = m.group(1).strip()
    return meta


def extract_media_info(message) -> dict | None:
    doc = getattr(message, "document", None)
    audio = getattr(message, "audio", None)

    if doc:
        media = doc
        media_kind = "document"
    elif audio:
        media = audio
        media_kind = "audio"
    else:
        return None

    raw_name = getattr(media, "file_name", "") or ""
    if not raw_name:
        ext = MIME_EXTENSION_FALLBACK.get(getattr(media, "mime_type", ""), "")
        raw_name = f"{media.file_unique_id}{ext}" if ext else media.file_unique_id

    ext = os.path.splitext(raw_name)[1].lower()
    if not ext and getattr(media, "mime_type", None):
        ext = MIME_EXTENSION_FALLBACK.get(media.mime_type, "")

    ebook_exts = supported_ebook_extensions()
    audiobook_exts = supported_audiobook_extensions()

    category = "ebook"
    if ext in audiobook_exts or media_kind == "audio":
        category = "audiobook"

    is_supported = (ext in ebook_exts or ext in audiobook_exts)
    cap_meta = _parse_caption_meta(getattr(message, "caption", "") or "")

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


async def send_media_to_storage(bot, storage_chat_id: int, info: dict, caption_html: str):
    if info["media_kind"] == "audio":
        try:
            return await bot.send_audio(
                chat_id=storage_chat_id,
                audio=info["file_id"],
                caption=caption_html,
                parse_mode="HTML",
            )
        except Exception:
            return await bot.send_document(
                chat_id=storage_chat_id,
                document=info["file_id"],
                caption=caption_html,
                parse_mode="HTML",
            )
    else:
        return await bot.send_document(
            chat_id=storage_chat_id,
            document=info["file_id"],
            caption=caption_html,
            parse_mode="HTML",
        )


def _make_storage_msg_link(storage_id: int, message_id: int) -> str:
    s_str = str(storage_id)
    if s_str.startswith("-100"):
        return f"https://t.me/c/{s_str[4:]}/{message_id}"
    return f"https://t.me/{message_id}"


# ---------------------------------------------------------------------------
# 3-Stage Ingestion & Healing Pipeline
# ---------------------------------------------------------------------------
async def handle_book_indexing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    storage_id = storage_group_id()
    log_group_id = logger_group_id()
    index_log_topic_id = log_topic("INDEX")
    error_log_topic_id = log_topic("ERROR")

    if not storage_id:
        return

    message = update.message or update.channel_post or update.effective_message
    if not message:
        return

    # Ignore messages sent directly inside the storage group itself
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
    user = message.from_user

    size_mb = file_size / (1024 * 1024)
    file_size_str = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{file_size / 1024:.2f} KB"

    # Stage 1 & 2: Database and Storage Presence Checks
    existing_record = get_file_by_unique_id_db(file_unique_id)
    db_badge = "📜 already present in database" if existing_record else "✅ updated"
    storage_badge = "✅ present" if (existing_record and existing_record["storage_message_id"]) else "🗃️ added to storage group"

    target_msg_id = existing_record["storage_message_id"] if existing_record else None

    # Check Caption: Is it already enriched?
    already_enriched = False
    if existing_record and getattr(existing_record, "is_enriched", 0):
        already_enriched = True
    elif info.get("caption_meta") and ("book_title" in info["caption_meta"] and "book_author" in info["caption_meta"]):
        already_enriched = True

    caption_badge = ""
    is_success_enrichment = False

    try:
        book_meta = {}
        if already_enriched:
            caption_badge = "📜 already enriched"
            book_meta = {
                "title": (info.get("caption_meta") or {}).get("book_title") or file_name,
                "author": (info.get("caption_meta") or {}).get("book_author") or "",
                "series": (info.get("caption_meta") or {}).get("book_series") or "Standalone",
                "is_matched": True,
            }
            is_success_enrichment = True
        else:
            # Stage 3: Multi-Site Caption Enrichment
            book_meta = await enrich_book_metadata(file_name, category=category)
            if book_meta.get("is_matched"):
                caption_badge = "📝 caption enriched"
                is_success_enrichment = True
            else:
                caption_badge = "🚧 info not found reported to error logs"
                is_success_enrichment = False

        if category == "audiobook" and (not book_meta.get("length")) and duration > 0:
            book_meta["length"] = _format_duration(duration)

        caption_html = format_index_channel_caption(
            file_name=file_name,
            file_size_str=file_size_str,
            extension=ext.lstrip("."),
            file_type=mime_type,
            book_meta=book_meta,
            category=category,
        )

        # Ensure presence in storage group
        if not target_msg_id:
            target_msg = await send_media_to_storage(context.bot, int(storage_id), info, caption_html)
            target_msg_id = target_msg.message_id
            storage_badge = "🗃️ added to storage group"
        else:
            storage_badge = "✅ present"

        storage_link = _make_storage_msg_link(int(storage_id), target_msg_id)

        # Save or update database
        searchable_caption = (
            f"{caption_html} {file_name} {book_meta.get('title', '')} "
            f"{book_meta.get('author', '')} {book_meta.get('series', '')}"
        ).strip()

        save_indexed_file_db(
            file_unique_id=file_unique_id,
            file_id=file_id,
            storage_message_id=target_msg_id,
            file_name=file_name,
            file_size=file_size,
            duration=duration,
            user_id=user.id if user else 0,
            user_title=user.full_name or user.username or "Unknown" if user else "Channel",
            caption=searchable_caption,
            extension=ext,
            file_type=mime_type,
            category=category,
            is_enriched=1 if is_success_enrichment else 0,
        )

        # Send Error Log alert if enrichment failed (< 2 parameters)
        if not is_success_enrichment and error_log_topic_id and log_group_id:
            try:
                err_text = (
                    f"⚠️ <b>Caption Enrichment Failed (&lt;2 Parameters Matched)</b>\n\n"
                    f"📁 <b>File:</b> <code>{html.escape(file_name)}</code>\n"
                    f"🔗 <b>Storage Message:</b> <a href=\"{storage_link}\">Message #{target_msg_id}</a>\n"
                    f"🔑 <b>Unique ID:</b> <code>{file_unique_id}</code>\n\n"
                    f"<i>Admins please edit the storage message caption manually. The bot will automatically capture your edit and update the database.</i>"
                )
                await context.bot.send_message(
                    chat_id=int(log_group_id),
                    text=err_text,
                    parse_mode="HTML",
                    message_thread_id=int(error_log_topic_id),
                )
            except Exception as e:
                logger.error("Failed to send error log: %s", e)

        # Post Standardized Index Log
        if log_group_id:
            try:
                log_msg = format_index_log_message(
                    file_name=file_name,
                    file_size_str=file_size_str,
                    file_unique_id=file_unique_id,
                    storage_link=storage_link,
                    user_id=user.id if user else 0,
                    user_title=user.full_name if user else "System",
                    db_badge=db_badge,
                    storage_badge=storage_badge,
                    caption_badge=caption_badge,
                )
                log_kwargs = {
                    "chat_id": int(log_group_id),
                    "text": log_msg,
                    "parse_mode": "HTML",
                }
                if index_log_topic_id:
                    log_kwargs["message_thread_id"] = int(index_log_topic_id)
                await context.bot.send_message(**log_kwargs)
            except Exception as e:
                logger.error("Failed to send index log: %s", e)

        if update.message and update.message.chat.type == "private":
            label = "Audiobook" if category == "audiobook" else "Ebook"
            if is_success_enrichment:
                await update.message.reply_text(f"✅ {label} successfully indexed and stored!")
            else:
                await update.message.reply_text(f"⚠️ {label} stored. Metadata requires manual admin review.")

    except Exception as e:
        logger.error("Failed to process media index: %s", e)
        if error_log_topic_id and log_group_id:
            try:
                await context.bot.send_message(
                    chat_id=int(log_group_id),
                    text=f"❌ <b>Indexing Error:</b> {html.escape(str(e))}\nFile: <code>{html.escape(file_name)}</code>",
                    parse_mode="HTML",
                    message_thread_id=int(error_log_topic_id),
                )
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Storage Group Caption Edit Listener (Real-Time Admin Sync)
# ---------------------------------------------------------------------------
async def handle_storage_caption_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Listens for edited_message updates inside the Storage Group.
    When an Admin edits a file's caption:
    1. Updates caption and sets is_enriched = 1 in files.db.
    2. Sends updated Index Log with ✍️ caption enriched by admin.
    """
    msg = update.edited_message
    if not msg:
        return

    storage_id = storage_group_id()
    if not storage_id or str(msg.chat.id) != str(storage_id):
        return

    # Check media attachment
    info = extract_media_info(msg)
    if not info:
        return

    admin_user = update.effective_user
    admin_id = admin_user.id if admin_user else 0
    admin_name = admin_user.full_name or "Admin" if admin_user else "Admin"

    new_caption = msg.caption_html or msg.caption or ""
    storage_msg_id = msg.message_id
    storage_link = _make_storage_msg_link(int(storage_id), storage_msg_id)

    # Update database
    update_file_caption_db(storage_message_id=storage_msg_id, new_caption=new_caption, is_enriched=1)

    log_group_id = logger_group_id()
    index_log_topic_id = log_topic("INDEX")

    if log_group_id:
        try:
            admin_link = f'<a href="tg://user?id={admin_id}">{html.escape(admin_name)}</a>'
            caption_badge = f"✍️ caption enriched by admin ({admin_link})"
            size_mb = info["file_size"] / (1024 * 1024)
            file_size_str = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{info['file_size'] / 1024:.2f} KB"

            log_msg = format_index_log_message(
                file_name=info["file_name"],
                file_size_str=file_size_str,
                file_unique_id=info["file_unique_id"],
                storage_link=storage_link,
                user_id=admin_id,
                user_title=admin_name,
                db_badge="✅ updated",
                storage_badge="✅ present",
                caption_badge=caption_badge,
            )
            log_kwargs = {
                "chat_id": int(log_group_id),
                "text": log_msg,
                "parse_mode": "HTML",
            }
            if index_log_topic_id:
                log_kwargs["message_thread_id"] = int(index_log_topic_id)
            await context.bot.send_message(**log_kwargs)
        except Exception as e:
            logger.error("Failed to send admin caption edit index log: %s", e)
