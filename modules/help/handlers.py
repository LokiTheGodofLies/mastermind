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


# ---------------------------------------------------------------------------
# Individual Command & Feature Documentation Cards (Bot API 10.3 Rich UI)
# Touch-to-copy format applied ONLY to command names, not arguments/queries.
# ---------------------------------------------------------------------------
COMMAND_DETAILS = {
    # =======================================================================
    # 👤 USER COMMANDS & GUIDES
    # =======================================================================
    "start": {
        "title": "🚀 start",
        "category": "user",
        "text": (
            "🚀 <b>Command:</b> <code>/start</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Launches the bot, initializes your daily search and request allowances, "
            "displays the interactive Bot API 10.3 rich main menu with colorful buttons, and handles one-tap book download links.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/start</code>\n"
            "• <code>/start</code> dl_&lt;file_id&gt;\n\n"
            "📌 <b>Examples:</b>\n"
            "• Send <code>/start</code> in private chat to open the main menu.\n"
            "• Tap any colorful <mark>📥 Download</mark> button in search results to receive files instantly."
        ),
    },
    "search": {
        "title": "🔍 search",
        "category": "user",
        "text": (
            "🔍 <b>Command:</b> <code>/search</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Searches our community library across book titles, authors, series, and descriptions using Bot API 10.3 Rich Messages and colorful in-text download buttons.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/search</code> &lt;book title or author&gt;\n\n"
            "📌 <b>Examples:</b>\n"
            "• <code>/search</code> Percy Jackson\n"
            "• <code>/search</code> Fifty-Fifty\n"
            "• <code>/search</code> Colleen Hoover\n\n"
            "✨ <i>Tip: Search results come as one wide table (swipe sideways): tap a green Download button under the table, use the format filters (📚 Ebooks / 🎧 Audio) and the green <mark>📨 Send All</mark> button!</i>"
        ),
    },
    "request": {
        "title": "📥 request",
        "category": "user",
        "text": (
            "📥 <b>Command:</b> <code>/request</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Submits a request for any missing book or audiobook directly to our community Request Channel with live Goodreads lookup and colorful in-text selection buttons.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/request</code> &lt;book title and author&gt;\n\n"
            "📌 <b>Examples:</b>\n"
            "• <code>/request</code> Fourth Wing by Rebecca Yarros\n"
            "• <code>/request</code> A Court of Thorns and Roses by Sarah J. Maas\n\n"
            "✨ <i>Tip: Moderators review requests and update colorful status buttons live!</i>"
        ),
    },
    "quota": {
        "title": "📊 quota",
        "category": "user",
        "text": (
            "📊 <b>Command:</b> <code>/quota</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Displays your live daily search and request balance, your account tier badge, and automatic midnight IST reset status.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/quota</code>\n\n"
            "🏆 <b>Daily Allowances by Tier:</b>\n"
            "• 👤 User: <mark>10 searches &amp; 10 requests</mark>\n"
            "• 📣 Promoter: <mark>20 searches &amp; 20 requests</mark>\n"
            "• 🤝 Volunteer: <mark>30 searches &amp; 30 requests</mark>\n"
            "• 🛡️ Moderator: <mark>40 searches &amp; 40 requests</mark>\n"
            "• ⚔️ Administrator / 👑 Creator: <mark>Unlimited</mark>"
        ),
    },
    "refer": {
        "title": "🔗 refer",
        "category": "user",
        "text": (
            "🔗 <b>Commands:</b> <code>/refer</code> &amp; <code>/myreferrals</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Generates your personal invite link with one-tap <mark>📋 Copy Invite Link</mark> and <mark>📤 Share Link</mark> buttons. Invite friends and earn bonus searches &amp; requests!\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/refer</code> (generates your unique invite link)\n"
            "• <code>/myreferrals</code> (checks your invite stats and bonus balance)\n\n"
            "🎁 <b>Reward:</b> <mark>+10 searches &amp; +10 requests</mark> per successful invite!"
        ),
    },
    "support": {
        "title": "💬 support",
        "category": "user",
        "text": (
            "💬 <b>Command:</b> <code>/support</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Launches our 10-question screening quiz with colorful Yes/No buttons and generates a single-use invite link to our official community support group.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/support</code>"
        ),
    },
    "stats": {
        "title": "📈 stats",
        "category": "user",
        "text": (
            "📈 <b>Command:</b> <code>/stats</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Displays live library metrics, including total indexed files, separate ebook and audiobook counts, active users, and system diagnostics.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/stats</code>"
        ),
    },
    "id": {
        "title": "🆔 id",
        "category": "user",
        "text": (
            "🆔 <b>Command:</b> <code>/id</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Retrieves unique Telegram IDs for users, groups, channels, or forum topics with one-tap <mark>📋 Copy ID</mark> buttons.\n"
            "When run inside a channel where the sender is anonymous, user fields are automatically omitted for a clean channel card.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/id</code>\n"
            "• <code>/id</code> @username\n"
            "• Reply to any message with <code>/id</code>"
        ),
    },
    "rosters": {
        "title": "👥 rosters",
        "category": "user",
        "text": (
            "👥 <b>Community Roster Commands</b>\n\n"
            "View official lists of community team members with colorful in-text profile and <mark>📋 Copy ID</mark> buttons:\n\n"
            "💡 <b>Commands:</b>\n"
            "• <code>/admins</code> — Lists all Administrators and the Creator.\n"
            "• <code>/moderators</code> (or <code>/mods</code>) — Lists all active Moderators.\n"
            "• <code>/volunteers</code> (or <code>/vols</code>) — Lists all active Volunteers.\n"
            "• <code>/promoters</code> (or <code>/promos</code>) — Lists all active Promoters."
        ),
    },
    "delivery": {
        "title": "📦 delivery",
        "category": "user",
        "text": (
            "📦 <b>Dual File Delivery System</b>\n\n"
            "When you download a file from search results, the bot delivers via two parallel routes:\n\n"
            "1. <b>🤖 Fast PM Delivery:</b> Sent directly to your private chat via helper bots (with 5-minute auto-delete).\n"
            "2. <b>📢 Posting Channel:</b> A temporary copy is posted in the channel (with 5-minute auto-delete).\n\n"
            "⚠️ <b>Important Tip:</b>\n"
            "Forward your received files to your <mark>Saved Messages</mark> before the 5-minute timer expires!"
        ),
    },
    "roles": {
        "title": "👥 roles",
        "category": "user",
        "text": (
            "👥 <b>Community User Roles &amp; Privileges Breakdown</b>\n\n"
            "Our community has 6 structured tiers to organize library contributions and governance:\n\n"
            "👤 <b>Normal User:</b>\n"
            "• Quota: <mark>10 daily searches &amp; 10 daily requests</mark>.\n"
            "• Access: /start, /search, /request, /quota, /refer, /support, /stats, /id, rosters.\n\n"
            "📣 <b>Promoter:</b>\n"
            "• Quota: <mark>20 daily searches &amp; 20 daily requests</mark>.\n"
            "• Appointed by Admins to share and promote our community library.\n\n"
            "🤝 <b>Volunteer:</b>\n"
            "• Quota: <mark>30 daily searches &amp; 30 daily requests</mark>.\n"
            "• Pre-approved direct book, audiobook, and archive indexing via Helper Bot DMs.\n\n"
            "🛡️ <b>Moderator:</b>\n"
            "• Quota: <mark>40 daily searches &amp; 40 daily requests</mark>.\n"
            "• Direct indexing + Request Channel status management (In Progress, Completed, Rejected).\n\n"
            "⚔️ <b>Administrator:</b>\n"
            "• Quota: <mark>Unlimited searches &amp; requests</mark>.\n"
            "• Batch range indexing (/index), announcements (/broadcast), fleet audit (/checkhelpers), bans (/ban), gifts (/gift), and team promotions.\n\n"
            "👑 <b>Creator:</b>\n"
            "• Supreme governance, admin appointments (/addadmin), in-chat updates (/update), production deployment (/publish), and timestamped SQLite backups."
        ),
    },

    # =======================================================================
    # 🤝 VOLUNTEER COMMANDS & GUIDES
    # =======================================================================
    "vol_privileges": {
        "title": "🤝 vol_privileges",
        "category": "volunteer",
        "text": (
            "🤝 <b>Volunteer Operational Privileges</b>\n\n"
            "• <b>Daily Quota:</b> <mark>30 searches and 30 requests</mark> per day.\n"
            "• <b>Direct Indexing:</b> Send or forward supported ebooks, audiobooks, or archives (.zip, .rar, .7z) directly to any Helper Bot in private chat.\n"
            "• <b>Automatic Approval &amp; Dual Logging:</b> Files uploaded by Volunteers are verified through the 3-Stage Self-Healing Pipeline and logged to both the Index Logs Channel and Logger Group Topic."
        ),
    },
    "vol_indexing": {
        "title": "📚 vol_indexing",
        "category": "volunteer",
        "text": (
            "📚 <b>Volunteer Helper Bot Indexing Guide</b>\n\n"
            "1. Start a private chat with any official Helper Bot (e.g. @Heyuqtbot or @RickRiordanBot).\n"
            "2. Send or forward supported ebook (<code>.epub, .pdf, .mobi, .azw3, .cbz, .cbr, .djvu, .fb2, .txt, .rtf</code>), audiobook (<code>.mp3, .m4b, .m4a, .aax, .flac, .wav, .ogg, .opus</code>), or archive (<code>.zip, .rar, .7z</code>) files.\n"
            "3. The bot strips spam captions, enriches metadata across our 8-site book/audiobook waterfall, stores the file in the Storage Group, and posts the 3-Tick Index Log automatically!"
        ),
    },
    "vol_notice": {
        "title": "⚠️ vol_notice",
        "category": "volunteer",
        "text": (
            "⚠️ <b>Index Command Notice for Volunteers</b>\n\n"
            "The batch range command <code>/index</code> is exclusive to Administrators and the Creator.\n"
            "Volunteers contribute files directly and cleanly via Helper Bot DMs."
        ),
    },

    # =======================================================================
    # 🛡️ MODERATOR COMMANDS & GUIDES
    # =======================================================================
    "mod_privileges": {
        "title": "⚖️ mod_privileges",
        "category": "moderator",
        "text": (
            "🛡️ <b>Moderator Operational Privileges</b>\n\n"
            "• <b>Daily Quota:</b> <mark>40 searches and 40 requests</mark> per day.\n"
            "• <b>Request Channel Control:</b> Update colorful status buttons on incoming book requests.\n"
            "• <b>Direct Library Indexing:</b> Pre-approved direct indexing via Helper Bot DMs."
        ),
    },
    "mod_requests": {
        "title": "📋 mod_requests",
        "category": "moderator",
        "text": (
            "📋 <b>Request Status Management</b>\n\n"
            "When users submit book requests via <code>/request</code>, they appear in the Request Channel.\n"
            "Moderators use colorful Bot API 10.3 buttons to update the status:\n"
            "• ⏳ <mark>In Progress</mark> (Blue): Request is actively being sourced.\n"
            "• ✅ <mark>Completed</mark> (Green): File was found and indexed into the library.\n"
            "• ❌ <mark>Rejected</mark> (Red): Book cannot be fulfilled."
        ),
    },
    "mod_indexing": {
        "title": "🤖 mod_indexing",
        "category": "moderator",
        "text": (
            "🤖 <b>Moderator Direct Indexing Guide</b>\n\n"
            "Send or forward supported ebook, audiobook, and archive files directly to any Helper Bot in private chat.\n"
            "Metadata is enriched automatically across 8 book &amp; audiobook databases and logged to both the Index Logs Channel and Logger Group Topic."
        ),
    },
    "mod_notice": {
        "title": "⚠️ mod_notice",
        "category": "moderator",
        "text": (
            "⚠️ <b>Batch /index Command Access Notice</b>\n\n"
            "The <code>/index</code> batch range command is reserved for Administrators and the Creator.\n"
            "Moderators index files cleanly through Helper Bot private chats."
        ),
    },

    # =======================================================================
    # ⚔️ ADMINISTRATOR COMMANDS
    # =======================================================================
    "checkhelpers": {
        "title": "🤖 checkhelpers",
        "category": "admin",
        "text": (
            "🤖 <b>Command:</b> <code>/checkhelpers</code> (alias: <code>/helpers</code>)\n\n"
            "📝 <b>Purpose:</b>\n"
            "Audits <b>both the Main Bot and all configured Helper Bots</b> across all required channels and groups:\n"
            "• 📦 <b>Storage Group:</b> Verifies membership &amp; file access.\n"
            "• 📢 <b>Posting Channel:</b> Verifies Admin status with Post &amp; Delete Messages rights.\n"
            "• 📥 <b>Index Logs Channel:</b> Verifies Admin status with Post Messages rights so whichever bot indexes files can post 3-Tick Index Logs.\n"
            "• 🪵 <b>Logger Group:</b> Verifies membership for Index &amp; Error log topics.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/checkhelpers</code>\n"
            "• <code>/helpers</code>"
        ),
    },
    "index": {
        "title": "📚 index",
        "category": "admin",
        "text": (
            "📚 <b>Command:</b> <code>/index</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Batch indexes ebooks, audiobooks, and archives (<code>.zip, .rar, .7z</code>) from channels or groups into the Storage Group with 3-Stage Ordered Self-Healing and 8-site metadata enrichment.\n"
            "• Works in channels where either the <b>Main Bot</b> or a <b>Helper Bot</b> is Admin!\n"
            "• Automatically deletes the <code>/index</code> command post in channels and auto-cleans the progress card after completion.\n"
            "• Sends the 3-Tick Index Log to <b>both</b> <code>INDEX_CHANNEL_ID</code> and <code>INDEX_LOG_TOPIC_ID</code> from whichever bot is indexing.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/index</code> (directly inside a source channel)\n"
            "• <code>/index</code> &lt;first_link&gt; &lt;last_link&gt;\n"
            "• <code>/index</code> (in private chat for interactive wizard)"
        ),
    },
    "broadcast": {
        "title": "📢 broadcast",
        "category": "admin",
        "text": (
            "📢 <b>Command:</b> <code>/broadcast</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Dispatches announcements with colorful Bot API 10.3 audience toggles (🌐 All, 👥 Users, 🤖 Helper Bots, 👥 Groups, 📢 Channels), "
            "auto-pinning, expandable quote preview, and live Pause/Resume/Cancel controls.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/broadcast</code> &lt;announcement text&gt;\n"
            "• Reply to any message with <code>/broadcast</code>\n"
            "• <code>/cancelbroadcast</code> — Stops the active broadcast"
        ),
    },
    "ban": {
        "title": "🚫 ban",
        "category": "admin",
        "text": (
            "🚫 <b>Commands:</b> <code>/ban</code>, <code>/ban_pm</code>, <code>/ban_support</code>, <code>/unban</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Applies or lifts granular restrictions on users or chats:\n"
            "• Global Ban: Restricts user from both DMs and community groups.\n"
            "• PM Ban: Restricts user from bot private chat only.\n"
            "• Support Ban: Restricts user from community support chat only.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/ban</code> &lt;user_id or @username&gt; [reason]\n"
            "• <code>/ban_pm</code> &lt;user_id or @username&gt;\n"
            "• <code>/ban_support</code> &lt;user_id or @username&gt;\n"
            "• <code>/unban</code> &lt;user_id or @username&gt;"
        ),
    },
    "gift": {
        "title": "🎁 gift",
        "category": "admin",
        "text": (
            "🎁 <b>Command:</b> <code>/gift</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Grants bonus daily search and request allowances to any user.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/gift</code> &lt;user_id&gt; &lt;searches&gt; &lt;requests&gt;\n\n"
            "📌 <b>Examples:</b>\n"
            "• <code>/gift</code> 123456789 25 25"
        ),
    },
    "editscript": {
        "title": "🛠️ editscript",
        "category": "admin",
        "text": (
            "🛠️ <b>Command:</b> <code>/editscript</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Opens the dynamic configuration hub with colorful buttons to modify banners, welcome messages, caption templates, "
            "and channel links live without restarting the bot.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/editscript</code>"
        ),
    },
    "log": {
        "title": "📋 log",
        "category": "admin",
        "text": (
            "📋 <b>Command:</b> <code>/log</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Exports in-memory system logs as a downloadable document directly in Telegram.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/log</code> (recent logs)\n"
            "• <code>/log</code> &lt;number of lines&gt;\n"
            "• <code>/log</code> &lt;duration, e.g. 1h, 30m&gt;"
        ),
    },
    "ping": {
        "title": "🏓 ping",
        "category": "admin",
        "text": (
            "🏓 <b>Command:</b> <code>/ping</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Tests bot responsiveness, round-trip API latency, and server uptime.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/ping</code>"
        ),
    },
    "addmoderator": {
        "title": "🛡️ addmoderator",
        "category": "admin",
        "text": (
            "🛡️ <b>Commands:</b> <code>/addmoderator</code> &amp; <code>/removemoderator</code>\n"
            "<i>(Aliases: /addmod, /removemod, /delmod)</i>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Promotes or demotes a Moderator (40 daily quota, request management buttons).\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/addmoderator</code> &lt;user_id or @username&gt;\n"
            "• <code>/removemoderator</code> &lt;user_id or @username&gt;"
        ),
    },
    "addvolunteer": {
        "title": "🤝 addvolunteer",
        "category": "admin",
        "text": (
            "🤝 <b>Commands:</b> <code>/addvolunteer</code> &amp; <code>/removevolunteer</code>\n"
            "<i>(Aliases: /addvol, /removevol, /delvol)</i>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Promotes or demotes a Volunteer (30 daily quota, pre-approved helper indexing).\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/addvolunteer</code> &lt;user_id or @username&gt;\n"
            "• <code>/removevolunteer</code> &lt;user_id or @username&gt;"
        ),
    },
    "addpromoter": {
        "title": "📣 addpromoter",
        "category": "admin",
        "text": (
            "📣 <b>Commands:</b> <code>/addpromoter</code> &amp; <code>/removepromoter</code>\n"
            "<i>(Aliases: /addpromo, /removepromo, /delpromo)</i>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Promotes or demotes a Promoter (20 daily quota).\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/addpromoter</code> &lt;user_id or @username&gt;\n"
            "• <code>/removepromoter</code> &lt;user_id or @username&gt;"
        ),
    },

    # =======================================================================
    # 👑 CREATOR COMMANDS
    # =======================================================================
    "publish": {
        "title": "🚀 publish",
        "category": "creator",
        "text": (
            "🚀 <b>Command:</b> <code>/publish</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Merges the tested &amp; verified <mark>test</mark> branch into <mark>main</mark> and pushes to "
            "both <code>loki main</code> and <code>origin main</code> using authenticated refspecs.\n"
            "Triggers live deployment on Render Public Books Bot with a single tap right from Telegram!\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/publish</code>\n\n"
            "🔒 <b>Access:</b> <mark>Creator Only 👑</mark>"
        ),
    },
    "update": {
        "title": "📦 update",
        "category": "creator",
        "text": (
            "📦 <b>Command:</b> <code>/update</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Updates bot code directly in-chat without Termux. Send or reply to an updated <code>.zip</code> file with <code>/update</code>.\n"
            "The bot unpacks the code, verifies with <code>compileall</code>, commits, and pushes to GitHub automatically!\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/update</code> (as caption or reply to a .zip archive)\n\n"
            "🔒 <b>Access:</b> <mark>Creator Only 👑</mark>"
        ),
    },
    "sh": {
        "title": "💻 sh",
        "category": "creator",
        "text": (
            "💻 <b>Command:</b> <code>/sh</code> (alias: <code>/term</code>)\n\n"
            "📝 <b>Purpose:</b>\n"
            "Executes bash shell commands directly on the host server and returns output live in Telegram.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/sh</code> &lt;shell command&gt;\n"
            "• <code>/term</code> &lt;shell command&gt;\n\n"
            "🔒 <b>Access:</b> <mark>Creator Only 👑</mark>"
        ),
    },
    "addadmin": {
        "title": "👑 addadmin",
        "category": "creator",
        "text": (
            "👑 <b>Commands:</b> <code>/addadmin</code> &amp; <code>/removeadmin</code>\n"
            "<i>(Alias: /deladmin)</i>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Appoints or removes an Administrator. Exclusive to the Creator.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/addadmin</code> &lt;user_id or @username&gt;\n"
            "• <code>/removeadmin</code> &lt;user_id or @username&gt;\n\n"
            "🔒 <b>Access:</b> <mark>Creator Only 👑</mark>"
        ),
    },
    "creator_privileges": {
        "title": "♾️ creator_privileges",
        "category": "creator",
        "text": (
            "👑 <b>Creator Supreme Authority</b>\n\n"
            "The Creator has absolute governance across all bot operations, helper pools, "
            "database persistence, and administrative appointments.\n\n"
            "🔒 <b>Access:</b> <mark>Creator Only 👑</mark>"
        ),
    },
    "backup": {
        "title": "💾 backup",
        "category": "creator",
        "text": (
            "💾 <b>Timestamped SQLite Backups &amp; Zero-Unpin Restore</b>\n\n"
            "Snapshots of <code>files.db</code>, <code>mastermind_users.db</code>, and <code>config.db</code> are zipped with an IST timestamp "
            "(<code>test_backup_YYYYMMDD-HHMM.zip</code> on Testing, <code>public_backup_YYYYMMDD-HHMM.zip</code> on Public), uploaded to the "
            "designated Backup Topic, and tracked via the Logger Group description tag <code>[MM_BACKUP:msg_id=&lt;id&gt;:file=&lt;fname&gt;]</code>.\n"
            "• Never requires unpinning other messages in the Logger Group!\n"
            "• If a previous backup is deleted before deployment, the bot starts fresh with auto-backup active.\n\n"
            "🔒 <b>Access:</b> <mark>Creator Only 👑</mark>"
        ),
    },
    "governance": {
        "title": "⚙️ governance",
        "category": "creator",
        "text": (
            "⚙️ <b>Global Architecture &amp; Identity Governance</b>\n\n"
            "Environment configuration, isolated Public/Testing credentials, Bot API 10.3 Rich UI, and Render deployment monitoring.\n\n"
            "🔒 <b>Access:</b> <mark>Creator Only 👑</mark>"
        ),
    },
}


