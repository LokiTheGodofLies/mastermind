from modules.database.user_db import record_user_last_file_db
"""Dual file delivery via Helper Bots (Posting Channel with Auto-Delete + Helper Bot PM)."""
import asyncio
import html
import logging
import time
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import (
    auto_delete_seconds,
    bot_token,
    community_link,
    creator_dm_link,
    helper_bot_tokens,
    posting_channel_id,
    storage_group_id,
)
from modules.database.file_db import (
    find_file_candidates_by_ids_db,
    get_file_by_id_db,
    get_storage_message_id_bounds_db,
    sync_unique_file_storage_db,
    update_storage_message_id_db,
)
from modules.log.startup_log import report_error
from modules.utility.rich_ui import styled_button

logger = logging.getLogger(__name__)

_HELPER_META_CACHE: dict[str, dict] = {}
_POSTING_CHAT_CACHE: dict[int, str | None] = {}
_rr_counter = 0


async def _get_helper_bot_meta(token: str, app=None) -> dict | None:
    """Resolves and caches helper bot username and id from its token via get_me()."""
    if token in _HELPER_META_CACHE:
        return _HELPER_META_CACHE[token]
    try:
        async with Bot(token) as hb:
            me = await hb.get_me()
        meta = {
            "token": token,
            "id": me.id,
            "username": me.username or "",
            "first_name": me.first_name or "Helper Bot",
        }
        _HELPER_META_CACHE[token] = meta
        return meta
    except Exception as exc:
        logger.error("Failed to resolve helper bot token (…%s): %s", token[-4:], exc)
        if app:
            err_details = (
                f"🚨 <b>Invalid / Unreachable Helper Bot Token</b>\n\n"
                f"• Token Suffix: <code>…{token[-6:]}</code>\n"
                f"• Error: <code>{html.escape(str(exc))}</code>\n\n"
                f"<i>Please verify PUBLIC_/TESTING_HELPER_BOT_TOKENS in environment variables or @BotFather.</i>"
            )
            try:
                asyncio.create_task(report_error(app, err_details, title="Invalid Helper Bot Token"))
            except Exception:
                pass
        return None


async def select_helper_bot(fallback_bot, app=None) -> dict:
    """Selects one reachable helper bot (round-robin) and returns its token and username."""
    global _rr_counter
    tokens = helper_bot_tokens()
    if tokens:
        n = len(tokens)
        start = _rr_counter % n
        _rr_counter += 1
        for offset in range(n):
            tok = tokens[(start + offset) % n]
            meta = await _get_helper_bot_meta(tok, app)
            if meta and meta.get("username"):
                return meta

    if app and tokens:
        err_details = (
            "🚨 <b>All Helper Bots Unreachable</b>\n\n"
            f"• Configured Tokens Count: {len(tokens)}\n"
            "• Issue: None of the configured helper bot tokens could resolve via get_me()."
        )
        try:
            asyncio.create_task(report_error(app, err_details, title="All Helper Bots Unreachable"))
        except Exception:
            pass

    # Fallback to main bot if no helper bot tokens are configured or reachable
    username = getattr(fallback_bot, "username", None)
    if not username:
        try:
            me = await fallback_bot.get_me()
            username = me.username
        except Exception:
            username = ""
    return {
        "token": None,
        "id": getattr(fallback_bot, "id", 0),
        "username": username or "",
        "first_name": "Main Bot",
    }


def build_channel_message_link(chat_id: int, message_id: int, chat_username: str | None = None) -> str:
    """Builds a direct Telegram deep link to a specific message inside the posting channel."""
    if chat_username:
        return f"https://t.me/{chat_username.lstrip('@')}/{message_id}"
    cid_str = str(chat_id)
    if cid_str.startswith("-100"):
        internal_id = cid_str[4:]
    else:
        internal_id = cid_str.lstrip("-")
    return f"https://t.me/c/{internal_id}/{message_id}"


async def _get_posting_channel_username(bot, chat_id: int) -> str | None:
    if chat_id in _POSTING_CHAT_CACHE:
        return _POSTING_CHAT_CACHE[chat_id]
    try:
        chat = await bot.get_chat(chat_id)
        uname = getattr(chat, "username", None)
        _POSTING_CHAT_CACHE[chat_id] = uname
        return uname
    except Exception:
        return None


async def _auto_delete_message(token: str | None, fallback_bot, chat_id: int, message_id: int, delay: int):
    """Deletes a message from the posting channel after `delay` seconds using the same helper bot."""
    await asyncio.sleep(max(1, delay))
    try:
        if token:
            async with Bot(token) as hb:
                await hb.delete_message(chat_id=chat_id, message_id=message_id)
        elif fallback_bot:
            await fallback_bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as exc:
        logger.warning("Auto-delete failed in chat %s for msg %s: %s", chat_id, message_id, exc)


