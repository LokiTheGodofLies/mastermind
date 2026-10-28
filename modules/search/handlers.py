import html
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.bot_manager import get_helper_bot, get_selected_helper_bot_details
from modules.database.file_db import search_books_by_mode_db, get_file_by_id_db, log_file_delivery_db, mark_delivery_deleted_db
from modules.database.config_db import get_config, get_config_int, get_config_bool
from modules.database.user_db import has_started_helper_bot_db, set_helper_started_db
from modules.allowance.allowance import can_user_search, deduct_search_quota, get_user_quota_summary
from modules.log.startup_log import send_log_with_fallback
from modules.log.logger import get_ist_str

logger = logging.getLogger(__name__)
ITEMS_PER_PAGE = 8

def _format_book_entry(idx: int, row: dict, bot_username: str) -> str:
    title = html.escape(row.get("title") or row.get("file_name") or "Unknown Title")
    series = html.escape(row.get("series") or "Standalone / No Series")
    author = html.escape(row.get("author") or "Unknown Author")
    ext = html.escape((row.get("extension") or ".epub").lstrip("."))
    dl_url = f"https://t.me/{bot_username}?start=dl_{row['id']}"

    return (
        f"<b>{idx}. {title}</b>\n"
        f"📚 <i>{series}</i>\n"
        f"✍️ {author}\n"
        f"📂 <code>.{ext}</code> — <a href=\"{dl_url}\"><b>download</b></a>"
    )

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE, search_term: str, page: int = 1, mode: str = "all"):
    search_term = search_term.strip()
    user = update.effective_user
    uid = user.id if user else 0
    uname = user.first_name if user else "Unknown"

    logger.info(f"[SEARCH] User={uid} ({uname}) | Term='{search_term}' | Mode={mode} | Page={page} | IST={get_ist_str()}")
    results = search_books_by_mode_db(search_term, mode=mode, limit=100)
    total = len(results)
    bot_title = get_config("bot_title", "Mastermind Library Bot")
    bot_uname = (context.bot.username or get_config("bot_username", "MastermindBot")).lstrip("@")
    mode_badge = {"all": "All Formats (📚 + 🎧)", "ebook": "eBooks Only 📚", "audiobook": "Audiobooks Only 🎧"}.get(mode, "All")

    q_short = search_term.encode("utf-8")[:20].decode("utf-8", errors="ignore")
    q_req = search_term.encode("utf-8")[:34].decode("utf-8", errors="ignore")
    kb = []

    if total > 0:
        tp = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        page = max(1, min(page, tp))
        slice_rows = results[(page - 1) * ITEMS_PER_PAGE : page * ITEMS_PER_PAGE]
        blocks = [_format_book_entry(i, r, bot_uname) for i, r in enumerate(slice_rows, start=(page - 1) * ITEMS_PER_PAGE + 1)]

        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton("« Back", callback_data=f"spg|{mode}|{page-1}|{q_short}"))
        nav.append(InlineKeyboardButton(f"{page}/{tp}", callback_data="noop"))
        if page < tp:
            nav.append(InlineKeyboardButton("Next »", callback_data=f"spg|{mode}|{page+1}|{q_short}"))
        kb.append(nav)

        kb.append([
            InlineKeyboardButton("📚" + (" ✓" if mode == "ebook" else ""), callback_data=f"spg|ebook|1|{q_short}"),
            InlineKeyboardButton("📤 Send All", callback_data=f"sendall|{mode}|{page}|{q_short}"),
            InlineKeyboardButton("🎧" + (" ✓" if mode == "audiobook" else ""), callback_data=f"spg|audiobook|1|{q_short}"),
        ])
        txt = (
            f"🔍 <b>Search Results — {html.escape(bot_title)}</b>\n"
            f"🔎 <b>Query:</b> <code>{html.escape(search_term)}</code> | <b>Filter:</b> {mode_badge} ({total} matches)\n\n"
            + "\n\n".join(blocks)
        )
    else:
        kb.append([
            InlineKeyboardButton("📚" + (" ✓" if mode == "ebook" else ""), callback_data=f"spg|ebook|1|{q_short}"),
            InlineKeyboardButton("🎧" + (" ✓" if mode == "audiobook" else ""), callback_data=f"spg|audiobook|1|{q_short}"),
        ])
        txt = (
            f"🔍 <b>Search Results — {html.escape(bot_title)}</b>\n"
            f"🔎 <b>Query:</b> <code>{html.escape(search_term)}</code> | <b>Filter:</b> {mode_badge}\n\n"
            f"No matching files found. Tap <b>📝 Request Book</b> below to request it!"
        )

    kb.append([
        InlineKeyboardButton("❌ Cancel", callback_data="search_cancel"),
        InlineKeyboardButton("📝 Request Book", callback_data=f"req_from_search|{mode}|{q_req}"),
    ])

    if update.callback_query:
        await update.callback_query.message.edit_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
        await update.callback_query.answer()
    else:
        await update.effective_message.reply_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)

