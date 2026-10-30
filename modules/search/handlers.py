import html
import logging
from telegram.error import TelegramError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import items_per_page, search_chat_id, search_topic_id, supported_audiobook_extensions
from modules.database.config_db import get_config
from modules.database.file_db import search_files_db
from modules.allowance.allowance import can_user_search, deduct_search_quota
from modules.search.delivery import deliver_file_dual


def is_search_topic_message(msg) -> bool:
    """True if msg lives in the configured Search topic (support chat on Public, logger group on Testing)."""
    cid, tid = search_chat_id(), search_topic_id()
    if msg is None or cid is None or tid is None:
        return False
    return getattr(msg, "chat_id", None) == cid and getattr(msg, "message_thread_id", None) == tid


def _search_allowed_here(update: Update) -> bool:
    """Search runs in private chat and inside the Search topic only."""
    chat = update.effective_chat
    if chat is None or chat.type == "private":
        return True
    return is_search_topic_message(update.effective_message)


def _topic_link():
    """t.me link that opens the Search topic (works for members)."""
    cid, tid = search_chat_id(), search_topic_id()
    if cid is None or tid is None or not str(cid).startswith("-100"):
        return None
    return f"https://t.me/c/{str(cid)[4:]}/{tid}"


def _clip_term(term: str, page: int, prefix: str = "search_page_") -> str:
    """Builds callback_data that fits Telegram's 64-byte limit by clipping the term."""
    tail = f"_{page}"
    room = 64 - len(prefix.encode()) - len(tail.encode())
    clipped = term.encode()[:room].decode("utf-8", "ignore")
    return f"{prefix}{clipped}{tail}"


async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE, search_term: str, page: int = 1):
    user = update.effective_user
    msg = update.effective_message

    if not _search_allowed_here(update):
        note = "Search works only in the Search topic or in private chat with the bot."
        if update.callback_query:
            await update.callback_query.answer(note, show_alert=True)
        elif msg:
            await msg.reply_text(f"🔍 {note}\nSend <code>/search &lt;keyword&gt;</code> to me in private chat.", parse_mode="HTML")
        return
    in_topic = update.effective_chat is not None and update.effective_chat.type != "private"

    if user and not can_user_search(user.id):
        quota_msg = (
            "⚠️ <b>Daily search quota reached!</b>\n\n"
            "Use <code>/quota</code> to view your limits or <code>/refer</code> to invite friends and earn bonus searches."
        )
        if update.callback_query:
            await update.callback_query.answer("Daily search quota reached!", show_alert=True)
            await update.callback_query.message.edit_text(quota_msg, parse_mode="HTML")
        elif msg:
            await msg.reply_text(quota_msg, parse_mode="HTML")
        return

    rows = search_files_db(search_term)
    audio_exts = supported_audiobook_extensions()
    results = []
    for row in rows:
        row_id = row["id"]
        label = row["file_name"] or f"File #{row_id}"
        ext = (row["extension"] or "").lower()
        cat = (row["category"] if "category" in row.keys() else "") or ""
        icon = "🎧" if (cat == "audiobook" or ext in audio_exts) else "📁"
        if len(label) > 40:
            label = label[:37] + "..."
        results.append((row_id, icon, label))

    total = len(results)
    if total > 0 and page == 1 and user and not update.callback_query:
        deduct_search_quota(user.id)

    keyboard = []
    esc_term = html.escape(search_term)
    if total > 0:
        per_page = items_per_page()
        tp = (total + per_page - 1) // per_page
        page = max(1, min(page, tp))
        for row_id, icon, lbl in results[(page - 1) * per_page : page * per_page]:
            keyboard.append([InlineKeyboardButton(f"{icon} {lbl}", callback_data=f"file_dl_{row_id}")])
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton("« Prev", callback_data=_clip_term(search_term, page - 1)))
        nav.append(InlineKeyboardButton(f"📄 {page}/{tp}", callback_data="noop"))
        if page < tp:
            nav.append(InlineKeyboardButton("Next »", callback_data=_clip_term(search_term, page + 1)))
        if nav:
            keyboard.append(nav)
        txt = f"🔍 <b>Search Results for:</b> <code>{esc_term}</code>\n\nFound {total} matching file(s). Page {page} of {tp}:"
    else:
        txt = f"🔍 <b>Search Results for:</b> <code>{esc_term}</code>\n\n• No matching files found in the database."

    if not in_topic:
        keyboard.append([InlineKeyboardButton("« Back to Search Menu", callback_data="search_menu")])
    if update.callback_query:
        await update.callback_query.message.edit_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        await update.callback_query.answer()
    elif msg:
        await msg.reply_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return
    chat = update.effective_chat
    if chat is not None and chat.type != "private" and not update.callback_query:
        # Groups: search only inside the Search topic (its commands are deleted there), never elsewhere.
        await msg.reply_text(
            "🔍 Search works only in the <b>Search topic</b> or in private chat with me.\n"
            "Open the Search topic and type the book title, or send me <code>/search &lt;keyword&gt;</code> in private chat.",
            parse_mode="HTML",
        )
        return
    if context.args:
        await perform_search(update, context, " ".join(context.args).strip(), 1)
        return
    if update.message and update.message.reply_to_message and update.message.reply_to_message.text:
        await perform_search(update, context, update.message.reply_to_message.text.strip(), 1)
        return
    txt = get_config(
        "search_script",
        default=(
            "🔍 <b>File Search Engine</b>\n\n"
            "You can either join our Search topic and just type the book title there, or search right here in private chat "
            "by providing a keyword after the search command or replying to a message with /search."
        ),
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Join Search Topic", callback_data="join_search_group_quiz")],
        [InlineKeyboardButton("« Back to Start", callback_data="start_menu")],
    ])
    if update.callback_query:
        await update.callback_query.message.edit_text(text=txt, reply_markup=kb, parse_mode="HTML")
        await update.callback_query.answer()
    else:
        await msg.reply_text(text=txt, reply_markup=kb, parse_mode="HTML")