def build_file_info_html(row) -> str:
    """Field | Value TABLE (Mira style) for the delivery card: italic emoji labels, monospace values.
    Rows: Book/Audiobook, Author/By, Series, Narrated by, Length, Release Date (only what the caption
    really has), then File, Size, Type. Rich tables exist only in text messages, so this is used for
    the main bot's delivery card; file captions (Storage Group / copied file) stay text."""
    from modules.indexing.book_index import _parse_caption_meta
    from modules.search.handlers import _format_size, _item_kind

    e = lambda v: html.escape(str(v), quote=False)
    kind = _item_kind(row)
    audio = kind == "Audiobook"
    meta = _parse_caption_meta(row["caption"] or "") or {}
    ext = (row["extension"] or "").lstrip(".")
    rows = []

    def add(label, value, code=True):
        value = (value or "").strip()
        if value:
            rows.append(f"<tr><td>{label}</td><td>{'<code>' + e(value) + '</code>' if code else e(value)}</td></tr>")

    add("🎧 <i>Audiobook</i>" if audio else "📚 <i>Book</i>", meta.get("book_title"), code=False)
    add("✍️ <i>By</i>" if audio else "✍️ <i>Author</i>", meta.get("book_author"))
    add("📚 <i>Series</i>", meta.get("book_series"))
    add("🎙 <i>Narrated by</i>", meta.get("narrator"))
    add("⏱ <i>Length</i>", meta.get("length"))
    add("📅 <i>Release Date</i>", meta.get("book_published"))
    add("📁 <i>File</i>", row["file_name"] or "File")
    add("📦 <i>Size</i>", _format_size(row["file_size"]))
    add("📦 <i>Type</i>", f".{ext}" if ext else "")
    return "<table><tr><th>Field</th><th>Value</th></tr>" + "".join(rows) + "</table>"


def _fmt_size(n) -> str:
    from modules.search.handlers import _format_size
    return _format_size(n)


def _is_missing_storage_msg_error(exc: Exception) -> bool:
    """Returns True when Telegram reports that the storage_message_id in the Storage Group does not exist."""
    msg = str(exc or "").lower()
    return any(
        p in msg
        for p in (
            "message to copy not found",
            "message_id_invalid",
            "message not found",
            "message to forward not found",
        )
    )


def _row_val(row, key: str, default=None):
    try:
        if hasattr(row, "keys") and key in row.keys():
            return row[key]
        if isinstance(row, dict):
            return row.get(key, default)
    except Exception:
        pass
    return default


def _build_backfill_caption(row) -> str:
    """Builds a clean Mira-style storage caption when syncing/restoring a file in the Storage Group."""
    from modules.indexing.book_index import _parse_caption_meta, format_index_channel_caption
    raw_cap = _row_val(row, "caption") or ""
    parsed = _parse_caption_meta(raw_cap) if raw_cap else {}
    fname = _row_val(row, "file_name") or "File"
    fsize_str = _fmt_size(_row_val(row, "file_size") or 0)
    ext = (_row_val(row, "extension") or "").lstrip(".")
    cat = _row_val(row, "category") or "ebook"
    if parsed.get("book_title") and parsed.get("book_author"):
        meta = {
            "is_matched": True,
            "title": parsed.get("book_title"),
            "author": parsed.get("book_author"),
            "series": parsed.get("book_series") or "Standalone",
            "narrator": parsed.get("narrator") or "",
            "length": parsed.get("length") or "",
            "published": parsed.get("book_published") or "",
        }
        return format_index_channel_caption(fname, fsize_str, ext, cat, meta, cat)
    return (
        f"📁 <b>File:</b> <code>{html.escape(fname)}</code>\n"
        f"📦 <b>Size:</b> <code>{html.escape(fsize_str)}</code> | "
        f"<b>Type:</b> <code>.{html.escape(ext)}</code>"
    )


async def _probe_storage_group_for_file(
    bot_inst,
    storage_id: int,
    target_unique_id: str | None,
    target_file_id: str | None,
    candidate_mids: list[int],
) -> tuple[int | None, str | None]:
    """
    Checks candidate message IDs in the Storage Group (`storage_id`) by temporarily forwarding/inspecting
    within `storage_id` to see if any message matches `target_unique_id` or `target_file_id`.
    Returns `(found_storage_message_id, found_file_id)` or `(None, None)`.
    """
    from modules.indexing.book_index import extract_media_info
    if not bot_inst or not hasattr(bot_inst, "forward_message"):
        return None, None

    for mid in candidate_mids:
        if not mid or mid <= 0:
            continue
        fwd = None
        try:
            fwd = await bot_inst.forward_message(
                chat_id=int(storage_id),
                from_chat_id=int(storage_id),
                message_id=int(mid),
                disable_notification=True,
            )
            info = extract_media_info(fwd) if fwd else None
            if fwd and hasattr(bot_inst, "delete_message"):
                try:
                    await bot_inst.delete_message(chat_id=int(storage_id), message_id=int(fwd.message_id))
                except Exception:
                    pass
            if info:
                # Sync any discovered Storage Group media message into files.db on the fly
                if info.get("file_unique_id"):
                    sync_unique_file_storage_db(
                        row_id=None,
                        file_unique_id=info["file_unique_id"],
                        file_id=info.get("file_id"),
                        storage_message_id=int(mid),
                    )
                if (target_unique_id and info.get("file_unique_id") == target_unique_id) or (
                    target_file_id and info.get("file_id") == target_file_id
                ):
                    return int(mid), info.get("file_id")
        except Exception:
            if fwd and hasattr(bot_inst, "delete_message"):
                try:
                    await bot_inst.delete_message(chat_id=int(storage_id), message_id=int(fwd.message_id))
                except Exception:
                    pass
            continue
    return None, None


