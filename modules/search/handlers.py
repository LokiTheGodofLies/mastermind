import os
import html
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.database.file_db import search_indexed_files_db, get_file_by_id_db, log_file_delivery_db, mark_delivery_deleted_db
from modules.database.config_db import get_config, get_config_int, get_config_bool, get_template, format_template_string
from modules.database.user_db import has_started_helper_bot_db, set_helper_started_db
from modules.allowance.allowance import can_user_search, deduct_search_quota, get_user_quota_summary
from modules.log.startup_log import send_log_with_fallback

ITEMS_PER_PAGE = 5


def _format_result_item(idx: int, row: dict) -> str:
    title = html.escape(row.get("title") or row.get("file_name") or "Unknown Title")
    series = html.escape(row.get("series") or "")
    author = html.escape(row.get("author") or "Unknown Author")
    narrator = html.escape(row.get("narrator") or "N/A")
    length_str = html.escape(row.get("length_str") or "N/A")
    rel_date = html.escape(row.get("release_date") or "N/A")
    publisher = html.escape(row.get("publisher") or "N/A")
    cat = html.escape(row.get("category") or "Book / Audiobook")
    size_b = int(row.get("file_size") or 0)
    size_str = f"{size_b / (1024*1024):.0f}MB" if size_b >= 1024 * 1024 else f"{size_b / 1024:.0f}KB"

    lines = [f"<b>{idx}. {title}</b>"]
    if series:
        lines.append(series)
    lines.append(f"By: {author}")
    if narrator and narrator != "N/A":
        lines.append(f"Narrated by: {narrator}")
    if length_str and length_str != "N/A":
        lines.append(f"Length: {length_str}")
    if rel_date and rel_date != "N/A":
        lines.append(f"Release Date: {rel_date}")
    if publisher and publisher != "N/A":
        lines.append(f"Publisher: {publisher}")
    lines.append(f"Categories: {cat}")
    lines.append(f"<i>{size_str}</i>")
    return "\n".join(lines)


async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE, search_term: str, page: int = 1):
    search_term = search_term.strip()
    results = search_indexed_files_db(search_term, limit=50)
    total = len(results)
    bot_title = get_config("bot_title", "Mastermind Cafe Bot")

    kb = []
    if total > 0:
        tp = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        page = max(1, min(page, tp))
        slice_rows = results[(page - 1) * ITEMS_PER_PAGE : page * ITEMS_PER_PAGE]

        item_blocks = []
        for i, r in enumerate(slice_rows, start=(page - 1) * ITEMS_PER_PAGE + 1):
            item_blocks.append(_format_result_item(i, r))
            btn_title = (r.get("title") or r.get("file_name") or "File")[:38]
            kb.append([InlineKeyboardButton(f"{i}. {btn_title}", callback_data=f"file_dl_{r['id']}")])

        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton("« Prev", callback_data=f"search_page_{search_term[:25]}_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page} / {tp}", callback_data="noop"))
        if page < tp:
            nav.append(InlineKeyboardButton("Next »", callback_data=f"search_page_{search_term[:25]}_{page+1}"))
        kb.append(nav)

        txt = (
            f"🔍 <b>Search results from the {html.escape(bot_title)}'s database</b>\n\n"
            f"<b>{html.escape(search_term)}</b> · {total} match{'es' if total != 1 else ''}\n\n"
            + "\n\n".join(item_blocks)
            + "\n\n❗️❗️❗️ <b>Select a title below to get the file instantly</b> ❗️❗️❗️"
        )
    else:
        txt = (
            f"🔍 <b>Search results from the {html.escape(bot_title)}'s database</b>\n\n"
            f"<b>{html.escape(search_term)}</b> · 0 matches\n\n"
            f"No indexed files matched your query. Tap <b>📝 Request Book</b> below to request it!"
        )

    kb.append([
        InlineKeyboardButton("❌ Cancel", callback_data="search_cancel"),
        InlineKeyboardButton("📝 Request Book", callback_data=f"req_from_search_{search_term[:35]}"),
    ])

    if update.callback_query:
        await update.callback_query.message.edit_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        await update.callback_query.answer()
    else:
        await update.effective_message.reply_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


