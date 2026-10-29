from config import bot_name
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.database.user_db import get_user_role_db, is_admin_or_god, is_god


# ---------------------------------------------------------------------------
# Individual Command & Feature Documentation Cards
# ---------------------------------------------------------------------------
COMMAND_DETAILS = {
    # =======================================================================
    # 👤 USER COMMANDS & GUIDES
    # =======================================================================
    "rosters": {
        "title": "👥 Community Roster Commands",
        "category": "user",
        "text": (
            "👥 <b>Community Roster Commands</b>\n\n"
            "View real-time lists of community members with direct profile links:\n\n"
            "• <code>/admins</code>: Lists all Administrators and GOD.\n"
            "• <code>/moderators</code>: Lists all active Moderators (alias: <code>/mods</code>).\n"
            "• <code>/volunteers</code>: Lists all active Volunteers (alias: <code>/vols</code>).\n"
            "• <code>/promoters</code>: Lists all active Promoters (alias: <code>/promos</code>)."
        ),
    },
    "broadcast": {
        "title": "📢 /broadcast & /pinbroadcast Commands",
        "category": "admin",
        "text": (
            "📢 <b>Broadcast & Pinning Commands</b>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Dispatches announcements across all users, groups, and channels with multi-bot tracking and optional pinning.\n\n"
            "💡 <b>Usage:</b>\n"
            "• Reply to any message with <code>/broadcast</code> to open the multi-target dashboard.\n"
            "• Reply with <code>/pinbroadcast</code> to broadcast and auto-pin the message in groups/channels.\n"
            "• Direct targets: <code>/broadcast &lt;id1 id2 ...&gt;</code> in reply to message.\n"
            "• Segment stop: <code>/cancelbroadcast &lt;bot_username&gt; &lt;users|groups|channels&gt;</code>\n\n"
            "🔒 <b>Access:</b> Administrators & GOD"
        ),
    },

    "start": {
        "title": "🚀 /start Command",
        "category": "user",
        "text": (
            "🚀 <b>Command:</b> <code>/start</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Launches the main interactive welcome dashboard, registers your user profile in the database, "
            "and unlocks file download deep-links.\n\n"
            "💡 <b>Usage:</b>\n"
            "• Send <code>/start</code> in private chat to open the main menu.\n"
            "• Referral link format: <code>/start ref_&lt;user_id&gt;</code>\n"
            "• File download link: <code>/start dl_&lt;file_id&gt;</code>\n\n"
            "📋 <b>Example:</b>\n"
            "<code>/start</code>"
        ),
    },
    "search": {
        "title": "🔍 /search Command",
        "category": "user",
        "text": (
            "🔍 <b>Command:</b> <code>/search &lt;query&gt;</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Searches the indexed library of ebooks and audiobooks using tokenized keyword matching. "
            "Shows page navigation and download buttons for instant dual-delivery.\n\n"
            "💡 <b>Usage:</b>\n"
            "• <code>/search &lt;title or author&gt;</code>\n"
            "• Reply to any message containing a title with <code>/search</code>.\n"
            "• Send <code>/search</code> alone to generate a single-use search group invite.\n\n"
            "📋 <b>Example:</b>\n"
            "<code>/search The Striker Ana Huang</code>"
        ),
    },
    "request": {
        "title": "📥 /request Command",
        "category": "user",
        "text": (
            "📥 <b>Command:</b> <code>/request &lt;query&gt;</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Requests books not yet available in the library. If matches already exist in our database, "
            "it prompts you with an interactive [🔍 Search in Library] button. Otherwise, it enriches the request "
            "with Goodreads metadata and forwards it directly to the request channel.\n\n"
            "💡 <b>Usage & Templates:</b>\n"
            "• Quick Request: <code>/request King of Wrath</code>\n"
            "• Standalone Template:\n"
            "<code>/request\nTitle: The Striker\nAuthor: Ana Huang\nFormat: Audiobook / EPUB</code>\n"
            "• Series Template:\n"
            "<code>/request\nTitle 1: King of Wrath\nTitle 2: King of Pride\nSeries: Kings of Sin\nAuthor: Ana Huang\nFormat: EPUB</code>"
        ),
    },
    "quota": {
        "title": "📊 /quota Command",
        "category": "user",
        "text": (
            "📊 <b>Command:</b> <code>/quota</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Displays your user role and remaining daily search and book request allowances. "
            "Quotas reset automatically every 24 hours.\n\n"
            "💡 <b>Usage:</b>\n"
            "<code>/quota</code>\n\n"
            "📋 <b>Tip:</b>\n"
            "Need more allowance? Share your invite link via <code>/refer</code> to earn permanent bonuses!"
        ),
    },
    "refer": {
        "title": "🔗 /refer & /myreferrals",
        "category": "user",
        "text": (
            "🔗 <b>Commands:</b> <code>/refer</code> & <code>/myreferrals</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Generates your personal referral link to invite friends. When a friend starts the bot via your link, "
            "both of you receive bonus search and request allowances!\n\n"
            "💡 <b>Usage:</b>\n"
            "• <code>/refer</code> (or <code>/ref</code>): View your link and share directly to chats.\n"
            "• <code>/myreferrals</code>: Check your invite history, total friends invited, and total bonuses earned.\n\n"
            "📋 <b>Example Link:</b>\n"
            "<code>https://t.me/YourBot?start=ref_123456789</code>"
        ),
    },
    "support": {
        "title": "🛡️ /support Command",
        "category": "user",
        "text": (
            "🛡️ <b>Command:</b> <code>/support</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Opens the Support Center verification screening quiz. Protects our community support group from spam, "
            "bots, and raids by generating a secure single-use invite link upon passing 10 quick screening questions.\n\n"
            "💡 <b>Usage:</b>\n"
            "<code>/support</code>\n\n"
            "📋 <b>Example:</b>\n"
            "Tap 'Start Verification Quiz' and answer the 10 Yes/No screening questions."
        ),
    },
    "stats": {
        "title": "📈 /stats Command",
        "category": "user",
        "text": (
            "📈 <b>Command:</b> <code>/stats</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Displays public operational metrics, server uptime, and media banners. "
            "Administrators also see extended internal database connection status.\n\n"
            "💡 <b>Usage:</b>\n"
            "<code>/stats</code>"
        ),
    },
    "roles": {
        "title": "👥 User Roles & Hierarchy",
        "category": "user",
        "text": (
            "👥 <b>User Roles & Access Hierarchy</b>\n\n"
            "Every user in the library belongs to a specific role with dedicated daily allowances and privileges:\n\n"
            "• 👑 <b>GOD:</b>\n"
            "  - Supreme system creator & authority.\n"
            "  - Unlimited searches and requests.\n"
            "  - Immunity from bans, admin promotion/demotion, and total governance.\n\n"
            "• ⚔️ <b>Admin:</b>\n"
            "  - System administrators.\n"
            "  - Unlimited searches and requests.\n"
            "  - Can ban/unban users, audit helper bots, batch index ranges, grant quota gifts, and access the admin hub.\n\n"
            "• 🛡️ <b>Moderator:</b>\n"
            "  - Community & library moderators.\n"
            "  - 40 searches & 40 requests daily.\n"
            "  - Can index ebooks & audiobooks without approval via Helper Bot DMs.\n"
            "  - Can change request statuses (In Progress, Completed, Rejected) in the request channel.\n\n"
            "• 🤝 <b>Volunteer:</b>\n"
            "  - Community library contributors.\n"
            "  - 30 searches & 30 requests daily.\n"
            "  - Can index ebooks & audiobooks without approval by sending files to Helper Bot DMs.\n\n"
            "• 📣 <b>Promoter:</b>\n"
            "  - Active community advocates.\n"
            "  - 20 searches & 20 requests daily.\n\n"
            "• 👤 <b>Normal User:</b>\n"
            "  - Standard library members.\n"
            "  - 10 searches & 10 requests daily.\n"
            "  - Can earn permanent bonuses via <code>/refer</code>!"
        ),
    },
    "delivery": {
        "title": "📥 Dual File Delivery Guide",
        "category": "user",
        "text": (
            "📥 <b>How Dual File Delivery Works</b>\n\n"
            "To ensure fast downloads and comply with Telegram limits, Mastermind uses <b>Helper Bots</b> for all file transfers:\n\n"
            "1. <b>Main Bot Stays Clean:</b> The main bot coordinates searches, quotas, and requests, but never hosts or sends files directly.\n"
            "2. <b>Posting Channel Delivery:</b> When you download a book, a helper bot posts it to our Posting Channel with a 5-minute auto-deletion timer.\n"
            "3. <b>Direct PM Delivery:</b> If you have started the helper bot in private messages, it simultaneously sends the file directly to your PM!\n\n"
            "💡 <i>Tip: Tap '🤖 Start @HelperBot' when prompted so you receive all files directly in your DM!</i>"
        ),
    },

    # =======================================================================
    # 🤝 VOLUNTEER COMMANDS & GUIDES
    # =======================================================================
    "vol_priv": {
        "title": "📚 Volunteer Privileges & Quota",
        "category": "volunteer",
        "text": (
            "📚 <b>Volunteer Privileges & Allowance</b>\n\n"
            "As a verified <b>Volunteer</b>, you have elevated allowances and direct contribution rights:\n\n"
            "• <b>Daily Searches:</b> 30 searches per day.\n"
            "• <b>Daily Requests:</b> 30 requests per day.\n"
            "• <b>Direct Indexing:</b> You can contribute ebooks and audiobooks directly to the library without requiring administrator approval!"
        ),
    },
    "vol_index": {
        "title": "🤖 Helper Bot Direct Indexing",
        "category": "volunteer",
        "text": (
            "🤖 <b>Direct Indexing via Helper Bot DMs</b>\n\n"
            "📝 <b>How to Index Books:</b>\n"
            "1. Open a direct private chat (DM) with any of our configured <b>Helper Bots</b>.\n"
            "2. Send or forward any supported ebook or audiobook file directly to the helper bot:\n"
            "   • <b>Supported Ebooks:</b> <code>.epub, .pdf, .azw, .azw3, .mobi, .cbz, .cbr</code>\n"
            "   • <b>Supported Audiobooks:</b> <code>.mp3, .m4b, .aax, .aa, .flac, .wav</code>\n"
            "3. The helper bot will automatically extract metadata, query Goodreads for author/title/cover/rating, "
            "store the file in the library storage group, and confirm with ✅ <i>Successfully indexed!</i>\n\n"
            "⚡ <b>No Approval Needed:</b> Volunteers have pre-approved indexing authority!"
        ),
    },
    "vol_notice": {
        "title": "⚠️ /index Command Restriction Notice",
        "category": "volunteer",
        "text": (
            "⚠️ <b>Index Command Access Notice</b>\n\n"
            "Please note that the <code>/index</code> batch command is reserved exclusively for Administrators and GOD.\n\n"
            "💡 <b>Why?</b>\n"
            "The <code>/index</code> command performs mass batch dumps across entire channel ranges. "
            "Volunteers and Moderators contribute files directly by sending them to <b>Helper Bot DMs</b>, "
            "which processes each file instantly without approvals!"
        ),
    },

    # =======================================================================
    # 🛡️ MODERATOR COMMANDS & GUIDES
    # =======================================================================
    "mod_priv": {
        "title": "⚖️ Moderator Privileges & Quota",
        "category": "moderator",
        "text": (
            "⚖️ <b>Moderator Privileges & Allowance</b>\n\n"
            "As a verified <b>Moderator</b>, you help manage community requests and library quality:\n\n"
            "• <b>Daily Searches:</b> 40 searches per day.\n"
            "• <b>Daily Requests:</b> 40 requests per day.\n"
            "• <b>Request Status Management:</b> Access to interactive status buttons in the request channel.\n"
            "• <b>Direct Indexing:</b> Pre-approved direct indexing via Helper Bot DMs."
        ),
    },
    "mod_status": {
        "title": "📋 Request Status Management",
        "category": "moderator",
        "text": (
            "📋 <b>Request Status Management Buttons</b>\n\n"
            "📝 <b>How to Update Requests:</b>\n"
            "When users submit a book request, it appears in the Request Channel with interactive buttons:\n\n"
            "• <code>[⏳ In Progress]</code>: Mark that you or a volunteer are currently locating the title.\n"
            "• <code>[✅ Completed]</code>: Mark that the book has been added to the library.\n"
            "• <code>[❌ Rejected]</code>: Mark if the request is duplicate, unreleased, or invalid.\n\n"
            "Tapping any button updates the post live and stamps your moderator username!"
        ),
    },
    "mod_index": {
        "title": "🤖 Helper Bot Direct Indexing",
        "category": "moderator",
        "text": (
            "🤖 <b>Direct Indexing via Helper Bot DMs</b>\n\n"
            "Moderators have full pre-approved indexing authority.\n\n"
            "Simply send or forward supported ebook or audiobook files to any Helper Bot in private chat. "
            "The bot enriches metadata, stores the file in <code>STORAGE_GROUP_ID</code>, and records it in the database immediately."
        ),
    },
    "mod_notice": {
        "title": "⚠️ /index Command Restriction Notice",
        "category": "moderator",
        "text": (
            "⚠️ <b>Index Command Access Notice</b>\n\n"
            "The <code>/index</code> batch range command is exclusive to Administrators and GOD.\n"
            "Moderators index files cleanly and reliably via Helper Bot private messages."
        ),
    },

    # =======================================================================
    # ⚔️ ADMINISTRATOR COMMANDS & GUIDES
    # =======================================================================
    "addmoderator": {
        "title": "🛡️ /addmoderator & /removemoderator",
        "category": "admin",
        "text": (
            "🛡️ <b>Commands:</b> <code>/addmoderator</code> & <code>/removemoderator</code>\n"
            "<i>(Aliases: <code>/addmod</code>, <code>/removemod</code>, <code>/delmod</code>)</i>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Promotes a user to <b>Moderator</b> or demotes them to Normal User. "
            "Grants 40 daily searches/requests, helper bot direct indexing, and request status management buttons.\n\n"
            "💡 <b>Usage:</b>\n"
            "• <code>/addmoderator &lt;user_id|@username&gt;</code>\n"
            "• <code>/removemoderator &lt;user_id|@username&gt;</code>\n"
            "• Or reply to a user's message with <code>/addmod</code> or <code>/delmod</code>.\n\n"
            "📋 <b>Access:</b> Administrators & GOD"
        ),
    },
    "addvolunteer": {
        "title": "🤝 /addvolunteer & /removevolunteer",
        "category": "admin",
        "text": (
            "🤝 <b>Commands:</b> <code>/addvolunteer</code> & <code>/removevolunteer</code>\n"
            "<i>(Aliases: <code>/addvol</code>, <code>/removevol</code>, <code>/delvol</code>)</i>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Promotes a user to <b>Volunteer</b> or demotes them to Normal User. "
            "Grants 30 daily searches/requests and pre-approved direct indexing via Helper Bot DMs.\n\n"
            "💡 <b>Usage:</b>\n"
            "• <code>/addvolunteer &lt;user_id|@username&gt;</code>\n"
            "• <code>/removevolunteer &lt;user_id|@username&gt;</code>\n"
            "• Or reply to a user's message with <code>/addvol</code> or <code>/delvol</code>.\n\n"
            "📋 <b>Access:</b> Administrators & GOD"
        ),
    },
    "addpromoter": {
        "title": "📣 /addpromoter & /removepromoter",
        "category": "admin",
        "text": (
            "📣 <b>Commands:</b> <code>/addpromoter</code> & <code>/removepromoter</code>\n"
            "<i>(Aliases: <code>/addpromo</code>, <code>/removepromo</code>, <code>/delpromo</code>)</i>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Promotes a user to <b>Promoter</b> or demotes them to Normal User. "
            "Grants 20 daily searches and 20 daily requests.\n\n"
            "💡 <b>Usage:</b>\n"
            "• <code>/addpromoter &lt;user_id|@username&gt;</code>\n"
            "• <code>/removepromoter &lt;user_id|@username&gt;</code>\n"
            "• Or reply to a user's message with <code>/addpromo</code> or <code>/delpromo</code>.\n\n"
            "📋 <b>Access:</b> Administrators & GOD"
        ),
    },

    "checkhelpers": {
        "title": "🤖 /checkhelpers Command",
        "category": "admin",
        "text": (
            "🤖 <b>Command:</b> <code>/checkhelpers</code> (alias: <code>/helpers</code>)\n\n"
            "📝 <b>Purpose:</b>\n"
            "Audits all configured helper delivery bots in <code>HELPER_BOT_TOKENS</code>. "
            "Verifies token reachability, username resolution, presence in the Storage Group, and "
            "verifies administrator rights (Post & Delete rights) in the Posting Channel for 5-min auto-delete.\n\n"
            "💡 <b>Usage:</b>\n"
            "<code>/checkhelpers</code>\n\n"
            "📋 <b>Access:</b> Administrators & GOD"
        ),
    },
    "index": {
        "title": "📚 /index Command",
        "category": "admin",
        "text": (
            "📚 <b>Command:</b> <code>/index</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Batch indexes ebooks (.epub, .pdf, .azw, .azw3, .mobi, .cbz, .cbr) and audiobooks "
            "(.mp3, .m4b, .aax, .aa, .flac, .wav) into the Storage Group with Goodreads metadata enrichment.\n\n"
            "💡 <b>Usage:</b>\n"
            "• Range links: <code>/index &lt;first_msg_link&gt; &lt;last_msg_link&gt;</code>\n"
            "• In source dump chat: <code>/index [skip_count]</code>\n"
            "• In private chat: send <code>/index</code> for interactive step-by-step setup.\n\n"
            "📋 <b>Example:</b>\n"
            "<code>/index https://t.me/c/12345/1 https://t.me/c/12345/250</code>\n\n"
            "🔒 <b>Access:</b> Administrators & GOD Only"
        ),
    },
    "ban": {
        "title": "🚫 /ban & /unban Commands",
        "category": "admin",
        "text": (
            "🚫 <b>Commands:</b> <code>/ban</code>, <code>/ban_pm</code>, <code>/ban_support</code>, <code>/unban</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Applies or lifts granular restrictions on users or chats:\n"
            "• <code>/ban &lt;id|@username&gt; [reason]</code>: Block everywhere.\n"
            "• <code>/ban_pm &lt;id|@username&gt; [reason]</code>: Block in private messages only.\n"
            "• <code>/ban_support &lt;id|@username&gt; [reason]</code>: Restrict to support group only.\n"
            "• <code>/unban &lt;id|@username&gt;</code>: Completely lifts all restrictions.\n\n"
            "📋 <b>Example:</b>\n"
            "<code>/ban 123456789 spamming commands</code>\n"
            "<code>/unban @spammer_user</code>"
        ),
    },
    "gift": {
        "title": "🎁 /gift Command",
        "category": "admin",
        "text": (
            "🎁 <b>Command:</b> <code>/gift &lt;user_id&gt; &lt;searches&gt; &lt;requests&gt;</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Grants bonus daily search and request allowances to any user.\n\n"
            "💡 <b>Usage:</b>\n"
            "<code>/gift &lt;user_id&gt; &lt;search_bonus&gt; &lt;request_bonus&gt;</code>\n\n"
            "📋 <b>Example:</b>\n"
            "<code>/gift 123456789 50 25</code>"
        ),
    },
    "editscript": {
        "title": "🛠️ /editscript Command",
        "category": "admin",
        "text": (
            "🛠️ <b>Command:</b> <code>/editscript</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Opens the dynamic administration configuration hub stored in <code>config.db</code>. "
            "Allows modifying text templates, banners, and variables live without restarting the bot.\n\n"
            "💡 <b>Usage:</b>\n"
            "<code>/editscript</code> (in private chat with the bot)"
        ),
    },
    "log": {
        "title": "📋 /log Command",
        "category": "admin",
        "text": (
            "📋 <b>Command:</b> <code>/log [count|duration]</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Exports in-memory ring-buffer system logs as a downloadable text document directly in Telegram.\n\n"
            "💡 <b>Usage:</b>\n"
            "• <code>/log</code>: Last 10 lines.\n"
            "• <code>/log 100</code>: Last 100 lines.\n"
            "• <code>/log 15m</code>: All logs from the last 15 minutes."
        ),
    },
    "ping": {
        "title": "🏓 /ping Command",
        "category": "admin",
        "text": (
            "🏓 <b>Command:</b> <code>/ping</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Tests bot responsiveness, round-trip Telegram API latency, and network traffic statistics.\n\n"
            "💡 <b>Usage:</b>\n"
            "<code>/ping</code>"
        ),
    },

    # =======================================================================
    # 👑 GOD COMMANDS & PRIVILEGES
    # =======================================================================
    "addadmin": {
        "title": "👑 /addadmin & /removeadmin",
        "category": "god",
        "text": (
            "👑 <b>Commands:</b> <code>/addadmin</code> & <code>/removeadmin</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Promotes a user to Administrator or demotes an administrator back to Normal User. "
            "Automatically updates their database role and expands default quota ceilings.\n\n"
            "💡 <b>Usage:</b>\n"
            "• <code>/addadmin &lt;user_id|@username&gt;</code>\n"
            "• <code>/removeadmin &lt;user_id|@username&gt;</code>\n"
            "• Or reply to a user's message with <code>/addadmin</code> or <code>/removeadmin</code>.\n\n"
            "📋 <b>Example:</b>\n"
            "<code>/addadmin 123456789</code>\n\n"
            "🔒 <b>Access:</b> GOD Only"
        ),
    },
    "godpriv": {
        "title": "♾️ GOD System Privileges",
        "category": "god",
        "text": (
            "♾️ <b>GOD Supreme Privileges</b>\n\n"
            "📝 <b>System Authority:</b>\n"
            "• <b>Unlimited Quotas:</b> GOD is completely exempt from all search and request daily limits.\n"
            "• <b>Absolute Ban Immunity:</b> GOD cannot be banned or restricted by administrators.\n"
            "• <b>Reason-Optional Actions:</b> GOD can execute administrative bans without requiring a reason.\n"
            "• <b>Admin Promotion:</b> Only GOD can promote or demote administrators via <code>/addadmin</code> and <code>/removeadmin</code>."
        ),
    },
    "backup": {
        "title": "💾 SQLite Persistence & Telegram Backup",
        "category": "god",
        "text": (
            "💾 <b>Database Persistence System</b>\n\n"
            "📝 <b>Overview:</b>\n"
            "The bot automatically takes consistent online SQLite snapshots of all 3 databases "
            "(<code>config.db</code>, <code>files.db</code>, <code>mastermind_users.db</code>) every 5 minutes "
            "when changes occur, keeping a pinned <code>mastermind_backup.zip</code> document in your "
            "backup chat (<code>BACKUP_CHAT_ID</code>).\n\n"
            "💡 <b>Restore Flow:</b>\n"
            "Whenever Render restarts or rebuilds a container, the bot automatically downloads the pinned "
            "backup and verifies SQLite integrity before opening tables."
        ),
    },
    "governance": {
        "title": "⚙️ Global Governance & Token Security",
        "category": "god",
        "text": (
            "⚙️ <b>Global System Governance</b>\n\n"
            "📝 <b>Overview:</b>\n"
            "• Master control over <code>TELEGRAM_BOT_TOKEN</code> and <code>HELPER_BOT_TOKENS</code>.\n"
            "• Direct authority over <code>STORAGE_GROUP_ID</code> and <code>POSTING_CHANNEL_ID</code>.\n"
            "• Real-time error routing to Logger Forum Topic 33."
        ),
    },
}


