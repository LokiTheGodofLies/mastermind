from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.database.user_db import get_user_role_db
from modules.database.config_db import get_template, format_template_string
from modules.log.startup_log import send_log_with_fallback

USER_HELP_MAIN = (
    "📖 <b>{bot_title} — Complete User Guide (/help)</b>\n\n"
    "Welcome! Use the buttons below to explore how every feature, button, and command works:\n\n"
    "🔹 <b>Basic Commands:</b>\n"
    "• <code>/start</code> — Register, activate Helper Bot, or claim referral bonus\n"
    "• <code>/help</code> — Open this interactive help menu\n"
    "• <code>/search &lt;keyword&gt;</code> — Search books & audiobooks by title, author, narrator, series, or metadata\n"
    "• <code>/request &lt;title&gt; &lt;author&gt;</code> — Request a missing book/audiobook\n"
    "• <code>/quota</code> — View your daily search & request quota\n"
    "• <code>/refer</code> — Get your invite link (+10 search & +10 request bonus)\n\n"
    "👇 <b>Tap any category button below for detailed instructions:</b>"
)

USER_HELP_SECTIONS = {
    "help_sec_search": (
        "🔍 <b>How to Search & Download Files</b>\n\n"
        "• <code>/search &lt;keyword&gt;</code> — Search all books & audiobooks\n"
        "• <code>/searchebook &lt;keyword&gt;</code> — Search eBooks only 📚\n"
        "• <code>/searchaudiobook &lt;keyword&gt;</code> — Search Audiobooks only 🎧\n\n"
        "Each result shows <b>Book Title, Series Name, Author Name, and Extension</b> with a clickable <b>download</b> link.\n"
        "Use <b>📚</b> (eBooks only), <b>📤 Send All</b> (send full page), or <b>🎧</b> (Audiobooks only) below the results!"
    ),
    "help_sec_requests": (
        "📥 <b>How to Request a Book / Audiobook</b>\n\n"
        "1. Use <code>/request &lt;title&gt; &lt;author&gt;</code> or tap <b>📝 Request Book</b> on search results.\n"
        "2. The bot fetches matching options from <b>Audible / Goodreads</b> with narrator, series, release year, and publisher details.\n"
        "3. Tap a matched book button to attach its metadata, OR tap <b>📋 None of these — Request Manually</b> to enter Title, Author, Format, and Series manually.\n"
        "4. Once posted to the Request Queue, Moderators/Admins can update its status (Added to Database, Not Available, Not Released, Request Again, Already Available)."
    ),
    "help_sec_uploads": (
        "📤 <b>How File Uploads & Indexing Work</b>\n\n"
        "• <b>Normal Users & Promoters:</b> Uploaded files are sent to the Approval Queue for Admin/Owner review before indexing.\n"
        "• <b>Volunteers, Admins & Owners:</b> Uploaded ebooks/audiobooks are automatically enriched with Goodreads metadata, captioned, sent to Storage, and indexed.\n"
        "• <b>Rate-Limited Queue:</b> Indexing runs at max <b>10 files per batch</b> with a <b>10-second cooldown</b> between batches. Direct user uploads get top priority."
    ),
    "help_sec_quota": (
        "📊 <b>How the Quota System Works</b>\n\n"
        "• <b>Searching is Free:</b> Entering <code>/search</code> and browsing result lists consumes <b>0 quota</b>.\n"
        "• <b>Search Quota Deduction:</b> 1 search quota is deducted <b>only</b> when your selected file is successfully delivered.\n"
        "• <b>Request Quota Deduction:</b> 1 request quota is deducted <b>only</b> when your request is successfully posted to the Request Log.\n"
        "• Failed, canceled, or incomplete actions never deduct quota."
    ),
}