async def _resolve_or_heal_storage_message_id(main_bot, row, storage_id: int, stale_msg_id: int | None = None) -> int | None:
    """
    Whenever a file's `storage_message_id` is not found in the Storage Group:
      1. Checks all records in `files.db` matching `file_unique_id`, `file_id`, or `file_name`
         (`find_file_candidates_by_ids_db`) to collect all candidate `storage_message_id`s and `file_id`s.
      2. Checks/probes the Storage Group for a valid message matching `file_unique_id` / `file_id`.
      3. Uses all known `file_id`s across the Main Bot and all Helper Bots to restore the file in
         the Storage Group if needed, verifying `file_unique_id`.
      4. Calls `sync_unique_file_storage_db()` so the file has strictly ONE unique `file_unique_id`,
         ONE `file_id`, and ONE `storage_message_id` in `files.db`.
    """
    if not storage_id:
        return None

    row_id = _row_val(row, "id")
    fuid = (_row_val(row, "file_unique_id") or "").strip() or None
    primary_fid = (_row_val(row, "file_id") or "").strip() or None
    fname = (_row_val(row, "file_name") or "").strip() or None

    # 1. Gather all candidate file_ids and storage_message_ids from files.db
    db_candidates = find_file_candidates_by_ids_db(fuid, primary_fid, fname)
    candidate_fids: list[str] = []
    if primary_fid:
        candidate_fids.append(primary_fid)
    candidate_mids: list[int] = []

    for c_row in db_candidates:
        cfid = (_row_val(c_row, "file_id") or "").strip()
        if cfid and cfid not in candidate_fids:
            candidate_fids.append(cfid)
        cmid = int(_row_val(c_row, "storage_message_id") or 0)
        if cmid > 0 and cmid != (stale_msg_id or 0) and cmid not in candidate_mids:
            candidate_mids.append(cmid)
        if not fuid and _row_val(c_row, "file_unique_id"):
            fuid = str(_row_val(c_row, "file_unique_id")).strip()

    # 2. Check candidate message IDs (and recent Storage Group messages) in the Storage Group
    probe_mids = list(candidate_mids)
    _, max_mid = get_storage_message_id_bounds_db()
    if max_mid > 0:
        for m in range(max_mid + 5, max(0, max_mid - 15), -1):
            if m != (stale_msg_id or 0) and m not in probe_mids:
                probe_mids.append(m)

    if probe_mids and (fuid or primary_fid):
        found_mid, found_fid = await _probe_storage_group_for_file(
            main_bot, int(storage_id), fuid, primary_fid, probe_mids[:20]
        )
        if found_mid:
            sync_unique_file_storage_db(row_id, fuid, found_fid or primary_fid, found_mid)
            return found_mid

    # 3. Restore/sync the file in the Storage Group using all candidate file_ids across Main Bot + Helper Bots
    if not candidate_fids:
        return None

    from modules.indexing.book_index import extract_media_info, storage_caption_markup
    cap = _build_backfill_caption(row)
    cat = _row_val(row, "category") or "ebook"
    is_audio = cat == "audiobook"

    async def _try_upload_with(bot_inst, fid_to_try: str) -> int | None:
        markup = storage_caption_markup()
        sent = None
        if is_audio and hasattr(bot_inst, "send_audio"):
            try:
                sent = await bot_inst.send_audio(
                    chat_id=int(storage_id),
                    audio=fid_to_try,
                    caption=cap,
                    parse_mode="HTML",
                    reply_markup=markup,
                )
            except Exception:
                sent = None
        if sent is None and hasattr(bot_inst, "send_document"):
            sent = await bot_inst.send_document(
                chat_id=int(storage_id),
                document=fid_to_try,
                caption=cap,
                parse_mode="HTML",
                reply_markup=markup,
            )
        mid = getattr(sent, "message_id", None)
        if mid:
            if hasattr(bot_inst, "edit_message_reply_markup"):
                try:
                    await bot_inst.edit_message_reply_markup(
                        chat_id=int(storage_id),
                        message_id=int(mid),
                        reply_markup=storage_caption_markup(int(mid)),
                    )
                except Exception:
                    pass
            s_info = extract_media_info(sent) if sent else None
            actual_fuid = (s_info or {}).get("file_unique_id") or fuid
            actual_fid = (s_info or {}).get("file_id") or fid_to_try
            sync_unique_file_storage_db(row_id, actual_fuid, actual_fid, int(mid))
            update_storage_message_id_db(row_id, int(mid))
            return int(mid)
        return None

    for fid_cand in candidate_fids:
        if main_bot is not None:
            try:
                new_mid = await _try_upload_with(main_bot, fid_cand)
                if new_mid:
                    return new_mid
            except Exception:
                pass
        for tok in helper_bot_tokens():
            try:
                async with Bot(tok) as hb:
                    new_mid = await _try_upload_with(hb, fid_cand)
                    if new_mid:
                        return new_mid
            except Exception:
                continue

    logger.warning("Could not resolve or heal storage_message_id for row %s (fuid=%s).", row_id, fuid)
    return None


