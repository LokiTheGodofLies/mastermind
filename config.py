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
SAMPLE_OWNER_ID = 123456789
SAMPLE_ADMIN_IDS = "123456789,987654321"

SAMPLE_STORAGE_GROUP_ID = -1001111111111
SAMPLE_POSTING_CHANNEL_ID = -1002222222222
SAMPLE_LOGGER_GROUP_ID = -1003333333333
SAMPLE_INDEX_CHANNEL_ID = -1004444444444
SAMPLE_REQUEST_CHANNEL_ID = -1005555555555
SAMPLE_SUPPORT_CHAT_ID = -1006666666666
SAMPLE_SEARCH_GROUP_ID = -1007777777777
SAMPLE_BACKUP_CHAT_ID = -1003333333333

SAMPLE_USER_LOG_TOPIC_ID = 2
SAMPLE_INDEX_LOG_TOPIC_ID = 3
SAMPLE_GROUP_LOG_TOPIC_ID = 4
SAMPLE_CHANNEL_LOG_TOPIC_ID = 5
SAMPLE_REQUEST_LOG_TOPIC_ID = 6
SAMPLE_ERROR_LOG_TOPIC_ID = 7

SAMPLE_COMMUNITY_LINK = "https://t.me/sample_mastermind_community"

# Default supported formats
DEFAULT_EBOOK_EXTENSIONS = (
    ".epub",
    ".pdf",
    ".azw",
    ".azw3",
    ".mobi",
    ".cbz",
    ".cbr",
)

