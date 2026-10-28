# ============================================================================
# modules/indexing/book_fetcher.py
# Multi-source Book & Audiobook metadata fetcher (Goodreads, Audible, Storytel,
# OceanofPDF, Anna's Archive, EbookHunter, Mobilism, AudioBookBay).
# ============================================================================
import os
import re
import asyncio
import logging
import urllib.parse
from html.parser import HTMLParser
import aiohttp

from lib.mediagoer import Mediagoer

# Initialize module logger for /log command tracking
logger = logging.getLogger(__name__)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
_MG = Mediagoer(audible_marketplace="in", storytel_locale="in")
_CACHE = {}
# End of global setup


# HTML tag stripper helper class
class _TagStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, d):
        self.parts.append(d)

    def get_text(self):
        return re.sub(r"\s+", " ", "".join(self.parts)).strip()


def strip_html_tags(raw: str) -> str:
    if not raw:
        return ""
    p = _TagStripper()
    p.feed(str(raw))
    return p.get_text()
# End of HTML tag stripper


# Smart parser that extracts Title, Series, and Author from filenames like:
# "The Striker {Gods of the Game 1} Ana Huang.epub" or "Book Title by Author.pdf"
def parse_filename_metadata(file_name: str) -> dict:
    if not file_name:
        return {"title": "Unknown Title", "author": "", "series": "", "clean_query": ""}

    # 1. Remove file extension (.epub, .pdf, .m4b, etc.)
    base = re.sub(r"\.[a-zA-Z0-9]{2,5}$", "", file_name).strip()

    # 2. Extract series from {Series 1}, (Series #1), or [Series 1]
    series_found = ""
    bracket_matches = re.findall(r"[\{\(\[]([^\}\)\]]+)[\}\)\]]", base)
    for bm in bracket_matches:
        if not re.search(r"\b(z-lib|epub|pdf|mobi|m4b|mp3|unabridged|retail|deluxe)\b", bm, re.I):
            series_found = re.sub(r"\bGod\s+s\b", "Gods", bm.strip(), flags=re.I)
            break

    # 3. Split before and after bracket if format is: Title {Series} Author
    m_bracket_split = re.match(r"^(.*?)[\{\(\[].*?[\}\)\]]\s*(.+)$", base)
    if m_bracket_split:
        cand_title = m_bracket_split.group(1).strip(" -_.")
        cand_author = m_bracket_split.group(2).strip(" -_.")
        cand_author = re.sub(r"^by\s+", "", cand_author, flags=re.I).strip()
        if cand_title and cand_author:
            clean_q = f"{cand_title} {cand_author}"
            logger.info(f"[FILENAME PARSER] Extracted from brackets -> Title: '{cand_title}' | Series: '{series_found}' | Author: '{cand_author}'")
            return {"title": cand_title, "author": cand_author, "series": series_found, "clean_query": clean_q}

    # 4. Remove brackets and noise words for general "Title by Author" or "Title - Author" parsing
    no_brackets = re.sub(r"\[.*?\]|\(.*?\)|\{.*?\}", " ", base)
    noise = r"\b(z-lib\.org|z-library|annas-archive|oceanofpdf|ebookhunter|libgen|mobilism|audiobookbay|epub|pdf|azw3|mobi|mp3|m4b|aax|audiobook|unabridged|deluxe\s*edition)\b"
    cleaned = re.sub(noise, " ", no_brackets, flags=re.I)
    cleaned = re.sub(r"[_\.]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # 5. Check "Title by Author" pattern
    m_by = re.search(r"^(.*?)\s+by\s+([^–\-]+?)(?:\s*[-–]\s*.*)?$", cleaned, re.I)
    if m_by:
        t, a = m_by.group(1).strip(" -–"), m_by.group(2).strip(" -–")
        logger.info(f"[FILENAME PARSER] Extracted 'by' pattern -> Title: '{t}' | Author: '{a}'")
        return {"title": t, "author": a, "series": series_found, "clean_query": f"{t} {a}"}

    # 6. Check "Title - Author" or "Title – Author" pattern
    if " - " in cleaned or " – " in cleaned:
        parts = re.split(r"\s+[-–]\s+", cleaned, maxsplit=1)
        if len(parts) == 2 and len(parts[1].split()) <= 4:
            t, a = parts[0].strip(), parts[1].strip()
            logger.info(f"[FILENAME PARSER] Extracted dash pattern -> Title: '{t}' | Author: '{a}'")
            return {"title": t, "author": a, "series": series_found, "clean_query": f"{t} {a}"}

    return {"title": cleaned, "author": "", "series": series_found, "clean_query": cleaned}
# End of parse_filename_metadata


def clean_book_filename(file_name: str) -> str:
    return parse_filename_metadata(file_name).get("clean_query") or file_name


# Helper to split "Title by Author" or "Title – Author" returned by scraped websites
def _split_scraped_title_author(raw_title: str) -> tuple[str, str]:
    if not raw_title:
        return "", ""
    t = re.sub(r"\[PDF\]|\[EPUB\]|\(PDF\)|\(EPUB\)|-\s*Deluxe\s*Edition", "", raw_title, flags=re.I).strip()
    m_by = re.search(r"^(.*?)\s+by\s+([^–\-\[\(]+)$", t, re.I)
    if m_by:
        return m_by.group(1).strip(" -–"), m_by.group(2).strip(" -–")
    m_dash = re.search(r"^(.*?)\s*[–\-]\s*([^–\-]+)$", t)
    if m_dash and len(m_dash.group(2).split()) <= 4:
        return m_dash.group(1).strip(), m_dash.group(2).strip()
    return t.strip(), ""
# End of _split_scraped_title_author


# 1. OceanofPDF Scraper
async def fetch_oceanofpdf_meta(query: str, session: aiohttp.ClientSession) -> dict | None:
    url = f"https://oceanofpdf.com/?s={urllib.parse.quote_plus(query)}"
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            if resp.status == 200:
                text = await resp.text()
                m = re.search(r'<article[^>]*>.*?<h2[^>]*><a[^>]+href="([^"]+)"[^>]*>([^<]+)</a></h2>', text, re.DOTALL | re.I)
                if m:
                    p_url, raw_t = m.group(1), strip_html_tags(m.group(2))
                    clean_t, author = _split_scraped_title_author(raw_t)
                    logger.info(f"[OCEANOFPDF SUCCESS] Matched '{clean_t}' by '{author}'")
                    return {"title": clean_t, "author": author, "url": p_url, "provider": "OceanofPDF"}
    except Exception as e:
        logger.debug(f"[OCEANOFPDF ERROR] { query }: {e}")
    return None
# End of OceanofPDF Scraper


# 2. EbookHunter Scraper (handles both "by Author" and "– Author")
async def fetch_ebookhunter_meta(query: str, session: aiohttp.ClientSession) -> dict | None:
    url = f"https://www.ebookhunter.net/?s={urllib.parse.quote_plus(query)}"
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            if resp.status == 200:
                text = await resp.text()
                m = re.search(r'<h2[^>]*class="entry-title"[^>]*><a[^>]+href="([^"]+)"[^>]*>([^<]+)</a></h2>', text, re.I)
                if m:
                    p_url, raw_t = m.group(1), strip_html_tags(m.group(2))
                    clean_t, author = _split_scraped_title_author(raw_t)
                    logger.info(f"[EBOOKHUNTER SUCCESS] Matched '{clean_t}' by '{author}'")
                    return {"title": clean_t, "author": author, "url": p_url, "provider": "EbookHunter"}
    except Exception as e:
        logger.debug(f"[EBOOKHUNTER ERROR] {query}: {e}")
    return None
# End of EbookHunter Scraper


# 3. Anna's Archive Scraper
async def fetch_annas_archive_meta(query: str, session: aiohttp.ClientSession) -> dict | None:
    url = f"https://annas-archive.org/search?q={urllib.parse.quote_plus(query)}"
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            if resp.status == 200:
                text = await resp.text()
                m = re.search(r'href="(/md5/[a-f0-9]{32})"[^>]*>.*?<h3[^>]*>([^<]+)</h3>.*?<div[^>]*class="[^"]*italic[^"]*"[^>]*>([^<]+)</div>', text, re.DOTALL | re.I)
                if m:
                    p_url = "https://annas-archive.org" + m.group(1)
                    clean_t = strip_html_tags(m.group(2))
                    author = strip_html_tags(m.group(3))
                    logger.info(f"[ANNAS ARCHIVE SUCCESS] Matched '{clean_t}' by '{author}'")
                    return {"title": clean_t, "author": author, "url": p_url, "provider": "Anna's Archive"}
    except Exception as e:
        logger.debug(f"[ANNAS ARCHIVE ERROR] {query}: {e}")
    return None
# End of Anna's Archive Scraper


# 4. Mobilism Scraper
async def fetch_mobilism_meta(query: str, session: aiohttp.ClientSession) -> dict | None:
    url = f"https://forum.mobilism.org/search.php?keywords={urllib.parse.quote_plus(query)}&sr=topics&sf=titleonly"
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            if resp.status == 200:
                text = await resp.text()
                m = re.search(r'<a[^>]+href="(\./viewtopic\.php\?f=\d+&amp;t=\d+)"[^>]*class="topictitle"[^>]*>([^<]+)</a>', text, re.I)
                if m:
                    p_url = "https://forum.mobilism.org/" + m.group(1).lstrip("./").replace("&amp;", "&")
                    raw_t = strip_html_tags(m.group(2))
                    clean_t, author = _split_scraped_title_author(raw_t)
                    logger.info(f"[MOBILISM SUCCESS] Matched '{clean_t}' by '{author}'")
                    return {"title": clean_t, "author": author, "url": p_url, "provider": "Mobilism"}
    except Exception as e:
        logger.debug(f"[MOBILISM ERROR] {query}: {e}")
    return None
# End of Mobilism Scraper


# 5. AudioBookBay (ABB) Scraper
async def fetch_audiobookbay_meta(query: str, session: aiohttp.ClientSession) -> dict | None:
    url = f"https://audiobookbay.lu/?s={urllib.parse.quote_plus(query)}"
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            if resp.status == 200:
                text = await resp.text()
                m = re.search(r'<div class="postTitle"><h2><a href="([^"]+)">([^<]+)</a></h2></div>', text, re.I)
                if m:
                    p_url = "https://audiobookbay.lu" + m.group(1) if m.group(1).startswith("/") else m.group(1)
                    raw_t = strip_html_tags(m.group(2))
                    clean_t, author = _split_scraped_title_author(raw_t)
                    narr_m = re.search(r"Read by\s+([^<\n\r–\-]+)", text, re.I)
                    narrator = narr_m.group(1).strip() if narr_m else "N/A"
                    logger.info(f"[AUDIOBOOKBAY SUCCESS] Matched '{clean_t}' by '{author}' (Narrator: {narrator})")
                    return {"title": clean_t, "author": author, "narrator": narrator, "url": p_url, "provider": "AudioBookBay", "is_audiobook": True}
    except Exception as e:
        logger.debug(f"[AUDIOBOOKBAY ERROR] {query}: {e}")
    return None
# End of AudioBookBay Scraper


# 6. Mediagoer Worker (Goodreads, Audible, Storytel)
def _mediagoer_sync_worker(queries: list[str], is_audio: bool) -> dict | None:
    providers = ["audible", "storytel", "goodreads"] if is_audio else ["goodreads", "storytel", "audible"]
    for q in queries:
        if not q:
            continue
        for prov in providers:
            try:
                results = _MG.search(q, provider=prov, results=2)
                if results:
                    top = results[0]
                    if top.mediaID and (not top.get("plot") or not top.get("authors")):
                        try:
                            full = _MG.get(top.mediaID, provider=prov)
                            if full and full.get("title"):
                                top = full
                        except Exception as ge:
                            logger.debug(f"[MEDIAGOER GET {prov}] {ge}")

                    raw_t = top.get("title") or q
                    clean_t, split_a = _split_scraped_title_author(raw_t)
                    authors = [str(a) for a in (top.get("authors") or []) if str(a)]
                    author_str = ", ".join(authors) if authors else split_a
                    narrators = [str(n) for n in (top.get("narrators") or []) if str(n)]
                    series_label = top.get("full series") or top.get("series") or ""
                    pages = top.get("pages")
                    length_val = str(top.get("runtime") or (f"{pages} pages" if pages else "N/A"))

                    logger.info(f"[MEDIAGOER {prov.upper()} SUCCESS] Query='{q}' -> Title='{clean_t}' | Author='{author_str}' | Series='{series_label}'")
                    return {
                        "title": clean_t or raw_t,
                        "author": author_str or "",
                        "narrator": ", ".join(narrators) if narrators else "N/A",
                        "series": series_label,
                        "year": str(top.get("year") or "N/A"),
                        "release_date": str(top.get("year") or "N/A"),
                        "rating": str(top.get("rating") or "N/A"),
                        "ratings_count": str(top.get("votes") or "0"),
                        "language": str(top.get("language") or "English"),
                        "country": str(top.get("country") or "N/A"),
                        "length_str": length_val,
                        "publisher": str(top.get("publisher") or prov.title()),
                        "plot": top.get("plot") or "",
                        "url": top.get("url") or "",
                        "provider": prov.title(),
                        "is_audiobook": is_audio or (top.get("kind") == "audiobook"),
                    }
            except Exception as e:
                logger.debug(f"[MEDIAGOER {prov.upper()} ERROR] Query='{q}': {e}")
    return None
# End of Mediagoer Worker


# Master function combining Filename Parser + Mediagoer + 5 Book/Audiobook Websites
async def fetch_comprehensive_book_metadata(file_name: str, ext: str = "") -> dict:
    # 1. Safely detect file extension
    if not ext and file_name:
        _, ext = os.path.splitext(file_name.lower())
    ext = (ext or "").lower()
    is_audio = ext in {".mp3", ".m4b", ".aax", ".flac", ".ogg", ".m4a"}

    # 2. Extract structured fallback fields directly from filename
    fn_info = parse_filename_metadata(file_name)
    fn_title = fn_info["title"]
    fn_author = fn_info["author"]
    fn_series = fn_info["series"]
    clean_q = fn_info["clean_query"] or fn_title or file_name

    # Build candidate search queries (Title + Author, then Title alone)
    queries = [clean_q]
    if fn_title and fn_title != clean_q:
        queries.append(fn_title)

    ckey = f"{'audio' if is_audio else 'book'}:{clean_q.lower()}"
    if ckey in _CACHE:
        logger.info(f"[CACHE HIT] Returning cached metadata for '{clean_q}'")
        return _CACHE[ckey]

    logger.info(f"[FETCH START] File='{file_name}' | Queries={queries} | PreParsed=({fn_title}, {fn_author}, {fn_series})")

    # 3. Query Mediagoer (Goodreads, Storytel, Audible)
    meta = await asyncio.to_thread(_mediagoer_sync_worker, queries, is_audio)
    if meta and not is_audio and (meta.get("year") in ("N/A", "") or meta.get("rating") in ("N/A", "")):
        aud_sup = await asyncio.to_thread(_mediagoer_sync_worker, queries, True)
        if aud_sup:
            if meta.get("year") in ("N/A", "") and aud_sup.get("year") not in ("N/A", ""):
                meta["year"] = aud_sup["year"]
                meta["release_date"] = aud_sup["year"]
            if meta.get("rating") in ("N/A", "") and aud_sup.get("rating") not in ("N/A", ""):
                meta["rating"] = aud_sup["rating"]
                meta["ratings_count"] = aud_sup.get("ratings_count", "0")

    # 4. Query OceanofPDF, EbookHunter, Anna's Archive, Mobilism, and AudioBookBay
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        if is_audio:
            tasks = [fetch_audiobookbay_meta(clean_q, session), fetch_mobilism_meta(clean_q, session)]
        else:
            tasks = [
                fetch_oceanofpdf_meta(clean_q, session),
                fetch_ebookhunter_meta(clean_q, session),
                fetch_annas_archive_meta(clean_q, session),
                fetch_mobilism_meta(clean_q, session),
            ]
        web_results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in web_results:
            if isinstance(res, dict) and res.get("title"):
                if not meta:
                    meta = res
                else:
                    if meta.get("author") in ("", "Unknown Author", "N/A") and res.get("author") not in ("", "Unknown Author", "N/A", None):
                        meta["author"] = res["author"]
                    if not meta.get("plot") and res.get("plot"):
                        meta["plot"] = res["plot"]
                    if not meta.get("url") and res.get("url"):
                        meta["url"] = res["url"]
                    if is_audio and meta.get("narrator") in ("", "N/A") and res.get("narrator") not in ("", "N/A", None):
                        meta["narrator"] = res["narrator"]

    # 5. Initialize default dict if all external sites failed
    if not meta:
        logger.warning(f"[FETCH FALLBACK] All external sites missed '{clean_q}', using filename parser.")
        meta = {}

    # 6. Clean any remaining "by Author" inside title and apply filename fallback so Author/Series are NEVER lost
    final_t, split_a = _split_scraped_title_author(meta.get("title") or fn_title or clean_q)
    final_author = meta.get("author") or split_a or fn_author or "Unknown Author"
    if final_author in ("Unknown Author", "N/A", "") and (split_a or fn_author):
        final_author = split_a or fn_author

    final_series = meta.get("series") or fn_series or ""
    final_year = meta.get("release_date") or meta.get("year") or "N/A"

    result = {
        "title": final_t or fn_title or clean_q,
        "author": final_author,
        "narrator": meta.get("narrator") or "N/A",
        "series": final_series,
        "year": final_year,
        "release_date": final_year,
        "rating": meta.get("rating") or "N/A",
        "ratings_count": meta.get("ratings_count") or "0",
        "language": meta.get("language") or "English",
        "country": meta.get("country") or "N/A",
        "length_str": meta.get("length_str") or "N/A",
        "publisher": meta.get("publisher") or meta.get("provider") or "Library",
        "plot": meta.get("plot") or "",
        "url": meta.get("url") or "",
        "provider": meta.get("provider") or "Filename Parser",
        "is_audiobook": is_audio,
    }
    logger.info(f"[FETCH COMPLETE] Title='{result['title']}' | Author='{result['author']}' | Series='{result['series']}' | Source='{result['provider']}'")
    _CACHE[ckey] = result
    return result
# End of fetch_comprehensive_book_metadata