USER_HELP_SECTIONS.update({
    "help_sec_referral": (
        "🔗 <b>How Referrals Work (+10 Bonus Quota)</b>\n\n"
        "• Run <code>/refer</code> to get your unique referral link (<code>?start=ref_&lt;id&gt;</code>).\n"
        "• When a <b>first-time user</b> starts the bot through your link, <b>both you and your friend receive +10 Search Quota and +10 Request Quota</b>!\n"
        "• Anti-abuse protection: Valid once per new user; existing or banned users cannot claim duplicate rewards."
    ),
    "help_sec_tempfiles": (
        "⏳ <b>How Temporary File Delivery Works</b>\n\n"
        "1. Make sure you have started @{helper_bot_username}.\n"
        "2. When you click a search result button, the Helper Bot posts the file to the <b>File Posting Channel</b> and sends you the channel link + message link.\n"
        "3. If your DM session is active, the Helper Bot also mirrors the file directly to your DM.\n"
        "4. The file in the Posting Channel is <b>auto-deleted after 2 minutes</b> to keep storage clean."
    ),
    "help_sec_groups": (
        "👥 <b>Using the Bot in Your Own Group (Groups Help)</b>\n\n"
        "Anyone can add <b>{bot_title}</b> to their own Telegram group to search and request books & audiobooks!\n\n"
        "🔹 <b>Topic Setup for Group Admins (<code>/settopic</code>):</b>\n"
        "If your group uses Topics (like <i>Beyond the Shelf</i>), any <b>Group Admin</b> can restrict the bot to specific topics:\n"
        "• <code>/settopic search</code> — Run inside your Search topic so only search commands (<code>/search</code>, <code>/searchebook</code>, <code>/searchaudiobook</code>) work there.\n"
        "• <code>/settopic request</code> — Run inside your Request topic so only <code>/request</code> commands work there.\n"
        "• Once set, the bot will stay completely silent in all other topics of your group!"
    ),
    "help_sec_roles": (
        "🛡 <b>Roles, Quotas & Permissions</b>\n\n"
        "• <b>Banned:</b> 0 quota (restricted access)\n"
        "• <b>Normal User:</b> 10 quota (uploads need approval)\n"
        "• <b>Promoter:</b> 20 quota (boosted normal user)\n"
        "• <b>Volunteer:</b> 30 quota (direct file indexing without approval)\n"
        "• <b>Moderator:</b> 40 quota (manages book request queue & statuses)\n"
        "• <b>Admin / Owner:</b> Unlimited quota + system & role control"
    ),
    "help_sec_formatting": (
        "✨ <b>Callback Buttons, Placeholders & Formatting</b>\n\n"
        "🔘 <b>What Inline Buttons Do:</b>\n"
        "• <b>Result Button:</b> Sends selected file to Posting Channel & DM\n"
        "• <b>Request Book:</b> Searches Audible/Goodreads or submits manual request\n"
        "• <b>Approve / Reject:</b> Allows or blocks file indexing\n"
        "• <b>Show Options:</b> Updates book request status\n"
        "• <b>Pause / Resume / Cancel:</b> Controls the 10-file batch indexing queue\n\n"
        "🏷 <b>Message Placeholders & Formatting:</b>\n"
        "• <code>{bot_title}</code> — Bot display name ({bot_title})\n"
        "• <code>@{bot_username}</code> — Bot username (@{bot_username})\n"
        "• <code>{chat_title}</code> — Current group/chat name\n"
        "• <code>{date}</code> / <code>{time}</code> — Current date ({date}) & time ({time})\n"
        "• Bold: <code>&#42;&#42;text&#42;&#42;</code> | Italic: <code>&#42;text&#42;</code> | Spoiler: <code>&#124;&#124;text&#124;&#124;</code>"
    ),
})