async def _auto_delete_posted_file(bot, posting_chat_id: int, message_id: int, log_id: int, delay_seconds: int, file_name: str, receiver_id: int):
    await asyncio.sleep(delay_seconds)
    try:
        await bot.delete_message(chat_id=int(posting_chat_id), message_id=int(message_id))
    except Exception:
        pass
    deleted_at = mark_delivery_deleted_db(log_id)
    audit_txt = (
        f"🗑 <b>Temporary File Auto-Deleted (2m Timer)</b>\n\n"
        f"📁 <b>File:</b> <code>{html.escape(file_name)}</code>\n"
        f"👤 <b>Receiver ID:</b> <code>{receiver_id}</code>\n"
        f"📢 <b>Channel / Msg ID:</b> <code>{posting_chat_id} / {message_id}</code>\n"
        f"⏱ <b>Deleted At:</b> <code>{deleted_at}</code>"
    )
    await send_log_with_fallback(bot, audit_txt, "admin_log_group_id", "channel_log_topic_id")


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return
    if context.args:
        await perform_search(update, context, " ".join(context.args).strip(), 1)
        return
    if msg.reply_to_message and msg.reply_to_message.text:
        await perform_search(update, context, msg.reply_to_message.text.strip(), 1)
        return

    txt = (
        "🔍 <b>Library Search Engine</b>\n\n"
        "Use <code>/search &lt;keyword&gt;</code> to search books & audiobooks by title, author, narrator, series, or file name.\n"
        "<i>(Searching is free — quota is only used when a file is delivered!)</i>"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("≼ Back to Start", callback_data="start_menu")]])
    if update.callback_query:
        await update.callback_query.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)
        await update.callback_query.answer()
    else:
        await msg.reply_text(txt, parse_mode="HTML", reply_markup=kb)


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
    elif d.startswith("search_page_"):
        parts = d.replace("search_page_", "", 1).rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            await perform_search(update, context, parts[0], int(parts[1]))
    elif d.startswith("file_dl_"):
        row_id = int(d.replace("file_dl_", ""))
        if not can_user_search(user.id):
            await q.answer("⚠️ Daily search quota reached! Use /refer or wait for reset.", show_alert=True)
            return

        # Step 1: Verify user has started helper bot
        if get_config_bool("require_helper_bot_start", True) and not has_started_helper_bot_db(user.id):
            helper_uname = get_config("helper_bot_username", context.bot.username or "Bot").lstrip("@")
            start_url = f"https://t.me/{helper_uname}?start=helper_init"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"🚀 Start @{helper_uname}", url=start_url)]])
            await q.answer("⚠️ Please start the helper bot first to receive the file.", show_alert=True)
            await q.message.reply_text("Please start the helper bot first to receive the file.", reply_markup=kb)
            return

        row = get_file_by_id_db(row_id)
        if not row:
            await q.answer("❌ File no longer exists in database.", show_alert=True)
            return

        storage_id = get_config("storage_channel_id", fallback_env="STORAGE_GROUP_ID")
        posting_id = get_config("posting_channel_id", fallback_env="SEARCH_CHAT_ID") or storage_id
        file_id = row.get("file_id")
        storage_msg_id = row.get("storage_message_id")
        file_name = row.get("title") or row.get("file_name") or "Book_File"

        await q.answer("📥 Preparing temporary delivery...")
        posted_msg = None
        dm_delivered = False

        # Step 2: Deliver to temporary file-posting channel
        if posting_id:
            try:
                if storage_msg_id and storage_id:
                    posted_msg = await context.bot.copy_message(chat_id=int(posting_id), from_chat_id=int(storage_id), message_id=int(storage_msg_id))
                elif file_id:
                    posted_msg = await context.bot.send_document(chat_id=int(posting_id), document=file_id, caption=f"📁 <b>{html.escape(file_name)}</b>\n⏳ <i>Auto-deletes in 2 minutes</i>", parse_mode="HTML")
            except Exception as ch_err:
                await send_log_with_fallback(
                    context.bot,
                    f"⚠️ <b>Helper/Bot Channel Admin Permission Error</b>\nCould not post to <code>{posting_id}</code>: <code>{ch_err}</code>",
                    "admin_log_group_id",
                    "channel_log_topic_id",
                )

        # Step 3: Mirror/Forward to user DM if possible
        try:
            if storage_msg_id and storage_id:
                await context.bot.copy_message(chat_id=user.id, from_chat_id=int(storage_id), message_id=int(storage_msg_id))
                dm_delivered = True
            elif file_id:
                await context.bot.send_document(chat_id=user.id, document=file_id, caption=f"📁 <b>{html.escape(file_name)}</b>", parse_mode="HTML")
                dm_delivered = True
            set_helper_started_db(user.id, True)
        except Exception:
            pass

        if not posted_msg and not dm_delivered:
            await q.message.reply_text("❌ File delivery failed. No quota was deducted.")
            return

        # Step 4: Deduct search quota ONLY on confirmed delivery
        deduct_search_quota(user.id)
        q_sum = get_user_quota_summary(user.id)

        post_mid = getattr(posted_msg, "message_id", 0) or 0
        clean_cid = str(posting_id).replace("-100", "") if posting_id else ""
        ch_link = f"https://t.me/c/{clean_cid}" if clean_cid else "DM Delivery"
        msg_link = f"https://t.me/c/{clean_cid}/{post_mid}" if (clean_cid and post_mid) else ch_link
        del_secs = get_config_int("file_delete_after_seconds", 120)

        reply_txt = (
            f"✅ <b>File Ready for Download!</b>\n\n"
            f"📁 <b>File:</b> <code>{html.escape(file_name)}</code>\n"
            f"📢 <b>Posting Channel:</b> <a href=\"{ch_link}\">Open Channel</a>\n"
            f"🔗 <b>Message Link:</b> <a href=\"{msg_link}\">Message #{post_mid}</a>\n"
            f"💬 <b>DM Mirror:</b> {'Sent to your DM ✅' if dm_delivered else 'Channel Link Only'}\n"
            f"📊 <b>Remaining Search Quota:</b> <code>{q_sum['searches_left']}</code>\n\n"
            f"⏳ <i>This file in the posting channel will auto-delete in {del_secs // 60} minutes.</i>"
        )
        await q.message.reply_text(reply_txt, parse_mode="HTML")

        log_id = log_file_delivery_db(file_id or "", file_name, context.bot.username or "Bot", user.id, ch_link, msg_link, post_mid, "delivered")
        audit_msg = (
            f"📤 <b>File Shared (Temporary Delivery)</b>\n\n"
            f"🆔 <b>File ID:</b> <code>{html.escape(str(file_id)[:35])}</code>\n"
            f"📁 <b>Title:</b> <code>{html.escape(file_name)}</code>\n"
            f"🤖 <b>Sender:</b> @{context.bot.username or 'Bot'}\n"
            f"👤 <b>Receiver:</b> {html.escape(user.full_name)} (<code>{user.id}</code>)\n"
            f"🔗 <b>Link:</b> {msg_link}\n"
            f"📦 <b>Status:</b> <code>delivered (auto-delete in {del_secs}s)</code>"
        )
        await send_log_with_fallback(context.bot, audit_msg, "admin_log_group_id", "channel_log_topic_id")

        if posted_msg and post_mid and get_config_bool("auto_delete_enabled", True):
            asyncio.create_task(_auto_delete_posted_file(context.bot, int(posting_id), post_mid, log_id, del_secs, file_name, user.id))
