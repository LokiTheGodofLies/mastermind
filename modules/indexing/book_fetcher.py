import sys, os
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
import re
import html
import asyncio
import logging
import urllib.parse
from html.parser import HTMLParser
import aiohttp
from mediagoer import Mediagoer, MediaItem

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_MG = Mediagoer(audible_marketplace="in", storytel_locale="in")
_CACHE = {}


class _SimpleHTMLTagCleaner(HTMLParser):
    def __init__(self):
        super().__init__()
        self._pieces = []

    def handle_data(self, d):
        self._pieces.append(d)

    def get_text(self):
        return re.sub(r"\s+", " ", "".join(self._pieces)).strip()


def strip_html_tags(raw_html: str) -> str:
    if not raw_html:
        return ""
    parser = _SimpleHTMLTagCleaner()
    parser.feed(raw_html)
    return parser.get_text()


def clean_book_filename(file_name: str) -> str:
    """Strips extension, brackets (round, square, curly), and warez/release tags."""
    if not file_name:
        return ""
    name = re.sub(r"\.[a-zA-Z0-9]{2,5}$", "", file_name)
    name = re.sub(r"\[.*?\]|\(.*?\)|(\{.*?\})", " ", name)
    noise = (
        r"\b(z-lib\.org|z-library|annas-archive|oceanofpdf|ebookhunter|libgen|mobilism|"
        r"audiobookbay|abb|epub|pdf|azw3|kfx|mobi|djvu|mp3|m4b|aax|audiobook|"
        r"unabridged|abridged|64kbps|128kbps|320kbps)\b"
    )
    name = re.sub(noise, " ", name, flags=re.IGNORECASE)
    name = re.sub(r"[_\.\-]+", " ", name)
    name = re.sub(r"\s+[a-zA-Z]\s+", " ", name)
    return re.sub(r"\s+", " ", name).strip()


async def fetch_oceanofpdf_meta(query: str, session: aiohttp.ClientSession) -> dict | None:
    try:
        url = f"https://oceanofpdf.com/?s={urllib.parse.quote_plus(query)}"
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            if resp.status == 200:
                text = await resp.text()
                m = re.search(r'<article[^>]*>.*?<h2[^>]*><a[^>]+href="([^"]+)"[^>]*>([^<]+)</a></h2>.*?<div class="post-excerpt">([^<]+)</div>', text, re.DOTALL | re.I)
                if m:
                    full_title = strip_html_tags(m.group(2))
                    post_url = m.group(1)
                    excerpt = strip_html_tags(m.group(3))
                    author_m = re.search(r"by\s+([^–\-\[\(]+)", full_title, re.I)
                    author = author_m.group(1).strip() if author_m else "Unknown Author"
                    clean_t = re.sub(r"\[PDF\]|\[EPUB\]|by\s+.*$", "", full_title, flags=re.I).strip()
                    return {"title": clean_t, "author": author, "plot": excerpt, "url": post_url, "provider": "OceanofPDF"}
    except Exception:
        pass
    return None


async def fetch_ebookhunter_meta(query: str, session: aiohttp.ClientSession) -> dict | None:
    try:
        url = f"https://www.ebookhunter.net/?s={urllib.parse.quote_plus(query)}"
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            if resp.status == 200:
                text = await resp.text()
                m = re.search(r'<h2 class="entry-title"><a href="([^"]+)"[^>]*>([^<]+)</a></h2>', text, re.I)
                if m:
                    p_url, full_title = m.group(1), strip_html_tags(m.group(2))
                    author_m = re.search(r"–\s*([^–]+)$", full_title)
                    author = author_m.group(1).strip() if author_m else "Unknown Author"
                    t = re.sub(r"–\s*[^–]+$", "", full_title).strip()
                    return {"title": t, "author": author, "url": p_url, "provider": "EbookHunter"}
    except Exception:
        pass
    return None