ADMIN_HELP_MAIN = (
    "👑 <b>Admin & Owner Control Panel (/adminhelp)</b>\n\n"
    "Restricted documentation for <b>Admins & Owners</b>:\n\n"
    "🔹 <b>Role & User Commands:</b>\n"
    "• <code>/addvol &lt;user&gt;</code> — Assign Volunteer (30 quota, direct indexing)\n"
    "• <code>/addprom &lt;user&gt;</code> — Assign Promoter (20 quota)\n"
    "• <code>/addmod &lt;user&gt;</code> — Assign Moderator (40 quota, request queue)\n"
    "• <code>/addadmin &lt;user&gt;</code> — Assign Admin (Unlimited, Owner only)\n"
    "• <code>/gift &lt;user_id&gt; &lt;search&gt; &lt;req&gt;</code> — Gift bonus quota\n"
    "• <code>/ban &lt;user&gt; [reason]</code> & <code>/unban &lt;user&gt;</code>\n\n"
    "🔹 <b>Indexing, Config & Template Commands:</b>\n"
    "• <code>/index</code> — Start interactive indexing wizard or range index\n"
    "• <code>/customize</code> — Open button-driven Bot Settings & Template Dashboard\n"
    "• <code>/setconfig &lt;k&gt; &lt;v&gt;</code> | <code>/getconfig &lt;k&gt;</code> | <code>/reloadconfig</code>\n"
    "• <code>/broadcast &lt;target&gt; &lt;msg&gt;</code> | <code>/stats</code> | <code>/log</code>"
)

ADMIN_HELP_SECTIONS = {
    "adm_sec_vol": "🎖 <b>Add Volunteer (<code>/addvol &lt;user&gt;</code>)</b>\nGrants <b>30 daily quota</b> and allows direct file indexing without waiting for admin approval.",
    "adm_sec_prom": "🚀 <b>Add Promoter (<code>/addprom &lt;user&gt;</code>)</b>\nBoosts a normal user to <b>20 daily search & request quota</b>.",
    "adm_sec_mod": "🛡 <b>Add Moderator (<code>/addmod &lt;user&gt;</code>)</b>\nGrants <b>40 daily quota</b> and access to <b>Show Options</b> on Request Log entries (Added to DB, Not Available, Not Released, Request Again, Already Available).",
    "adm_sec_admin": "👑 <b>Add Admin (<code>/addadmin &lt;user&gt;</code>)</b>\nGrants <b>Unlimited quota</b>, upload approval rights, role assignment, broadcast, and log access.",
    "adm_sec_queue": "⏸ <b>Queue Control & Throttling</b>\nGlobal cap of <b>10 files per batch</b> + <b>10s sleep</b>. Direct user uploads pause bulk channel scans and run first. Use Pause, Resume, and Cancel buttons on the progress card.",
    "adm_sec_logs": "📋 <b>Log Configuration & Fallback</b>\nEvents route to specific log topics (Index, Request, Group, Channel, User). If missing, they fall back to General Log + Owner PM alert.",
    "adm_sec_index": (
        "📚 <b>Manual Indexing Commands (<code>/index</code>)</b>\n\n"
        "• <code>/index</code> — Interactive step-by-step wizard (Set Source -> Skip -> Double Check)\n"
        "• <code>/index t.me/channel/100 t.me/channel/300</code>\n"
        "• <code>/index t.me/channel/100-300</code>\n"
        "• <code>/index t.me/channel skip 200</code>\n"
        "• <code>/index t.me/channel skip 200-250</code>\n"
        "• <code>/index t.me/channel limit=10</code>"
    ),
    "adm_sec_usermgmt": "👥 <b>User Management</b>\nUse <code>/ban &lt;user&gt; [reason]</code>, <code>/ban_pm</code>, <code>/ban_support</code>, <code>/unban &lt;user&gt;</code>, and <code>/gift &lt;user_id&gt; &lt;s_bonus&gt; &lt;r_bonus&gt;</code>.",
}