# ---------------------------------------------------------------------------
# Menu Builders
# ---------------------------------------------------------------------------
def build_main_help_menu(user_id: int):
    """Builds the primary categorized help menu based on role permissions."""
    role = get_user_role_db(user_id)
    is_god_user = is_god(user_id)
    is_admin = is_admin_or_god(user_id)
    is_mod = (role in ("Moderator", "Admin", "GOD", "Owner"))
    is_vol = (role in ("Volunteer", "Moderator", "Admin", "GOD", "Owner"))

    text = (
        f"📖 <b>{bot_name()} Bot — Help & Documentation</b>\n\n"
        "Welcome! To keep guides clean and easy to browse, our documentation is organized into role-based tiers.\n\n"
        f"👤 <b>Your Access Level:</b> <code>{role}</code>\n\n"
        "Select a category below to explore available features:"
    )

    buttons = [
        [InlineKeyboardButton("👤 User Help", callback_data="help_cat_user")],
    ]

    second_row = []
    if is_vol:
        second_row.append(InlineKeyboardButton("🤝 Volunteer Help", callback_data="help_cat_volunteer"))
    if is_mod:
        second_row.append(InlineKeyboardButton("🛡️ Moderator Help", callback_data="help_cat_moderator"))
    if second_row:
        buttons.append(second_row)

    admin_row = []
    if is_admin:
        admin_row.append(InlineKeyboardButton("⚔️ Admin Help", callback_data="help_cat_admin"))
    if is_god_user:
        admin_row.append(InlineKeyboardButton("👑 GOD Help", callback_data="help_cat_god"))
    if admin_row:
        buttons.append(admin_row)

    buttons.append([
        InlineKeyboardButton("🔍 Search", callback_data="search_menu"),
        InlineKeyboardButton("📊 My Quota", callback_data="quota"),
    ])
    buttons.append([InlineKeyboardButton("« Back to Start", callback_data="start_menu")])

    return text, InlineKeyboardMarkup(buttons)