async def _ensure_storage_message_id(main_bot, row) -> int | None:
    """Ensures the file has a valid message inside PUBLIC_/TESTING_STORAGE_GROUP_ID so helper bots can copy_message it."""
    storage_id = storage_group_id()
    storage_msg_id = _row_val(row, "storage_message_id")
    if storage_msg_id and storage_id:
        return int(storage_msg_id)
    if not storage_id:
        return None
    return await _resolve_or_heal_storage_message_id(main_bot, row, int(storage_id))


async def _copy_with_bot(token: str | None, target_chat_id: int, from_chat_id: int, message_id: int):
    """Copies a message from PUBLIC_/TESTING_STORAGE_GROUP_ID to target_chat_id using helper bot ONLY (main bot never copies files)."""
    if not token:
        raise ValueError("No helper bot token configured.")
    async with Bot(token) as hb:
        return await hb.copy_message(
            chat_id=int(target_chat_id),
            from_chat_id=int(from_chat_id),
            message_id=int(message_id),
        )


# Helper-bot permission audits (storage group / posting channel) cost several API calls per file. A passing
# audit is remembered for a few minutes so "Send All" (10 files) does not repeat it ten times.
_AUDIT_OK_UNTIL: dict[tuple, float] = {}
_AUDIT_TTL_SECONDS = 600
_BG_TASKS: set = set()


def _spawn(coro):
    task = asyncio.create_task(coro)
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)


def _is_main_bot(bot) -> bool:
    """True when `bot` is the MAIN bot (compared with the id inside the configured main token).
    Helper bots never send delivery cards: the card belongs to the main bot's PM."""
    try:
        main_token = bot_token()
        return bool(main_token) and int(str(main_token).split(":")[0]) == int(bot.id)
    except Exception:
        return False


async def _audit_helper_access(context, helper_token, helper_id, helper_username, storage_id, post_chan_id):
    """Reports (to the Error Logs topic) a helper bot that is missing from the Storage Group / Posting Channel.
    A clean audit is cached for `_AUDIT_TTL_SECONDS`."""
    key = (helper_id, storage_id, post_chan_id)
    if _AUDIT_OK_UNTIL.get(key, 0) > time.time():
        return
    problem = False

    if helper_token and storage_id:
        try:
            async with Bot(helper_token) as hb:
                sm = await hb.get_chat_member(int(storage_id), helper_id)
                if sm.status not in ("administrator", "creator", "member"):
                    problem = True
                    err_details = (
                        f"🚨 <b>Helper Bot Missing in Storage Group</b>\n\n"
                        f"• Helper Bot: @{helper_username} (<code>{helper_id}</code>)\n"
                        f"• Storage Group: <code>{storage_id}</code>\n"
                        f"• Status: <code>{sm.status}</code>\n\n"
                        f"<i>Add @{helper_username} to the Storage Group so it can access messages!</i>"
                    )
                    await report_error(context.application, err_details, title="Helper Bot Missing in Storage Group")
        except Exception as exc:
            problem = True
            err_details = (
                f"🚨 <b>Helper Bot Storage Group Access Error</b>\n\n"
                f"• Helper Bot: @{helper_username} (<code>{helper_id}</code>)\n"
                f"• Storage Group: <code>{storage_id}</code>\n"
                f"• Error: <code>{html.escape(str(exc))}</code>\n\n"
                f"<i>Helper bot could not access the Storage Group. Verify it is added as Administrator.</i>"
            )
            await report_error(context.application, err_details, title="Helper Bot Storage Group Access Error")

    if helper_token and post_chan_id:
        try:
            async with Bot(helper_token) as hb:
                pm = await hb.get_chat_member(int(post_chan_id), helper_id)
                can_post = getattr(pm, "can_post_messages", True)
                can_delete = getattr(pm, "can_delete_messages", True)
                if pm.status not in ("administrator", "creator") or not (can_post and can_delete):
                    problem = True
                    err_details = (
                        f"🚨 <b>Helper Bot Posting Channel Permission Error</b>\n\n"
                        f"• Helper Bot: @{helper_username} (<code>{helper_id}</code>)\n"
                        f"• Posting Channel: <code>{post_chan_id}</code>\n"
                        f"• Status: <code>{pm.status}</code> (Post: {can_post}, Delete: {can_delete})\n\n"
                        f"<i>Helper bot must be an Administrator with Post &amp; Delete rights in the Posting Channel!</i>"
                    )
                    await report_error(context.application, err_details, title="Helper Bot Posting Channel Permission Error")
        except Exception as exc:
            problem = True
            err_details = (
                f"🚨 <b>Helper Bot Posting Channel Access Error</b>\n\n"
                f"• Helper Bot: @{helper_username} (<code>{helper_id}</code>)\n"
                f"• Posting Channel: <code>{post_chan_id}</code>\n"
                f"• Error: <code>{html.escape(str(exc))}</code>\n\n"
                f"<i>Ensure @{helper_username} is added as Administrator to Posting Channel {post_chan_id}.</i>"
            )
            await report_error(context.application, err_details, title="Helper Bot Posting Channel Access Error")

    if not problem:
        _AUDIT_OK_UNTIL[key] = time.time() + _AUDIT_TTL_SECONDS


