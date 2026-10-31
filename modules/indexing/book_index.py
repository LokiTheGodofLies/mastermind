import asyncio
import html
import io
import json
import logging
import os
import re
import zipfile
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from urllib.parse import quote, quote_plus, urljoin
import urllib.request
import urllib.error

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    from telegram import Update
    from telegram.error import BadRequest, TelegramError
    from telegram.ext import ContextTypes
except ImportError:
    Update = object
    BadRequest = Exception
    TelegramError = Exception

    class ContextTypes:
        DEFAULT_TYPE = object

from config import (
    admin_ids,
    creator_id,
    goodreads_base_url,
    goodreads_cache_max,
    index_channel_id,
    log_topic,
    logger_group_id,
    max_download_bytes,
    scraper_user_agent,
    storage_group_id,
    supported_archive_extensions,
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
SUPPORTED_ARCHIVE_EXTENSIONS = supported_archive_extensions()
SUPPORTED_EXTENSIONS = supported_extensions()

MIME_EXTENSION_FALLBACK = {
    "application/epub+zip": ".epub",
    "application/pdf": ".pdf",
    "application/x-mobipocket-ebook": ".mobi",
    "application/vnd.amazon.ebook": ".azw",
    "application/x-cbr": ".cbr",
    "application/x-cbz": ".cbz",
    "image/vnd.djvu": ".djvu",
    "application/zip": ".zip",
    "application/x-zip-compressed": ".zip",
    "application/vnd.rar": ".rar",
    "application/x-rar-compressed": ".rar",
    "application/x-7z-compressed": ".7z",
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
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/vnd.audible.aax": ".aax",
}

_METADATA_CACHE: dict[str, dict] = {}

_RE_SCRIPT_JSON_LD = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
_RE_SCRIPT_NEXT_DATA = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
_RE_ISO_DURATION = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", re.IGNORECASE)

# Small-caps / stylized Unicode translation table for spam caption detection
_SMALL_CAPS_MAP = str.maketrans(
    "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ",
    "abcdefghijklmnopqrstuvwxyz",
)


class _HTMLTextExtractor(HTMLParser):
    """Strip HTML tags and normalize whitespace."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in ("br", "p", "div", "li"):
            self._parts.append(" ")

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        raw = "".join(self._parts)
        return re.sub(r"\s+", " ", unescape(raw)).strip()


def clean_html_text(value: str | None) -> str:
    if not value:
        return ""
    parser = _HTMLTextExtractor()
    parser.feed(str(value))
    parser.close()
    return parser.get_text().strip()


def parse_iso8601_duration(duration: str | None) -> str:
    if not duration:
        return ""
    match = _RE_ISO_DURATION.search(str(duration))
    if not match:
        return ""
    hours = int(match.group(1) or 0)
    mins = int(match.group(2) or 0)
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    if mins:
        return f"{mins}m"
    return ""


def _headers() -> dict:
    return {
        "User-Agent": scraper_user_agent(),
        "Accept": "application/json, text/html, application/xhtml+xml, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }


def _ist_now_str() -> str:
    """Returns current timestamp string in true IST (UTC+05:30)."""
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).strftime("%d %b %Y, %H:%M IST")


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
# Spam / Promo Caption & Filename Cleaning + Option B Series Formatting
# ---------------------------------------------------------------------------
def clean_promo_text(raw_text: str | None) -> str:
    """
    Strips promotional/spam lines (such as `ᴊᴏɪɴ @heyucutie ꜰᴏʀ ᴍᴏʀᴇ`, `@channel`,
    `t.me/...`, `uploaded by`, etc.) from captions or text.
    """
    if not raw_text:
        return ""
    cleaned_lines = []
    for line in str(raw_text).splitlines():
        norm_line = line.translate(_SMALL_CAPS_MAP).strip()
        if not norm_line:
            continue
        if re.search(
            r"(?:\bjoin\s+@\w+|\bjoin\b.*\bfor\s+more\b|t\.me/|telegram\.me/|@\w+\s+for\s+more|\buploaded\s+by\b|\bshared\s+by\b)",
            norm_line,
            re.IGNORECASE,
        ):
            continue
        cleaned_lines.append(line.strip())
    return "\n".join(cleaned_lines).strip()


def format_series_label(series_name: str | None, position: str | None = None) -> str:
    """
    Formats series in Option B style:
      - `Eddie Flynn (Book #5)`
      - `Twisted (Book #2)`
      - `Standalone` when empty/standalone.
    """
    if not series_name:
        return "Standalone"
    s = str(series_name).strip(" -_,;:")
    if not s or s.lower() in ("standalone", "none", "n/a"):
        return "Standalone"

    pos_str = str(position or "").strip().lstrip("#").strip()

    # Check if series_name already contains (#N) or (Book #N) or #N
    m_existing = re.search(
        r"^(.*?)\s*(?:\(\s*(?:Book\s*)?#?\s*(\d+(?:\.\d+)?)\s*\)|,\s*(?:Book|Vol(?:ume)?\.?)\s*#?\s*(\d+(?:\.\d+)?)|\s+#\s*(\d+(?:\.\d+)?))$",
        s,
        re.IGNORECASE,
    )
    if m_existing:
        base_s = m_existing.group(1).strip(" -_,;:")
        num = m_existing.group(2) or m_existing.group(3) or m_existing.group(4) or pos_str
        if base_s and num:
            return f"{base_s} (Book #{num})"
        if base_s:
            return base_s

    if pos_str:
        return f"{s} (Book #{pos_str})"
    return s


def clean_filename_for_search(file_name: str) -> str:
    if not file_name:
        return ""

    name = clean_promo_text(file_name) or file_name
    name = re.sub(r"\.[a-zA-Z0-9]{2,5}$", "", name)
    # Strip leading chapter, track, or index numbers (e.g. "38 ", "5 ", "01. ", "[02] ", "#5 ")
    name = re.sub(r"^\s*(?:#?\d+|\[\d+\])[\s\.\-_]+", "", name)
    name = name.replace("’", "'").replace("‘", "'").replace("`", "'")
    name = re.sub(r"(^|\s)'([^']*)'(\s|$)", r"\1 \2 \3", name)

    name = re.sub(
        r"\b(z-lib\.org|z-library|annas-archive|libgen|oceanofpdf|audiobookbay|mobilism|pdfdrive|epub|pdf|azw|azw3|mobi|cbz|cbr|djvu|fb2|mp3|m4b|m4a|aax|flac|wav|ogg|opus|zip|rar|7z)\b",
        " ",
        name,
        flags=re.IGNORECASE,
    )
    name = re.sub(r"@\w+", " ", name)
    name = re.sub(r"[^a-zA-Z0-9\s'-]", " ", name)
    # Keep hyphens inside compound words like Fifty-Fifty while also spacing other symbols
    name = re.sub(r"\s*-\s*", " ", name)
    name = re.sub(r"\s+'+\s+", " ", name)
    name = re.sub(r"^'+\s*|\s*'+$", "", name)

    return re.sub(r"\s+", " ", name).strip()


def parse_title_and_series(raw_title: str) -> tuple[str, str]:
    """
    Separates raw_title into `(clean_title, option_b_series)`.
    Never leaves `(Series #N)` inside `clean_title`.
    """
    if not raw_title:
        return "Unknown Title", "Standalone"

    series_pattern = r"\s*\(([^)]*?(?:#\s*\d+(?:\.\d+)?|Book\s+#?\d+(?:\.\d+)?|Vol(?:ume)?\.?\s*#?\d+(?:\.\d+)?)[^)]*)\)"
    m = re.search(series_pattern, raw_title, re.IGNORECASE)
    if m:
        series_raw = m.group(1).strip()
        clean_t = (raw_title[: m.start()] + raw_title[m.end() :]).strip(" -_:")
        return clean_t or raw_title.strip(), format_series_label(series_raw)

    m2 = re.search(r"\s*\(([^)]+)\)$", raw_title)
    if m2:
        inside = m2.group(1).strip()
        if any(c.isdigit() for c in inside) or "series" in inside.lower() or "book" in inside.lower():
            clean_t = raw_title[: m2.start()].strip(" -_:")
            return clean_t or raw_title.strip(), format_series_label(inside)

    return raw_title.strip(), "Standalone"


def parse_filename_components(file_name: str) -> tuple[str, str]:
    """Extracts likely (title, author) from filename pattern, stripping release tags and watermarks."""
    base = re.sub(r"\.[a-zA-Z0-9]{2,5}$", "", file_name or "")
    base = re.sub(r"^\s*(?:#?\d+|\[\d+\])[\s\.\-_]+", "", base)
    base = re.sub(
        r"\[[^\]]*(?:retail|z-lib|epub|pdf|mobi|audiobookbay|libgen|mp3|m4b)[^\]]*\]",
        "",
        base,
        flags=re.IGNORECASE,
    )
    base = re.sub(
        r"\([^)]*(?:retail|z-lib|epub|pdf|mobi|audiobookbay|libgen|unabridged)[^)]*\)",
        "",
        base,
        flags=re.IGNORECASE,
    )

    t, a = "", ""
    if " - " in base:
        parts = base.split(" - ", 1)
        t, a = parts[0].strip(), parts[1].strip()
    else:
        m_by = re.search(r"\s+by\s+", base, re.IGNORECASE)
        if m_by:
            t, a = base[: m_by.start()].strip(), base[m_by.end() :].strip()
        else:
            t, a = base.strip(), ""

    t = re.sub(r"\s*\[[^\]]+\]$", "", t).strip()
    a = re.sub(r"\s*\[[^\]]+\]$", "", a).strip()
    clean_t, _ = parse_title_and_series(t)
    return clean_t or t, a


def is_derivative_or_compilation(title: str, query: str) -> bool:
    """Strictly identifies derivative works (study guides, summaries) and multi-book collections/omnibuses."""
    q_low = query.lower()
    t_low = title.lower()

    derivatives = [
        "study guide", "summary of", "summary & analysis", "summary and analysis",
        "book analysis", "companion guide", "supersummary", "instaread", "quicklet",
        "cliffsnotes", "sparknotes", "sidekick", "workbook for", "key takeaways",
    ]
    for d in derivatives:
        if d in t_low and d not in q_low:
            return True

    compilations = [
        "complete novels", "complete works", "complete collection", "collected works",
        "omnibus", "boxed set", "box set", "anthology", "novels of",
        "3-in-1", "2-in-1", "4-in-1", "5-in-1", "books 1-", "vol 1:", "vol. 1:", "volume 1:",
    ]
    for c in compilations:
        if c in t_low and c not in q_low:
            return True

    if "/" in title and "/" not in query:
        parts = [p.strip() for p in title.split("/") if len(p.strip()) > 3]
        if len(parts) >= 2:
            return True

    return False


is_derivative_work = is_derivative_or_compilation


def _normalize_tokens(text: str) -> set[str]:
    text = (text or "").replace("’", "'").replace("‘", "'").replace("`", "'")
    words = re.findall(r"[a-zA-Z0-9']+", text.lower())
    tokens = set()
    for w in words:
        clean_w = w.strip("'")
        if len(clean_w) > 1 or clean_w.isdigit():
            tokens.add(clean_w)
            if "'" in w:
                tokens.add(w.replace("'", ""))
    return tokens


def _normalize_title_cmp(text: str) -> str:
    """Normalizes hyphens, punctuation, and case for exact title comparison (e.g. 'Fifty-Fifty' == 'Fifty Fifty')."""
    text = (text or "").replace("’", "'").replace("‘", "'").replace("`", "'").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def score_candidate(cand: dict, filename_query: str, expected_title: str = "", expected_author: str = "") -> float:
    """
    Scores a candidate book/audiobook record against filename query and expected components.
    Penalizes derivative study guides, omnibuses, and mismatched authors; rewards exact title matches,
    verified series metadata, and popularity/ratings count when disambiguating single-title queries
    (such as `Fifty-Fifty.zip`).
    """
    cand_title = cand.get("title", "")
    cand_raw_title = cand.get("raw_title", "") or cand_title
    cand_author = cand.get("author", "")

    if not cand_title or not cand_author:
        return -100.0

    if is_derivative_or_compilation(cand_raw_title, filename_query) or is_derivative_or_compilation(cand_title, filename_query):
        return -100.0

    score = 0.0
    fn_tokens = _normalize_tokens(filename_query)
    title_target = expected_title if expected_title else filename_query
    target_tokens = _normalize_tokens(title_target)
    cand_title_tokens = _normalize_tokens(cand_title)
    cand_author_tokens = _normalize_tokens(cand_author)

    author_target = expected_author if expected_author else ""
    author_target_tokens = _normalize_tokens(author_target) if author_target else set()

    # 1. Author Matching
    if author_target_tokens:
        if cand_author_tokens.intersection(author_target_tokens):
            score += 5.0
        else:
            score -= 5.0
    elif cand_author_tokens and fn_tokens:
        if cand_author_tokens.intersection(fn_tokens):
            score += 3.0

    # 2. Title Matching (including hyphen-normalized exact match like 'Fifty-Fifty' == 'Fifty Fifty')
    norm_cand_t = _normalize_title_cmp(cand_title)
    norm_target_t = _normalize_title_cmp(title_target)
    if norm_cand_t and norm_cand_t == norm_target_t:
        score += 10.0
    elif target_tokens and cand_title_tokens:
        overlap = cand_title_tokens.intersection(target_tokens)
        if len(overlap) == len(target_tokens):
            score += 6.0
        elif len(overlap) >= 2:
            score += len(overlap) * 2.0
        elif len(overlap) == 1 and len(target_tokens) == 1:
            score += 3.5
        else:
            return -50.0

        excess = cand_title_tokens - target_tokens - author_target_tokens
        score -= len(excess) * 1.0
    else:
        return -50.0

    # 3. Bonus for verified series, narrator/runtime, and ratings count tie-breaker
    if cand.get("series") and cand.get("series") != "Standalone":
        score += 0.5
    if cand.get("rating"):
        score += 0.25
    try:
        rc = int(str(cand.get("ratings_count") or "0").replace(",", ""))
        if rc >= 1000:
            score += 0.5
        elif rc >= 100:
            score += 0.25
    except ValueError:
        pass

    return score


def match_parameters(
    filename_query: str,
    item_title: str,
    item_author: str,
    item_series: str = "",
) -> int:
    """Backward-compatibility adapter for legacy match_parameters callers."""
    cand = {"title": item_title, "author": item_author, "series": item_series}
    sc = score_candidate(cand, filename_query)
    return max(0, int(sc // 2))


# ---------------------------------------------------------------------------
# Async HTTP Helpers (JSON + HTML for Deep Scrapers)
# ---------------------------------------------------------------------------
async def _async_get_json(url: str, timeout_sec: int = 6, extra_headers: dict | None = None) -> dict | list | None:
    headers = _headers()
    if extra_headers:
        headers.update(extra_headers)
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


async def _async_get_text(url: str, timeout_sec: int = 7, extra_headers: dict | None = None) -> str | None:
    headers = _headers()
    if extra_headers:
        headers.update(extra_headers)
    if aiohttp is not None:
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout_sec)) as resp:
                    if resp.status == 200:
                        return await resp.text(errors="replace")
        except Exception as e:
            logger.debug("aiohttp get_text error for %s: %s", url, e)
            return None
    else:
        def _sync_fetch_text():
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=timeout_sec) as response:
                    if response.status == 200:
                        return response.read().decode("utf-8", "replace")
            except Exception as e:
                logger.debug("urllib get_text error for %s: %s", url, e)
                return None

        return await asyncio.to_thread(_sync_fetch_text)


# ---------------------------------------------------------------------------
# 8-Website Book & Audiobook Providers (Integrating Mediagoer Deep Scrapers)
# ---------------------------------------------------------------------------
async def _enrich_goodreads_book_page(cand: dict) -> dict:
    """
    Fetches Goodreads `/book/show/<id>` HTML and parses `__NEXT_DATA__` Apollo state
    (from `mediagoer.py` `GoodreadsAdapter`) + JSON-LD to backfill exact Series (Option B),
    Pages, Genres, Release Year, and Rating.
    """
    url = cand.get("url") or ""
    if not url:
        return cand
    html_text = await _async_get_text(url, timeout_sec=6)
    if not html_text:
        return cand

    # 1. JSON-LD
    ld_match = _RE_SCRIPT_JSON_LD.search(html_text)
    if ld_match:
        try:
            ld = json.loads(ld_match.group(1).strip())
            if isinstance(ld, dict):
                if ld.get("numberOfPages") and not cand.get("pages"):
                    cand["pages"] = str(ld["numberOfPages"])
                agg = ld.get("aggregateRating") or {}
                if agg.get("ratingValue") is not None and not cand.get("rating"):
                    cand["rating"] = str(agg["ratingValue"])
                if agg.get("ratingCount") is not None and not cand.get("ratings_count"):
                    cand["ratings_count"] = str(agg["ratingCount"])
        except Exception:
            pass

    # 2. __NEXT_DATA__ Apollo State (from mediagoer.py GoodreadsAdapter)
    next_match = _RE_SCRIPT_NEXT_DATA.search(html_text)
    if next_match:
        try:
            nd = json.loads(next_match.group(1).strip())
            apollo = (
                nd.get("props", {})
                .get("pageProps", {})
                .get("apolloState", {})
            )
            series_nodes: dict[str, dict] = {}
            book_node: dict = {}
            for key, val in apollo.items():
                if not isinstance(val, dict):
                    continue
                if key.startswith("Series:"):
                    series_nodes[key] = val
                elif key.startswith("Book:") and (val.get("title") or val.get("description")):
                    if not book_node or val.get("bookSeries"):
                        book_node = val

            if book_node:
                details = book_node.get("details") or {}
                if details.get("numPages") and not cand.get("pages"):
                    cand["pages"] = str(details["numPages"])
                pub_time = details.get("publicationTime")
                if isinstance(pub_time, (int, float)) and pub_time > 0 and not cand.get("published"):
                    cand["published"] = str(datetime.utcfromtimestamp(pub_time / 1000.0).year)

                genres = [
                    ((bg.get("genre") or {}).get("name"))
                    for bg in (book_node.get("bookGenres") or [])
                    if isinstance(bg, dict) and (bg.get("genre") or {}).get("name")
                ]
                if genres and not cand.get("genres"):
                    cand["genres"] = ", ".join(genres[:4])

                b_series = book_node.get("bookSeries") or []
                if b_series and isinstance(b_series[0], dict):
                    pos = b_series[0].get("userPosition") or ""
                    s_ref = (b_series[0].get("series") or {}).get("__ref") or ""
                    s_obj = series_nodes.get(s_ref) or (b_series[0].get("series") or {})
                    if s_obj.get("title"):
                        cand["series"] = format_series_label(s_obj["title"], pos)
        except Exception:
            pass

    return cand


async def _fetch_goodreads(query: str) -> list[dict]:
    """1. Goodreads (`auto_complete` JSON API + `/book/show/` Apollo state deep scraper)."""
    url = f"{goodreads_base_url()}/book/auto_complete?format=json&q={quote_plus(query)}"
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
                if clean_t and "(" in clean_t:
                    clean_t, s2 = parse_title_and_series(clean_t)
                    if series == "Standalone" and s2 != "Standalone":
                        series = s2

                rating = str(item.get("avgRating") or "")
                ratings_count = str(item.get("ratingsCount") or "")
                pages = str(item.get("numPages") or "")

                candidates.append({
                    "title": clean_t,
                    "raw_title": raw_title,
                    "author": author_name,
                    "series": series,
                    "pages": pages,
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
    """2. Audible Catalog API across `.in`, `.com`, `.co.uk`, `.au`, `.ca` (from `mediagoer.py` `AudibleAdapter`)."""
    response_groups = (
        "contributors,media,price,product_attrs,product_desc,"
        "product_extended_attrs,rating,series,category_ladders,relationships"
    )
    for tld in ("in", "com", "co.uk", "au", "ca"):
        url = (
            f"https://api.audible.{tld}/1.0/catalog/products"
            f"?title={quote_plus(query)}&num_results=6&products_plan=all"
            f"&response_groups={response_groups}"
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
                    if series_list and isinstance(series_list[0], dict):
                        s = series_list[0]
                        stitle = s.get("title") or ""
                        seq = s.get("sequence") or ""
                        series_name = format_series_label(stitle, seq)

                    runtime = prod.get("runtime_length_min") or 0
                    length_str = f"{runtime // 60}h {runtime % 60}m" if runtime else ""
                    pub_date = prod.get("release_date") or prod.get("issue_date") or ""

                    rating_obj = (prod.get("rating") or {}).get("overall_distribution") or {}
                    rating = ""
                    if rating_obj.get("display_average_rating") is not None:
                        try:
                            rating = str(round(float(rating_obj["display_average_rating"]), 2))
                        except (TypeError, ValueError):
                            rating = str(rating_obj["display_average_rating"])
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


async def _fetch_storytel(query: str) -> list[dict]:
    """3. Storytel (`__NEXT_DATA__` `pageProps` + JSON-LD parser ported from `mediagoer.py` `StorytelAdapter`)."""
    for locale in ("in", "en"):
        url = f"https://www.storytel.com/{locale}/search-{quote(query.strip())}"
        try:
            html_text = await _async_get_text(url, timeout_sec=6)
            if not html_text:
                continue
            candidates = []
            next_match = _RE_SCRIPT_NEXT_DATA.search(html_text)
            if next_match:
                nd = json.loads(next_match.group(1).strip())
                page_props = nd.get("props", {}).get("pageProps", {})
                items = (
                    (page_props.get("searchResult") or {}).get("books")
                    or page_props.get("books")
                    or (page_props.get("initialState") or {}).get("search", {}).get("items")
                    or []
                )
                for b in items[:6]:
                    node = b.get("book") or b.get("consumable") or b
                    if not isinstance(node, dict):
                        continue
                    raw_title = node.get("title") or node.get("name") or ""
                    if not raw_title:
                        continue
                    authors = [
                        a.get("name", "") if isinstance(a, dict) else str(a)
                        for a in (node.get("authors") or [])
                    ]
                    authors = [a for a in authors if a]
                    narrators = [
                        n.get("name", "") if isinstance(n, dict) else str(n)
                        for n in (node.get("narrators") or [])
                    ]
                    narrators = [n for n in narrators if n]

                    s_info = node.get("series") or node.get("seriesInfo") or {}
                    series_name = "Standalone"
                    if isinstance(s_info, list) and s_info:
                        s_info = s_info[0]
                    if isinstance(s_info, dict) and (s_info.get("name") or s_info.get("title")):
                        s_title = s_info.get("name") or s_info.get("title") or ""
                        s_pos = node.get("seriesPosition") or s_info.get("position") or s_info.get("numberInSeries") or ""
                        series_name = format_series_label(s_title, s_pos)

                    clean_t, parsed_s = parse_title_and_series(raw_title)
                    if series_name == "Standalone" and parsed_s != "Standalone":
                        series_name = parsed_s

                    dur_mins = None
                    if node.get("duration"):
                        val = int(node["duration"])
                        dur_mins = val // 60 if val > 1000 else val
                    elif node.get("lengthInMinutes"):
                        dur_mins = int(node["lengthInMinutes"])
                    length_str = f"{dur_mins // 60}h {dur_mins % 60}m" if dur_mins else ""

                    rating = str(node.get("rating") or node.get("averageRating") or "")
                    ratings_count = str(node.get("ratingCount") or node.get("ratingsCount") or "")
                    pub_date = str(node.get("releaseDate") or node.get("publicationYear") or "")[:10]

                    cat_obj = node.get("category") or {}
                    genres = ""
                    if isinstance(cat_obj, dict) and cat_obj.get("name"):
                        genres = str(cat_obj["name"])

                    bid = str(node.get("id") or node.get("bookId") or "")
                    book_url = node.get("url") or node.get("shareUrl") or (
                        f"https://www.storytel.com/{locale}/books/{bid}" if bid else ""
                    )

                    candidates.append({
                        "title": clean_t,
                        "raw_title": raw_title,
                        "author": ", ".join(authors),
                        "narrator": ", ".join(narrators),
                        "series": series_name,
                        "length": length_str,
                        "published": pub_date,
                        "rating": rating,
                        "ratings_count": ratings_count,
                        "genres": genres,
                        "url": book_url,
                        "provider": "Storytel",
                    })
            if candidates:
                return candidates
        except Exception as e:
            logger.debug("Storytel (%s) error: %s", locale, e)
    return []


async def _fetch_apple_books(query: str, is_audiobook: bool = False) -> list[dict]:
    """4. Apple Books (`itunes.apple.com/search` for Audiobooks & Ebooks)."""
    entity = "audiobook" if is_audiobook else "ebook"
    url = f"https://itunes.apple.com/search?term={quote_plus(query)}&entity={entity}&limit=6"
    try:
        data = await _async_get_json(url, timeout_sec=5)
        if isinstance(data, dict):
            results = data.get("results") or []
            candidates = []
            for item in results:
                title = item.get("trackName") or item.get("collectionName") or ""
                author = item.get("artistName") or ""
                track_url = item.get("trackViewUrl") or item.get("collectionViewUrl") or ""
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


async def _fetch_penguin_random_house(query: str, is_audiobook: bool = False) -> list[dict]:
    """5. Penguin Random House / PRH Audio search scraper & OpenLibrary PRH catalog."""
    url = f"https://openlibrary.org/search.json?q={quote_plus(query)}+publisher:(Penguin+OR+Random+House)&limit=5"
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
                isbn_list = doc.get("isbn") or []
                prh_url = (
                    f"https://www.penguinrandomhouse.com/books/?q={quote_plus(title)}"
                    if not isbn_list
                    else f"https://www.penguinrandomhouse.com/search/site?q={isbn_list[0]}"
                )
                clean_t, series = parse_title_and_series(title)
                candidates.append({
                    "title": clean_t,
                    "raw_title": title,
                    "author": ", ".join(authors[:3]),
                    "series": series,
                    "pages": "" if is_audiobook else pages,
                    "published": year,
                    "genres": ", ".join(subjects[:3]),
                    "url": prh_url,
                    "provider": "Penguin Random House",
                })
            return candidates
    except Exception as e:
        logger.debug("Penguin Random House lookup error: %s", e)
    return []


async def _fetch_internet_archive_or_crossref(query: str, is_audiobook: bool = False) -> list[dict]:
    """
    6. Internet Archive Audio (`mediatype:audio`) for Audiobooks, and
       Crossref Academic Works API + Internet Archive Texts (`mediatype:texts`) for Ebooks/Academic/Self-Help.
    """
    candidates = []
    if is_audiobook:
        ia_url = (
            f"https://archive.org/advancedsearch.php?q={quote_plus(query)}+AND+mediatype:(audio)"
            f"&fl[]=identifier,title,creator,date,subject,runtime,avg_rating&rows=6&page=1&output=json"
        )
        try:
            data = await _async_get_json(ia_url, timeout_sec=5)
            docs = ((data or {}).get("response") or {}).get("docs") or []
            for doc in docs:
                ident = doc.get("identifier") or ""
                title = doc.get("title") or ""
                creator = doc.get("creator") or ""
                if isinstance(creator, list):
                    creator = ", ".join(str(c) for c in creator if c)
                subj = doc.get("subject") or []
                if isinstance(subj, str):
                    subj = [subj]
                clean_t, series = parse_title_and_series(title)
                candidates.append({
                    "title": clean_t,
                    "raw_title": title,
                    "author": str(creator),
                    "series": series,
                    "length": str(doc.get("runtime") or ""),
                    "published": str(doc.get("date") or "")[:10],
                    "rating": str(doc.get("avg_rating") or ""),
                    "genres": ", ".join(str(s) for s in subj[:3] if s),
                    "url": f"https://archive.org/details/{ident}" if ident else "",
                    "provider": "Internet Archive Audio",
                })
        except Exception as e:
            logger.debug("Internet Archive Audio error: %s", e)
        return candidates

    # For Ebooks / Academic / Textbooks / Self-Help: Crossref Works API + Internet Archive Texts
    cr_url = f"https://api.crossref.org/works?query.bibliographic={quote_plus(query)}&filter=type:book,type:monograph&rows=5"
    try:
        data = await _async_get_json(cr_url, timeout_sec=5)
        items = ((data or {}).get("message") or {}).get("items") or []
        for item in items:
            titles = item.get("title") or []
            title = titles[0] if titles else ""
            if not title:
                continue
            authors = []
            for a in item.get("author") or []:
                given = a.get("given") or ""
                family = a.get("family") or ""
                full_a = f"{given} {family}".strip()
                if full_a:
                    authors.append(full_a)
            pub_parts = (
                ((item.get("published-print") or item.get("published-online") or {}).get("date-parts") or [[]])[0]
            )
            year = str(pub_parts[0]) if pub_parts else ""
            subjects = item.get("subject") or []
            clean_t, series = parse_title_and_series(title)
            candidates.append({
                "title": clean_t,
                "raw_title": title,
                "author": ", ".join(authors[:3]),
                "series": series,
                "published": year,
                "genres": ", ".join(str(s) for s in subjects[:3] if s),
                "url": item.get("URL") or "",
                "provider": "Crossref",
            })
    except Exception as e:
        logger.debug("Crossref error: %s", e)

    if not candidates:
        ia_txt_url = (
            f"https://archive.org/advancedsearch.php?q={quote_plus(query)}+AND+mediatype:(texts)"
            f"&fl[]=identifier,title,creator,date,subject&rows=5&page=1&output=json"
        )
        try:
            data = await _async_get_json(ia_txt_url, timeout_sec=5)
            docs = ((data or {}).get("response") or {}).get("docs") or []
            for doc in docs:
                ident = doc.get("identifier") or ""
                title = doc.get("title") or ""
                creator = doc.get("creator") or ""
                if isinstance(creator, list):
                    creator = ", ".join(str(c) for c in creator if c)
                subj = doc.get("subject") or []
                if isinstance(subj, str):
                    subj = [subj]
                clean_t, series = parse_title_and_series(title)
                candidates.append({
                    "title": clean_t,
                    "raw_title": title,
                    "author": str(creator),
                    "series": series,
                    "published": str(doc.get("date") or "")[:10],
                    "genres": ", ".join(str(s) for s in subj[:3] if s),
                    "url": f"https://archive.org/details/{ident}" if ident else "",
                    "provider": "Internet Archive",
                })
        except Exception as e:
            logger.debug("Internet Archive Texts error: %s", e)

    return candidates


async def _fetch_google_books(query: str) -> list[dict]:
    """7. Google Books Volumes API (`googleapis.com/books/v1/volumes`)."""
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
                if series == "Standalone":
                    clean_t, _ = parse_title_and_series(title)

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
    """8. OpenLibrary Search API (`openlibrary.org/search.json`)."""
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


async def _dispatch_provider(prov: str, query: str, is_audio: bool) -> list[dict]:
    if prov == "goodreads":
        return await _fetch_goodreads(query)
    if prov == "audible":
        return await _fetch_audible(query)
    if prov == "storytel":
        return await _fetch_storytel(query)
    if prov == "apple":
        return await _fetch_apple_books(query, is_audiobook=is_audio)
    if prov == "prh":
        return await _fetch_penguin_random_house(query, is_audiobook=is_audio)
    if prov == "ia_crossref":
        return await _fetch_internet_archive_or_crossref(query, is_audiobook=is_audio)
    if prov == "google":
        return await _fetch_google_books(query)
    if prov == "openlibrary":
        return await _fetch_openlibrary(query)
    return []


# ---------------------------------------------------------------------------
# .ZIP Archive Inspection (<= 20 MB via Telegram Bot API) & Smart Fallback
# ---------------------------------------------------------------------------
async def inspect_zip_archive_if_possible(bot, file_id: str, file_size: int, file_name: str) -> dict:
    """
    If the file is a `.zip` and `file_size <= max_download_bytes()` (20 MB Telegram Bot API limit),
    downloads and inspects its central directory (`zipfile.ZipFile`) to detect:
      - `category`: `'audiobook'` if audio tracks (.mp3/.m4b/.flac/.ogg/.wav/.aax) dominate,
                    `'ebook'` if ebook files (.epub/.pdf/.mobi/.azw3/.djvu/.cbz/.cbr) dominate.
      - `inner_query`: inner filename if outer filename is generic.
    If `file_size > 20 MB` (like `Fifty-Fifty.zip` at 303.95 MB, where Bot API `getFile` raises
    `BadRequest: File is too big`), returns `category='archive'` without throwing any error,
    allowing `enrich_book_metadata` to run dual Ebook + Audiobook lookup without assuming >100 MB is audio-only.
    """
    result = {"category": "archive", "inner_query": "", "inspected": False}
    if not bot or not file_id or not file_name.lower().endswith(".zip"):
        return result
    if file_size and file_size > max_download_bytes():
        return result

    try:
        tg_file = await bot.get_file(file_id)
        buf = io.BytesIO()
        await tg_file.download_to_memory(out=buf)
        buf.seek(0)
        with zipfile.ZipFile(buf, "r") as zf:
            names = [n for n in zf.namelist() if not n.endswith("/") and not os.path.basename(n).startswith(".")]
        audio_exts = supported_audiobook_extensions()
        ebook_exts = supported_ebook_extensions()
        audio_count = sum(1 for n in names if os.path.splitext(n)[1].lower() in audio_exts)
        ebook_count = sum(1 for n in names if os.path.splitext(n)[1].lower() in ebook_exts)
        if audio_count > ebook_count and audio_count > 0:
            result["category"] = "audiobook"
        elif ebook_count > 0:
            result["category"] = "ebook"
        if names:
            first_base = os.path.basename(names[0])
            result["inner_query"] = clean_filename_for_search(first_base)
        result["inspected"] = True
    except Exception as e:
        logger.debug("Zip inspection skipped for %s (%s bytes): %s", file_name, file_size, e)
    return result


# ---------------------------------------------------------------------------
# 8-Site Metadata Enrichment Pipeline
# ---------------------------------------------------------------------------
async def enrich_book_metadata(file_name: str, category: str = "ebook", raw_caption: str = "") -> dict:
    clean_query = clean_filename_for_search(file_name)
    cleaned_cap = clean_promo_text(raw_caption)
    if not clean_query and cleaned_cap:
        clean_query = clean_filename_for_search(cleaned_cap.splitlines()[0])
    if not clean_query:
        return {"is_matched": False, "clean_query": file_name}

    cache_key = f"{category}:{clean_query.lower()}"
    if cache_key in _METADATA_CACHE:
        return dict(_METADATA_CACHE[cache_key])

    # Determine whether this is an audiobook, ebook, or un-inspected archive (.zip/.rar > 20 MB)
    combined_hint = f"{file_name} {cleaned_cap}".lower()
    is_audio = category == "audiobook" or (
        category == "archive"
        and bool(re.search(r"\b(audiobook|mp3|m4b|aax|narrated|unabridged|audio)\b", combined_hint))
    )

    # Exact 8-website sequence for Audiobooks vs. Ebooks
    if is_audio:
        primary_sequence = [
            "audible",       # 1. Audible
            "storytel",      # 2. Storytel
            "apple",         # 3. Apple Books (Audiobook)
            "goodreads",     # 4. Goodreads
            "prh",           # 5. Penguin Random House Audio
            "ia_crossref",   # 6. Internet Archive Audio
            "google",        # 7. Google Books
            "openlibrary",   # 8. OpenLibrary
        ]
    else:
        primary_sequence = [
            "goodreads",     # 1. Goodreads
            "storytel",      # 2. Storytel
            "apple",         # 3. Apple Books (Ebook)
            "audible",       # 4. Audible
            "prh",           # 5. Penguin Random House
            "ia_crossref",   # 6. Crossref / Internet Archive Texts
            "google",        # 7. Google Books
            "openlibrary",   # 8. OpenLibrary
        ]

    expected_title, expected_author = parse_filename_components(file_name)
    best_overall_cand = None
    best_overall_score = -100.0
    matched_provider = None

    try:
        for prov in primary_sequence:
            candidates = await _dispatch_provider(prov, clean_query, is_audio=is_audio)

            prov_best_cand = None
            prov_best_score = -100.0

            for cand in candidates:
                sc = score_candidate(
                    cand=cand,
                    filename_query=clean_query,
                    expected_title=expected_title,
                    expected_author=expected_author,
                )
                if sc > prov_best_score:
                    prov_best_score = sc
                    prov_best_cand = cand

            if prov_best_cand and prov_best_score >= 3.0:
                if prov_best_score > best_overall_score:
                    best_overall_score = prov_best_score
                    best_overall_cand = prov_best_cand
                    matched_provider = prov

                # Exact match found (score >= 10.0), accept immediately without checking lower-tier providers
                if prov_best_score >= 10.0:
                    break

        matched_item = dict(best_overall_cand) if best_overall_cand else None

        if matched_item:
            # If Goodreads matched (or we need deeper Goodreads page state), enrich via Apollo __NEXT_DATA__
            if matched_provider == "goodreads" and (
                matched_item.get("series") in (None, "", "Standalone")
                or not matched_item.get("genres")
                or not matched_item.get("pages")
            ):
                matched_item = await _enrich_goodreads_book_page(matched_item)

            v_title = matched_item.get("title") or ""
            v_author = matched_item.get("author") or ""
            cross_query = f"{v_title} {v_author}".strip()
            check_series = matched_item.get("series") in (None, "", "Standalone")

            # Cross-verify across top providers (Goodreads, Audible, Storytel, Google Books) to backfill missing fields
            cross_sequence = ["goodreads", "audible", "storytel", "google", "apple", "openlibrary"]
            for prov in cross_sequence:
                if prov == matched_provider:
                    continue
                # Stop cross-querying once we have series, genres, published date, and pages/length
                has_core_extras = bool(
                    not check_series
                    and matched_item.get("genres")
                    and matched_item.get("published")
                    and (matched_item.get("pages") or matched_item.get("length"))
                )
                if has_core_extras and not (category == "archive" and prov == "audible"):
                    break

                cross_cands = await _dispatch_provider(prov, cross_query, is_audio=(is_audio or prov == "audible"))
                for cc in cross_cands:
                    if is_derivative_work(cc.get("raw_title", "") or cc.get("title", ""), cross_query):
                        continue
                    if _normalize_tokens(v_title).intersection(_normalize_tokens(cc.get("title", ""))):
                        for field in ("pages", "published", "rating", "ratings_count", "genres", "narrator", "length"):
                            if not matched_item.get(field) and cc.get(field):
                                matched_item[field] = cc[field]
                        if check_series and cc.get("series") and cc["series"] != "Standalone":
                            matched_item["series"] = format_series_label(cc["series"])
                            check_series = False
                        break

            # Normalize series to Option B format (`Series Name (Book #N)` or `Standalone`)
            matched_item["series"] = format_series_label(matched_item.get("series"))
            matched_item["title"], _ = parse_title_and_series(matched_item.get("title") or v_title)
            matched_item["is_matched"] = True

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
# Caption & Log Formatters (Option B Series + Zero N/A + 3-Tick Ordered Log)
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
    Constructs clean, structured Storage Group caption (Option B):
    1. If metadata was matched:
       - Clean `📖 Title:` hyperlinked with the matched website book info URL (`<a href="URL">Title</a>`).
       - Separate `📚 Series:` line (`Eddie Flynn (Book #5)` or `Standalone`).
       - `✍️ Author:` line.
       - Zero N/A: omits any missing optional field (`Narrated by`, `Length`, `Pages`, `Rating`, `Genres`, `Release Date`).
    2. If enrichment failed (<2 parameters):
       - Leaves Title and Author empty with clean placeholders so search does not index false info.
    """
    esc_file_name = html.escape(file_name or "Unknown")
    ext_clean = html.escape(extension.lstrip("."))
    is_matched = book_meta.get("is_matched", False)
    is_audio = category == "audiobook" or f".{ext_clean.lower()}" in supported_audiobook_extensions()
    is_archive = category == "archive" or f".{ext_clean.lower()}" in supported_archive_extensions()

    if not is_matched:
        header_lbl = "🎧 <b>Audiobook:</b> " if is_audio else "📚 <b>Book:</b> "
        author_lbl = "✍️ <b>By:</b> " if is_audio else "✍️ <b>Author:</b> "
        lines = [
            header_lbl,
            "📚 <b>Series:</b> ",
            author_lbl,
            f"📁 <b>File Name:</b> <code>{esc_file_name}</code>",
            f"📦 <b>Size:</b> <code>{html.escape(file_size_str)}</code> | <b>Type:</b> <code>{html.escape(file_type)} (.{ext_clean})</code>",
        ]
        return "\n".join(lines)[:1020]

    raw_title = book_meta.get("title") or book_meta.get("book_title") or ""
    clean_t, parsed_s = parse_title_and_series(raw_title)
    esc_title = html.escape(clean_t or raw_title)
    book_url = book_meta.get("url") or book_meta.get("book_url") or ""
    title_display = f'<a href="{html.escape(book_url)}">{esc_title}</a>' if book_url else esc_title

    esc_author = html.escape(book_meta.get("author") or book_meta.get("book_author") or "")
    raw_series = book_meta.get("series") or book_meta.get("book_series") or parsed_s or "Standalone"
    esc_series = html.escape(format_series_label(raw_series))
    esc_published = html.escape(book_meta.get("published") or book_meta.get("book_published") or "")
    esc_narrator = html.escape(book_meta.get("narrator") or "")
    esc_length = html.escape(book_meta.get("length") or "")
    esc_pages = html.escape(book_meta.get("pages") or book_meta.get("book_pages") or "")
    esc_rating = html.escape(book_meta.get("rating") or book_meta.get("book_rating") or "")
    esc_ratings_count = html.escape(book_meta.get("ratings_count") or book_meta.get("book_ratings_count") or "")
    esc_genres = html.escape(book_meta.get("genres") or book_meta.get("book_genres") or "")

    lines = []
    if is_audio:
        lines.append(f"🎧 <b>Audiobook:</b> {title_display}")
    elif is_archive:
        lines.append(f"📦 <b>Book / Audiobook:</b> {title_display}")
    else:
        lines.append(f"📚 <b>Book:</b> {title_display}")

    lines.append(f"📚 <b>Series:</b> <code>{esc_series}</code>")
    if esc_author:
        lines.append(f"✍️ <b>Author:</b> <code>{esc_author}</code>")
    if esc_narrator:
        lines.append(f"🎙 <b>Narrated by:</b> <code>{esc_narrator}</code>")
    if esc_rating:
        rc_str = f" ({esc_ratings_count} ratings)" if esc_ratings_count else ""
        lines.append(f"⭐ <b>Rating:</b> <code>{esc_rating}</code>{rc_str}")
    if esc_genres:
        lines.append(f"🏷 <b>Genres:</b> <code>{esc_genres}</code>")

    meta_span = []
    if esc_length:
        meta_span.append(f"⏱ <b>Length:</b> <code>{esc_length}</code>")
    if esc_pages:
        meta_span.append(f"📄 <b>Pages:</b> <code>{esc_pages}</code>")
    if esc_published:
        meta_span.append(f"📅 <b>Release Date:</b> <code>{esc_published}</code>")
    if meta_span:
        lines.append(" | ".join(meta_span))

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
    indexed_by_bot: str | None = None,
) -> str:
    """
    Standardized 3-Stage Ordered Index Log format:
    1. Database Presence
    2. Storage Group Presence
    3. Caption Enrichment
    """
    esc_fn = html.escape(file_name)
    esc_user = html.escape(user_title or "Unknown")
    user_link = f'<a href="tg://user?id={user_id}">{esc_user}</a>' if user_id else esc_user
    ts = _ist_now_str()
    esc_slink = html.escape(storage_link or "", quote=True)

    lines = [
        "📥 <b>File Index Log</b>\n",
        f"📁 <b>File Name:</b> <code>{esc_fn}</code>",
        f"📦 <b>File Size:</b> <mark>{html.escape(file_size_str)}</mark>",
        f"🔑 <b>Unique ID:</b> <code>{html.escape(file_unique_id)}</code>",
        f"🔗 <b>Storage Link:</b> <a href=\"{esc_slink}\">{esc_slink}</a>",
        f"👤 <b>Sent By:</b> {user_link}",
    ]
    if indexed_by_bot:
        lines.append(f"🤖 <b>Indexed By:</b> <mark>{html.escape(indexed_by_bot)}</mark>")
    if source_info:
        lines.append(f"🌐 <b>Source:</b> {source_info}")

    lines.extend([
        "",
        "<b>3-Stage Verification Status:</b>",
        f"1. 🗄 <b>Database Presence:</b> {db_badge}",
        f"2. 📦 <b>Storage Group Presence:</b> {storage_badge}",
        f"3. 📝 <b>Caption Enrichment:</b> {caption_badge}",
        f"⏰ <b>Timestamp:</b> <code>{ts}</code>",
    ])
    if esc_slink:
        lines.append("")
        lines.append(
            f'<tg-button-row align="center">'
            f'<tg-button type="url" style="primary" url="{esc_slink}">📦 Open in Storage Group</tg-button>'
            f'</tg-button-row>'
        )
    return "\n".join(lines)