def build_user_help_menu():
    text = (
        "👤 <b>User Help Menu — Standard Commands & Guides</b>\n\n"
        "Tap any topic below to view its purpose, usage syntax, and real examples:"
    )
    buttons = [
        [
            InlineKeyboardButton("🚀 /start", callback_data="help_cmd_start"),
            InlineKeyboardButton("🔍 /search", callback_data="help_cmd_search"),
        ],
        [
            InlineKeyboardButton("📥 /request", callback_data="help_cmd_request"),
            InlineKeyboardButton("📊 /quota", callback_data="help_cmd_quota"),
        ],
        [
            InlineKeyboardButton("🔗 /refer & /myreferrals", callback_data="help_cmd_refer"),
            InlineKeyboardButton("🛡️ /support", callback_data="help_cmd_support"),
        ],
        [
            InlineKeyboardButton("📈 /stats", callback_data="help_cmd_stats"),
            InlineKeyboardButton("👥 User Roles", callback_data="help_cmd_roles"),
            InlineKeyboardButton("📜 /admins & Rosters", callback_data="help_cmd_rosters"),
        ],
        [
            InlineKeyboardButton("📥 Dual File Delivery Guide", callback_data="help_cmd_delivery"),
        ],
        [
            InlineKeyboardButton("« Back to Categories", callback_data="help_main"),
        ],
    ]
    return text, InlineKeyboardMarkup(buttons)


