import asyncio
import html
import logging
import re
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
from config import (
    creator_dm_link,
    bot_name,
    items_per_page,
    search_chat_id,
    search_topic_id,
    supported_archive_extensions,
    supported_audiobook_extensions,
    supported_ebook_extensions,
)
from modules.database.config_db import get_config
from modules.database.file_db import search_files_db
from modules.allowance.allowance import can_user_search, deduct_search_quota
from modules.indexing.book_index import format_series_label, parse_title_and_series
from modules.search.delivery import deliver_file_dual
from modules.utility.rich_ui import styled_button
from modules.utility.small_caps import from_small_caps

logger = logging.getLogger(__name__)


def is_search_topic_message(msg) -> bool:
    """True if msg lives in the configured Search topic."""
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
    cid, tid = search_chat_id(), search_topic_id()
    if cid is None or tid is None or not str(cid).startswith("-100"):
        return None
    return f"https://t.me/c/{str(cid)[4:]}/{tid}"


def _format_size(size_bytes: int) -> str:
    if not size_bytes:
        return "Unknown size"
    mb = size_bytes / (1024 * 1024)
    if mb >= 1:
        return f"{mb:.2f} MB"
    return f"{size_bytes / 1024:.2f} KB"


def _extract_item_fields(row) -> tuple[str, str, str, str, str]:
    """
    Extracts Title, Series, Author, Size, and Extension from DB record.
    Parses Option B caption (`📖 Title:`, `📚 Series:`, `✍️ Author:`) if present; falls back to filename/metadata.
    """
    caption = row["caption"] or ""
    file_name = row["file_name"] or f"File #{row['id']}"
    ext = (row["extension"] or "").lstrip(".")
    size_str = _format_size(row["file_size"])

    # 1. Title
    title = ""
    m_t = re.search(r"(?:Title|Book|Audiobook|Archive):[ \t]*([^\n]+)", caption, re.IGNORECASE)
    if m_t:
        clean_t = re.sub(r"<[^>]+>", "", m_t.group(1)).strip()
        if clean_t:
            title, _ = parse_title_and_series(clean_t)
    if not title:
        raw_t, _ = parse_title_and_series(file_name)
        if " - " in raw_t:
            raw_t = raw_t.split(" - ")[0].strip()
        title = re.sub(r"\.[a-zA-Z0-9]{2,5}$", "", raw_t).strip()

    # 2. Series (Option B format)
    series = ""
    m_s = re.search(r"Series:[ \t]*([^\n]+)", caption, re.IGNORECASE)
    if m_s:
        clean_s = re.sub(r"<[^>]+>", "", m_s.group(1)).strip()
        if clean_s:
            series = format_series_label(clean_s)
    if not series:
        _, series = parse_title_and_series(file_name)
    if not series:
        series = "Standalone"

    # 3. Author
    author = ""
    m_a = re.search(r"(?:Author|By):[ \t]*([^\n]+)", caption, re.IGNORECASE)
    if m_a:
        clean_a = re.sub(r"<[^>]+>", "", m_a.group(1)).strip()
        if clean_a:
            author = clean_a
    if not author:
        author = row["user_title"] or "Author Unknown"
    author = re.sub(r"<[^>]+>", "", author).strip()
    return title, series, author, size_str, ext


def _item_kind(row) -> str:
    """'Audiobook', 'Archive' or 'Ebook' for a DB row (same rules as the search filters)."""
    cat = (row["category"] or "").lower()
    ext = f".{(row['extension'] or '').lstrip('.').lower()}"
    if cat == "audiobook" or ext in supported_audiobook_extensions():
        return "Audiobook"
    if cat == "archive" or ext in supported_archive_extensions():
        return "Archive"
    return "Ebook"


_TABLE_HEADERS = ("No.", "Title", "Author", "Series", "Size", "Format", "Ext")


def build_results_table_html(items) -> str:
    """ONE wide rich-HTML table for a whole result page (Mira style: scrolls sideways on a phone).

    `items` = iterable of (idx, row_id, title, author, series, size_str, kind, ext, dl_url).
    Column 1 is the download column: `<a href="...?start=dl_<row id>">📥 N</a>`. Telegram tables
    accept inline formatting only (no `<tg-button>` blocks inside cells), so a tappable link is the
    closest thing to a button; the deep link runs the same `deliver_file_dual` pipeline.
    All values are HTML-escaped. In a plain-HTML fallback `rich_ui.tables_to_pre()` turns the table
    into a monospace block and `rich_ui` rebuilds the 📥 links as real keyboard buttons."""
    def esc(v) -> str:
        return html.escape(str(v), quote=False)

    head = "<tr>" + "".join(f"<th>{esc(h)}</th>" for h in _TABLE_HEADERS) + "</tr>"
    body = []
    for idx, _row_id, title, author, series, size_str, kind, ext, dl_url in items:
        body.append(
            "<tr>"
            f'<td><a href="{html.escape(dl_url, quote=True)}">📥 {idx}</a></td>'
            f"<td>{esc(title)}</td>"
            f"<td>{esc(author)}</td>"
            f"<td>{esc(series)}</td>"
            f"<td>{esc(size_str)}</td>"
            f"<td>{esc(kind)}</td>"
            f"<td>{esc(f'.{ext}' if ext else '-')}</td>"
            "</tr>"
        )
    return f"<table striped>{head}{''.join(body)}</table>"


