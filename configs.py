"""Central configuration for the Mastermind bot.

Everything here is read from environment variables (Render env or env.txt)
LAZILY, i.e. when the function is called, because main.load_env() runs after
modules are imported.

Intentionally NOT configurable here (kept as-is on purpose):
  * Owner ID           - hardcoded in the modules that use it
  * Community link     - handled where it is used
  * General topic ID   - always 1

Chat IDs and topic IDs have NO default values: if the env variable is missing
the feature that needs it is skipped / reports "not configured".
"""
import os


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
    if minimum is not None:
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


# ---- Branding -------------------------------------------------------------
def bot_name():
    """Display name used in user-facing texts (env BOT_NAME, default Mastermind)."""
    return _clean("BOT_NAME") or "Mastermind"


# ---- Chats (env, no defaults) ---------------------------------------------
def search_group_id():
    """Group used for single-use search-group invite links (env SEARCH_GROUP_ID)."""
    return _opt_int("SEARCH_GROUP_ID")


def request_channel_id():
    """Channel where book requests are posted (env REQUEST_CHANNEL_ID)."""
    return _opt_int("REQUEST_CHANNEL_ID")


def support_chat_id():
    """Support group ID used for support quiz invites and support-only bans (env SUPPORT_CHAT_ID)."""
    return _opt_int("SUPPORT_CHAT_ID")


def storage_group_id():
    """Storage group/channel ID (env STORAGE_GROUP_ID or STORAGE_CHANNEL_ID)."""
    return _opt_int_any(("STORAGE_GROUP_ID", "STORAGE_CHANNEL_ID"))


def logger_group_id():
    """Logger supergroup ID (env LOGGER_GROUP_ID)."""
    return _opt_int("LOGGER_GROUP_ID")


def backup_chat_id():
    """Chat ID for Telegram database backups (BACKUP_CHAT_ID -> INDEX_CHANNEL_ID -> LOGGER_GROUP_ID)."""
    return _opt_int_any(("BACKUP_CHAT_ID", "INDEX_CHANNEL_ID", "LOGGER_GROUP_ID"))


def backup_interval_seconds():
    """Seconds between automatic database backup checks (env BACKUP_INTERVAL_SECONDS, default 300, min 60)."""
    return _int("BACKUP_INTERVAL_SECONDS", 300, 60)


# ---- Log topics (env <KIND>_LOG_TOPIC_ID, no defaults) --------------------
def log_topic(kind):
    """kind: USER | INDEX | GROUP | CHANNEL | REQUEST | ERROR  -> int or None."""
    return _opt_int(f"{kind.upper()}_LOG_TOPIC_ID")


# ---- Search ---------------------------------------------------------------
def items_per_page():
    return _int("ITEMS_PER_PAGE", 10, 1)


# ---- Quotas & referrals ---------------------------------------------------
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


# ---- Indexing / logs ------------------------------------------------------
def max_index_batch():
    return _int("MAX_INDEX_BATCH", 10, 1)


def index_sleep_seconds():
    return _int("INDEX_SLEEP_SECONDS", 10, 0)


def max_log_lines():
    return _int("MAX_LOG_LINES", 1000, 1)