def build_volunteer_help_menu():
    text = (
        "🤝 <b>Volunteer Help Menu — Direct Library Contribution</b>\n\n"
        "Volunteers can index books directly without requiring administrator approval.\n"
        "Tap any topic below to view contribution guidelines:"
    )
    buttons = [
        [
            InlineKeyboardButton("📚 Volunteer Privileges", callback_data="help_cmd_vol_priv"),
            InlineKeyboardButton("🤖 Helper Bot Indexing", callback_data="help_cmd_vol_index"),
        ],
        [
            InlineKeyboardButton("⚠️ /index Restriction Notice", callback_data="help_cmd_vol_notice"),
        ],
        [
            InlineKeyboardButton("« Back to Categories", callback_data="help_main"),
        ],
    ]
    return text, InlineKeyboardMarkup(buttons)


def build_moderator_help_menu():
    text = (
        "🛡️ <b>Moderator Help Menu — Requests & Moderation</b>\n\n"
        "Moderators manage book requests and contribute pre-approved library additions.\n"
        "Tap any topic below to view operational guides:"
    )
    buttons = [
        [
            InlineKeyboardButton("⚖️ Moderator Privileges", callback_data="help_cmd_mod_priv"),
            InlineKeyboardButton("📋 Request Status Buttons", callback_data="help_cmd_mod_status"),
        ],
        [
            InlineKeyboardButton("🤖 Helper Bot Indexing", callback_data="help_cmd_mod_index"),
            InlineKeyboardButton("⚠️ /index Restriction Notice", callback_data="help_cmd_mod_notice"),
        ],
        [
            InlineKeyboardButton("« Back to Categories", callback_data="help_main"),
        ],
    ]
    return text, InlineKeyboardMarkup(buttons)