async def fetch_audiobookbay_meta(query: str, session: aiohttp.ClientSession) -> dict | None:
    try:
        url = f"https://audiobookbay.lu/?s={urllib.parse.quote_plus(query)}"
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            if resp.status == 200:
                text = await resp.text()
                m = re.search(r'<div class="postTitle"><h2><a href="([^"]+)">([^<]+)</a></h2></div>', text, re.I)
                if m:
                    p_url, title_raw = m.group(1), strip_html_tags(m.group(2))
                    narr_m = re.search(r"Read by\s+([^–\-\[\(]+)", text, re.I)
                    narrator = narr_m.group(1).strip() if narr_m else "N/A"
                    return {"title": title_raw, "narrator": narrator, "url": p_url, "provider": "AudioBookBay", "is_audiobook": True}
    except Exception:
        pass
    return None


def _mediagoer_sync_worker(clean_q: str, is_audio: bool) -> dict | None:
    providers = ["audible", "storytel", "goodreads"] if is_audio else ["goodreads", "storytel", "audible"]
    for prov in providers:
        try:
            results = _MG.search(clean_q, provider=prov, results=2)
            if results:
                top = results[0]
                if top.mediaID and (not top.get("plot") or not top.get("genres")):
                    try:
                        full = _MG.get(top.mediaID, provider=prov)
                        if full and full.get("title"):
                            top = full
                    except Exception:
                        pass

                authors = [str(a) for a in (top.get("authors") or []) if str(a)]
                narrators = [str(n) for n in (top.get("narrators") or []) if str(n)]
                series_label = top.get("full series") or top.get("series") or ""
                return {
                    "title": top.get("title") or clean_q,
                    "author": ", ".join(authors) if authors else "Unknown Author",
                    "narrator": ", ".join(narrators) if narrators else "N/A",
                    "series": series_label,
                    "year": str(top.get("year") or "N/A"),
                    "rating": str(top.get("rating") or "N/A"),
                    "ratings_count": str(top.get("votes") or "0"),
                    "language": str(top.get("language") or "English"),
                    "country": str(top.get("country") or "N/A"),
                    "length_str": str(top.get("runtime") or (f"{top.get('pages')} pages" if top.get("pages") else "N/A")),
                    "publisher": str(top.get("publisher") or prov.title()),
                    "plot": top.get("plot") or "",
                    "url": top.get("url") or "",
                    "provider": prov.title(),
                    "is_audiobook": is_audio or (top.get("kind") == "audiobook"),
                }
        except Exception:
            continue
    return None


async def fetch_comprehensive_book_metadata(file_name: str, ext: str = "") -> dict:
    """
    Fetches rich metadata for Books & Audiobooks across:
    Audible, Storytel, Goodreads, OceanofPDF, EbookHunter, AudioBookBay, and Anna's Archive.
    """
    if not ext and file_name:
        _, ext = re.findall(r"\.[a-zA-Z0-9]+$", file_name)[-1].lower() if "." in file_name else ("", "")

    is_audio = ext in {".mp3", ".m4b", ".aax", ".flac", ".ogg", ".m4a"}
    clean_q = clean_book_filename(file_name)
    if not clean_q:
        clean_q = file_name

    ckey = f"{'audio' if is_audio else 'book'}:{clean_q.lower()}"
    if ckey in _CACHE:
        return _CACHE[ckey]

    # 1. Primary lookup via Mediagoer (Audible, Storytel, Goodreads)
    meta = await asyncio.to_thread(_mediagoer_sync_worker, clean_q, is_audio)

    # 2. Supplementary lookup on specialized book sites (OceanofPDF, EbookHunter, AudioBookBay)
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        if is_audio:
            abb_meta = await fetch_audiobookbay_meta(clean_q, session)
            if abb_meta and meta and meta.get("narrator") == "N/A" and abb_meta.get("narrator") != "N/A":
                meta["narrator"] = abb_meta["narrator"]
            elif not meta and abb_meta:
                meta = abb_meta
        else:
            tasks = [fetch_oceanofpdf_meta(clean_q, session), fetch_ebookhunter_meta(clean_q, session)]
            sub_results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in sub_results:
                if isinstance(res, dict) and res.get("title"):
                    if not meta:
                        meta = res
                    else:
                        if not meta.get("plot") and res.get("plot"):
                            meta["plot"] = res["plot"]
                        if not meta.get("author") and res.get("author"):
                            meta["author"] = res["author"]

    if not meta:
        meta = {
            "title": clean_q, "author": "Unknown Author", "narrator": "N/A",
            "series": "", "year": "N/A", "rating": "N/A", "ratings_count": "0",
            "language": "English", "country": "N/A", "length_str": "N/A",
            "publisher": "Unknown", "plot": "", "url": "",
            "provider": "Local", "is_audiobook": is_audio,
        }

    _CACHE[ckey] = meta
    return meta