async def search_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    d = q.data
    if d == "join_search_group_quiz":
        await q.message.edit_text(
            "📝 <b>Search Topic Invite</b>\n\nDo you want to join our group and use the Search topic?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Yes, Generate Invite Link", callback_data="generate_group_invite")],
                [InlineKeyboardButton("« Back", callback_data="search_menu")],
            ]),
        )
        await q.answer()
    elif d == "generate_group_invite":
        await q.answer("Generating invite link...")
        gid = search_chat_id()
        if gid is None or search_topic_id() is None:
            await q.message.edit_text(
                "❌ <b>Search topic is not configured.</b>\n\nPlease contact the administrator.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Search Menu", callback_data="search_menu")]]),
            )
            return
        try:
            link = await context.bot.create_chat_invite_link(chat_id=gid, member_limit=1)
            rows = []
            t_url = _topic_link()
            if t_url:
                rows.append([InlineKeyboardButton("📍 Open Search Topic (after joining)", url=t_url)])
            rows.append([InlineKeyboardButton("« Back to Search Menu", callback_data="search_menu")])
            await q.message.edit_text(
                f"🎉 <b>Here is your single-use invite link:</b>\n\n{link.invite_link}\n\n"
                "After joining, open the <b>Search</b> topic and just type the book title or author.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(rows),
            )
        except Exception as e:
            await q.message.edit_text(
                f"❌ <b>Could not generate invite link.</b>\n\nReason: <code>{html.escape(str(e))}</code>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Search Menu", callback_data="search_menu")]]),
            )
    elif d == "search_menu":
        await search_command(update, context)
    elif d == "noop":
        await q.answer("Current Page")
    elif d.startswith("search_page_"):
        parts = d.replace("search_page_", "", 1).rsplit("_", 1)
        if len(parts) == 2:
            await perform_search(update, context, parts[0], int(parts[1]))
    elif d.startswith("search_direct_"):
        query = d.replace("search_direct_", "", 1)
        await perform_search(update, context, query, 1)
    elif d.startswith("file_dl_"):
        row_id = d.replace("file_dl_", "")
        try:
            await q.answer("Preparing dual delivery via helper bot...")
        except TelegramError as exc:
            logging.getLogger(__name__).warning(
                "File-download callback acknowledgement failed; "
                "continuing delivery: %s", exc
            )
        try:
            await deliver_file_dual(update, context, int(row_id))
        except Exception as e:
            await q.message.reply_text(
                f"❌ Error delivering file: <code>{html.escape(str(e))}</code>",
                parse_mode="HTML"
            )


async def search_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass


search_handler = search_command
