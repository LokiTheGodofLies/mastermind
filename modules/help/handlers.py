import html
from config import bot_name
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import ContextTypes
except ImportError:
    class InlineKeyboardButton:
        def __init__(self, text, callback_data=None, url=None, api_kwargs=None):
            self.text = text
            self.callback_data = callback_data
            self.url = url
            self.api_kwargs = api_kwargs or {}
    class InlineKeyboardMarkup:
        def __init__(self, inline_keyboard):
            self.inline_keyboard = inline_keyboard
    Update = object
    class ContextTypes:
        DEFAULT_TYPE = object

from modules.database.user_db import get_user_role_db, is_admin_or_creator, is_creator
from modules.utility.rich_ui import styled_button, tg_button_html, tg_button_row_html


def _help_card(header: str, rows: list[tuple[str, str]], footer: str = "") -> str:
    """Formats a command documentation card with a structured <table striped>."""
    tr_html = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    out = f"{header}\n\n<table striped><tr><th>Field</th><th>Details</th></tr>{tr_html}</table>"
    if footer:
        out += f"\n\n{footer}"
    return out


# ---------------------------------------------------------------------------
# Individual Command & Feature Documentation Cards (Bot API 10.3 Rich UI)
# Touch-to-copy format applied ONLY to command names, not arguments/queries.
# Every card uses <table striped> for structured data.
# ---------------------------------------------------------------------------
COMMAND_DETAILS = {
    # =======================================================================
    # 👤 USER COMMANDS & GUIDES
    # =======================================================================
    "start": {
        "title": "🚀 start",
        "summary": "Launch bot & main menu",
        "category": "user",
        "text": _help_card(
            "🚀 <b>Command Documentation —</b> <code>/start</code>",
            [
                ("🚀 <b>Command</b>", "<code>/start</code>"),
                ("🔓 <b>Access</b>", "All Members"),
                ("📝 <b>Purpose</b>", "Opens main menu &amp; initializes daily quota"),
                ("🔗 <b>Deep Links</b>", "Handles book downloads &amp; referrals"),
                ("💡 <b>Syntax 1</b>", "<code>/start</code>"),
                ("💡 <b>Syntax 2</b>", "<code>/start</code> dl_&lt;file_id&gt;"),
            ],
            "✨ <i>Tap any green Download button in search results to receive files instantly!</i>",
        ),
    },
    "search": {
        "title": "🔍 search",
        "summary": "Search ebooks & audiobooks",
        "category": "user",
        "text": _help_card(
            "🔍 <b>Command Documentation —</b> <code>/search</code>",
            [
                ("🔍 <b>Command</b>", "<code>/search</code>"),
                ("🔓 <b>Access</b>", "All Members (Uses 1 Search Quota)"),
                ("📝 <b>Purpose</b>", "Searches titles, authors &amp; series"),
                ("💡 <b>Syntax</b>", "<code>/search</code> &lt;title or author&gt;"),
                ("📌 <b>Example 1</b>", "<code>/search</code> Percy Jackson"),
                ("📌 <b>Example 2</b>", "<code>/search</code> Colleen Hoover"),
                ("🎛 <b>Filters</b>", "📚 Ebooks | 🎧 Audio | 📨 Send All"),
            ],
            "✨ <i>Search results are displayed in a structured table with one-tap Download buttons!</i>",
        ),
    },
    "request": {
        "title": "📥 request",
        "summary": "Request missing books",
        "category": "user",
        "text": _help_card(
            "📥 <b>Command Documentation —</b> <code>/request</code>",
            [
                ("📥 <b>Command</b>", "<code>/request</code> (alias: <code>/req</code>)"),
                ("🔓 <b>Access</b>", "All Members (Uses 1 Request Quota)"),
                ("📝 <b>Purpose</b>", "Requests missing books via Goodreads"),
                ("💡 <b>Syntax</b>", "<code>/request</code> &lt;title and author&gt;"),
                ("📌 <b>Example 1</b>", "<code>/request</code> Fourth Wing Rebecca Yarros"),
                ("📌 <b>Example 2</b>", "<code>/request</code> King of Wrath Ana Huang"),
            ],
            "✨ <i>Moderators review requests in the Request Channel and update live status buttons!</i>",
        ),
    },
    "quota": {
        "title": "📊 quota",
        "summary": "Check daily search/request balance",
        "category": "user",
        "text": _help_card(
            "📊 <b>Command Documentation —</b> <code>/quota</code>",
            [
                ("📊 <b>Command</b>", "<code>/quota</code>"),
                ("🕒 <b>Reset Time</b>", "Daily at Midnight IST"),
                ("👤 <b>Normal User</b>", "<code>10 searches &amp; 10 requests</code>"),
                ("📣 <b>Promoter</b>", "<code>20 searches &amp; 20 requests</code>"),
                ("🤝 <b>Volunteer</b>", "<code>30 searches &amp; 30 requests</code>"),
                ("🛡️ <b>Moderator</b>", "<code>40 searches &amp; 40 requests</code>"),
                ("⚔️ <b>Admin / Creator</b>", "<code>Unlimited</code>"),
            ],
            "✨ <i>Use <code>/refer</code> to invite friends and earn permanent bonus quota!</i>",
        ),
    },
    "refer": {
        "title": "🔗 refer",
        "summary": "Invite friends & earn bonus quota",
        "category": "user",
        "text": _help_card(
            "🔗 <b>Command Documentation —</b> <code>/refer</code> &amp; <code>/myreferrals</code>",
            [
                ("🔗 <b>Invite Link</b>", "<code>/refer</code> (or <code>/ref</code>)"),
                ("📋 <b>Invite Table</b>", "<code>/myreferrals</code>"),
                ("🎁 <b>Reward</b>", "<code>+10 searches &amp; +10 requests</code>"),
                ("👥 <b>Who Earns</b>", "Both you and your invited friend"),
                ("📤 <b>Actions</b>", "Copy Invite Link &amp; Share Link"),
            ],
            "✨ <i><code>/myreferrals</code> displays a paginated table of everyone you invited!</i>",
        ),
    },
    "support": {
        "title": "💬 support",
        "summary": "Join community support group",
        "category": "user",
        "text": _help_card(
            "💬 <b>Command Documentation —</b> <code>/support</code>",
            [
                ("💬 <b>Command</b>", "<code>/support</code>"),
                ("🔓 <b>Access</b>", "All Members"),
                ("📝 <b>Purpose</b>", "10-question screening quiz for support"),
                ("🎟 <b>Output</b>", "Single-use Support Group invite link"),
                ("💡 <b>Syntax</b>", "<code>/support</code>"),
            ],
        ),
    },
    "stats": {
        "title": "📈 stats",
        "summary": "Live library & user statistics",
        "category": "user",
        "text": _help_card(
            "📈 <b>Command Documentation —</b> <code>/stats</code>",
            [
                ("📈 <b>Command</b>", "<code>/stats</code>"),
                ("📚 <b>Library Table</b>", "Total Files, Ebooks &amp; Audiobooks"),
                ("👥 <b>Community Table</b>", "Users, Groups &amp; Channels"),
                ("🖥 <b>Admin Table</b>", "Role, DB Size, RAM &amp; API Ping"),
                ("💡 <b>Syntax</b>", "<code>/stats</code>"),
            ],
        ),
    },
    "id": {
        "title": "🆔 id",
        "summary": "Lookup User, Chat & Topic IDs",
        "category": "user",
        "text": _help_card(
            "🆔 <b>Command Documentation —</b> <code>/id</code>",
            [
                ("🆔 <b>Command</b>", "<code>/id</code>"),
                ("📝 <b>Purpose</b>", "Displays User, Chat &amp; Topic IDs in table"),
                ("💡 <b>Syntax 1</b>", "<code>/id</code> (current chat &amp; user)"),
                ("💡 <b>Syntax 2</b>", "<code>/id</code> @username"),
                ("💡 <b>Syntax 3</b>", "Reply to any message with <code>/id</code>"),
                ("📢 <b>Channel Mode</b>", "Omits user fields when anonymous"),
            ],
        ),
    },
    "rosters": {
        "title": "👥 rosters",
        "summary": "View Admin, Mod, Vol & Promo lists",
        "category": "user",
        "text": _help_card(
            "👥 <b>Community Roster Commands</b>",
            [
                ("⚔️ <b>Admins</b>", "<code>/admins</code> — Creators &amp; Admins"),
                ("🛡️ <b>Moderators</b>", "<code>/moderators</code> (or <code>/mods</code>)"),
                ("🤝 <b>Volunteers</b>", "<code>/volunteers</code> (or <code>/vols</code>)"),
                ("📣 <b>Promoters</b>", "<code>/promoters</code> (or <code>/promos</code>)"),
                ("📊 <b>Format</b>", "Structured table + Profile/Copy buttons"),
            ],
        ),
    },
    "delivery": {
        "title": "📦 delivery",
        "summary": "Dual PM & Channel file delivery",
        "category": "user",
        "text": _help_card(
            "📦 <b>Dual File Delivery System</b>",
            [
                ("🤖 <b>Route 1: PM</b>", "Direct delivery via Helper Bots"),
                ("📢 <b>Route 2: Channel</b>", "Mirror copy in Posting Channel"),
                ("⏱ <b>Auto-Delete</b>", "5 minutes (300 seconds)"),
                ("📨 <b>Send All</b>", "Delivers page + 1 combined PM table"),
                ("💾 <b>Tip</b>", "Forward files to Saved Messages!"),
            ],
        ),
    },
    "roles": {
        "title": "👥 roles",
        "summary": "6-tier role hierarchy & quotas",
        "category": "user",
        "text": (
            "👥 <b>Community User Roles &amp; Privileges</b>\n\n"
            "<table striped>"
            "<tr><th>Tier</th><th>Daily Quota</th><th>Privileges</th></tr>"
            "<tr><td>👤 <b>Normal User</b></td><td>10 / 10</td><td>Search, Request, Quota, Refer</td></tr>"
            "<tr><td>📣 <b>Promoter</b></td><td>20 / 20</td><td>Community promotion tier</td></tr>"
            "<tr><td>🤝 <b>Volunteer</b></td><td>30 / 30</td><td>Direct Helper Bot DM indexing</td></tr>"
            "<tr><td>🛡️ <b>Moderator</b></td><td>40 / 40</td><td>Direct indexing + Request status</td></tr>"
            "<tr><td>⚔️ <b>Administrator</b></td><td>Unlimited</td><td>Batch /index, /broadcast, /ban</td></tr>"
            "<tr><td>👑 <b>Creator</b></td><td>Unlimited</td><td>/addadmin, /update, /publish, DB</td></tr>"
            "</table>"
        ),
    },

    # =======================================================================
    # 🤝 VOLUNTEER COMMANDS & GUIDES
    # =======================================================================
    "vol_privileges": {
        "title": "🤝 vol_privileges",
        "summary": "Volunteer quota & direct indexing",
        "category": "volunteer",
        "text": _help_card(
            "🤝 <b>Volunteer Operational Privileges</b>",
            [
                ("📊 <b>Daily Quota</b>", "<code>30 searches &amp; 30 requests</code>"),
                ("📥 <b>Direct Indexing</b>", "Send files to Helper Bot DMs"),
                ("📚 <b>Supported Types</b>", "Ebooks, Audiobooks &amp; Archives"),
                ("✅ <b>Verification</b>", "3-Stage Self-Healing Pipeline"),
                ("🪵 <b>Audit Logging</b>", "Table cards to Topic &amp; Channel"),
            ],
        ),
    },
    "vol_indexing": {
        "title": "📚 vol_indexing",
        "summary": "How to index via Helper Bot DMs",
        "category": "volunteer",
        "text": _help_card(
            "📚 <b>Volunteer Helper Bot Indexing Guide</b>",
            [
                ("1️⃣ <b>Step 1</b>", "Open DM with any Helper Bot"),
                ("2️⃣ <b>Step 2</b>", "Send or forward book/audio/archive"),
                ("📖 <b>Ebook Formats</b>", "<code>.epub .pdf .mobi .azw3 .cbz .fb2</code>"),
                ("🎧 <b>Audio Formats</b>", "<code>.m4b .mp3 .m4a .flac .ogg .opus</code>"),
                ("📦 <b>Archives</b>", "<code>.zip .rar .7z</code>"),
                ("3️⃣ <b>Step 3</b>", "Auto-enriched &amp; stored with table log"),
            ],
        ),
    },
    "vol_notice": {
        "title": "⚠️ vol_notice",
        "summary": "Batch /index access notice",
        "category": "volunteer",
        "text": _help_card(
            "⚠️ <b>Index Command Notice for Volunteers</b>",
            [
                ("🔒 <b>Batch /index</b>", "Reserved for Admins &amp; Creator"),
                ("🤝 <b>Volunteer Route</b>", "Upload directly in Helper Bot DMs"),
                ("⚡ <b>Approval</b>", "Pre-approved (no admin wait)"),
            ],
        ),
    },

    # =======================================================================
    # 🛡️ MODERATOR COMMANDS & GUIDES
    # =======================================================================
    "mod_privileges": {
        "title": "⚖️ mod_privileges",
        "summary": "Moderator quota & permissions",
        "category": "moderator",
        "text": _help_card(
            "🛡️ <b>Moderator Operational Privileges</b>",
            [
                ("📊 <b>Daily Quota</b>", "<code>40 searches &amp; 40 requests</code>"),
                ("📋 <b>Request Control</b>", "Update Request Channel status"),
                ("🤖 <b>Direct Indexing</b>", "Pre-approved via Helper Bot DMs"),
            ],
        ),
    },
    "mod_requests": {
        "title": "📋 mod_requests",
        "summary": "Manage Request Channel statuses",
        "category": "moderator",
        "text": _help_card(
            "📋 <b>Request Status Management</b>",
            [
                ("⏳ <b>In Progress</b>", "Request is actively being sourced"),
                ("✅ <b>Completed</b>", "Book indexed into the library"),
                ("❌ <b>Rejected</b>", "Request cannot be fulfilled"),
                ("📍 <b>Where</b>", "Request Channel &amp; Request Log Topic"),
            ],
        ),
    },
    "mod_indexing": {
        "title": "🤖 mod_indexing",
        "summary": "Direct Helper Bot DM indexing",
        "category": "moderator",
        "text": _help_card(
            "🤖 <b>Moderator Direct Indexing Guide</b>",
            [
                ("📥 <b>Upload Route</b>", "Send files to any Helper Bot DM"),
                ("🌐 <b>Enrichment</b>", "8-site book/audiobook waterfall"),
                ("🪵 <b>Topic Log</b>", "Full 3-Stage Table Audit Card"),
                ("📢 <b>Channel Log</b>", "Clean Table Library Card"),
            ],
        ),
    },
    "mod_notice": {
        "title": "⚠️ mod_notice",
        "summary": "Batch /index access notice",
        "category": "moderator",
        "text": _help_card(
            "⚠️ <b>Batch /index Command Access Notice</b>",
            [
                ("🔒 <b>Batch /index</b>", "Exclusive to Admins &amp; Creator"),
                ("🛡️ <b>Moderator Route</b>", "Direct indexing via Helper Bot DMs"),
            ],
        ),
    },

    # =======================================================================
    # ⚔️ ADMINISTRATOR COMMANDS
    # =======================================================================
    "checkhelpers": {
        "title": "🤖 checkhelpers",
        "summary": "Audit Main & Helper Bot permissions",
        "category": "admin",
        "text": _help_card(
            "🤖 <b>Command Documentation —</b> <code>/checkhelpers</code>",
            [
                ("🤖 <b>Command</b>", "<code>/checkhelpers</code> (or <code>/helpers</code>)"),
                ("📦 <b>Storage Group</b>", "Verifies membership &amp; file access"),
                ("📢 <b>Posting Channel</b>", "Verifies Admin + Post &amp; Delete"),
                ("📥 <b>Index Channel</b>", "Verifies Admin + Post Messages"),
                ("🪵 <b>Logger Group</b>", "Verifies membership for log topics"),
            ],
        ),
    },
    "index": {
        "title": "📚 index",
        "summary": "Batch channel/group indexing",
        "category": "admin",
        "text": _help_card(
            "📚 <b>Command Documentation —</b> <code>/index</code>",
            [
                ("📚 <b>Command</b>", "<code>/index</code>"),
                ("🔒 <b>Access</b>", "Administrators &amp; Creator"),
                ("⚙️ <b>Live Controls</b>", "Table progress + Pause/Resume/Cancel"),
                ("♻️ <b>Persistence</b>", "Auto-resumes unfinished jobs on restart"),
                ("💡 <b>Syntax 1</b>", "<code>/index</code> (inside source channel)"),
                ("💡 <b>Syntax 2</b>", "<code>/index</code> &lt;first_link&gt; &lt;last_link&gt;"),
                ("💡 <b>Syntax 3</b>", "<code>/index</code> (in PM for setup wizard)"),
            ],
        ),
    },
    "ongoing": {
        "title": "📋 ongoing",
        "summary": "Fleet indexing tasks dashboard",
        "category": "admin",
        "text": _help_card(
            "📋 <b>Command Documentation —</b> <code>/ongoing</code>",
            [
                ("📋 <b>Command</b>", "<code>/ongoing</code> (<code>/tasks</code>)"),
                ("🔒 <b>Access</b>", "Administrators &amp; Creator"),
                ("🤖 <b>Fleet View</b>", "Active, Paused &amp; Queued Helper Tasks"),
                ("🎛 <b>Controls</b>", "Pause, Resume, Prioritize &amp; Cancel"),
                ("🔄 <b>Refresh</b>", "Static Fleet Dashboard (saves API calls)"),
            ],
        ),
    },
    "editcaption": {
        "title": "✏️ editcaption",
        "summary": "Edit file captions in Storage Group",
        "category": "admin",
        "text": _help_card(
            "✏️ <b>Command Documentation —</b> <code>/editcaption</code>",
            [
                ("✏️ <b>Command</b>", "<code>/editcaption</code> (<code>/setcaption</code>)"),
                ("📍 <b>Scope</b>", "Storage Group Only"),
                ("🔘 <b>Button</b>", "Tap <code>✏️ Edit Caption</code> on any file"),
                ("💡 <b>Syntax 1</b>", "Reply to a Storage file with <code>/editcaption</code>"),
                ("💡 <b>Syntax 2</b>", "<code>/editcaption</code> &lt;storage_msg_id&gt;"),
                ("🔄 <b>Sync</b>", "Updates Storage + files.db + Table Logs"),
            ],
        ),
    },
    "broadcast": {
        "title": "📢 broadcast",
        "summary": "Broadcast with audience toggles",
        "category": "admin",
        "text": _help_card(
            "📢 <b>Command Documentation —</b> <code>/broadcast</code>",
            [
                ("📢 <b>Command</b>", "<code>/broadcast</code> (or <code>/pinbroadcast</code>)"),
                ("🛑 <b>Stop Command</b>", "<code>/cancelbroadcast</code>"),
                ("🎯 <b>Targets</b>", "All, Users, Helpers, Groups, Channels"),
                ("📌 <b>Auto-Pin</b>", "Toggle ON/OFF in control panel"),
                ("⚙️ <b>Live Controls</b>", "Pause, Resume &amp; Cancel buttons"),
            ],
        ),
    },
    "ban": {
        "title": "🚫 ban",
        "summary": "Ban/unban users or chats",
        "category": "admin",
        "text": _help_card(
            "🚫 <b>Moderation &amp; Ban Commands</b>",
            [
                ("🌐 <b>Global Ban</b>", "<code>/ban</code> &lt;id|@user&gt; [reason]"),
                ("💬 <b>PM Ban</b>", "<code>/ban_pm</code> &lt;id|@user&gt; [reason]"),
                ("👥 <b>Support Ban</b>", "<code>/ban_support</code> &lt;id|@user&gt; [reason]"),
                ("✅ <b>Unban</b>", "<code>/unban</code> &lt;id|@user&gt;"),
            ],
        ),
    },
    "gift": {
        "title": "🎁 gift",
        "summary": "Grant bonus searches & requests",
        "category": "admin",
        "text": _help_card(
            "🎁 <b>Command Documentation —</b> <code>/gift</code>",
            [
                ("🎁 <b>Command</b>", "<code>/gift</code>"),
                ("📝 <b>Purpose</b>", "Adds bonus search &amp; request limits"),
                ("💡 <b>Syntax</b>", "<code>/gift</code> &lt;uid&gt; &lt;searches&gt; &lt;requests&gt;"),
                ("📌 <b>Example</b>", "<code>/gift</code> 123456789 25 25"),
            ],
        ),
    },
    "editscript": {
        "title": "🛠️ editscript",
        "summary": "Live template & config editor",
        "category": "admin",
        "text": _help_card(
            "🛠️ <b>Command Documentation —</b> <code>/editscript</code>",
            [
                ("🛠️ <b>Command</b>", "<code>/editscript</code>"),
                ("📝 <b>Purpose</b>", "Live config &amp; template editor"),
                ("🎛 <b>Options</b>", "Headers, media banners &amp; toggles"),
                ("💡 <b>Syntax</b>", "<code>/editscript</code>"),
            ],
        ),
    },
    "log": {
        "title": "📋 log",
        "summary": "Export in-memory system logs",
        "category": "admin",
        "text": _help_card(
            "📋 <b>Command Documentation —</b> <code>/log</code>",
            [
                ("📋 <b>Command</b>", "<code>/log</code>"),
                ("📝 <b>Purpose</b>", "Exports system logs as a .txt file"),
                ("💡 <b>Syntax 1</b>", "<code>/log</code> (last 10 lines)"),
                ("💡 <b>Syntax 2</b>", "<code>/log</code> 100 (last N lines)"),
                ("💡 <b>Syntax 3</b>", "<code>/log</code> 30m (last N minutes)"),
            ],
        ),
    },
    "ping": {
        "title": "🏓 ping",
        "summary": "Latency & network usage table",
        "category": "admin",
        "text": _help_card(
            "🏓 <b>Command Documentation —</b> <code>/ping</code>",
            [
                ("🏓 <b>Command</b>", "<code>/ping</code>"),
                ("⏱ <b>Latency</b>", "Round-trip Telegram API ping (ms)"),
                ("📊 <b>Network</b>", "Server TX / RX bandwidth table"),
                ("💡 <b>Syntax</b>", "<code>/ping</code>"),
            ],
        ),
    },
    "addmoderator": {
        "title": "🛡️ addmoderator",
        "summary": "Promote/demote Moderators",
        "category": "admin",
        "text": _help_card(
            "🛡️ <b>Moderator Role Management</b>",
            [
                ("⬆️ <b>Promote</b>", "<code>/addmoderator</code> &lt;id|@user&gt;"),
                ("⬇️ <b>Demote</b>", "<code>/removemoderator</code> &lt;id|@user&gt;"),
                ("🏷 <b>Aliases</b>", "<code>/addmod</code>, <code>/removemod</code>, <code>/delmod</code>"),
                ("📊 <b>Tier Quota</b>", "40 searches &amp; 40 requests/day"),
            ],
        ),
    },
    "addvolunteer": {
        "title": "🤝 addvolunteer",
        "summary": "Promote/demote Volunteers",
        "category": "admin",
        "text": _help_card(
            "🤝 <b>Volunteer Role Management</b>",
            [
                ("⬆️ <b>Promote</b>", "<code>/addvolunteer</code> &lt;id|@user&gt;"),
                ("⬇️ <b>Demote</b>", "<code>/removevolunteer</code> &lt;id|@user&gt;"),
                ("🏷 <b>Aliases</b>", "<code>/addvol</code>, <code>/removevol</code>, <code>/delvol</code>"),
                ("📊 <b>Tier Quota</b>", "30 searches &amp; 30 requests/day"),
            ],
        ),
    },
    "addpromoter": {
        "title": "📣 addpromoter",
        "summary": "Promote/demote Promoters",
        "category": "admin",
        "text": _help_card(
            "📣 <b>Promoter Role Management</b>",
            [
                ("⬆️ <b>Promote</b>", "<code>/addpromoter</code> &lt;id|@user&gt;"),
                ("⬇️ <b>Demote</b>", "<code>/removepromoter</code> &lt;id|@user&gt;"),
                ("🏷 <b>Aliases</b>", "<code>/addpromo</code>, <code>/removepromo</code>"),
                ("📊 <b>Tier Quota</b>", "20 searches &amp; 20 requests/day"),
            ],
        ),
    },

    # =======================================================================
    # 👑 CREATOR COMMANDS
    # =======================================================================
    "publish": {
        "title": "🚀 publish",
        "summary": "Merge test -> main & deploy",
        "category": "creator",
        "text": _help_card(
            "🚀 <b>Command Documentation —</b> <code>/publish</code>",
            [
                ("🚀 <b>Command</b>", "<code>/publish</code>"),
                ("🔒 <b>Access</b>", "Creator Only 👑"),
                ("🔀 <b>Git Flow</b>", "Merges <code>test</code> into <code>main</code>"),
                ("🌐 <b>Remotes</b>", "Pushes to <code>loki</code> &amp; <code>origin</code>"),
                ("💡 <b>Syntax</b>", "<code>/publish</code>"),
            ],
        ),
    },
    "update": {
        "title": "📦 update",
        "summary": "In-chat .zip code deployment",
        "category": "creator",
        "text": _help_card(
            "📦 <b>Command Documentation —</b> <code>/update</code>",
            [
                ("📦 <b>Command</b>", "<code>/update</code>"),
                ("🔒 <b>Access</b>", "Creator Only 👑"),
                ("📝 <b>Purpose</b>", "Unpacks .zip, runs compileall &amp; pushes"),
                ("💡 <b>Syntax</b>", "Reply to or caption a <code>.zip</code> with <code>/update</code>"),
            ],
        ),
    },
    "sh": {
        "title": "💻 sh",
        "summary": "Execute host shell commands",
        "category": "creator",
        "text": _help_card(
            "💻 <b>Command Documentation —</b> <code>/sh</code>",
            [
                ("💻 <b>Command</b>", "<code>/sh</code> (alias: <code>/term</code>)"),
                ("🔒 <b>Access</b>", "Creator Only 👑"),
                ("📝 <b>Purpose</b>", "Runs bash commands on host server"),
                ("💡 <b>Syntax</b>", "<code>/sh</code> &lt;command&gt;"),
            ],
        ),
    },
    "addadmin": {
        "title": "👑 addadmin",
        "summary": "Appoint/remove Administrators",
        "category": "creator",
        "text": _help_card(
            "👑 <b>Administrator Appointment</b>",
            [
                ("⬆️ <b>Appoint</b>", "<code>/addadmin</code> &lt;id|@user&gt;"),
                ("⬇️ <b>Remove</b>", "<code>/removeadmin</code> (<code>/deladmin</code>)"),
                ("🔒 <b>Access</b>", "Creator Only 👑"),
                ("📊 <b>Admin Quota</b>", "Unlimited searches &amp; requests"),
            ],
        ),
    },
    "creator_privileges": {
        "title": "♾️ creator_privileges",
        "summary": "Supreme governance overview",
        "category": "creator",
        "text": _help_card(
            "👑 <b>Creator Supreme Authority</b>",
            [
                ("👑 <b>Role</b>", "Creator / Owner"),
                ("📊 <b>Allowances</b>", "Unlimited searches &amp; requests"),
                ("⚔️ <b>Governance</b>", "Appoints Admins, Mods, Vols, Promos"),
                ("🚀 <b>Deployment</b>", "In-chat <code>/update</code> &amp; <code>/publish</code>"),
            ],
        ),
    },
    "backup": {
        "title": "💾 backup",
        "summary": "Timestamped SQLite backups",
        "category": "creator",
        "text": _help_card(
            "💾 <b>Timestamped SQLite Backups</b>",
            [
                ("🗄 <b>Databases</b>", "<code>files.db, mastermind_users.db, config.db</code>"),
                ("🧪 <b>Testing Zip</b>", "<code>test_backup_YYYYMMDD-HHMM.zip</code>"),
                ("🌐 <b>Public Zip</b>", "<code>public_backup_YYYYMMDD-HHMM.zip</code>"),
                ("🏷 <b>Tracker</b>", "Logger Group description tag (no unpin)"),
            ],
        ),
    },
    "governance": {
        "title": "⚙️ governance",
        "summary": "Environment & fleet architecture",
        "category": "creator",
        "text": _help_card(
            "⚙️ <b>Global Architecture &amp; Governance</b>",
            [
                ("🔀 <b>Branches</b>", "<code>test</code> (Testing) / <code>main</code> (Public)"),
                ("🤖 <b>Bot Fleet</b>", "Main Bot + Round-Robin Helper Bots"),
                ("🎨 <b>UI Engine</b>", "Tables + Transparent Colorful Buttons"),
            ],
        ),
    },
}