async def _auto_delete_posted_file(bot, posting_chat_id: int, message_id: int, log_id: int, delay_seconds: int, file_name: str, receiver_id: int):
    await asyncio.sleep(delay_seconds)
    try:
        await bot.delete_message(chat_id=int(posting_chat_id), message_id=int(message_id))
    except Exception:
        pass
    deleted_at = mark_delivery_deleted_db(log_id)
    audit_txt = (
        f"🗑 <b>Temporary File Auto-Deleted</b>\n"
        f"📁 <b>File:</b> <code>{html.escape(file_name)}</code>\n"
        f"👤 <b>Receiver:</b> <code>{receiver_id}</code>\n"
        f"📢 <b>Msg:</b> <code>{posting_chat_id}/{message_id}</code>\n"
        f"⏱ <b>Deleted At (IST):</b> <code>{deleted_at}</code>"
    )
    await send_log_with_fallback(bot, audit_txt, "admin_log_group_id", "channel_log_topic_id")

async def deliver_file_to_user(reply_target_msg, user, row_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not can_user_search(user.id):
        await reply_target_msg.reply_text("⚠️ <b>Daily search quota reached!</b> Use <code>/refer</code> to earn +10 bonus quota.", parse_mode="HTML")
        return False

    if get_config_bool("require_helper_bot_start", True) and not has_started_helper_bot_db(user.id):
        try:
            h_details = await get_selected_helper_bot_details()
            helper_uname = (h_details.get("username") or context.bot.username or "Bot").lstrip("@")
            helper_title = h_details.get("title") or "Helper Bot"
        except Exception:
            helper_uname = (get_config("helper_bot_username", context.bot.username or "Bot")).lstrip("@")
            helper_title = "Helper Bot"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"🚀 Start @{helper_uname} ({helper_title})", url=f"https://t.me/{helper_uname}?start=helper_init")]])
        await reply_target_msg.reply_text(f"Please start the helper bot (@{helper_uname}) first to receive the file.", reply_markup=kb)
        return False

    row = get_file_by_id_db(row_id)
    if not row:
        await reply_target_msg.reply_text("❌ File no longer exists in database.")
        return False

    storage_id = get_config("storage_channel_id", fallback_env="STORAGE_GROUP_ID")
    posting_id = get_config("posting_channel_id", fallback_env="SEARCH_CHAT_ID") or storage_id
    file_id, storage_msg_id = row.get("file_id"), row.get("storage_message_id")
    file_name = row.get("title") or row.get("file_name") or "Book_File"

    try:
        h_details = await get_selected_helper_bot_details()
        delivery_bot = h_details["bot"]
    except Exception:
        delivery_bot = context.bot

    posted_msg, dm_ok = None, False

    if posting_id:
        try:
            if storage_msg_id and storage_id:
                posted_msg = await delivery_bot.copy_message(chat_id=int(posting_id), from_chat_id=int(storage_id), message_id=int(storage_msg_id))
            elif file_id:
                posted_msg = await delivery_bot.send_document(chat_id=int(posting_id), document=file_id, caption=f"📁 <b>{html.escape(file_name)}</b>", parse_mode="HTML")
        except Exception as ch_err:
            await send_log_with_fallback(context.bot, f"⚠️ <b>Helper Channel Error</b>: <code>{ch_err}</code>", "admin_log_group_id", "channel_log_topic_id")

    try:
        if storage_msg_id and storage_id:
            await delivery_bot.copy_message(chat_id=user.id, from_chat_id=int(storage_id), message_id=int(storage_msg_id))
            dm_ok = True
        elif file_id:
            await delivery_bot.send_document(chat_id=user.id, document=file_id, caption=f"📁 <b>{html.escape(file_name)}</b>", parse_mode="HTML")
            dm_ok = True
        set_helper_started_db(user.id, True)
    except Exception:
        pass

    if not posted_msg and not dm_ok:
        await reply_target_msg.reply_text("❌ Delivery failed. No quota was deducted.")
        return False

    deduct_search_quota(user.id)
    q_sum = get_user_quota_summary(user.id)
    post_mid = getattr(posted_msg, "message_id", 0) or 0
    clean_cid = str(posting_id).replace("-100", "") if posting_id else ""
    ch_link = f"https://t.me/c/{clean_cid}" if clean_cid else "DM"
    msg_link = f"https://t.me/c/{clean_cid}/{post_mid}" if (clean_cid and post_mid) else ch_link
    del_secs = get_config_int("file_delete_after_seconds", 120)

    await reply_target_msg.reply_text(
        f"✅ <b>File Delivered!</b>\n"
        f"📁 <b>File:</b> <code>{html.escape(file_name)}</code>\n"
        f"📢 <b>Channel Link:</b> <a href=\"{ch_link}\">Open Channel</a>\n"
        f"🔗 <b>Message Link:</b> <a href=\"{msg_link}\">Message #{post_mid}</a>\n"
        f"💬 <b>DM Mirror:</b> {'Sent to DM ✅' if dm_ok else 'Channel Only'}\n"
        f"📊 <b>Searches Left:</b> <code>{q_sum['searches_left']}</code>\n"
        f"⏳ <i>Auto-deletes from channel in {del_secs // 60} minutes.</i>",
        parse_mode="HTML",
    )
    log_id = log_file_delivery_db(file_id or "", file_name, getattr(delivery_bot, "username", None) or "HelperBot", user.id, ch_link, msg_link, post_mid, "delivered")
    if posted_msg and post_mid and get_config_bool("auto_delete_enabled", True):
        asyncio.create_task(_auto_delete_posted_file(used_bot, int(posting_id), post_mid, log_id, del_secs, file_name, user.id))
    return True