async def _deliver_core(update: Update, context: ContextTypes.DEFAULT_TYPE, row_id: int, helper: dict | None = None) -> dict:
    """Copies ONE file to the Posting Channel and to the user's PM through ONE helper bot.
    Sends NOTHING to the user: returns a result dict that the caller turns into a card.

    Result keys: ok, error, row, helper_username, helper_start_url, pm_delivered, posting_link,
    delete_secs, delete_mins."""
    user = update.effective_user
    res = {
        "ok": False, "error": None, "row": None, "helper_username": "", "helper_start_url": None,
        "pm_delivered": False, "posting_link": None, "delete_secs": auto_delete_seconds(),
    }
    res["delete_mins"] = max(1, round(res["delete_secs"] / 60))

    record_user_last_file_db(user.id, row_id)
    row = get_file_by_id_db(int(row_id))
    if not row:
        res["error"] = "❌ File record no longer found in database."
        return res
    res["row"] = row

    storage_id = storage_group_id()
    post_chan_id = posting_channel_id()
    delete_secs = res["delete_secs"]

    storage_msg_id = await _ensure_storage_message_id(context.bot, row)
    if not storage_msg_id or not storage_id:
        res["error"] = "❌ Storage group or file message is not available."
        return res

    if helper is None:
        helper = await select_helper_bot(context.bot, context.application)
    helper_token = helper.get("token")
    helper_username = (helper.get("username") or "").lstrip("@")
    helper_id = helper.get("id")
    res["helper_username"] = helper_username
    res["helper_start_url"] = f"https://t.me/{helper_username}?start=dl_{row_id}" if helper_username else None

    await _audit_helper_access(context, helper_token, helper_id, helper_username, storage_id, post_chan_id)

    storage_msg_missing = False

    # 1. Posting Channel copy (auto-deleted) through the selected helper bot
    if post_chan_id:
        try:
            posted_msg = await _copy_with_bot(helper_token, int(post_chan_id), int(storage_id), int(storage_msg_id))
            chan_uname = await _get_posting_channel_username(context.bot, int(post_chan_id))
            res["posting_link"] = build_channel_message_link(int(post_chan_id), posted_msg.message_id, chan_uname)
            _spawn(_auto_delete_message(helper_token, context.bot, int(post_chan_id), posted_msg.message_id, delete_secs))
        except Exception as exc:
            if _is_missing_storage_msg_error(exc):
                healed_mid = await _resolve_or_heal_storage_message_id(
                    context.bot, row, int(storage_id), stale_msg_id=int(storage_msg_id)
                )
                if healed_mid:
                    storage_msg_id = healed_mid
                    try:
                        posted_msg = await _copy_with_bot(helper_token, int(post_chan_id), int(storage_id), int(storage_msg_id))
                        chan_uname = await _get_posting_channel_username(context.bot, int(post_chan_id))
                        res["posting_link"] = build_channel_message_link(int(post_chan_id), posted_msg.message_id, chan_uname)
                        _spawn(_auto_delete_message(helper_token, context.bot, int(post_chan_id), posted_msg.message_id, delete_secs))
                    except Exception as retry_exc:
                        exc = retry_exc
                else:
                    storage_msg_missing = True

            if not res["posting_link"]:
                if storage_msg_missing:
                    fname_esc = html.escape(str(_row_val(row, "file_name") or "Unknown"))
                    fuid_esc = html.escape(str(_row_val(row, "file_unique_id") or "—"))
                    err_details = (
                        f"🚨 <b>Storage Group Message Not Found</b>\n\n"
                        f"<table striped>"
                        f"<tr><th>Field</th><th>Details</th></tr>"
                        f"<tr><td>📁 <b>File Name</b></td><td><code>{fname_esc}</code></td></tr>"
                        f"<tr><td>🔑 <b>File Unique ID</b></td><td><code>{fuid_esc}</code></td></tr>"
                        f"<tr><td>📦 <b>Storage Group</b></td><td><code>{storage_id}</code></td></tr>"
                        f"<tr><td>🔢 <b>Missing Msg ID</b></td><td><code>{storage_msg_id}</code></td></tr>"
                        f"<tr><td>🤖 <b>Helper Bot</b></td><td>@{html.escape(helper_username or 'unknown')}</td></tr>"
                        f"</table>\n\n"
                        f"<i>Message #{storage_msg_id} was deleted from the Storage Group and its old file_id could not be resolved. Re-index the source channel to restore it.</i>"
                    )
                    try:
                        await report_error(context.application, err_details, title="Storage Group Message Not Found")
                    except Exception:
                        pass
                else:
                    logger.error("Helper bot posting channel delivery failed: %s", exc)
                    err_details = (
                        f"🚨 <b>Posting Channel Delivery Error</b>\n\n"
                        f"<table striped>"
                        f"<tr><th>Field</th><th>Details</th></tr>"
                        f"<tr><td>📢 <b>Target Channel</b></td><td><code>{post_chan_id}</code></td></tr>"
                        f"<tr><td>📦 <b>Storage Group</b></td><td><code>{storage_id}</code> (Msg: <code>{storage_msg_id}</code>)</td></tr>"
                        f"<tr><td>🤖 <b>Helper Bot</b></td><td>@{html.escape(helper_username or 'unknown')}</td></tr>"
                        f"<tr><td>⚠️ <b>Error</b></td><td><code>{html.escape(str(exc))}</code></td></tr>"
                        f"</table>\n\n"
                        f"<i>Ensure @{html.escape(helper_username or 'helper_bot')} is added as an Administrator in both the Storage Group and Posting Channel with Post &amp; Delete rights!</i>"
                    )
                    try:
                        await report_error(context.application, err_details, title="Posting Channel Delivery Error")
                    except Exception as report_err:
                        logger.error("Failed to report delivery error to logger group: %s", report_err)

    # 2. PM copy (auto-deleted) through the SAME helper bot (skip if Storage Group message is confirmed missing)
    if helper_token and not storage_msg_missing:
        try:
            pm_copy = await _copy_with_bot(helper_token, int(user.id), int(storage_id), int(storage_msg_id))
            res["pm_delivered"] = True
            if pm_copy and delete_secs > 0:
                _spawn(_auto_delete_message(helper_token, context.bot, int(user.id), pm_copy.message_id, delete_secs))
        except Exception as exc:
            if _is_missing_storage_msg_error(exc):
                healed_mid = await _resolve_or_heal_storage_message_id(
                    context.bot, row, int(storage_id), stale_msg_id=int(storage_msg_id)
                )
                if healed_mid:
                    storage_msg_id = healed_mid
                    try:
                        pm_copy = await _copy_with_bot(helper_token, int(user.id), int(storage_id), int(storage_msg_id))
                        res["pm_delivered"] = True
                        if pm_copy and delete_secs > 0:
                            _spawn(_auto_delete_message(helper_token, context.bot, int(user.id), pm_copy.message_id, delete_secs))
                    except Exception as retry_exc:
                        exc = retry_exc
                else:
                    storage_msg_missing = True

            if not res["pm_delivered"] and not storage_msg_missing:
                exc_str = str(exc)
                logger.info("Helper bot PM delivery pending user /start for %s: %s", user.id, exc_str)
                if "bot can't initiate conversation with a user" not in exc_str.lower() and "bot was blocked by the user" not in exc_str.lower():
                    err_details = (
                        f"🚨 <b>Helper Bot Direct PM Delivery Error</b>\n\n"
                        f"<table striped>"
                        f"<tr><th>Field</th><th>Details</th></tr>"
                        f"<tr><td>🤖 <b>Helper Bot</b></td><td>@{html.escape(helper_username or 'unknown')}</td></tr>"
                        f"<tr><td>👤 <b>User ID</b></td><td><code>{user.id}</code></td></tr>"
                        f"<tr><td>📦 <b>Storage Group</b></td><td><code>{storage_id}</code> (Msg: <code>{storage_msg_id}</code>)</td></tr>"
                        f"<tr><td>⚠️ <b>Error</b></td><td><code>{html.escape(exc_str)}</code></td></tr>"
                        f"</table>"
                    )
                    try:
                        await report_error(context.application, err_details, title="Helper Bot Direct PM Delivery Error")
                    except Exception:
                        pass

    if storage_msg_missing and not res["ok"]:
        res["helper_username"] = ""
        res["helper_start_url"] = None
        res["error"] = (
            f"⚠️ <b>File Storage Record Needs Re-Indexing</b>\n\n"
            f"Storage message <code>#{storage_msg_id}</code> for <code>{html.escape(str(_row_val(row, 'file_name') or 'this book'))}</code> "
            f"was not found in the Storage Group. Our admins have been notified!"
        )
        return res

    res["ok"] = bool(res["pm_delivered"] or res["posting_link"])
    if not res["ok"]:
        res["error"] = (
            "❌ Could not deliver the file. Please ensure PUBLIC_/TESTING_HELPER_BOT_TOKENS and PUBLIC_/TESTING_POSTING_CHANNEL_ID "
            "are configured and the helper bot is an admin in the Storage Group and Posting Channel."
        )
    return res


