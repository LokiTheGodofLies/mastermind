from config import bot_name
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import ContextTypes
except ImportError:
    class InlineKeyboardButton:
        def __init__(self, text, callback_data=None, url=None):
            self.text = text
            self.callback_data = callback_data
            self.url = url
    class InlineKeyboardMarkup:
        def __init__(self, inline_keyboard):
            self.inline_keyboard = inline_keyboard
    Update = object
    class ContextTypes:
        DEFAULT_TYPE = object

from modules.database.user_db import get_user_role_db, is_admin_or_creator, is_creator


# ---------------------------------------------------------------------------
# Individual Command & Feature Documentation Cards (with Emojis)
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
            "displays the interactive main menu, and handles one-tap book download links.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/start</code>\n"
            "• <code>/start</code> dl_&lt;file_id&gt;\n\n"
            "📌 <b>Examples:</b>\n"
            "• Send <code>/start</code> in private chat to open the main menu.\n"
            "• Click any download button in search results to receive files instantly via <code>/start</code> dl_6."
        ),
    },
    "search": {
        "title": "🔍 search",
        "category": "user",
        "text": (
            "🔍 <b>Command:</b> <code>/search</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Searches our community library across book titles, authors, series, and descriptions.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/search</code> &lt;book title or author&gt;\n\n"
            "📌 <b>Examples:</b>\n"
            "• <code>/search</code> Percy Jackson\n"
            "• <code>/search</code> Haunting Adeline\n"
            "• <code>/search</code> Colleen Hoover\n\n"
            "✨ <i>Tip: Results feature format filters (📚 Ebooks / 🎧 Audiobooks) and deep-link downloads!</i>"
        ),
    },
    "request": {
        "title": "📥 request",
        "category": "user",
        "text": (
            "📥 <b>Command:</b> <code>/request</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Submits a request for any missing book or audiobook directly to our community Request Channel.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/request</code> &lt;book title and author&gt;\n\n"
            "📌 <b>Examples:</b>\n"
            "• <code>/request</code> Fourth Wing by Rebecca Yarros\n"
            "• <code>/request</code> A Court of Thorns and Roses by Sarah J. Maas\n\n"
            "✨ <i>Tip: Moderators review requests and update status buttons live!</i>"
        ),
    },
    "quota": {
        "title": "📊 quota",
        "category": "user",
        "text": (
            "📊 <b>Command:</b> <code>/quota</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Displays your live daily search and request balance, your account tier, and midnight IST reset timer.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/quota</code>\n\n"
            "📌 <b>Example:</b>\n"
            "• Send <code>/quota</code> in any chat to view your remaining daily quota card.\n\n"
            "🏆 <b>Daily Allowances by Tier:</b>\n"
            "• 👤 User: 10 searches & 10 requests\n"
            "• 📣 Promoter: 20 searches & 20 requests\n"
            "• 🤝 Volunteer: 30 searches & 30 requests\n"
            "• 🛡️ Moderator: 40 searches & 40 requests\n"
            "• ⚔️ Administrator: Unlimited"
        ),
    },
    "refer": {
        "title": "🔗 refer",
        "category": "user",
        "text": (
            "🔗 <b>Commands:</b> <code>/refer</code> & <code>/myreferrals</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Generates your personal invite link. Invite friends to join our library and earn bonus searches & requests!\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/refer</code> (generates your unique invite link)\n"
            "• <code>/myreferrals</code> (checks your invite stats and bonus balance)\n\n"
            "📌 <b>Examples:</b>\n"
            "• Send <code>/refer</code> to copy your invite link.\n"
            "• Send <code>/myreferrals</code> to check how many friends joined through your link.\n\n"
            "🎁 <b>Reward:</b> +10 searches & +10 requests per successful invite!"
        ),
    },
    "support": {
        "title": "💬 support",
        "category": "user",
        "text": (
            "💬 <b>Command:</b> <code>/support</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Provides the direct invite link to our official community support group for reading discussions, help, and feedback.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/support</code>\n\n"
            "📌 <b>Example:</b>\n"
            "• Send <code>/support</code> to receive the official community join button."
        ),
    },
    "stats": {
        "title": "📈 stats",
        "category": "user",
        "text": (
            "📈 <b>Command:</b> <code>/stats</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Displays live library metrics, including total indexed books, separate ebook and audiobook counts, active users, and system uptime.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/stats</code>\n\n"
            "📌 <b>Example:</b>\n"
            "• Send <code>/stats</code> to inspect current library and system metrics."
        ),
    },
    "id": {
        "title": "🆔 id",
        "category": "user",
        "text": (
            "🆔 <b>Command:</b> <code>/id</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Retrieves unique Telegram IDs for users, groups, channels, or forum topics.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/id</code>\n"
            "• <code>/id</code> @username\n"
            "• Reply to any message with <code>/id</code>\n\n"
            "📌 <b>Examples:</b>\n"
            "• Send <code>/id</code> to view your own User ID and Chat ID.\n"
            "• <code>/id</code> @HDCarltonbot\n"
            "• Reply to any message with <code>/id</code> to inspect that user\'s info."
        ),
    },
    "rosters": {
        "title": "👥 rosters",
        "category": "user",
        "text": (
            "👥 <b>Community Roster Commands</b>\n\n"
            "View official lists of community team members with direct profile links:\n\n"
            "💡 <b>Commands & Examples:</b>\n"
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
            "When you download a file from search results, the bot offers two delivery methods:\n\n"
            "1. <b>🤖 Fast PM Delivery:</b> The file is sent directly to your private chat via helper bots (with 5-minute auto-delete).\n"
            "2. <b>📢 Posting Channel:</b> A temporary copy is posted in the channel (with 5-minute auto-delete).\n\n"
            "⚠️ <b>Important Tip:</b>\n"
            "Forward your received files to your <b>Saved Messages</b> before the 5-minute timer expires!"
        ),
    },
    "roles": {
        "title": "👥 roles",
        "category": "user",
        "text": (
            "👥 <b>Community User Roles & Privileges Breakdown</b>\n\n"
            "Our community has 6 structured tiers to organize library contributions and governance:\n\n"
            "👤 <b>Normal User:</b>\n"
            "• Quota: 10 daily searches & 10 daily requests.\n"
            "• Access: /start, /search, /request, /quota, /refer, /support, /stats, /id, rosters.\n\n"
            "📣 <b>Promoter:</b>\n"
            "• Quota: 20 daily searches & 20 daily requests.\n"
            "• Appointed by Admins to share and promote our community library.\n\n"
            "🤝 <b>Volunteer:</b>\n"
            "• Quota: 30 daily searches & 30 daily requests.\n"
            "• Pre-approved direct book & audiobook indexing via Helper Bot DMs.\n\n"
            "🛡️ <b>Moderator:</b>\n"
            "• Quota: 40 daily searches & 40 daily requests.\n"
            "• Direct indexing + Request Channel status management (Pending, Processing, Completed, Rejected).\n\n"
            "⚔️ <b>Administrator:</b>\n"
            "• Quota: Unlimited searches & requests.\n"
            "• Batch range indexing (/index), announcements (/broadcast), bans (/ban), gifts (/gift), and team promotions.\n\n"
            "👑 <b>Creator:</b>\n"
            "• Supreme governance, admin appointments (/addadmin), production deployment (/publish), and system backups."
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
            "• <b>Daily Quota:</b> 30 searches and 30 requests per day.\n"
            "• <b>Direct Indexing:</b> Send or forward supported ebooks or audiobooks directly to any Helper Bot in private chat.\n"
            "• <b>Automatic Approval:</b> Files uploaded by Volunteers are stored in the library without requiring admin review."
        ),
    },
    "vol_indexing": {
        "title": "📚 vol_indexing",
        "category": "volunteer",
        "text": (
            "📚 <b>Volunteer Helper Bot Indexing Guide</b>\n\n"
            "1. Start a private chat with any official Helper Bot (e.g. @Heyuqtbot or @RickRiordanBot).\n"
            "2. Send or forward supported book (.epub, .pdf, .mobi, .azw) or audiobook (.mp3, .m4b, .flac) files.\n"
            "3. The bot extracts metadata, enriches book details, stores the file in the Storage Group, and logs it automatically!"
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
            "• <b>Daily Quota:</b> 40 searches and 40 requests per day.\n"
            "• <b>Request Channel Control:</b> Update status buttons on incoming book requests.\n"
            "• <b>Direct Library Indexing:</b> Pre-approved direct indexing via Helper Bot DMs."
        ),
    },
    "mod_requests": {
        "title": "📋 mod_requests",
        "category": "moderator",
        "text": (
            "📋 <b>Request Status Management</b>\n\n"
            "When users submit book requests via <code>/request</code>, they appear in the Request Channel.\n"
            "Moderators use inline buttons to update the status:\n"
            "• ⏳ <b>Pending:</b> Request is awaiting review.\n"
            "• 🔄 <b>Processing:</b> Request is currently being sourced.\n"
            "• ✅ <b>Completed:</b> File was found and indexed into the library.\n"
            "• ❌ <b>Rejected:</b> Book cannot be fulfilled."
        ),
    },
    "mod_indexing": {
        "title": "🤖 mod_indexing",
        "category": "moderator",
        "text": (
            "🤖 <b>Moderator Direct Indexing Guide</b>\n\n"
            "Send or forward supported ebook and audiobook files directly to any Helper Bot in private chat.\n"
            "Metadata is enriched automatically across multiple book databases and stored in the library."
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
            "Audits all configured helper delivery bots. Verifies token reachability, username resolution, "
            "presence in the Storage Group, and admin rights in the Posting Channel.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/checkhelpers</code>\n"
            "• <code>/helpers</code>\n\n"
            "📌 <b>Example:</b>\n"
            "• Send <code>/checkhelpers</code> to inspect your helper bot delivery fleet."
        ),
    },
    "index": {
        "title": "📚 index",
        "category": "admin",
        "text": (
            "📚 <b>Command:</b> <code>/index</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Batch indexes ebooks and audiobooks from channels or groups into the Storage Group with multi-site metadata enrichment.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/index</code> &lt;first_link&gt; &lt;last_link&gt;\n"
            "• <code>/index</code> [skip_count] (in source channel)\n"
            "• <code>/index</code> (in private chat for interactive wizard)\n\n"
            "📌 <b>Examples:</b>\n"
            "• <code>/index</code> https://t.me/c/12345/10 https://t.me/c/12345/50\n"
            "• <code>/index</code> 5\n"
            "• <code>/index</code>"
        ),
    },
    "broadcast": {
        "title": "📢 broadcast",
        "category": "admin",
        "text": (
            "📢 <b>Command:</b> <code>/broadcast</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Dispatches announcements with interactive audience filters (Users, Groups, Channels, or All), "
            "auto-pinning, and live Pause/Resume/Cancel controls.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/broadcast</code> &lt;announcement text&gt;\n"
            "• Reply to any message or media with <code>/broadcast</code>\n"
            "• <code>/pausebroadcast</code> — Pauses the ongoing broadcast\n"
            "• <code>/resumebroadcast</code> — Resumes a paused broadcast\n"
            "• <code>/cancelbroadcast</code> — Cancels the broadcast\n\n"
            "📌 <b>Examples:</b>\n"
            "• <code>/broadcast</code> 📚 We have added 100 new fantasy books to the catalog!\n"
            "• <code>/pausebroadcast</code>\n"
            "• <code>/resumebroadcast</code>"
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
            "• <code>/unban</code> &lt;user_id or @username&gt;\n\n"
            "📌 <b>Examples:</b>\n"
            "• <code>/ban</code> 123456789 Spamming promotional links\n"
            "• <code>/ban_pm</code> @bad_user\n"
            "• <code>/unban</code> 123456789"
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
            "• <code>/gift</code> 123456789 25 25\n"
            "• <code>/gift</code> 987654321 50 10"
        ),
    },
    "editscript": {
        "title": "🛠️ editscript",
        "category": "admin",
        "text": (
            "🛠️ <b>Command:</b> <code>/editscript</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Opens the dynamic configuration hub to modify banners, welcome messages, caption templates, "
            "and channel links live without restarting the bot.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/editscript</code>\n\n"
            "📌 <b>Example:</b>\n"
            "• Send <code>/editscript</code> to open the dynamic template management menu."
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
            "• <code>/log</code> &lt;duration, e.g. 1h, 30m&gt;\n\n"
            "📌 <b>Examples:</b>\n"
            "• <code>/log</code>\n"
            "• <code>/log</code> 500\n"
            "• <code>/log</code> 2h"
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
            "• <code>/ping</code>\n\n"
            "📌 <b>Example:</b>\n"
            "• Send <code>/ping</code> to verify bot health and response latency."
        ),
    },
    "addmoderator": {
        "title": "🛡️ addmoderator",
        "category": "admin",
        "text": (
            "🛡️ <b>Commands:</b> <code>/addmoderator</code> & <code>/removemoderator</code>\n"
            "<i>(Aliases: /addmod, /removemod, /delmod)</i>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Promotes or demotes a Moderator (40 daily quota, request management buttons).\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/addmoderator</code> &lt;user_id or @username&gt;\n"
            "• <code>/removemoderator</code> &lt;user_id or @username&gt;\n\n"
            "📌 <b>Examples:</b>\n"
            "• <code>/addmoderator</code> 123456789\n"
            "• <code>/removemoderator</code> @username"
        ),
    },
    "addvolunteer": {
        "title": "🤝 addvolunteer",
        "category": "admin",
        "text": (
            "🤝 <b>Commands:</b> <code>/addvolunteer</code> & <code>/removevolunteer</code>\n"
            "<i>(Aliases: /addvol, /removevol, /delvol)</i>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Promotes or demotes a Volunteer (30 daily quota, pre-approved helper indexing).\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/addvolunteer</code> &lt;user_id or @username&gt;\n"
            "• <code>/removevolunteer</code> &lt;user_id or @username&gt;\n\n"
            "📌 <b>Examples:</b>\n"
            "• <code>/addvolunteer</code> 123456789\n"
            "• <code>/removevolunteer</code> @username"
        ),
    },
    "addpromoter": {
        "title": "📣 addpromoter",
        "category": "admin",
        "text": (
            "📣 <b>Commands:</b> <code>/addpromoter</code> & <code>/removepromoter</code>\n"
            "<i>(Aliases: /addpromo, /removepromo, /delpromo)</i>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Promotes or demotes a Promoter (20 daily quota).\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/addpromoter</code> &lt;user_id or @username&gt;\n"
            "• <code>/removepromoter</code> &lt;user_id or @username&gt;\n\n"
            "📌 <b>Examples:</b>\n"
            "• <code>/addpromoter</code> 123456789\n"
            "• <code>/removepromoter</code> @username"
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
            "Merges the tested & verified <code>test</code> branch into <code>main</code> and pushes to "
            "both <code>loki main</code> and <code>origin main</code> using authenticated refspecs.\n"
            "Triggers the live deployment on Render Public Books Bot with a single tap right from Telegram!\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/publish</code>\n\n"
            "📌 <b>Example:</b>\n"
            "• Send <code>/publish</code> in Telegram after verifying features on the testing bot.\n\n"
            "🔒 <b>Access:</b> Creator Only 👑"
        ),
    },
    "update": {
        "title": "📦 update",
        "category": "creator",
        "text": (
            "📦 <b>Command:</b> <code>/update</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Updates bot code directly in-chat without Termux. Send or reply to an updated <code>.zip</code> file with <code>/update</code>.\n"
            "The bot unpacks the code, verifies with compileall, commits, and pushes to GitHub automatically!\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/update</code> (as caption or reply to a .zip archive)\n\n"
            "📌 <b>Example:</b>\n"
            "• Forward <code>mastermind-test-updated-....zip</code> to the bot with caption <code>/update</code>.\n\n"
            "🔒 <b>Access:</b> Creator Only 👑"
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
            "📌 <b>Examples:</b>\n"
            "• <code>/sh</code> git status\n"
            "• <code>/sh</code> git log -1 --oneline\n"
            "• <code>/sh</code> df -h\n\n"
            "🔒 <b>Access:</b> Creator Only 👑"
        ),
    },
    "addadmin": {
        "title": "👑 addadmin",
        "category": "creator",
        "text": (
            "👑 <b>Commands:</b> <code>/addadmin</code> & <code>/removeadmin</code>\n"
            "<i>(Alias: /deladmin)</i>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Appoints or removes an Administrator. Exclusive to the Creator.\n\n"
            "💡 <b>Syntax:</b>\n"
            "• <code>/addadmin</code> &lt;user_id or @username&gt;\n"
            "• <code>/removeadmin</code> &lt;user_id or @username&gt;\n\n"
            "📌 <b>Examples:</b>\n"
            "• <code>/addadmin</code> 123456789\n"
            "• <code>/removeadmin</code> @username\n\n"
            "🔒 <b>Access:</b> Creator Only 👑"
        ),
    },
    "creator_privileges": {
        "title": "♾️ creator_privileges",
        "category": "creator",
        "text": (
            "👑 <b>Creator Supreme Authority</b>\n\n"
            "The Creator has absolute governance across all bot operations, helper pools, "
            "database persistence, and administrative appointments.\n\n"
            "🔒 <b>Access:</b> Creator Only 👑"
        ),
    },
    "backup": {
        "title": "💾 backup",
        "category": "creator",
        "text": (
            "💾 <b>Automated SQLite Backups</b>\n\n"
            "Backups of <code>files.db</code>, <code>users.db</code>, and <code>config.db</code> are compiled into a ZIP archive "
            "every 6 hours and dispatched to the designated Backup Topic.\n\n"
            "🔒 <b>Access:</b> Creator Only 👑"
        ),
    },
    "governance": {
        "title": "⚙️ governance",
        "category": "creator",
        "text": (
            "⚙️ <b>Global Architecture & Identity Governance</b>\n\n"
            "Environment configuration, isolated Public/Testing credentials, and Render deployment monitoring.\n\n"
            "🔒 <b>Access:</b> Creator Only 👑"
        ),
    },
}