async def _run_search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str = "all"):
    msg = update.effective_message
    if not msg:
        return
    if context.args:
        await perform_search(update, context, " ".join(context.args).strip(), 1, mode=mode)
        return
    if msg.reply_to_message and msg.reply_to_message.text:
        await perform_search(update, context, msg.reply_to_message.text.strip(), 1, mode=mode)
        return
    txt = (
        "🔍 <b>Library Search Engine</b>\n\n"
        "• <code>/search &lt;keyword&gt;</code> — Search all books & audiobooks\n"
        "• <code>/searchebook &lt;keyword&gt;</code> — Search eBooks only 📚\n"
        "• <code>/searchaudiobook &lt;keyword&gt;</code> — Search Audiobooks only 🎧\n\n"
        "<i>Matches title, author, series, or keywords!</i>"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("≼ Back to Start", callback_data="start_menu")]])
    if update.callback_query:
        await update.callback_query.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)
        await update.callback_query.answer()
    else:
        await msg.reply_text(txt, parse_mode="HTML", reply_markup=kb)

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _run_search_cmd(update, context, mode="all")

async def searchebook_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _run_search_cmd(update, context, mode="ebook")

async def searchaudiobook_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _run_search_cmd(update, context, mode="audiobook")

async def search_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    d = q.data
    user = q.from_user

    if d == "search_menu":
        await search_command(update, context)
    elif d == "noop":
        await q.answer("Current Page")
    elif d == "search_cancel":
        await q.answer("Search closed.")
        await q.message.delete()
    elif d.startswith("spg|"):
        _, mode, pg_str, kw = d.split("|", 3)
        await perform_search(update, context, kw, int(pg_str), mode=mode)
    elif d.startswith("sendall|"):
        _, mode, pg_str, kw = d.split("|", 3)
        page = int(pg_str)
        results = search_books_by_mode_db(kw, mode=mode, limit=100)
        slice_rows = results[(page - 1) * ITEMS_PER_PAGE : page * ITEMS_PER_PAGE]
        if not slice_rows:
            await q.answer("No files on this page.", show_alert=True)
            return
        await q.answer(f"📤 Sending {len(slice_rows)} file(s)...")
        for r in slice_rows:
            ok = await deliver_file_to_user(q.message, user, r["id"], context)
            if not ok:
                break
            await asyncio.sleep(0.4)
    elif d.startswith("file_dl_"):
        await q.answer("📥 Delivering file...")
        await deliver_file_to_user(q.message, user, int(d.replace("file_dl_", "")), context)