def _single_card(res: dict) -> tuple[str, InlineKeyboardMarkup | None]:
    """Delivery card text + buttons for one file (same wording as before)."""
    row = res["row"]
    helper_username = res["helper_username"]
    posting_link = res["posting_link"]
    pm_delivered = res["pm_delivered"]
    delete_mins = res["delete_mins"]
    file_info = build_file_info_html(row)
    hu = html.escape(helper_username)

    if helper_username and posting_link:
        if pm_delivered:
            text = (
                f"{file_info}\n"
                f"✅ <b>Delivered directly to your PM via @{hu}!</b>\n"
                f"📢 A backup copy is also ready in the Posting Channel.\n\n"
                f"⚠️ <b>Forward the file to your Saved Messages — both copies auto-delete in <mark>{delete_mins} mins</mark>!</b>"
            )
        else:
            text = (
                f"{file_info}\n"
                f"🤖 Tap the green button below to start <b>@{hu}</b> and receive the file in PM, "
                f"or open it directly in the Posting Channel.\n\n"
                f"⚠️ <b>Forward the file to your Saved Messages — copies auto-delete in <mark>{delete_mins} mins</mark>!</b>"
            )
    elif helper_username:
        if pm_delivered:
            text = (
                f"{file_info}\n"
                f"✅ <b>Delivered directly to your PM via @{hu}!</b>\n\n"
                f"⚠️ <b>Forward the file to your Saved Messages — PM copy auto-deletes in <mark>{delete_mins} mins</mark>!</b>"
            )
        else:
            text = (
                f"{file_info}\n"
                f"🤖 Tap the green button below to start <b>@{hu}</b> and receive your file in PM.\n\n"
                f"⚠️ <b>Forward the file to your Saved Messages — PM copy auto-deletes in <mark>{delete_mins} mins</mark>!</b>"
            )
    elif posting_link:
        text = (
            f"{file_info}\n"
            f"📢 Tap the button below to get your file from the Posting Channel.\n\n"
            f"⚠️ <b>Forward the file to your Saved Messages — it auto-deletes in <mark>{delete_mins} mins</mark>!</b>"
        )
    else:
        text = res.get("error") or "❌ Could not deliver the file."

    buttons = []
    if helper_username and res["helper_start_url"]:
        label = f"🤖 Open in @{helper_username} PM ↗️" if pm_delivered else f"🤖 Start @{helper_username} (Receive in PM) ↗️"
        buttons.append([styled_button(label, url=res["helper_start_url"], style="success")])
    if posting_link:
        buttons.append([styled_button("📢 View in Posting Channel ↗️", url=posting_link, style="primary")])
    return text, (InlineKeyboardMarkup(buttons) if buttons else None)