# ---------------------------------------------------------------------------
# Menu Builders with Pagination (Max 6 buttons per page, Transparent Colorful Styles)
# Note: On Telegram Android/Web, `success` (green) and `danger` (red/coral) render
# as transparent tinted buttons, whereas `primary` renders as solid opaque blue.
# We alternate `success` and `danger` across the help menu so every button is
# transparent and colorful!
# ---------------------------------------------------------------------------
PAGE_SIZE = 6

CATEGORY_COMMANDS = {
    "user": ["start", "search", "request", "quota", "refer", "support", "stats", "id", "rosters", "delivery", "roles"],
    "volunteer": ["vol_privileges", "vol_indexing", "vol_notice"],
    "moderator": ["mod_privileges", "mod_requests", "mod_indexing", "mod_notice"],
    "admin": [
        "checkhelpers", "index", "ongoing", "editcaption", "broadcast", "ban", "gift", "editscript",
        "log", "ping", "addmoderator", "addvolunteer", "addpromoter"
    ],
    "creator": ["publish", "update", "sh", "addadmin", "creator_privileges", "backup", "governance"],
}


def build_paginated_category_menu(category: str, page: int = 1):
    cmd_keys = CATEGORY_COMMANDS.get(category, [])
    total_items = len(cmd_keys)
    total_pages = max(1, (total_items + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * PAGE_SIZE
    page_keys = cmd_keys[start_idx : start_idx + PAGE_SIZE]

    titles = {
        "user": "👤 User Functions & Commands",
        "volunteer": "🤝 Volunteer Privileges & Guides",
        "moderator": "🛡️ Moderator Management Menu",
        "admin": "⚔️ Administrator Command Hub",
        "creator": "👑 Creator Supreme Governance",
    }
    cat_title = titles.get(category, "Documentation")

    table_rows = []
    buttons = []
    row = []
    for idx, key in enumerate(page_keys):
        item = COMMAND_DETAILS.get(key, {})
        label = item.get("title", key)
        summary = item.get("summary", "Command guide")
        table_rows.append(f"<tr><td>{html.escape(label)}</td><td>{html.escape(summary)}</td></tr>")
        # Checkerboard alternation of transparent colorful styles (success = green, danger = coral/red)
        row_num = idx // 2
        col_num = idx % 2
        btn_style = "success" if (row_num + col_num) % 2 == 0 else "danger"
        row.append(styled_button(label, callback_data=f"help_cmd_{key}", style=btn_style))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    text = (
        f"<b>{cat_title}</b> (<mark>Page {page}/{total_pages}</mark>)\n\n"
        f"<table striped><tr><th>Command</th><th>Summary</th></tr>{''.join(table_rows)}</table>\n\n"
        "Tap any transparent colorful button below to open full details:"
    )

    # Navigation Row with transparent colorful buttons
    nav_row = []
    if page > 1:
        nav_row.append(styled_button("◀️ Prev", callback_data=f"help_cat_{category}_p{page - 1}", style="danger"))
    nav_row.append(styled_button(f"📄 {page}/{total_pages}", callback_data="noop", style="success", disabled=True))
    if page < total_pages:
        nav_row.append(styled_button("Next ▶️", callback_data=f"help_cat_{category}_p{page + 1}", style="success"))
    buttons.append(nav_row)

    buttons.append([styled_button("« Back to Categories", callback_data="help_main", style="danger")])
    return text, InlineKeyboardMarkup(buttons)


def build_main_help_menu(user_id: int):
    """
    Builds the main help menu page using Bot API 10.3 Rich Tables & Transparent Colorful Buttons:
    1. Only displays categories accessible to the user's role level.
    2. Includes a structured <table striped> overview of available sections.
    3. Alternates transparent `success` (green) and `danger` (red/coral) buttons across rows.
    """
    role = get_user_role_db(user_id)
    is_creator_user = is_creator(user_id)
    is_admin = is_admin_or_creator(user_id)
    is_mod = (role in ("Moderator", "Admin", "Creator", "Owner"))
    is_vol = (role in ("Volunteer", "Moderator", "Admin", "Creator", "Owner"))

    sec_rows = [
        "<tr><td>👤 <b>Your Role</b></td><td><code>" + html.escape(str(role)) + "</code></td></tr>",
        "<tr><td>👤 <b>User Hub</b></td><td>11 Commands &amp; Guides</td></tr>",
        "<tr><td>👥 <b>User Roles</b></td><td>6 Community Tiers</td></tr>",
    ]
    if is_vol:
        sec_rows.append("<tr><td>🤝 <b>Volunteer</b></td><td>Direct Helper DM Indexing</td></tr>")
    if is_mod:
        sec_rows.append("<tr><td>🛡️ <b>Moderator</b></td><td>Request Status &amp; Indexing</td></tr>")
    if is_admin:
        sec_rows.append("<tr><td>⚔️ <b>Admin Hub</b></td><td>12 Admin &amp; Batch Tools</td></tr>")
    if is_creator_user:
        sec_rows.append("<tr><td>👑 <b>Creator</b></td><td>7 Governance &amp; Deploy Tools</td></tr>")

    text = (
        f"📖 <b>{bot_name()} Bot — Help &amp; Documentation Hub</b>\n\n"
        f"<table striped><tr><th>Section</th><th>Overview</th></tr>{''.join(sec_rows)}</table>\n\n"
        "Select a transparent colorful section below to browse commands:"
    )

    buttons = [
        [
            styled_button("👤 User Commands", callback_data="help_cat_user_p1", style="success"),
            styled_button("👥 User Roles", callback_data="help_cmd_roles", style="danger"),
        ],
    ]

    second_row = []
    if is_vol:
        second_row.append(styled_button("🤝 Volunteer", callback_data="help_cat_volunteer_p1", style="danger"))
    if is_mod:
        second_row.append(styled_button("🛡️ Moderator", callback_data="help_cat_moderator_p1", style="success"))
    if second_row:
        buttons.append(second_row)

    admin_row = []
    if is_admin:
        admin_row.append(styled_button("⚔️ Admin Hub", callback_data="help_cat_admin_p1", style="success"))
    if is_creator_user:
        admin_row.append(styled_button("👑 Creator", callback_data="help_cat_creator_p1", style="danger"))
    if admin_row:
        buttons.append(admin_row)
    if is_admin:
        buttons.append([styled_button("📋 Ongoing Tasks", callback_data="idx_ongoing_menu", style="success")])

    buttons.append([
        styled_button("🔍 Search Library", callback_data="search_menu", style="success"),
        styled_button("📊 My Quota", callback_data="quota", style="danger"),
    ])
    buttons.append([styled_button("« Back to Start", callback_data="start_menu", style="danger")])

    return text, InlineKeyboardMarkup(buttons)


# ---------------------------------------------------------------------------
# Handlers & Callback Router
# ---------------------------------------------------------------------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return

    text, markup = build_main_help_menu(user.id)
    if update.callback_query:
        await update.callback_query.answer()
        await msg.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await msg.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def help_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.data:
        return
    await q.answer()
    data = q.data
    user = update.effective_user
    user_id = user.id if user else 0
    role = get_user_role_db(user_id)

    if data in ("help_main", "help_menu", "help_button"):
        text, markup = build_main_help_menu(user_id)
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=markup)

    elif data.startswith("help_cat_"):
        parts = data.replace("help_cat_", "").split("_p")
        category = parts[0]
        page = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1

        # Role access enforcement
        if category == "volunteer" and role not in ("Volunteer", "Moderator", "Admin", "Creator", "Owner"):
            await q.answer("⛔ Access restricted to Volunteers and above.", show_alert=True)
            return
        if category == "moderator" and role not in ("Moderator", "Admin", "Creator", "Owner"):
            await q.answer("⛔ Access restricted to Moderators and above.", show_alert=True)
            return
        if category == "admin" and not is_admin_or_creator(user_id):
            await q.answer("⛔ Access restricted to Administrators.", show_alert=True)
            return
        if category == "creator" and not is_creator(user_id):
            await q.answer("⛔ Access restricted to the Creator.", show_alert=True)
            return

        text, markup = build_paginated_category_menu(category, page)
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=markup)

    elif data.startswith("help_cmd_"):
        key = data.replace("help_cmd_", "")
        item = COMMAND_DETAILS.get(key)
        if not item:
            await q.answer("Documentation not found.", show_alert=True)
            return

        category = item.get("category", "user")
        # Enforce role access on direct command inspects
        if category == "volunteer" and role not in ("Volunteer", "Moderator", "Admin", "Creator", "Owner"):
            await q.answer("⛔ Access restricted to Volunteers and above.", show_alert=True)
            return
        if category == "moderator" and role not in ("Moderator", "Admin", "Creator", "Owner"):
            await q.answer("⛔ Access restricted to Moderators and above.", show_alert=True)
            return
        if category == "admin" and not is_admin_or_creator(user_id):
            await q.answer("⛔ Access restricted to Administrators.", show_alert=True)
            return
        if category == "creator" and not is_creator(user_id):
            await q.answer("⛔ Access restricted to the Creator.", show_alert=True)
            return

        text = item["text"]
        markup = InlineKeyboardMarkup([
            [styled_button(f"« Back to {category.capitalize()} Menu", callback_data=f"help_cat_{category}_p1", style="danger")],
            [styled_button("« Main Help Hub", callback_data="help_main", style="success")],
        ])
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