async def fetch_oceanofpdf_meta(query: str, session: aiohttp.ClientSession) -> dict | None:
    try:
        url = f"https://oceanofpdf.com/?s={urllib.parse.quote_plus(query)}"
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            if resp.status == 200:
                text = await resp.text()
                m = re.search(r'<article[^>]*>.*?<h2[^>]*><a[^>]+href="([^"]+)"[^>]*>([^<]+)</a></h2>.*?<div class="post-excerpt">([^<]+)</div>', text, re.DOTALL | re.I)
                if m:
                    full_title = strip_html_tags(m.group(2))
                    post_url = m.group(1)
                    excerpt = strip_html_tags(m.group(3))
                    author_m = re.search(r"by\s+([^–\-\[\(]+)", full_title, re.I)
                    author = author_m.group(1).strip() if author_m else "Unknown Author"
                    clean_t = re.sub(r"\[PDF\]|\[EPUB\]|by\s+.*$", "", full_title, flags=re.I).strip()
                    return {"title": clean_t, "author": author, "plot": excerpt, "url": post_url, "provider": "OceanofPDF"}
    except Exception:
        pass
    return None


async def fetch_ebookhunter_meta(query: str, session: aiohttp.ClientSession) -> dict | None:
    try:
        url = f"https://www.ebookhunter.net/?s={urllib.parse.quote_plus(query)}"
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            if resp.status == 200:
                text = await resp.text()
                m = re.search(r'<h2 class="entry-title"><a href="([^"]+)"[^>]*>([^<]+)</a></h2>', text, re.I)
                if m:
                    p_url, full_title = m.group(1), strip_html_tags(m.group(2))
                    author_m = re.search(r"–\s*([^–]+)$", full_title)
                    author = author_m.group(1).strip() if author_m else "Unknown Author"
                    t = re.sub(r"–\s*[^–]+$", "", full_title).strip()
                    return {"title": t, "author": author, "url": p_url, "provider": "EbookHunter"}
    except Exception:
        pass
    return None


async def fetch_audiobookbay_meta(query: str, session: aiohttp.ClientSession) -> dict | None:
    try:
        url = f"https://audiobookbay.lu/?s={urllib.parse.quote_plus(query)}"
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            if resp.status == 200:
                text = await resp.text()
                m = re.search(r'<div class="postTitle"><h2><a href="([^"]+)">([^<]+)</a></h2></div>', text, re.I)
                if m:
                    p_url, title_raw = m.group(1), strip_html_tags(m.group(2))
                    narr_m = re.search(r"Read by\s+([^–\-\[\(]+)", text, re.I)
                    narrator = narr_m.group(1).strip() if narr_m else "N/A"
                    return {"title": title_raw, "narrator": narrator, "url": p_url, "provider": "AudioBookBay", "is_audiobook": True}
    except Exception:
        pass
    return None


