"""Central configuration for the Mastermind bot (config.py).

All runtime settings are read from environment variables (Render environment
or env.txt) with fallback to config.db or safe sample defaults.
No real secrets, tokens, or personal Telegram IDs are hardcoded here.
"""
import os

# ---------------------------------------------------------------------------
# Sample placeholder variables (replace via env.txt or Render Environment)
# ---------------------------------------------------------------------------
SAMPLE_BOT_TOKEN = "1234567890:AAF_SAMPLE_MAIN_BOT_TOKEN_REPLACE_ME"
SAMPLE_HELPER_BOT_TOKENS = (
    "1234567891:AAF_SAMPLE_HELPER_BOT_1_TOKEN,"
    "1234567892:AAF_SAMPLE_HELPER_BOT_2_TOKEN"
)

SAMPLE_STORAGE_GROUP_ID = -1001111111111
SAMPLE_POSTING_CHANNEL_ID = -1002222222222
SAMPLE_LOGGER_GROUP_ID = -1003333333333
SAMPLE_INDEX_CHANNEL_ID = -1004444444444
SAMPLE_REQUEST_CHANNEL_ID = -1005555555555
SAMPLE_SUPPORT_CHAT_ID = -1006666666666

SAMPLE_USER_LOG_TOPIC_ID = 2
SAMPLE_INDEX_LOG_TOPIC_ID = 3
SAMPLE_GROUP_LOG_TOPIC_ID = 4
SAMPLE_CHANNEL_LOG_TOPIC_ID = 5
SAMPLE_REQUEST_LOG_TOPIC_ID = 6
SAMPLE_ERROR_LOG_TOPIC_ID = 7

SAMPLE_COMMUNITY_LINK = "https://t.me/sample_mastermind_community"

# Default supported formats (Ebooks, Audiobooks, and Book/Audiobook Archives)
DEFAULT_EBOOK_EXTENSIONS = (
    ".epub",
    ".pdf",
    ".azw",
    ".azw3",
    ".mobi",
    ".cbz",
    ".cbr",
    ".djvu",
    ".fb2",
    ".txt",
    ".rtf",
)

DEFAULT_AUDIOBOOK_EXTENSIONS = (
    ".mp3",
    ".m4b",
    ".m4a",
    ".aax",
    ".aa",
    ".flac",
    ".wav",
    ".ogg",
    ".opus",
)

DEFAULT_ARCHIVE_EXTENSIONS = (
    ".zip",
    ".rar",
    ".7z",
)

DEFAULT_SCRAPER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _clean(name):
    raw = os.getenv(name)
    if raw is None:
        return None
    raw = str(raw).strip()
    return raw or None


def _int(name, default, minimum=None):
    raw = _clean(name)
    try:
        value = int(raw) if raw is not None else default
    except ValueError:
        value = default
    if minimum is not None and value is not None:
        value = max(value, minimum)
    return value