# ---------------------------------------------------------------------------
# Menu Builders with Pagination (Max 6 buttons per page, Clean Command Labels with Emojis)
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
        f"<b>{cat_title}</b> (Page {page}/{total_pages})\n\n"
        "Tap any command below to inspect its purpose, syntax, and examples:"
    )

    buttons = []
    # 2 columns per row
    row = []
    for key in page_keys:
        item = COMMAND_DETAILS.get(key, {})
        label = item.get("title", key)
        row.append(InlineKeyboardButton(label, callback_data=f"help_cmd_{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Navigation Row
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️ Prev", callback_data=f"help_cat_{category}_p{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("Next ▶️", callback_data=f"help_cat_{category}_p{page + 1}"))
    buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("« Back to Categories", callback_data="help_main")])
    return text, InlineKeyboardMarkup(buttons)


def build_main_help_menu(user_id: int):
    """
    Builds the main help menu page:
    1. Only displays categories accessible to the user\'s role level.
    2. Includes a dedicated '👥 roles' button directly on the main page.
    """
    role = get_user_role_db(user_id)
    is_creator_user = is_creator(user_id)
    is_admin = is_admin_or_creator(user_id)
    is_mod = (role in ("Moderator", "Admin", "Creator", "Owner"))
    is_vol = (role in ("Volunteer", "Moderator", "Admin", "Creator", "Owner"))

    text = (
        f"📖 <b>{bot_name()} Bot — Help & Documentation</b>\n\n"
        "Welcome! Browse our official documentation below:\n\n"
        f"👤 <b>Your Access Level:</b> <code>{role}</code>\n\n"
        "Select a section below to view available functions and guides:"
    )

    buttons = [
        [
            InlineKeyboardButton("👤 user", callback_data="help_cat_user_p1"),
            InlineKeyboardButton("👥 roles", callback_data="help_cmd_roles"),
        ],
    ]

    second_row = []
    if is_vol:
        second_row.append(InlineKeyboardButton("🤝 volunteer", callback_data="help_cat_volunteer_p1"))
    if is_mod:
        second_row.append(InlineKeyboardButton("🛡️ moderator", callback_data="help_cat_moderator_p1"))
    if second_row:
        buttons.append(second_row)

    admin_row = []
    if is_admin:
        admin_row.append(InlineKeyboardButton("⚔️ admin", callback_data="help_cat_admin_p1"))
    if is_creator_user:
        admin_row.append(InlineKeyboardButton("👑 creator", callback_data="help_cat_creator_p1"))
    if admin_row:
        buttons.append(admin_row)

    buttons.append([
        InlineKeyboardButton("🔍 search", callback_data="search_menu"),
        InlineKeyboardButton("📊 quota", callback_data="quota"),
    ])
    buttons.append([InlineKeyboardButton("« Back to Start", callback_data="start_menu")])

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
            [InlineKeyboardButton(f"« Back to {category.capitalize()} Menu", callback_data=f"help_cat_{category}_p1")],
            [InlineKeyboardButton("« Main Help Hub", callback_data="help_main")],
        ])
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