async def perform_search(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    search_term: str,
    page: int = 1,
    filter_mode: str = "all",
):
    """
    Renders search results in Bot API 10.3 Rich Format with colorful in-text buttons.
    One wide, sideways-scrolling table per page (one row per book):
      | 📥 N (download link) | Title | Author | Series (or Standalone) | Size | Format | Ext |
    Bottom keyboard: pagination, Ebooks / Send All / Audio filters.
    """
    user = update.effective_user
    msg = update.effective_message
    search_term = from_small_caps(search_term or "")  # accept text copied from the bot's small-caps messages

    if not _search_allowed_here(update):
        note = "Search works only in the Search topic or in private chat with the bot."
        if update.callback_query:
            await update.callback_query.answer(note, show_alert=True)
        elif msg:
            await msg.reply_text(
                f"🔍 {note}\nSend <code>/search &lt;keyword&gt;</code> to me in private chat.",
                parse_mode="HTML",
            )
        return

    in_topic = update.effective_chat is not None and update.effective_chat.type != "private"

    if user and not can_user_search(user.id):
        quota_msg = (
            "⚠️ <b>Daily search quota reached!</b>\n\n"
            "Use <code>/quota</code> to view your limits or <code>/refer</code> to invite friends and earn bonus searches."
        )
        quota_kb = InlineKeyboardMarkup([
            [
                styled_button("📊 Check Quota", callback_data="quota", style="primary"),
                styled_button("🎁 Refer & Earn", callback_data="refer_more_callback", style="success"),
            ]
        ])
        if update.callback_query:
            await update.callback_query.answer("Daily search quota reached!", show_alert=True)
            await update.callback_query.message.edit_text(quota_msg, parse_mode="HTML", reply_markup=quota_kb)
        elif msg:
            await msg.reply_text(quota_msg, parse_mode="HTML", reply_markup=quota_kb)
        return

    all_rows = search_files_db(search_term)
    audio_exts = supported_audiobook_extensions()
    ebook_exts = supported_ebook_extensions()
    arch_exts = supported_archive_extensions()

    # Apply format filters
    filtered_rows = []
    for r in all_rows:
        cat = (r["category"] or "").lower()
        ext = f".{(r['extension'] or '').lstrip('.').lower()}"
        is_audio = (cat == "audiobook" or ext in audio_exts)
        is_ebook = (cat in ("ebook", "archive") or ext in ebook_exts or ext in arch_exts)

        if filter_mode == "audio":
            if is_audio or ext in arch_exts:
                filtered_rows.append(r)
        elif filter_mode == "ebook":
            if is_ebook:
                filtered_rows.append(r)
        else:
            filtered_rows.append(r)

    total_matches = len(filtered_rows)
    if total_matches > 0 and page == 1 and user and not update.callback_query:
        deduct_search_quota(user.id)

    per_page = 10
    total_pages = max(1, (total_matches + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))

    filter_labels = {
        "all": "All Formats (📚 + 🎧)",
        "ebook": "Ebooks Only (📚)",
        "audio": "Audiobooks Only (🎧)",
    }
    filter_label_str = filter_labels.get(filter_mode, "All Formats (📚 + 🎧)")

    bot_uname = context.bot.username or "GeorgeOrwellAi"
    bot_title = getattr(context.bot, "first_name", None) or bot_name()
    esc_term = html.escape(search_term)

    # Build Rich Header
    lines = [
        f"🔍 <b>Search Results — {html.escape(bot_title)} Library Bot</b>",
        f"🔎 <b>Query:</b> <mark>{esc_term}</mark> | <b>Filter:</b> <mark>{filter_label_str}</mark> (<b>{total_matches}</b> matches)\n",
    ]

    start_idx = (page - 1) * per_page
    page_items = filtered_rows[start_idx : start_idx + per_page]

    if page_items:
        table_items = []
        for idx, row in enumerate(page_items, start=start_idx + 1):
            title, series, author, size_str, ext = _extract_item_fields(row)
            row_id_val = str(row["id"])
            dl_url = f"https://t.me/{bot_uname}?start=dl_{row_id_val}"
            table_items.append((idx, row_id_val, title, author, series, size_str, _item_kind(row), ext, dl_url))
        lines.append(build_results_table_html(table_items))
        lines.append("")
        lines.append("<i>👆 Tap the 📥 number in the first column to download that book.</i>")
    else:
        lines.append(f"• No files found matching <mark>{esc_term}</mark> in <b>{filter_label_str}</b>.\n")

    text_body = "\n".join(lines).strip()

    # Short query clip to fit callback data inside 64 bytes
    clip_q = search_term[:20]

    # Build Bottom Navigation & Filter Controls
    keyboard = []

    # Row 1: Pagination with DisabledButton indicator
    if total_pages > 1:
        nav = []
        if page > 1:
            nav.append(styled_button("◀️ Prev", callback_data=f"sp_{filter_mode}_{page - 1}_{clip_q}", style="primary"))
        nav.append(styled_button(f"📄 {page}/{total_pages}", callback_data="noop", disabled=True))
        if page < total_pages:
            nav.append(styled_button("Next ▶️", callback_data=f"sp_{filter_mode}_{page + 1}_{clip_q}", style="primary"))
        keyboard.append(nav)
    else:
        keyboard.append([styled_button("📄 1/1", callback_data="noop", disabled=True)])

    # Row 2: Filters & Send All
    ebk_target = "all" if filter_mode == "ebook" else "ebook"
    aud_target = "all" if filter_mode == "audio" else "audio"
    ebk_lbl = "📚 Ebooks ✅" if filter_mode == "ebook" else "📚 Ebooks"
    aud_lbl = "🎧 Audio ✅" if filter_mode == "audio" else "🎧 Audio"

    action_row = [
        styled_button(ebk_lbl, callback_data=f"sf_{ebk_target}_1_{clip_q}", style="success" if filter_mode == "ebook" else "primary"),
        styled_button("📨 Send All", callback_data=f"sa_{filter_mode}_{page}_{clip_q}", style="success"),
        styled_button(aud_lbl, callback_data=f"sf_{aud_target}_1_{clip_q}", style="success" if filter_mode == "audio" else "primary"),
    ]
    keyboard.append(action_row)

    if not in_topic:
        keyboard.append([styled_button("« Back to Search Menu", callback_data="search_menu", style="primary")])

    markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.message.edit_text(
            text_body,
            parse_mode="HTML",
            reply_markup=markup,
            disable_web_page_preview=True,
        )
        await update.callback_query.answer()
    elif msg:
        await msg.reply_text(
            text_body,
            parse_mode="HTML",
            reply_markup=markup,
            disable_web_page_preview=True,
        )


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return
    chat = update.effective_chat
    if chat is not None and chat.type != "private" and not update.callback_query:
        await msg.reply_text(
            "🔍 Search works only in the <b>Search topic</b> or in private chat with me.\n"
            "Open the Search topic and type the book title, or send me <code>/search &lt;keyword&gt;</code> in private chat.",
            parse_mode="HTML",
        )
        return

    if context.args:
        await perform_search(update, context, " ".join(context.args).strip(), 1, filter_mode="all")
        return

    if update.message and update.message.reply_to_message and update.message.reply_to_message.text:
        await perform_search(update, context, update.message.reply_to_message.text.strip(), 1, filter_mode="all")
        return

    txt = get_config(
        "search_script",
        default=(
            "🔍 <b>File Search Engine</b>\n\n"
            "You can either join our <b>Search Topic</b> and simply type the book title there, or search right here in private chat "
            "by sending <code>/search &lt;book title or author&gt;</code>."
        ),
    )
    kb = InlineKeyboardMarkup([
        [styled_button("👥 Join Search Topic", callback_data="join_search_group_quiz", style="success")],
        [styled_button("« Back to Start", callback_data="start_menu", style="primary")],
    ])
    if update.callback_query:
        await update.callback_query.message.edit_text(text=txt, reply_markup=kb, parse_mode="HTML")
        await update.callback_query.answer()
    else:
        await msg.reply_text(text=txt, reply_markup=kb, parse_mode="HTML")