def build_admin_help_menu():
    text = (
        "⚔️ <b>Administrator Help Menu — System Management</b>\n\n"
        "Tap any management command below to inspect syntax, options, and guidelines:"
    )
    buttons = [
        [
            InlineKeyboardButton("🤖 /checkhelpers", callback_data="help_cmd_checkhelpers"),
            InlineKeyboardButton("📚 /index", callback_data="help_cmd_index"),
        ],
        [
            InlineKeyboardButton("🚫 /ban & /unban", callback_data="help_cmd_ban"),
            InlineKeyboardButton("🎁 /gift", callback_data="help_cmd_gift"),
        ],
        [
            InlineKeyboardButton("🛠️ /editscript", callback_data="help_cmd_editscript"),
            InlineKeyboardButton("📋 /log", callback_data="help_cmd_log"),
        ],
        [
            InlineKeyboardButton("🛡️ /addmod & /delmod", callback_data="help_cmd_addmoderator"),
            InlineKeyboardButton("🤝 /addvol & /delvol", callback_data="help_cmd_addvolunteer"),
        ],
        [
            InlineKeyboardButton("📣 /addpromo & /delpromo", callback_data="help_cmd_addpromoter"),
            InlineKeyboardButton("📢 /broadcast", callback_data="help_cmd_broadcast"),
            InlineKeyboardButton("🏓 /ping", callback_data="help_cmd_ping"),
        ],
        [
            InlineKeyboardButton("« Back to Categories", callback_data="help_main"),
        ],
    ]
    return text, InlineKeyboardMarkup(buttons)