async def _send_card_to_pm(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, markup, delete_secs: int):
    """Sends a delivery card to the user's PM with the MAIN bot (never into the Search topic / group).
    If the user has not started the main bot yet, ONE short card is posted in the current chat instead
    (with an "open PM" button) and removed after `delete_secs`, so the group never fills with cards.
    Cards delete themselves after `delete_secs`, like the file copies."""
    user = update.effective_user
    sent = None
    try:
        sent = await context.bot.send_message(
            chat_id=int(user.id), text=text, parse_mode="HTML",
            disable_web_page_preview=True, reply_markup=markup,
        )
    except Exception as exc:
        logger.info("Delivery card to PM of %s failed (%s); falling back to current chat.", user.id, exc)
        msg = update.effective_message
        chat = update.effective_chat
        if msg is not None and chat is not None and chat.type != "private":
            bot_uname = getattr(context.bot, "username", None) or ""
            rows = list(markup.inline_keyboard) if markup else []
            if bot_uname:
                rows.append([styled_button("💬 Open bot PM (start it once)", url=f"https://t.me/{bot_uname}?start", style="primary")])
            try:
                sent = await msg.reply_text(
                    text + "\n\n💡 <i>Start the bot in PM once so delivery cards arrive privately.</i>",
                    parse_mode="HTML", disable_web_page_preview=True,
                    reply_markup=InlineKeyboardMarkup(rows) if rows else None,
                )
            except Exception as exc2:
                logger.warning("Delivery card fallback failed: %s", exc2)
    if sent is not None and delete_secs > 0:
        _spawn(_auto_delete_message(None, context.bot, sent.chat_id, sent.message_id, delete_secs))
    return sent


async def deliver_file_dual(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    row_id: int,
    *,
    send_card: bool = True,
    helper: dict | None = None,
) -> dict | None:
    """
    Dual file delivery when a user taps a search result / deep link:
      1. ONE helper bot copies the file to the Posting Channel (auto-delete) and to the user's PM (auto-delete).
      2. The MAIN bot sends ONE delivery card to the user's PM (never to the Search topic), which also
         deletes itself. Helper bots never send a card.
    `send_card=False` (used by Send All) skips the card and returns the result dict so the caller can build
    a single combined card. `helper` lets a batch reuse one helper bot for every file.
    """
    user = update.effective_user
    if not user:
        return None
    res = await _deliver_core(update, context, row_id, helper=helper)
    if not send_card or not _is_main_bot(context.bot):
        return res
    if res["row"] is None or (not res["ok"] and not res["helper_username"]):
        text, markup = (res.get("error") or "❌ Could not deliver the file."), None
    else:
        text, markup = _single_card(res)
    await _send_card_to_pm(update, context, text, markup, res["delete_secs"])
    return res