def build_user_help_keyboard(is_admin: bool) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("🔍 Search", callback_data="help_sec_search"), InlineKeyboardButton("📥 Requests", callback_data="help_sec_requests")],
        [InlineKeyboardButton("📤 Uploads", callback_data="help_sec_uploads"), InlineKeyboardButton("📊 Quota", callback_data="help_sec_quota")],
        [InlineKeyboardButton("🔗 Referral", callback_data="help_sec_referral"), InlineKeyboardButton("⏳ Temporary Files", callback_data="help_sec_tempfiles")],
        [InlineKeyboardButton("🛡 Roles", callback_data="help_sec_roles"), InlineKeyboardButton("👥 Groups Help", callback_data="help_sec_groups")],
        [InlineKeyboardButton("✨ Formatting & Buttons", callback_data="help_sec_formatting")],
    ]
    if is_admin:
        kb.append([InlineKeyboardButton("👑 Admin Commands (/adminhelp)", callback_data="help_open_admin")])
    kb.append([InlineKeyboardButton("≼ Back to Start", callback_data="start_menu")])
    return InlineKeyboardMarkup(kb)


def build_admin_help_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton("🎖 Add Volunteer", callback_data="adm_sec_vol"), InlineKeyboardButton("🚀 Add Promoter", callback_data="adm_sec_prom")],
        [InlineKeyboardButton("🛡 Add Moderator", callback_data="adm_sec_mod"), InlineKeyboardButton("👑 Add Admin", callback_data="adm_sec_admin")],
        [InlineKeyboardButton("⏸ Queue Control", callback_data="adm_sec_queue"), InlineKeyboardButton("📋 Logs", callback_data="adm_sec_logs")],
        [InlineKeyboardButton("📚 Indexing", callback_data="adm_sec_index"), InlineKeyboardButton("👥 User Management", callback_data="adm_sec_usermgmt")],
        [InlineKeyboardButton("🪄 Customize Bot (/customize)", callback_data="cust_open_main")],
        [InlineKeyboardButton("≼ Back to User Help", callback_data="help_menu")],
    ]
    return InlineKeyboardMarkup(kb)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    role = get_user_role_db(user.id)
    is_admin = role in ("Admin", "Owner")

    tpl = get_template("help")
    raw = tpl.get("text") or USER_HELP_MAIN
    text = format_template_string(raw, {"user_name": user.first_name or "User", "chat_title": update.effective_chat.title or "Private Chat"})
    markup = build_user_help_keyboard(is_admin)

    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await msg.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def adminhelp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    role = get_user_role_db(user.id)
    if role not in ("Admin", "Owner"):
        if update.callback_query:
            await update.callback_query.answer("⛔ Access denied — Not authorized.", show_alert=True)
        else:
            await msg.reply_text("⛔ <b>Access denied:</b> You are not authorized to view admin commands.", parse_mode="HTML")
        await send_log_with_fallback(
            context.bot,
            f"⚠️ <b>Unauthorized /adminhelp Attempt</b>\n👤 User: {user.full_name} (<code>{user.id}</code>)\n🛡 Role: <code>{role}</code>",
            "admin_log_group_id",
            "user_log_topic_id",
        )
        return

    tpl = get_template("adminhelp")
    raw = tpl.get("text") or ADMIN_HELP_MAIN
    text = format_template_string(raw, {"user_name": user.first_name or "Admin"})
    markup = build_admin_help_keyboard()

    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await msg.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def help_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data
    user = q.from_user
    role = get_user_role_db(user.id)
    is_admin = role in ("Admin", "Owner")

    if data in ("help_button", "help_menu"):
        await q.answer()
        await help_command(update, context)
    elif data == "help_open_admin":
        await adminhelp_command(update, context)
    elif data in USER_HELP_SECTIONS:
        await q.answer()
        txt = format_template_string(USER_HELP_SECTIONS[data], {"user_name": user.first_name or "User"})
        await q.message.edit_text(txt, parse_mode="HTML", reply_markup=build_user_help_keyboard(is_admin))
    elif data in ADMIN_HELP_SECTIONS:
        if not is_admin:
            await q.answer("⛔ Access denied — Not authorized.", show_alert=True)
            return
        await q.answer()
        txt = format_template_string(ADMIN_HELP_SECTIONS[data], {"user_name": user.first_name or "Admin"})
        await q.message.edit_text(txt, parse_mode="HTML", reply_markup=build_admin_help_keyboard())