async def search_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.data:
        return
    d = q.data

    if d == "join_search_group_quiz":
        await q.message.edit_text(
            "📝 <b>Search Topic Invite</b>\n\nDo you want to join our community group and use the live Search topic?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [styled_button("✅ Yes, Generate Invite Link", callback_data="generate_group_invite", style="success")],
                [styled_button("« Back", callback_data="search_menu", style="primary")],
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
                reply_markup=InlineKeyboardMarkup([[styled_button("« Back to Search Menu", callback_data="search_menu", style="primary")]]),
            )
            return
        try:
            link = await context.bot.create_chat_invite_link(chat_id=gid, member_limit=1)
            rows = [[styled_button("🚀 Join Group (Single-Use Invite)", url=link.invite_link, style="success")]]
            t_url = _topic_link()
            if t_url:
                rows.append([styled_button("📍 Open Search Topic (after joining)", url=t_url, style="primary")])
            rows.append([styled_button("« Back to Search Menu", callback_data="search_menu", style="primary")])
            await q.message.edit_text(
                "🎉 <b>Your Single-Use Invite Link is Ready!</b>\n\n"
                "Tap the green button below to join, then open the <mark>Search</mark> topic and type any book title or author.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(rows),
            )
        except Exception as e:
            await q.message.edit_text(
                f"❌ <b>Could not generate invite link.</b>\n\nReason: <code>{html.escape(str(e))}</code>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[styled_button("« Back to Search Menu", callback_data="search_menu", style="primary")]]),
            )

    elif d == "search_menu":
        await search_command(update, context)

    elif d.startswith("search_direct_"):
        query = d.replace("search_direct_", "", 1)
        await perform_search(update, context, query, 1, filter_mode="all")

    elif d == "noop":
        await q.answer("Page indicator")

    # Page Navigation: sp_{filter}_{page}_{query}
    elif d.startswith("sp_"):
        parts = d.split("_", 3)
        if len(parts) >= 4:
            f_mode, p_str, query = parts[1], parts[2], parts[3]
            page = int(p_str) if p_str.isdigit() else 1
            await perform_search(update, context, query, page, filter_mode=f_mode)

    # Filter Toggle: sf_{target_filter}_{page}_{query}
    elif d.startswith("sf_"):
        parts = d.split("_", 3)
        if len(parts) >= 4:
            f_mode, p_str, query = parts[1], parts[2], parts[3]
            page = int(p_str) if p_str.isdigit() else 1
            await perform_search(update, context, query, page, filter_mode=f_mode)

    # Send All: sa_{filter}_{page}_{query}
    elif d.startswith("sa_"):
        parts = d.split("_", 3)
        if len(parts) >= 4:
            f_mode, p_str, query = parts[1], parts[2], parts[3]
            page = int(p_str) if p_str.isdigit() else 1

            all_rows = search_files_db(query)
            audio_exts = supported_audiobook_extensions()
            ebook_exts = supported_ebook_extensions()
            arch_exts = supported_archive_extensions()

            target_rows = []
            for r in all_rows:
                cat = (r["category"] or "").lower()
                ext = f".{(r['extension'] or '').lstrip('.').lower()}"
                is_audio = (cat == "audiobook" or ext in audio_exts)
                is_ebook = (cat in ("ebook", "archive") or ext in ebook_exts or ext in arch_exts)

                if f_mode == "audio" and (is_audio or ext in arch_exts):
                    target_rows.append(r)
                elif f_mode == "ebook" and is_ebook:
                    target_rows.append(r)
                elif f_mode == "all":
                    target_rows.append(r)

            per_page = 10
            start_idx = (page - 1) * per_page
            batch = target_rows[start_idx : start_idx + per_page]

            if not batch:
                await q.answer("No files to deliver.", show_alert=True)
                return

            await q.answer(f"🚀 Delivering {len(batch)} files via dual delivery...", show_alert=False)

            delivered_count = 0
            for row in batch:
                try:
                    await deliver_file_dual(update, context, int(row["id"]))
                    delivered_count += 1
                    await asyncio.sleep(0.4)
                except Exception:
                    pass

            await q.message.reply_text(
                f"✅ <b>Send All Complete:</b> Successfully queued <mark>{delivered_count}</mark> file(s) for dual delivery!",
                parse_mode="HTML",
            )

    # Backward compatibility for file_dl_
    elif d.startswith("file_dl_"):
        row_id = d.replace("file_dl_", "")
        await q.answer("Preparing dual delivery via helper bot...")
        try:
            await deliver_file_dual(update, context, int(row_id))
        except Exception as e:
            logger.error("Inline delivery failed: %s", e)
            try:
                from modules.log.startup_log import report_error
                u = update.effective_user
                err_details = (
                    f"🚨 <b>Inline Button Delivery Error</b>\n\n"
                    f"• User: {u.first_name if u else 'User'} (<code>{u.id if u else 0}</code>)\n"
                    f"• File Row ID: <code>{row_id}</code>\n"
                    f"• Error: <code>{html.escape(str(e))}</code>"
                )
                await report_error(context.application, err_details, title="Inline Button Delivery Error")
            except Exception:
                pass
            support_link = creator_dm_link()
            markup = InlineKeyboardMarkup([[styled_button("💬 Contact Support", url=support_link, style="primary")]]) if support_link else None
            user_msg = (
                "⚠️ <b>We encountered an error while sending your file.</b>\n\n"
                "Our administrators have been notified and it will be resolved shortly.\n"
                "Please wait a moment and try again, or tap below to contact support!"
            )
            await q.message.reply_text(user_msg, reply_markup=markup, parse_mode="HTML")


async def search_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass


search_handler = search_command