def build_god_help_menu():
    text = (
        "👑 <b>GOD Help Menu — Supreme System Control</b>\n\n"
        "Tap any feature below to inspect supreme management privileges:"
    )
    buttons = [
        [
            InlineKeyboardButton("👑 /addadmin & /removeadmin", callback_data="help_cmd_addadmin"),
        ],
        [
            InlineKeyboardButton("🛡️ Role Management (Mod/Vol/Promo)", callback_data="help_cmd_addmoderator"),
        ],
        [
            InlineKeyboardButton("♾️ GOD Supreme Privileges", callback_data="help_cmd_godpriv"),
        ],
        [
            InlineKeyboardButton("💾 SQLite Persistence & Telegram Backup", callback_data="help_cmd_backup"),
        ],
        [
            InlineKeyboardButton("⚙️ Global Governance & Tokens", callback_data="help_cmd_governance"),
            InlineKeyboardButton("📢 Broadcast & Pinning", callback_data="help_cmd_broadcast"),
        ],
        [
            InlineKeyboardButton("« Back to Categories", callback_data="help_main"),
        ],
    ]
    return text, InlineKeyboardMarkup(buttons)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for /help command."""
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
    """Callback router for all help navigation and individual command cards."""
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

    elif data == "help_cat_user":
        text, markup = build_user_help_menu()
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=markup)

    elif data == "help_cat_volunteer":
        if role not in ("Volunteer", "Moderator", "Admin", "GOD", "Owner"):
            await q.answer("⛔ Access restricted to Volunteers, Moderators, Admins, and GOD.", show_alert=True)
            return
        text, markup = build_volunteer_help_menu()
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=markup)

    elif data == "help_cat_moderator":
        if role not in ("Moderator", "Admin", "GOD", "Owner"):
            await q.answer("⛔ Access restricted to Moderators, Admins, and GOD.", show_alert=True)
            return
        text, markup = build_moderator_help_menu()
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=markup)

    elif data == "help_cat_admin":
        if not is_admin_or_god(user_id):
            await q.answer("⛔ Access restricted to Administrators.", show_alert=True)
            return
        text, markup = build_admin_help_menu()
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=markup)

    elif data == "help_cat_god" or data == "help_cat_owner":
        if not is_god(user_id):
            await q.answer("⛔ Access restricted to GOD only.", show_alert=True)
            return
        text, markup = build_god_help_menu()
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=markup)

    elif data.startswith("help_cmd_"):
        cmd_key = data.replace("help_cmd_", "", 1)
        item = COMMAND_DETAILS.get(cmd_key)
        if not item:
            await q.answer("Command details not found.", show_alert=True)
            return

        cat = item["category"]
        if cat == "admin" and not is_admin_or_god(user_id):
            await q.answer("⛔ Access restricted to Administrators.", show_alert=True)
            return
        if cat == "god" and not is_god(user_id):
            await q.answer("⛔ Access restricted to GOD only.", show_alert=True)
            return
        if cat == "moderator" and role not in ("Moderator", "Admin", "GOD", "Owner"):
            await q.answer("⛔ Access restricted to Moderators, Admins, and GOD.", show_alert=True)
            return
        if cat == "volunteer" and role not in ("Volunteer", "Moderator", "Admin", "GOD", "Owner"):
            await q.answer("⛔ Access restricted to Volunteers, Moderators, Admins, and GOD.", show_alert=True)
            return

        back_cat_data = f"help_cat_{cat}"
        keyboard = [
            [InlineKeyboardButton(f"« Back to {cat.capitalize()} Menu", callback_data=back_cat_data)],
            [InlineKeyboardButton("📖 Main Help Menu", callback_data="help_main")],
        ]
        await q.edit_message_text(
            item["text"],
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True,
        )


async def help_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await help_callback_handler(update, context)
