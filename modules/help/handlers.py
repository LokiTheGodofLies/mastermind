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
            "Launches the bot, initializes your daily quota, displays the interactive main navigation hub, "
            "and supports direct file downloading via helper deep-links.\n\n"
            "💡 <b>Usage:</b>\n"
            "• Send <code>/start</code> in private chat to open the main menu.\n"
            "• Click any download button in search results to trigger deep-link delivery via <code>/start dl_...</code>."
        ),
    },
    "search": {
        "title": "🔍 search",
        "category": "user",
        "text": (
            "🔍 <b>Command:</b> <code>/search</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Searches the indexed community book and audiobook library across filenames, titles, authors, series, and captions.\n\n"
            "💡 <b>Usage:</b>\n"
            "• <code>/search &lt;keywords&gt;</code> (in private chat or in the official Search topic).\n"
            "• Features structured results, format filters (📚 / 🎧), Send All button, and deep-link downloads."
        ),
    },
    "request": {
        "title": "📥 request",
        "category": "user",
        "text": (
            "📥 <b>Command:</b> <code>/request</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Submits a request for a missing book or audiobook directly to the community Request Channel.\n\n"
            "💡 <b>Usage:</b>\n"
            "• <code>/request &lt;Book Title and Author&gt;</code>\n"
            "• The request is forwarded with interactive status buttons (Pending, Processing, Completed, Rejected) for Moderators."
        ),
    },
    "quota": {
        "title": "📊 quota",
        "category": "user",
        "text": (
            "📊 <b>Command:</b> <code>/quota</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Displays your live daily search and request allowances, remaining balance, and midnight IST reset timer.\n\n"
            "💡 <b>Usage:</b>\n"
            "• Send <code>/quota</code> to view your quota card.\n"
            "• Daily Limits: User (10/10), Promoter (20/20), Volunteer (30/30), Moderator (40/40), Admin (Unlimited)."
        ),
    },
    "refer": {
        "title": "🔗 refer",
        "category": "user",
        "text": (
            "🔗 <b>Commands:</b> <code>/refer</code> & <code>/myreferrals</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Generates your personal referral link. Share it with friends to earn bonus search and request allowances!\n\n"
            "💡 <b>Usage:</b>\n"
            "• <code>/refer</code>: View your referral link and reward milestones (+10 searches & requests per referral).\n"
            "• <code>/myreferrals</code>: Check your successful invite count and earned bonuses."
        ),
    },
    "support": {
        "title": "🛡️ support",
        "category": "user",
        "text": (
            "🛡️ <b>Command:</b> <code>/support</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Connects you to the official Support Community Chat for inquiries, book discussions, and community assistance.\n\n"
            "💡 <b>Usage:</b>\n"
            "• Send <code>/support</code> to receive the official community join link."
        ),
    },
    "stats": {
        "title": "📈 stats",
        "category": "user",
        "text": (
            "📈 <b>Command:</b> <code>/stats</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Displays live library metrics, total indexed files, ebook and audiobook counts, and bot uptime.\n\n"
            "💡 <b>Usage:</b>\n"
            "• Send <code>/stats</code> to view system statistics."
        ),
    },
    "id": {
        "title": "🆔 id",
        "category": "user",
        "text": (
            "🆔 <b>Command:</b> <code>/id</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Retrieves full identification details for users, chats, groups, channels, and forum topics.\n\n"
            "💡 <b>Usage:</b>\n"
            "• <code>/id</code> in any chat to view your User ID, Chat ID, and Topic ID.\n"
            "• Reply to any message with <code>/id</code> to inspect that sender's name and ID.\n"
            "• <code>/id @username</code>: Look up user details."
        ),
    },
    "rosters": {
        "title": "👥 rosters",
        "category": "user",
        "text": (
            "👥 <b>Community Roster Commands</b>\n\n"
            "View official lists of community team members with direct profile links:\n\n"
            "• <code>/admins</code>: Lists all Administrators and the Creator.\n"
            "• <code>/moderators</code>: Lists all active Moderators (alias: <code>/mods</code>).\n"
            "• <code>/volunteers</code>: Lists all active Volunteers (alias: <code>/vols</code>).\n"
            "• <code>/promoters</code>: Lists all active Promoters (alias: <code>/promos</code>)."
        ),
    },
    "delivery": {
        "title": "📦 delivery",
        "category": "user",
        "text": (
            "📦 <b>Dual File Delivery System</b>\n\n"
            "When you download a file from search results, the bot offers two delivery methods:\n\n"
            "1. <b>🤖 Fast DM Delivery:</b> File is delivered directly to your private chat via helper bots.\n"
            "2. <b>📢 Posting Channel:</b> File is temporarily posted in the official channel and auto-deleted after 5 minutes for privacy."
        ),
    },
    "roles": {
        "title": "👥 roles",
        "category": "user",
        "text": (
            "👥 <b>Community User Roles & Privileges Breakdown</b>\n\n"
            "Our community has 6 structured roles to organize library contributions and governance:\n\n"
            "👤 <b>Normal User:</b>\n"
            "• Quota: 10 daily searches & 10 daily requests.\n"
            "• Access: /start, /search, /request, /quota, /refer, /support, /stats, /id, and rosters.\n\n"
            "📣 <b>Promoter:</b>\n"
            "• Quota: 20 daily searches & 20 daily requests.\n"
            "• Appointed by Admins to promote the community.\n\n"
            "🤝 <b>Volunteer:</b>\n"
            "• Quota: 30 daily searches & 30 daily requests.\n"
            "• Pre-approved direct book & audiobook indexing via Helper Bot DMs.\n\n"
            "🛡️ <b>Moderator:</b>\n"
            "• Quota: 40 daily searches & 40 daily requests.\n"
            "• Direct indexing + Request Channel status management (Pending, Processing, Completed, Rejected).\n\n"
            "⚔️ <b>Administrator:</b>\n"
            "• Quota: Unlimited searches & requests.\n"
            "• Batch range /index, /broadcast with auto-pin & pause/resume, /ban, /gift, /editscript, /checkhelpers, and promoting Mods/Vols/Promos.\n\n"
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
        "title": "🤖 vol_indexing",
        "category": "volunteer",
        "text": (
            "📚 <b>Volunteer Helper Bot Indexing Guide</b>\n\n"
            "1. Start a private chat with any official Helper Bot (e.g. @Heyuqtbot or @RickRiordanBot).\n"
            "2. Send or forward supported book (.epub, .pdf, .mobi, .azw) or audiobook (.mp3, .m4b, .flac) files.\n"
            "3. The bot extracts metadata, stores the file in the Storage Group, and logs it automatically."
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
            "• 🔄 <b>Processing:</b> Request is being sourced.\n"
            "• ✅ <b>Completed:</b> File was found and indexed into the library.\n"
            "• ❌ <b>Rejected:</b> Book cannot be fulfilled."
        ),
    },
    "mod_indexing": {
        "title": "🤖 mod_indexing",
        "category": "moderator",
        "text": (
            "🤖 <b>Moderator Direct Indexing Guide</b>\n\n"
            "Send or forward supported ebook and audiobook files directly to any Helper Bot in private chat. "
            "Metadata is enriched automatically and stored in the library."
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
            "presence in the Storage Group, and admin rights in the Posting Channel."
        ),
    },
    "index": {
        "title": "📚 index",
        "category": "admin",
        "text": (
            "📚 <b>Command:</b> <code>/index</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Batch indexes ebooks and audiobooks from channels or groups into the Storage Group with multi-site metadata enrichment.\n\n"
            "💡 <b>Usage:</b>\n"
            "• <code>/index &lt;first_link&gt; &lt;last_link&gt;</code>\n"
            "• <code>/index [skip_count]</code> (in source chat)\n"
            "• <code>/index</code> in private chat for interactive step-by-step setup."
        ),
    },
    "broadcast": {
        "title": "📢 broadcast",
        "category": "admin",
        "text": (
            "📢 <b>Command:</b> <code>/broadcast</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Dispatches announcements with interactive toggles (Users, Groups, Channels, All), multi-bot pool delivery, "
            "auto-pinning, and live Pause/Resume/Cancel controls."
        ),
    },
    "ban": {
        "title": "🚫 ban",
        "category": "admin",
        "text": (
            "🚫 <b>Commands:</b> <code>/ban</code>, <code>/ban_pm</code>, <code>/ban_support</code>, <code>/unban</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Applies or lifts granular restrictions on users or chats:\n"
            "• <code>/ban &lt;id|@username&gt; [reason]</code>: Block globally.\n"
            "• <code>/ban_pm &lt;id|@username&gt;</code>: Block in DMs only.\n"
            "• <code>/ban_support &lt;id|@username&gt;</code>: Restrict in support chat.\n"
            "• <code>/unban &lt;id|@username&gt;</code>: Completely lifts restrictions."
        ),
    },
    "gift": {
        "title": "🎁 gift",
        "category": "admin",
        "text": (
            "🎁 <b>Command:</b> <code>/gift &lt;user_id&gt; &lt;searches&gt; &lt;requests&gt;</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Grants bonus daily search and request allowances to any user."
        ),
    },
    "editscript": {
        "title": "🛠️ editscript",
        "category": "admin",
        "text": (
            "🛠️ <b>Command:</b> <code>/editscript</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Opens the dynamic configuration hub in <code>config.db</code> to modify templates, banners, "
            "and text live without restarting the bot."
        ),
    },
    "log": {
        "title": "📋 log",
        "category": "admin",
        "text": (
            "📋 <b>Command:</b> <code>/log [count|duration]</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Exports in-memory system logs as a downloadable document directly in Telegram."
        ),
    },
    "ping": {
        "title": "🏓 ping",
        "category": "admin",
        "text": (
            "🏓 <b>Command:</b> <code>/ping</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Tests bot responsiveness, round-trip API latency, and network statistics."
        ),
    },
    "addmoderator": {
        "title": "🛡️ addmoderator",
        "category": "admin",
        "text": (
            "🛡️ <b>Commands:</b> <code>/addmoderator</code> & <code>/removemoderator</code>\n"
            "<i>(Aliases: /addmod, /removemod, /delmod)</i>\n\n"
            "Promotes or demotes a Moderator (40 daily quota, request management buttons)."
        ),
    },
    "addvolunteer": {
        "title": "🤝 addvolunteer",
        "category": "admin",
        "text": (
            "🤝 <b>Commands:</b> <code>/addvolunteer</code> & <code>/removevolunteer</code>\n"
            "<i>(Aliases: /addvol, /removevol, /delvol)</i>\n\n"
            "Promotes or demotes a Volunteer (30 daily quota, pre-approved helper indexing)."
        ),
    },
    "addpromoter": {
        "title": "📣 addpromoter",
        "category": "admin",
        "text": (
            "📣 <b>Commands:</b> <code>/addpromoter</code> & <code>/removepromoter</code>\n"
            "<i>(Aliases: /addpromo, /removepromo, /delpromo)</i>\n\n"
            "Promotes or demotes a Promoter (20 daily quota)."
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
            "both <code>loki main</code> and <code>origin main</code>.\n"
            "Triggers the live deployment on Render Public Books Bot with a single tap right from Telegram.\n\n"
            "🔒 <b>Access:</b> Creator Only"
        ),
    },
    "update": {
        "title": "📦 update",
        "category": "creator",
        "text": (
            "📦 <b>Command:</b> <code>/update</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Updates bot code in-chat without Termux. Send or reply to an updated <code>.zip</code> file with <code>/update</code>.\n"
            "The bot unpacks the code, verifies with compileall, commits, and pushes to GitHub automatically!\n\n"
            "🔒 <b>Access:</b> Creator Only"
        ),
    },
    "sh": {
        "title": "💻 sh",
        "category": "creator",
        "text": (
            "💻 <b>Command:</b> <code>/sh &lt;command&gt;</code> (alias: <code>/term</code>)\n\n"
            "📝 <b>Purpose:</b>\n"
            "Executes bash shell commands directly from Telegram.\n\n"
            "💡 <b>Usage:</b>\n"
            "• <code>/sh git status</code>\n"
            "• <code>/sh git log -1 --oneline</code>\n"
            "• <code>/sh df -h</code>\n\n"
            "🔒 <b>Access:</b> Creator Only"
        ),
    },
    "addadmin": {
        "title": "👑 addadmin",
        "category": "creator",
        "text": (
            "👑 <b>Commands:</b> <code>/addadmin</code> & <code>/removeadmin</code>\n\n"
            "📝 <b>Purpose:</b>\n"
            "Appoints or removes an Administrator. Exclusive to the Creator."
        ),
    },
    "creator_privileges": {
        "title": "♾️ creator_privileges",
        "category": "creator",
        "text": (
            "👑 <b>Creator Supreme Authority</b>\n\n"
            "The Creator has absolute governance across all bot operations, helper pools, "
            "database persistence, and administrative appointments."
        ),
    },
    "backup": {
        "title": "💾 backup",
        "category": "creator",
        "text": (
            "💾 <b>Automated SQLite Backups</b>\n\n"
            "Backups of <code>files.db</code>, <code>users.db</code>, and <code>config.db</code> are compiled into a ZIP "
            "and posted to the Backup Topic (PUBLIC_BACKUP_TOPIC_ID=4 / TESTING_BACKUP_TOPIC_ID=583)."
        ),
    },
    "governance": {
        "title": "⚙️ governance",
        "category": "creator",
        "text": (
            "⚙️ <b>Global Architecture & Identity Governance</b>\n\n"
            "Environment configuration, isolated Public/Testing credentials, and Render deployment monitoring."
        ),
    },
}