# ---------------------------------------------------------------------------
# Menu Builders with Pagination (Max 6 buttons per page, Colorful Bot API 10.3 Styles)
# ---------------------------------------------------------------------------
PAGE_SIZE = 6

CATEGORY_COMMANDS = {
    "user": ["start", "search", "request", "quota", "refer", "support", "stats", "id", "rosters", "delivery", "roles"],
    "volunteer": ["vol_privileges", "vol_indexing", "vol_notice"],
    "moderator": ["mod_privileges", "mod_requests", "mod_indexing", "mod_notice"],
    "admin": [
        "checkhelpers", "index", "broadcast", "ban", "gift", "editscript",
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

    text = (
        f"<b>{cat_title}</b> (<mark>Page {page}/{total_pages}</mark>)\n\n"
        "Tap any colorful command button below to inspect its purpose, syntax, and examples:"
    )

    # Alternate vibrant styles across command cards
    cat_style = "success" if category in ("volunteer", "creator") else "primary"
    buttons = []
    row = []
    for key in page_keys:
        item = COMMAND_DETAILS.get(key, {})
        label = item.get("title", key)
        btn_style = "success" if key in ("start", "search", "request", "refer", "publish", "update", "index") else cat_style
        row.append(styled_button(label, callback_data=f"help_cmd_{key}", style=btn_style))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Navigation Row with Bot API 10.3 DisabledButton indicator
    nav_row = []
    if page > 1:
        nav_row.append(styled_button("◀️ Prev", callback_data=f"help_cat_{category}_p{page - 1}", style="primary"))
    nav_row.append(styled_button(f"📄 {page}/{total_pages}", callback_data="noop", disabled=True))
    if page < total_pages:
        nav_row.append(styled_button("Next ▶️", callback_data=f"help_cat_{category}_p{page + 1}", style="primary"))
    buttons.append(nav_row)

    buttons.append([styled_button("« Back to Categories", callback_data="help_main", style="primary")])
    return text, InlineKeyboardMarkup(buttons)


def build_main_help_menu(user_id: int):
    """
    Builds the main help menu page using Bot API 10.3 Rich Formatting & Colorful Buttons:
    1. Only displays categories accessible to the user's role level.
    2. Includes a dedicated '👥 roles' button directly on the main page.
    """
    role = get_user_role_db(user_id)
    is_creator_user = is_creator(user_id)
    is_admin = is_admin_or_creator(user_id)
    is_mod = (role in ("Moderator", "Admin", "Creator", "Owner"))
    is_vol = (role in ("Volunteer", "Moderator", "Admin", "Creator", "Owner"))

    text = (
        f"📖 <b>{bot_name()} Bot — Help &amp; Documentation Hub</b>\n\n"
        "Welcome! Browse our official interactive documentation below:\n\n"
        f"👤 <b>Your Access Level:</b> <mark>{role}</mark>\n\n"
        "Select a colorful section below to view available functions and guides:"
    )

    buttons = [
        [
            styled_button("👤 User Commands", callback_data="help_cat_user_p1", style="primary"),
            styled_button("👥 User Roles", callback_data="help_cmd_roles", style="success"),
        ],
    ]

    second_row = []
    if is_vol:
        second_row.append(styled_button("🤝 Volunteer", callback_data="help_cat_volunteer_p1", style="success"))
    if is_mod:
        second_row.append(styled_button("🛡️ Moderator", callback_data="help_cat_moderator_p1", style="primary"))
    if second_row:
        buttons.append(second_row)

    admin_row = []
    if is_admin:
        admin_row.append(styled_button("⚔️ Admin Hub", callback_data="help_cat_admin_p1", style="primary"))
    if is_creator_user:
        admin_row.append(styled_button("👑 Creator", callback_data="help_cat_creator_p1", style="success"))
    if admin_row:
        buttons.append(admin_row)

    buttons.append([
        styled_button("🔍 Search Library", callback_data="search_menu", style="success"),
        styled_button("📊 My Quota", callback_data="quota", style="primary"),
    ])
    buttons.append([styled_button("« Back to Start", callback_data="start_menu", style="primary")])

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
            [styled_button(f"« Back to {category.capitalize()} Menu", callback_data=f"help_cat_{category}_p1", style="primary")],
            [styled_button("« Main Help Hub", callback_data="help_main", style="success")],
        ])
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