async def send_index_log_dual(bot, log_msg: str, fallback_bot=None) -> None:
    """
    Dispatches an Index Log message to BOTH:
      1. `PUBLIC_/TESTING_INDEX_CHANNEL_ID` (Index Logs Channel)
      2. `PUBLIC_/TESTING_LOGGER_GROUP_ID` (`INDEX_LOG_TOPIC_ID` topic)
    using whichever bot (`bot`) is actively indexing the file, with optional `fallback_bot`.
    """
    idx_chan = index_channel_id()
    log_gid = logger_group_id()
    idx_topic = log_topic("INDEX")

    # 1. Send to Index Logs Channel (if configured and distinct from logger group)
    if idx_chan:
        sent_chan = False
        for b in (bot, fallback_bot):
            if b is None:
                continue
            try:
                await b.send_message(
                    chat_id=int(idx_chan),
                    text=log_msg,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                sent_chan = True
                break
            except Exception as exc:
                logger.warning("Index log delivery to INDEX_CHANNEL_ID (%s) failed via %s: %s", idx_chan, getattr(b, "username", "bot"), exc)
        if not sent_chan:
            logger.error("Could not deliver index log to INDEX_CHANNEL_ID (%s) on any bot.", idx_chan)

    # 2. Send to Logger Group -> INDEX_LOG_TOPIC_ID
    if log_gid and str(log_gid) != str(idx_chan or ""):
        for b in (bot, fallback_bot):
            if b is None:
                continue
            try:
                kwargs = {
                    "chat_id": int(log_gid),
                    "text": log_msg,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                }
                if idx_topic:
                    kwargs["message_thread_id"] = int(idx_topic)
                await b.send_message(**kwargs)
                break
            except Exception as exc:
                logger.warning("Index log delivery to LOGGER_GROUP_ID (%s) failed via %s: %s", log_gid, getattr(b, "username", "bot"), exc)


# ---------------------------------------------------------------------------
# Telegram Extraction & Upload Utilities
# ---------------------------------------------------------------------------
def _parse_caption_meta(raw_caption: str) -> dict:
    """
    Extracts structured metadata from a pre-existing caption after stripping spam/promo lines.
    Ignores empty placeholder lines.
    """
    cleaned = clean_promo_text(raw_caption)
    if not cleaned:
        return {}
    meta = {}
    m = re.search(r"(?:Title|Book|Audiobook):\s*([^\n]+)", cleaned, re.IGNORECASE)
    if m and m.group(1).strip():
        clean_t, s_from_t = parse_title_and_series(re.sub(r"<[^>]+>", "", m.group(1)).strip())
        if clean_t:
            meta["book_title"] = clean_t
        if s_from_t and s_from_t != "Standalone":
            meta["book_series"] = s_from_t
    m = re.search(r"(?:Author|By):\s*([^\n]+)", cleaned, re.IGNORECASE)
    if m and m.group(1).strip():
        val = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if val:
            meta["book_author"] = val
    m = re.search(r"Narrated by:\s*([^\n]+)", cleaned, re.IGNORECASE)
    if m and m.group(1).strip():
        meta["narrator"] = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    m = re.search(r"Length:\s*([^\n]+)", cleaned, re.IGNORECASE)
    if m and m.group(1).strip():
        meta["length"] = re.sub(r"<[^>]+>", "", m.group(1)).strip().split("|")[0].strip()
    m = re.search(r"Release Date:\s*([^\n]+)", cleaned, re.IGNORECASE)
    if m and m.group(1).strip():
        meta["book_published"] = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    m = re.search(r"Series:\s*([^\n]+)", cleaned, re.IGNORECASE)
    if m and m.group(1).strip():
        meta["book_series"] = format_series_label(re.sub(r"<[^>]+>", "", m.group(1)).strip())
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
    archive_exts = supported_archive_extensions()

    category = "ebook"
    if ext in audiobook_exts or media_kind == "audio":
        category = "audiobook"
    elif ext in archive_exts:
        category = "archive"

    is_supported = ext in ebook_exts or ext in audiobook_exts or ext in archive_exts
    raw_caption = getattr(message, "caption", "") or ""
    cap_meta = _parse_caption_meta(raw_caption)

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
        "raw_caption": raw_caption,
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


def _is_caption_truly_enriched(caption_text: str | None, is_enriched_flag: int = 0) -> bool:
    """
    Returns True ONLY if `is_enriched_flag == 1` AND the stored caption has non-empty
    structured Title and Author lines and no raw spam caption.
    """
    if not is_enriched_flag or not caption_text:
        return False
    parsed = _parse_caption_meta(caption_text)
    return bool(parsed.get("book_title") and parsed.get("book_author"))


# ---------------------------------------------------------------------------
# Unified 3-Stage Ordered Verification & Self-Healing Engine
# ---------------------------------------------------------------------------
async def verify_and_heal_indexed_file(
    bot,
    info: dict,
    storage_id: int,
    user_id: int,
    user_title: str,
    source_info: str | None = None,
) -> dict:
    """
    Executes the 3-Stage Verification & Self-Healing Pipeline in strict 1 -> 2 -> 3 order:
      Stage 1: Database Presence (`files.db`)
      Stage 2: Storage Group Presence (`PUBLIC_/TESTING_STORAGE_GROUP_ID`)
      Stage 3: Caption Enrichment (8-Site Book/Audiobook Waterfall + Storage Caption Update)

    Returns a dict with:
      - `status`: `'indexed'` (new or healed), `'duplicate'` (all 3 stages already verified), or `'error'`
      - `storage_message_id`: int
      - `storage_link`: str
      - `db_badge`: str
      - `storage_badge`: str
      - `caption_badge`: str
      - `is_success_enrichment`: bool
    """
    file_unique_id = info["file_unique_id"]
    file_id = info["file_id"]
    file_name = info["file_name"]
    file_size = info["file_size"]
    duration = info["duration"]
    mime_type = info["mime_type"]
    ext = info["extension"]
    category = info["category"]

    size_mb = file_size / (1024 * 1024)
    file_size_str = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{file_size / 1024:.2f} KB"

    # If archive (.zip <= 20 MB), inspect inner files to refine category
    if category == "archive" and ext == ".zip":
        zip_info = await inspect_zip_archive_if_possible(bot, file_id, file_size, file_name)
        if zip_info.get("category") in ("ebook", "audiobook"):
            category = zip_info["category"]

    # -----------------------------------------------------------------------
    # STAGE 1: Database Presence Check (files.db)
    # -----------------------------------------------------------------------
    existing_record = get_file_by_unique_id_db(file_unique_id)
    was_in_db = existing_record is not None
    existing_msg_id = int(existing_record["storage_message_id"]) if (existing_record and existing_record["storage_message_id"]) else None
    existing_caption = (existing_record["caption"] or "") if existing_record else ""
    existing_enriched_flag = int(existing_record["is_enriched"] or 0) if existing_record else 0

    # -----------------------------------------------------------------------
    # STAGE 3 Preparation: Check if Caption is Already Enriched or Needs 8-Site Lookup
    # -----------------------------------------------------------------------
    already_enriched = _is_caption_truly_enriched(existing_caption, existing_enriched_flag)
    if not already_enriched and info.get("caption_meta"):
        cm = info["caption_meta"]
        if cm.get("book_title") and cm.get("book_author"):
            already_enriched = True

    book_meta = {}
    is_success_enrichment = False
    was_caption_healed = False

    if already_enriched:
        parsed_cm = _parse_caption_meta(existing_caption) if existing_caption else (info.get("caption_meta") or {})
        book_meta = {
            "title": parsed_cm.get("book_title") or file_name,
            "author": parsed_cm.get("book_author") or "",
            "series": format_series_label(parsed_cm.get("book_series") or "Standalone"),
            "narrator": parsed_cm.get("narrator") or "",
            "length": parsed_cm.get("length") or "",
            "published": parsed_cm.get("book_published") or "",
            "is_matched": True,
        }
        is_success_enrichment = True
        caption_badge = "✅ Already Enriched"
    else:
        book_meta = await enrich_book_metadata(
            file_name=file_name,
            category=category,
            raw_caption=info.get("raw_caption") or "",
        )
        if book_meta.get("is_matched"):
            prov_name = book_meta.get("provider") or "Catalog"
            series_disp = book_meta.get("series") or "Standalone"
            caption_badge = f"✅ Enriched via {prov_name} ({series_disp})"
            is_success_enrichment = True
            was_caption_healed = True
        else:
            caption_badge = "🚧 Info Not Found (Reported to Error Logs)"
            is_success_enrichment = False

    if category == "audiobook" and (not book_meta.get("length")) and duration > 0:
        book_meta["length"] = _format_duration(duration)

    # If an archive matched with narrator/length on Audible/Storytel and has no pages, treat display category as audiobook
    if category == "archive" and book_meta.get("narrator") and book_meta.get("length") and not book_meta.get("pages"):
        category = "audiobook"

    caption_html = format_index_channel_caption(
        file_name=file_name,
        file_size_str=file_size_str,
        extension=ext.lstrip("."),
        file_type=mime_type,
        book_meta=book_meta,
        category=category,
    )

    # -----------------------------------------------------------------------
    # STAGE 2: Storage Group Presence Check & Self-Healing
    # -----------------------------------------------------------------------
    target_msg_id = existing_msg_id
    was_in_storage = False

    if target_msg_id:
        # Always verify message still exists in Storage Group (and update caption if healed)
        try:
            await bot.edit_message_caption(
                chat_id=int(storage_id),
                message_id=int(target_msg_id),
                caption=caption_html,
                parse_mode="HTML",
            )
            was_in_storage = True
            if was_caption_healed or not existing_enriched_flag:
                storage_badge = f"✅ Present in Storage Group (Caption Updated at Msg #{target_msg_id})"
            else:
                storage_badge = f"✅ Present in Storage Group (Msg #{target_msg_id})"
        except BadRequest as br:
            err_s = str(br).lower()
            if "message is not modified" in err_s:
                was_in_storage = True
                storage_badge = f"✅ Present in Storage Group (Msg #{target_msg_id})"
            elif "message to edit not found" in err_s or "message_id_invalid" in err_s or "message can't be edited" in err_s:
                # Storage Group message was deleted! Self-heal by re-uploading
                target_msg_id = None
                was_in_storage = False
            else:
                was_in_storage = True
                storage_badge = f"✅ Present in Storage Group (Msg #{target_msg_id})"
        except Exception:
            was_in_storage = True
            storage_badge = f"✅ Present in Storage Group (Msg #{target_msg_id})"

    if not target_msg_id:
        target_msg = await send_media_to_storage(bot, int(storage_id), info, caption_html)
        target_msg_id = target_msg.message_id
        if was_in_db and existing_msg_id:
            storage_badge = f"✅ Restored Missing File to Storage Group (Msg #{target_msg_id})"
        else:
            storage_badge = f"✅ Added to Storage Group (Msg #{target_msg_id})"

    storage_link = _make_storage_msg_link(int(storage_id), target_msg_id)

    # -----------------------------------------------------------------------
    # STAGE 1 Completion: Save / Update Verified Record in files.db
    # -----------------------------------------------------------------------
    searchable_caption = (
        f"{caption_html} {file_name} {book_meta.get('title', '')} "
        f"{book_meta.get('author', '')} {book_meta.get('series', '')}"
    ).strip()

    db_ok = save_indexed_file_db(
        file_unique_id=file_unique_id,
        file_id=file_id,
        storage_message_id=target_msg_id,
        file_name=file_name,
        file_size=file_size,
        duration=duration,
        user_id=user_id,
        user_title=user_title,
        caption=searchable_caption,
        extension=ext,
        file_type=mime_type,
        category=category,
        is_enriched=1 if is_success_enrichment else 0,
    )

    if not db_ok:
        db_badge = "❌ Database Write Failed (Reported to Error Logs)"
    elif was_in_db and was_in_storage and not was_caption_healed and existing_enriched_flag:
        db_badge = "✅ Already Present in files.db"
    elif was_in_db:
        db_badge = "✅ Present & Self-Healed in files.db"
    else:
        db_badge = "✅ Added to files.db"

    overall_status = (
        "duplicate"
        if (was_in_db and was_in_storage and not was_caption_healed and existing_enriched_flag)
        else "indexed"
    )

    return {
        "status": overall_status,
        "storage_message_id": target_msg_id,
        "storage_link": storage_link,
        "file_size_str": file_size_str,
        "db_badge": db_badge,
        "storage_badge": storage_badge,
        "caption_badge": caption_badge,
        "is_success_enrichment": is_success_enrichment,
        "db_ok": db_ok,
        "category": category,
    }


# ---------------------------------------------------------------------------
# Direct Upload Handler (Helper Bot DM)
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
            arch_list = ", ".join(sorted(supported_archive_extensions()))
            await update.message.reply_text(
                f"❌ <b>Unsupported format!</b>\n\n"
                f"📚 <b>Supported Ebooks:</b> <code>{ebook_list}</code>\n"
                f"🎧 <b>Supported Audiobooks:</b> <code>{audio_list}</code>\n"
                f"📦 <b>Supported Archives:</b> <code>{arch_list}</code>",
                parse_mode="HTML",
            )
        return

    file_name = info["file_name"]
    file_unique_id = info["file_unique_id"]
    user = message.from_user
    uid = user.id if user else 0
    utitle = (user.full_name or user.username or "Unknown") if user else "Channel"

    try:
        res = await verify_and_heal_indexed_file(
            bot=context.bot,
            info=info,
            storage_id=int(storage_id),
            user_id=uid,
            user_title=utitle,
            source_info=None,
        )

        storage_link = res["storage_link"]
        target_msg_id = res["storage_message_id"]
        is_success_enrichment = res["is_success_enrichment"]

        # Send Error Log alert if any stage failed or enrichment failed (< 2 parameters)
        if (not is_success_enrichment or not res["db_ok"]) and error_log_topic_id and log_group_id:
            try:
                err_text = (
                    f"⚠️ <b>Caption Enrichment Failed (&lt;2 Parameters Matched)</b>\n\n"
                    f"📁 <b>File:</b> <code>{html.escape(file_name)}</code>\n"
                    f"🔗 <b>Storage Message:</b> <a href=\"{storage_link}\">Message #{target_msg_id}</a>\n"
                    f"🔑 <b>Unique ID:</b> <code>{file_unique_id}</code>\n\n"
                    f"<b>3-Stage Check:</b>\n"
                    f"1. 🗄 <b>Database:</b> {res['db_badge']}\n"
                    f"2. 📦 <b>Storage:</b> {res['storage_badge']}\n"
                    f"3. 📝 <b>Caption:</b> {res['caption_badge']}\n\n"
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

        # Post Standardized 3-Tick Index Log to BOTH Index Logs Channel and Logger Group Topic
        try:
            bot_uname = getattr(context.bot, "username", None)
            if not bot_uname:
                try:
                    me = await context.bot.get_me()
                    bot_uname = me.username
                except Exception:
                    bot_uname = None
            bot_label = f"@{bot_uname}" if bot_uname else "Helper Bot"
            log_msg = format_index_log_message(
                file_name=file_name,
                file_size_str=res["file_size_str"],
                file_unique_id=file_unique_id,
                storage_link=storage_link,
                user_id=uid,
                user_title=utitle,
                db_badge=res["db_badge"],
                storage_badge=res["storage_badge"],
                caption_badge=res["caption_badge"],
                indexed_by_bot=bot_label,
            )
            await send_index_log_dual(context.bot, log_msg)
        except Exception as e:
            logger.error("Failed to send index log: %s", e)

        if update.message and update.message.chat.type == "private":
            label = "Audiobook" if res["category"] == "audiobook" else "Book"
            if is_success_enrichment:
                await update.message.reply_text(
                    f"✅ <b>{label} Verified &amp; Indexed!</b>\n"
                    f"1. 🗄 {res['db_badge']}\n"
                    f"2. 📦 {res['storage_badge']}\n"
                    f"3. 📝 {res['caption_badge']}",
                    parse_mode="HTML",
                )
            else:
                await update.message.reply_text(
                    f"⚠️ <b>{label} Stored (Manual Caption Review Needed)</b>\n"
                    f"1. 🗄 {res['db_badge']}\n"
                    f"2. 📦 {res['storage_badge']}\n"
                    f"3. 📝 {res['caption_badge']}",
                    parse_mode="HTML",
                )

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

    info = extract_media_info(msg)
    if not info:
        return

    admin_user = update.effective_user
    admin_id = admin_user.id if admin_user else 0
    admin_name = (admin_user.full_name or "Admin") if admin_user else "Admin"

    new_caption = msg.caption_html or msg.caption or ""
    storage_msg_id = msg.message_id
    storage_link = _make_storage_msg_link(int(storage_id), storage_msg_id)

    update_file_caption_db(storage_message_id=storage_msg_id, new_caption=new_caption, is_enriched=1)

    log_group_id = logger_group_id()
    index_log_topic_id = log_topic("INDEX")

    try:
        admin_link = f'<a href="tg://user?id={admin_id}">{html.escape(admin_name)}</a>'
        caption_badge = f"✅ ✍️ Enriched by Admin ({admin_link})"
        size_mb = info["file_size"] / (1024 * 1024)
        file_size_str = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{info['file_size'] / 1024:.2f} KB"
        bot_uname = getattr(context.bot, "username", None)
        bot_label = f"@{bot_uname}" if bot_uname else "Main Bot"

        log_msg = format_index_log_message(
            file_name=info["file_name"],
            file_size_str=file_size_str,
            file_unique_id=info["file_unique_id"],
            storage_link=storage_link,
            user_id=admin_id,
            user_title=admin_name,
            db_badge="✅ Updated in files.db",
            storage_badge=f"✅ Present in Storage Group (Msg #{storage_msg_id})",
            caption_badge=caption_badge,
            indexed_by_bot=bot_label,
        )
        await send_index_log_dual(context.bot, log_msg)
    except Exception as e:
        logger.error("Failed to send admin caption edit index log: %s", e)