# ---------------------------------------------------------------------------
# Menu Builders with Pagination (Max 4-6 buttons per page, Clean Command Labels with Emojis)
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
        "Tap any command below to inspect its purpose, syntax, and guidelines:"
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
    1. Only displays categories accessible to the user's role level.
    2. Includes a dedicated '👥 roles' (User Roles) button directly on the main page so all users
       can view and understand the roles of other users without seeing higher-level commands.
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
            await q.answer("⛔ Access restricted to Creator only.", show_alert=True)
            return

        text, markup = build_paginated_category_menu(category, page=page)
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=markup)

    elif data.startswith("help_cmd_"):
        cmd_key = data.replace("help_cmd_", "", 1)
        item = COMMAND_DETAILS.get(cmd_key)
        if not item:
            await q.answer("Command details not found.", show_alert=True)
            return

        cat = item["category"]
        if cat == "admin" and not is_admin_or_creator(user_id):
            await q.answer("⛔ Access restricted to Administrators.", show_alert=True)
            return
        if cat == "creator" and not is_creator(user_id):
            await q.answer("⛔ Access restricted to Creator only.", show_alert=True)
            return
        if cat == "moderator" and role not in ("Moderator", "Admin", "Creator", "Owner"):
            await q.answer("⛔ Access restricted to Moderators.", show_alert=True)
            return
        if cat == "volunteer" and role not in ("Volunteer", "Moderator", "Admin", "Creator", "Owner"):
            await q.answer("⛔ Access restricted to Volunteers.", show_alert=True)
            return

        back_cat_data = f"help_cat_{cat}_p1"
        keyboard = [
            [InlineKeyboardButton("« Back to Category", callback_data=back_cat_data)],
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