def _mediagoer_sync_worker(clean_q: str, is_audio: bool) -> dict | None:
    providers = ["audible", "storytel", "goodreads"] if is_audio else ["goodreads", "storytel", "audible"]
    for prov in providers:
        try:
            results = _MG.search(clean_q, provider=prov, results=2)
            if results:
                top = results[0]
                if top.mediaID and (not top.get("plot") or not top.get("genres")):
                    try:
                        full = _MG.get(top.mediaID, provider=prov)
                        if full and full.get("title"):
                            top = full
                    except Exception:
                        pass

                authors = [str(a) for a in (top.get("authors") or []) if str(a)]
                narrators = [str(n) for n in (top.get("narrators") or []) if str(n)]
                series_label = top.get("full series") or top.get("series") or ""
                return {
                    "title": top.get("title") or clean_q,
                    "author": ", ".join(authors) if authors else "Unknown Author",
                    "narrator": ", ".join(narrators) if narrators else "N/A",
                    "series": series_label,
                    "year": str(top.get("year") or "N/A"),
                    "rating": str(top.get("rating") or "N/A"),
                    "ratings_count": str(top.get("votes") or "0"),
                    "language": str(top.get("language") or "English"),
                    "country": str(top.get("country") or "N/A"),
                    "length_str": str(top.get("runtime") or (f"{top.get('pages')} pages" if top.get("pages") else "N/A")),
                    "publisher": str(top.get("publisher") or prov.title()),
                    "plot": top.get("plot") or "",
                    "url": top.get("url") or "",
                    "provider": prov.title(),
                    "is_audiobook": is_audio or (top.get("kind") == "audiobook"),
                }
        except Exception:
            continue
    return None


async def fetch_comprehensive_book_metadata(file_name: str, ext: str = "") -> dict:
    """
    Fetches rich metadata for Books & Audiobooks across:
    Audible, Storytel, Goodreads, OceanofPDF, EbookHunter, AudioBookBay, and Anna's Archive.
    """
    if not ext and file_name:
        _, ext = re.findall(r"\.[a-zA-Z0-9]+$", file_name)[-1].lower() if "." in file_name else ("", "")

    is_audio = ext in {".mp3", ".m4b", ".aax", ".flac", ".ogg", ".m4a"}
    clean_q = clean_book_filename(file_name)
    if not clean_q:
        clean_q = file_name

    ckey = f"{'audio' if is_audio else 'book'}:{clean_q.lower()}"
    if ckey in _CACHE:
        return _CACHE[ckey]

    # 1. Primary lookup via Mediagoer (Audible, Storytel, Goodreads)
    meta = await asyncio.to_thread(_mediagoer_sync_worker, clean_q, is_audio)

    # 2. Supplementary lookup on specialized book sites (OceanofPDF, EbookHunter, AudioBookBay)
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        if is_audio:
            abb_meta = await fetch_audiobookbay_meta(clean_q, session)
            if abb_meta and meta and meta.get("narrator") == "N/A" and abb_meta.get("narrator") != "N/A":
                meta["narrator"] = abb_meta["narrator"]
            elif not meta and abb_meta:
                meta = abb_meta
        else:
            tasks = [fetch_oceanofpdf_meta(clean_q, session), fetch_ebookhunter_meta(clean_q, session)]
            sub_results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in sub_results:
                if isinstance(res, dict) and res.get("title"):
                    if not meta:
                        meta = res
                    else:
                        if not meta.get("plot") and res.get("plot"):
                            meta["plot"] = res["plot"]
                        if not meta.get("author") and res.get("author"):
                            meta["author"] = res["author"]

    if not meta:
        meta = {
            "title": clean_q, "author": "Unknown Author", "narrator": "N/A",
            "series": "", "year": "N/A", "rating": "N/A", "ratings_count": "0",
            "language": "English", "country": "N/A", "length_str": "N/A",
            "publisher": "Unknown", "plot": "", "url": "",
            "provider": "Local", "is_audiobook": is_audio,
        }

    _CACHE[ckey] = meta
    return meta