def _opt_int(name):
    raw = _clean(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Bot Mode, Tokens & Identity (Dual Main Bot Architecture: Public vs Testing)
# ---------------------------------------------------------------------------
def bot_mode():
    """Returns 'testing' or 'public' from BOT_MODE; if unset, 'testing' when Render's RENDER_GIT_BRANCH is 'test'."""
    mode = (_clean("BOT_MODE") or "").lower()
    if mode in ("test", "testing", "staging", "dev"):
        return "testing"
    if mode in ("public", "prod", "production", "main"):
        return "public"
    branch = (_clean("RENDER_GIT_BRANCH") or "").lower()
    if branch in ("test", "testing", "staging", "dev"):
        return "testing"
    return "public"


def is_testing_mode() -> bool:
    """Returns True when deployed as the Testing Main Bot (BOT_MODE=testing or branch=test)."""
    return bot_mode() == "testing"


def public_bot_token():
    """Token for the Public Main Bot (env PUBLIC_BOT_TOKEN ONLY - no fallback)."""
    return _clean("PUBLIC_BOT_TOKEN")


def testing_bot_token():
    """Token for the Testing Main Bot (env TESTING_BOT_TOKEN ONLY - no fallback)."""
    return _clean("TESTING_BOT_TOKEN")


def bot_token():
    """Active Main Bot token resolved dynamically based on BOT_MODE (Public vs Testing)."""
    if is_testing_mode():
        return testing_bot_token()
    return public_bot_token()


def helper_bot_tokens():
    """Helper bot tokens (env PUBLIC_HELPER_BOT_TOKENS or TESTING_HELPER_BOT_TOKENS ONLY)."""
    raw = _clean(f"{_pfx()}_HELPER_BOT_TOKENS") or ""
    return [t.strip() for t in raw.split(",") if t.strip()]


def helper_polling_enabled() -> bool:
    """Controls whether this service polls helper bots (/start deep-links & DM indexing).
    Defaults to True. Public and Testing must use DIFFERENT helper bots, otherwise Telegram
    returns 409 Conflict when both services poll the same bot."""
    raw = _clean(f"{_pfx()}_HELPER_POLLING_ENABLED")
    if raw is not None:
        return raw.lower() in ("true", "1", "yes", "on")
    return True


def bot_name():
    """Display name (env PUBLIC_BOT_NAME on Public, TESTING_BOT_NAME on Testing; no shared BOT_NAME)."""
    var = "TESTING_BOT_NAME" if is_testing_mode() else "PUBLIC_BOT_NAME"
    return _clean(var) or "Mastermind"


def community_link():
    """Community invite/channel URL (env COMMUNITY_LINK only)."""
    return _clean("COMMUNITY_LINK") or SAMPLE_COMMUNITY_LINK


def creator_id():
    """Creator Telegram user ID (env CREATOR_ID ONLY; same ID on Public and Testing).
    Raises RuntimeError when unset/invalid (no sample fallback). main.py validates this at startup."""
    cid = _opt_int("CREATOR_ID")
    if cid is None:
        raise RuntimeError("CREATOR_ID is not set (or not a number). Set it in Render / env.txt.")
    return cid


def creator_username():
    """Creator Telegram @username without '@' (env CREATOR_USERNAME)."""
    return (_clean("CREATOR_USERNAME") or "").lstrip("@")


def creator_dm_link() -> str:
    """Direct Telegram DM link to the bot Creator.
    Uses CREATOR_USERNAME if set (e.g. heyucutie), otherwise tg://user?id=<cid>."""
    un = (_clean("CREATOR_USERNAME") or "").lstrip("@").strip()
    if un:
        return f"https://t.me/{un}"
    try:
        cid = creator_id()
        if cid:
            return f"tg://user?id={cid}"
    except Exception:
        pass
    return "https://t.me/heyucutie"


def admin_ids():
    """Set of configured Admin/Creator Telegram user IDs (env ADMIN_IDS + CREATOR_ID)."""
    ids = {creator_id()}
    raw = _clean("ADMIN_IDS") or ""
    for part in raw.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            ids.add(int(part))
    return ids


def anon_admin_id():
    """Telegram's GroupAnonymousBot ID (env ANON_ADMIN_ID, default 1087968824)."""
    return _int("ANON_ADMIN_ID", 1087968824)


# ---------------------------------------------------------------------------
# Chats & Channels (Dual-Bot Aware: Public vs. Testing Separate Groups/Channels)
# ---------------------------------------------------------------------------
def _pfx():
    """Variable prefix of the running service: TESTING or PUBLIC."""
    return "TESTING" if is_testing_mode() else "PUBLIC"


def _mode_opt_int(base_names):
    """Integer chat/topic ID from PUBLIC_<NAME> or TESTING_<NAME> ONLY (no fallbacks)."""
    return _opt_int(f"{_pfx()}_{base_names}")


def search_topic_id():
    """Forum topic where members search (env PUBLIC_/TESTING_SEARCH_TOPIC_ID)."""
    return _mode_opt_int("SEARCH_TOPIC_ID")


def search_chat_id():
    """Chat that hosts the search topic AND whose invite link /search hands out.

    Derived (no variable): Public = PUBLIC_SUPPORT_CHAT_ID, Testing = TESTING_LOGGER_GROUP_ID.
    """
    return logger_group_id() if is_testing_mode() else support_chat_id()


def request_channel_id():
    """Channel where book requests are posted (env PUBLIC_/TESTING_REQUEST_CHANNEL_ID)."""
    return _mode_opt_int("REQUEST_CHANNEL_ID")


def support_chat_id():
    """Support group ID used for support quiz invites and support-only bans (env PUBLIC_/TESTING_SUPPORT_CHAT_ID)."""
    return _mode_opt_int("SUPPORT_CHAT_ID")


def storage_group_id():
    """Storage group/channel ID (env PUBLIC_/TESTING_STORAGE_GROUP_ID)."""
    return _mode_opt_int("STORAGE_GROUP_ID")


def posting_channel_id():
    """Posting channel ID where helper bots send files with auto-delete (env PUBLIC_/TESTING_POSTING_CHANNEL_ID)."""
    return _mode_opt_int("POSTING_CHANNEL_ID")


def index_channel_id():
    """Index logs channel ID (env PUBLIC_/TESTING_INDEX_CHANNEL_ID)."""
    return _mode_opt_int("INDEX_CHANNEL_ID")


def logger_group_id():
    """Logger supergroup ID (env PUBLIC_/TESTING_LOGGER_GROUP_ID)."""
    return _mode_opt_int("LOGGER_GROUP_ID")


def backup_chat_id():
    """Chat that receives database backups. Derived, no variable: it is the logger group
    (PUBLIC_/TESTING_LOGGER_GROUP_ID), so Public and Testing always use different chats."""
    return logger_group_id()


def backup_topic_id():
    """Forum topic inside the logger group that holds the pinned backup (env PUBLIC_/TESTING_BACKUP_TOPIC_ID)."""
    return _mode_opt_int("BACKUP_TOPIC_ID")


def fsub_channel_ids():
    """Optional force-subscribe channel IDs (env PUBLIC_/TESTING_FSUB_CHANNEL_IDS)."""
    raw = _clean(f"{_pfx()}_FSUB_CHANNEL_IDS") or ""
    out = []
    for part in raw.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.append(int(part))
    return out


# ---------------------------------------------------------------------------
# Log topics & intervals (Dual-Bot Aware)
# ---------------------------------------------------------------------------
def general_topic_id():
    """General forum topic ID (env PUBLIC_/TESTING_GENERAL_TOPIC_ID, default 1)."""
    val = _mode_opt_int("GENERAL_TOPIC_ID")
    return max(val, 1) if val is not None else 1


def log_topic(kind):
    """kind: USER | INDEX | GROUP | CHANNEL | REQUEST | ERROR -> int or None."""
    return _mode_opt_int(f"{kind.upper()}_LOG_TOPIC_ID")


def backup_interval_seconds():
    """Seconds between automatic database backup checks (env BACKUP_INTERVAL_SECONDS, default 300, min 60)."""
    return _int("BACKUP_INTERVAL_SECONDS", 300, 60)


def auto_delete_seconds():
    """Seconds before helper-bot file posts in PUBLIC_/TESTING_POSTING_CHANNEL_ID are auto-deleted."""
    return _int("AUTO_DELETE_SECONDS", 300, 10)


# ---------------------------------------------------------------------------
# Supported File Formats (Ebooks, Audiobooks & Archives)
# ---------------------------------------------------------------------------
def _parse_ext_set(env_name, defaults):
    raw = _clean(env_name)
    if not raw:
        return set(defaults)
    items = set()
    for part in raw.split(","):
        ext = part.strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        items.add(ext)
    return items or set(defaults)


def supported_ebook_extensions():
    """Supported ebook extensions: .epub, .pdf, .azw, .azw3, .mobi, .cbz, .cbr, .djvu, .fb2, .txt, .rtf."""
    return _parse_ext_set("SUPPORTED_EBOOK_EXTENSIONS", DEFAULT_EBOOK_EXTENSIONS)


def supported_audiobook_extensions():
    """Supported audiobook extensions: .mp3, .m4b, .m4a, .aax, .aa, .flac, .wav, .ogg, .opus."""
    return _parse_ext_set("SUPPORTED_AUDIOBOOK_EXTENSIONS", DEFAULT_AUDIOBOOK_EXTENSIONS)


def supported_archive_extensions():
    """Supported archive extensions for packed books/audiobooks: .zip, .rar, .7z."""
    return _parse_ext_set("SUPPORTED_ARCHIVE_EXTENSIONS", DEFAULT_ARCHIVE_EXTENSIONS)


def supported_extensions():
    """Union of all supported ebook, audiobook, and archive extensions."""
    return (
        supported_ebook_extensions()
        | supported_audiobook_extensions()
        | supported_archive_extensions()
    )


# ---------------------------------------------------------------------------
# Search, Quotas & Referrals
# ---------------------------------------------------------------------------
def items_per_page():
    return _int("ITEMS_PER_PAGE", 10, 1)


def default_search_quota():
    return _int("DEFAULT_SEARCH_QUOTA", 10, 0)


def default_request_quota():
    return _int("DEFAULT_REQUEST_QUOTA", 10, 0)


def promoter_quota():
    return _int("PROMOTER_QUOTA_DEFAULT", 20, 0)


def volunteer_quota():
    return _int("VOLUNTEER_QUOTA_DEFAULT", 30, 0)


def moderator_quota():
    return _int("MODERATOR_QUOTA_DEFAULT", 40, 0)


def unlimited_quota_value():
    return _int("UNLIMITED_QUOTA_VALUE", 999999, 1000)


def referral_search_bonus():
    return _int("REFERRAL_SEARCH_BONUS", 10, 0)


def referral_request_bonus():
    return _int("REFERRAL_REQUEST_BONUS", 10, 0)


def referral_bonus_label():
    """e.g. '+10 searches & requests' (or '+10 searches & +5 requests')."""
    s, r = referral_search_bonus(), referral_request_bonus()
    if s == r:
        return f"+{s} searches & requests"
    return f"+{s} searches & +{r} requests"


def referral_earned_label(total_invites: int):
    """Formats cumulative referral bonus earned for `total_invites` invites."""
    s = total_invites * referral_search_bonus()
    r = total_invites * referral_request_bonus()
    if s == r:
        return f"+{s} Searches & Requests"
    return f"+{s} Searches & +{r} Requests"


# ---------------------------------------------------------------------------
# Indexing, Scraping, Paths & Runtime Limits
# ---------------------------------------------------------------------------
def max_index_batch():
    return _int("MAX_INDEX_BATCH", 10, 1)


def index_sleep_seconds():
    return _int("INDEX_SLEEP_SECONDS", 10, 0)


def max_log_lines():
    return _int("MAX_LOG_LINES", 1000, 1)


def log_buffer_maxlen():
    return _int("LOG_BUFFER_MAXLEN", 2000, 100)


def env_file_path():
    return _clean("ENV_FILE_PATH") or "env.txt"


def port():
    return _int("PORT", 8080, 1)


def db_dir():
    return _clean("DB_DIR") or "database"


def config_db_path():
    return _clean("CONFIG_DB_PATH") or os.path.join(db_dir(), "config.db")


def files_db_path():
    return _clean("FILES_DB_PATH") or os.path.join(db_dir(), "files.db")


def users_db_path():
    return _clean("USERS_DB_PATH") or "mastermind_users.db"


def backup_filename():
    default = "mastermind_test_backup.zip" if is_testing_mode() else "mastermind_backup.zip"
    return _clean(f"{_pfx()}_BACKUP_FILENAME") or default


def max_upload_bytes():
    return _int("MAX_UPLOAD_BYTES", 49 * 1024 * 1024, 1024 * 1024)


def max_download_bytes():
    return _int("MAX_DOWNLOAD_BYTES", 20 * 1024 * 1024, 1024 * 1024)


def goodreads_base_url():
    return (_clean("GOODREADS_BASE_URL") or "https://www.goodreads.com").rstrip("/")


def goodreads_cache_max():
    return _int("GOODREADS_CACHE_MAX", 500, 10)


def scraper_user_agent():
    return _clean("SCRAPER_USER_AGENT") or DEFAULT_SCRAPER_USER_AGENT