async def deliver_batch_combined(update: Update, context: ContextTypes.DEFAULT_TYPE, rows) -> dict:
    """Send All: delivers every row through ONE helper bot, then sends ONE combined `<table striped>` card
    (# | Title | Author | Size | Ext | Status | Channel link) to the user's PM instead of one card per file."""
    from modules.search.handlers import _extract_item_fields, _format_size

    helper = await select_helper_bot(context.bot, context.application)
    results = []
    for row in rows:
        try:
            res = await deliver_file_dual(update, context, int(row["id"]), send_card=False, helper=helper)
        except Exception as exc:
            logger.error("Send All item %s failed: %s", row["id"], exc)
            res = {"ok": False, "row": row, "pm_delivered": False, "posting_link": None, "error": str(exc),
                   "helper_username": helper.get("username") or ""}
        results.append(res or {"ok": False, "row": row, "pm_delivered": False, "posting_link": None})
        await asyncio.sleep(0.4)

    delete_secs = auto_delete_seconds()
    delete_mins = max(1, round(delete_secs / 60))
    helper_username = (helper.get("username") or "").lstrip("@")
    esc = lambda v: html.escape(str(v or ""), quote=False)

    body = []
    pending_ids = []
    ok_pm = 0
    for n, res in enumerate(results, 1):
        row = res.get("row")
        if row is not None:
            title, _series, author, _size, ext = _extract_item_fields(row)
            size = _format_size(row["file_size"])
        else:
            title = author = size = ext = "—"
        if res.get("pm_delivered"):
            status = "✅ PM"
            ok_pm += 1
        elif row is not None and res.get("helper_username"):
            status = "⏳ Start bot"
            pending_ids.append(row["id"])
        else:
            status = "❌ Failed"
        link = res.get("posting_link")
        link_cell = f'<a href="{html.escape(link, quote=True)}">View</a>' if link else "—"
        body.append(
            f"<tr><td>{n}</td><td>{esc(title)}</td><td>{esc(author)}</td><td>{esc(size)}</td>"
            f"<td>{esc(f'.{ext}' if ext and ext != '—' else '—')}</td><td>{status}</td><td>{link_cell}</td></tr>"
        )
    table = (
        "<table striped><tr><th>#</th><th>Title</th><th>Author</th><th>Size</th><th>Ext</th><th>Status</th><th>Channel</th></tr>"
        + "".join(body) + "</table>"
    )
    failed = sum(1 for r in results if not r.get("ok"))
    lines = [f"📨 <b>Send All — {len(results)} file(s)</b>", "", table, ""]
    if helper_username:
        lines.append(f"✅ <b>{ok_pm}</b> delivered to your PM via @{html.escape(helper_username)}")
    if pending_ids:
        lines.append(f"⏳ <b>{len(pending_ids)}</b> waiting: tap the green button to start @{html.escape(helper_username)}, then press Send All again.")
    if failed:
        lines.append(f"❌ <b>{failed}</b> could not be delivered (admins were notified).")
    lines += ["", f"⚠️ <b>Forward the files to your Saved Messages — all copies auto-delete in <mark>{delete_mins} mins</mark>!</b>"]

    buttons = []
    if helper_username:
        start_id = pending_ids[-1] if pending_ids else (results[-1]["row"]["id"] if results and results[-1].get("row") is not None else "")
        url = f"https://t.me/{helper_username}" + (f"?start=dl_{start_id}" if start_id != "" else "")
        label = f"🤖 Start @{helper_username} (Receive in PM) ↗️" if pending_ids else f"🤖 Open @{helper_username} PM ↗️"
        buttons.append([styled_button(label, url=url, style="success")])
    markup = InlineKeyboardMarkup(buttons) if buttons else None
    await _send_card_to_pm(update, context, "\n".join(lines), markup, delete_secs)
    return {"results": results, "delivered_pm": ok_pm, "failed": failed}


async def handle_deeplink_file_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: str):
    """
    Handles `/start dl_<row_id|file_unique_id>` triggered by download buttons or deep-links.
    Uses the exact same deliver_file_dual pipeline as inline keyboard buttons.
    """
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return

    from modules.database.file_db import get_file_by_unique_id_db
    val = payload.replace("dl_", "", 1).strip()
    row = None
    if val.isdigit():
        row = get_file_by_id_db(int(val))
    if not row:
        row = get_file_by_unique_id_db(val)

    if not row:
        await msg.reply_text("❌ File record no longer found in database.")
        return

    # Trigger dual delivery using the configured helper bot pool
    try:
        await deliver_file_dual(update, context, int(row["id"]))
    except Exception as exc:
        logger.error("Deep-link deliver_file_dual failed: %s", exc)
        err_details = (
            f"🚨 <b>Deep-Link File Delivery Error</b>\n\n"
            f"• User: {user.first_name} (<code>{user.id}</code>, @{user.username or 'none'})\n"
            f"• File Row: <code>{row['id'] if row else 'unknown'}</code>\n"
            f"• Payload: <code>{html.escape(payload)}</code>\n"
            f"• Error: <code>{html.escape(str(exc))}</code>"
        )
        try:
            await report_error(context.application, err_details, title="File Delivery Error")
        except Exception as rep_err:
            logger.error("Failed to report delivery error: %s", rep_err)

        support_link = creator_dm_link()
        markup = InlineKeyboardMarkup([[styled_button("💬 Contact Support", url=support_link, style="primary")]]) if support_link else None
        user_msg = (
            "⚠️ <b>We encountered an error while sending your file.</b>\n\n"
            "Our administrators have been notified and it will be resolved shortly.\n"
            "Please wait a moment and try again, or tap below to contact support!"
        )
        await msg.reply_text(user_msg, reply_markup=markup, parse_mode="HTML")