DEFAULT_AUDIOBOOK_EXTENSIONS = (
    ".mp3",
    ".m4b",
    ".aax",
    ".aa",
    ".flac",
    ".wav",
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


def _clean_any(names):
    for name in names:
        val = _clean(name)
        if val is not None:
            return val
    return None


def _int(name, default, minimum=None):
    raw = _clean(name)
    try:
        value = int(raw) if raw is not None else default
    except ValueError:
        value = default
    if minimum is not None and value is not None:
        value = max(value, minimum)
    return value


def _int_any(names, default, minimum=None):
    """First env name that is set wins (lets Render use either naming)."""
    for name in names:
        if _clean(name) is not None:
            return _int(name, default, minimum)
    return default if minimum is None else max(default, minimum)


def _opt_int(name):
    raw = _clean(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _opt_int_any(names):
    for name in names:
        val = _opt_int(name)
        if val is not None:
            return val
    return None


# ---------------------------------------------------------------------------
# Bot Mode, Tokens & Identity (Dual Main Bot Architecture: Public vs Testing)
# ---------------------------------------------------------------------------
def bot_mode():
    """Returns 'testing' or 'public'. Auto-detects 'testing' if RENDER_GIT_BRANCH/GIT_BRANCH is 'test'."""
    mode = (_clean_any(("BOT_MODE", "DEPLOY_ENV", "ENVIRONMENT")) or "").lower()
    if mode in ("test", "testing", "staging", "dev"):
        return "testing"
    if mode in ("public", "prod", "production", "main"):
        return "public"
    branch = (_clean_any(("RENDER_GIT_BRANCH", "GIT_BRANCH", "BRANCH")) or "").lower()
    if branch in ("test", "testing", "staging", "dev"):
        return "testing"
    return "public"


def is_testing_mode() -> bool:
    """Returns True when deployed as the Testing Main Bot (BOT_MODE=testing or branch=test)."""
    return bot_mode() == "testing"


def public_bot_token():
    """Token for the Public Main Bot (env PUBLIC_BOT_TOKEN or TELEGRAM_BOT_TOKEN)."""
    return _clean_any(("PUBLIC_BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "BOT_TOKEN"))


def testing_bot_token():
    """Token for the Testing Main Bot (env TESTING_BOT_TOKEN or TEST_BOT_TOKEN)."""
    return _clean_any(("TESTING_BOT_TOKEN", "TEST_BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "BOT_TOKEN"))


def bot_token():
    """Active Main Bot token resolved dynamically based on BOT_MODE (Public vs Testing)."""
    if is_testing_mode():
        return testing_bot_token()
    return public_bot_token()


def helper_bot_tokens():
    """List of helper bot tokens (supports TESTING_HELPER_BOT_TOKENS override in testing mode)."""
    if is_testing_mode():
        raw = _clean_any(("TESTING_HELPER_BOT_TOKENS", "TEST_HELPER_BOT_TOKENS", "HELPER_BOT_TOKENS")) or ""
    else:
        raw = _clean_any(("PUBLIC_HELPER_BOT_TOKENS", "HELPER_BOT_TOKENS")) or ""
    return [t.strip() for t in raw.split(",") if t.strip()]


def helper_polling_enabled() -> bool:
    """Controls whether this service polls helper bots (/start deep-links & DM indexing).
    Defaults to True in Public mode and False in Testing mode so two Render services sharing
    the same HELPER_BOT_TOKENS never collide with Telegram 409 Conflict errors."""
    raw = _clean_any(("HELPER_POLLING_ENABLED", "ENABLE_HELPER_POLLING"))
    if raw is not None:
        return raw.lower() in ("true", "1", "yes", "on")
    if is_testing_mode():
        return bool(_clean_any(("TESTING_HELPER_BOT_TOKENS", "TEST_HELPER_BOT_TOKENS")))
    return True


def bot_name():
    """Display name used in user-facing texts (env BOT_NAME, default Mastermind)."""
    return _clean("BOT_NAME") or "Mastermind"


def community_link():
    """Community invite/channel URL (env COMMUNITY_LINK or COMMUNITY_URL)."""
    return _clean_any(("COMMUNITY_LINK", "COMMUNITY_URL")) or SAMPLE_COMMUNITY_LINK


def god_id():
    """Primary bot GOD Telegram user ID (env GOD_ID or OWNER_ID, fallback first ADMIN_IDS or sample)."""
    gid = _opt_int("GOD_ID") or _opt_int("OWNER_ID")
    if gid is not None:
        return gid
    raw_admins = _clean("ADMIN_IDS") or ""
    for part in raw_admins.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            return int(part)
    return SAMPLE_OWNER_ID


def owner_id():
    """Alias for god_id for backward compatibility."""
    return god_id()


def admin_ids():
    """Set of configured Admin/GOD Telegram user IDs (env ADMIN_IDS + GOD_ID/OWNER_ID)."""
    ids = set()
    oid = god_id()
    if oid is not None:
        ids.add(oid)
    raw = _clean("ADMIN_IDS") or ""
    for part in raw.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            ids.add(int(part))
    if not ids:
        ids.add(SAMPLE_OWNER_ID)
    return ids


def anon_admin_id():
    """Telegram's GroupAnonymousBot ID (env ANON_ADMIN_ID, default 1087968824)."""
    return _int("ANON_ADMIN_ID", 1087968824)


# ---------------------------------------------------------------------------
# Chats & Channels (Dual-Bot Aware: Public vs. Testing Separate Groups/Channels)
# ---------------------------------------------------------------------------
def _mode_opt_int(base_names):
    """Resolves integer chat/topic ID with TESTING_* or PUBLIC_* priority based on BOT_MODE."""
    if isinstance(base_names, str):
        base_names = (base_names,)
    if is_testing_mode():
        prefixed = tuple(f"TESTING_{n}" for n in base_names) + tuple(f"TEST_{n}" for n in base_names)
    else:
        prefixed = tuple(f"PUBLIC_{n}" for n in base_names)
    return _opt_int_any(prefixed + tuple(base_names))


def search_group_id():
    """Group used for single-use search-group invite links (env SEARCH_GROUP_ID / TESTING_SEARCH_GROUP_ID)."""
    return _mode_opt_int("SEARCH_GROUP_ID")


def request_channel_id():
    """Channel where book requests are posted (env REQUEST_CHANNEL_ID / TESTING_REQUEST_CHANNEL_ID)."""
    return _mode_opt_int("REQUEST_CHANNEL_ID")


def support_chat_id():
    """Support group ID used for support quiz invites and support-only bans (env SUPPORT_CHAT_ID / TESTING_SUPPORT_CHAT_ID)."""
    return _mode_opt_int("SUPPORT_CHAT_ID")


def storage_group_id():
    """Storage group/channel ID (env STORAGE_GROUP_ID / TESTING_STORAGE_GROUP_ID)."""
    return _mode_opt_int(("STORAGE_GROUP_ID", "STORAGE_CHANNEL_ID"))


def posting_channel_id():
    """Posting channel ID where helper bots send files with auto-delete (env POSTING_CHANNEL_ID / TESTING_POSTING_CHANNEL_ID)."""
    return _mode_opt_int(("POSTING_CHANNEL_ID", "INDEX_CHANNEL_ID"))


def index_channel_id():
    """Index logs channel ID (env INDEX_CHANNEL_ID / TESTING_INDEX_CHANNEL_ID)."""
    return _mode_opt_int("INDEX_CHANNEL_ID")


def logger_group_id():
    """Logger supergroup ID (env LOGGER_GROUP_ID / TESTING_LOGGER_GROUP_ID)."""
    return _mode_opt_int("LOGGER_GROUP_ID")


def backup_chat_id():
    """Chat ID for Telegram database backups (BACKUP_CHAT_ID -> INDEX_CHANNEL_ID -> LOGGER_GROUP_ID)."""
    return _mode_opt_int(("BACKUP_CHAT_ID", "INDEX_CHANNEL_ID", "LOGGER_GROUP_ID"))


def fsub_channel_ids():
    """Optional force-subscribe channel IDs (env FSUB_CHANNEL_IDS or TESTING_FSUB_CHANNEL_IDS)."""
    if is_testing_mode():
        raw = _clean_any(("TESTING_FSUB_CHANNEL_IDS", "TEST_FSUB_CHANNEL_IDS", "FSUB_CHANNEL_IDS", "FSUB_CHANNEL_ID")) or ""
    else:
        raw = _clean_any(("PUBLIC_FSUB_CHANNEL_IDS", "FSUB_CHANNEL_IDS", "FSUB_CHANNEL_ID")) or ""
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
    """General forum topic ID (env GENERAL_TOPIC_ID / TESTING_GENERAL_TOPIC_ID, default 1)."""
    val = _mode_opt_int("GENERAL_TOPIC_ID")
    return max(val, 1) if val is not None else 1


def log_topic(kind):
    """kind: USER | INDEX | GROUP | CHANNEL | REQUEST | ERROR -> int or None."""
    return _mode_opt_int(f"{kind.upper()}_LOG_TOPIC_ID")


def backup_interval_seconds():
    """Seconds between automatic database backup checks (env BACKUP_INTERVAL_SECONDS, default 300, min 60)."""
    return _int("BACKUP_INTERVAL_SECONDS", 300, 60)


def auto_delete_seconds():
    """Seconds before helper-bot file posts in POSTING_CHANNEL_ID are auto-deleted."""
    return _int_any(("AUTO_DELETE_SECONDS", "FILE_AUTO_DELETE_SECONDS", "FILE_DELETE_AFTER_SECONDS"), 300, 10)


# ---------------------------------------------------------------------------
# Supported File Formats (Ebooks & Audiobooks)
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
    """Supported ebook extensions: .epub, .pdf, .azw, .azw3, .mobi, .cbz, .cbr."""
    return _parse_ext_set("SUPPORTED_EBOOK_EXTENSIONS", DEFAULT_EBOOK_EXTENSIONS)


def supported_audiobook_extensions():
    """Supported audiobook extensions: .mp3, .m4b, .aax, .aa, .flac, .wav."""
    return _parse_ext_set("SUPPORTED_AUDIOBOOK_EXTENSIONS", DEFAULT_AUDIOBOOK_EXTENSIONS)


def supported_extensions():
    """Union of all supported ebook and audiobook extensions."""
    return supported_ebook_extensions() | supported_audiobook_extensions()


# ---------------------------------------------------------------------------
# Search, Quotas & Referrals
# ---------------------------------------------------------------------------
def items_per_page():
    return _int("ITEMS_PER_PAGE", 10, 1)


def default_search_quota():
    return _int_any(("DEFAULT_SEARCH_QUOTA", "SEARCH_QUOTA_DEFAULT"), 10, 0)


def default_request_quota():
    return _int_any(("DEFAULT_REQUEST_QUOTA", "REQUEST_QUOTA_DEFAULT"), 10, 0)


def promoter_quota():
    return _int_any(("PROMOTER_QUOTA_DEFAULT", "DEFAULT_PROMOTER_QUOTA"), 20, 0)


def volunteer_quota():
    return _int_any(("VOLUNTEER_QUOTA_DEFAULT", "DEFAULT_VOLUNTEER_QUOTA"), 30, 0)


def moderator_quota():
    return _int_any(("MODERATOR_QUOTA_DEFAULT", "DEFAULT_MODERATOR_QUOTA"), 40, 0)


def unlimited_quota_value():
    return _int("UNLIMITED_QUOTA_VALUE", 999999, 1000)


def referral_search_bonus():
    return _int_any(("REFERRAL_SEARCH_BONUS", "REFERRAL_BONUS_SEARCH"), 10, 0)


def referral_request_bonus():
    return _int_any(("REFERRAL_REQUEST_BONUS", "REFERRAL_BONUS_REQUEST"), 10, 0)


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
    if is_testing_mode():
        return _clean_any(("TESTING_BACKUP_FILENAME", "TEST_BACKUP_FILENAME", "BACKUP_FILENAME")) or "mastermind_test_backup.zip"
    return _clean_any(("PUBLIC_BACKUP_FILENAME", "BACKUP_FILENAME")) or "mastermind_backup.zip"


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
