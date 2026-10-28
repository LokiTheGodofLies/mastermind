from modules.indexing.book_fetcher import fetch_comprehensive_book_metadata, clean_book_filename
import os
import re
import html
import time
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import RetryAfter
from telegram.ext import ContextTypes
from modules.database.file_db import get_file_by_unique_id_db, save_indexed_file_db, get_connection as get_file_conn
from modules.database.config_db import get_config, get_config_int
from modules.database.user_db import get_user_role_db
from modules.log.startup_log import send_log_with_fallback
from modules.utility.tg_compat import get_forward_chat
from modules.converter.handlers import handle_convert_upload

logger = logging.getLogger(__name__)
EBOOK_EXTENSIONS = {".epub", ".pdf", ".mobi", ".azw3", ".djvu", ".cbz"}
AUDIO_EXTENSIONS = {".mp3", ".m4b", ".aax"}
SUPPORTED_EXTENSIONS = EBOOK_EXTENSIONS | AUDIO_EXTENSIONS


QUEUE_STATE = {
    "running": False, "paused": False, "cancelled": False, "status": "idle",
    "fetched": 0, "remaining": 0, "forwarded": 0, "duplicates": 0,
    "deleted": 0, "skipped": 0, "filtered": 0, "start_time": 0.0,
    "card_chat_id": None, "card_msg_id": None,
}


def clean_filename_for_search(file_name: str) -> str:
    if not file_name:
        return ""
    name = re.sub(r"\.[a-zA-Z0-9]{2,5}$", "", file_name)
    # Strip round, square, and curly brackets
    name = re.sub(r"\[.*?\]|\(.*?\)|(\{.*?\})", " ", name)
    noise = r"\b(z-lib\.org|z-library|annas-archive|libgen|epub|pdf|azw3|kfx|mp3|m4b|aax|audiobook|unabridged|64kbps|128kbps)\b"
    name = re.sub(noise, " ", name, flags=re.IGNORECASE)
    name = re.sub(r"[_\.\-]+", " ", name)
    # Clean isolated single characters like ' s '
    name = re.sub(r"\s+[a-zA-Z]\s+", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def format_index_caption(file_name: str, size_str: str, ext: str, mime: str, meta: dict) -> str:
    esc_fn = html.escape(file_name)
    esc_t = html.escape(meta.get("title") or file_name)
    esc_a = html.escape(meta.get("author") or "Unknown Author")
    burl = meta.get("url") or ""
    t_disp = f'<a href="{html.escape(burl)}">{esc_t}</a>' if burl else esc_t

    if meta.get("is_audiobook"):
        esc_n = html.escape(meta.get("narrator") or "N/A")
        esc_len = html.escape(meta.get("length_str") or "N/A")
        esc_pub = html.escape(meta.get("publisher") or "N/A")
        esc_rel = html.escape(meta.get("release_date") or "N/A")
        lines = [
            f"🎧 <b>Audiobook:</b> {t_disp}",
            f"✍️ <b>By:</b> <code>{esc_a}</code>",
            f"🎙 <b>Narrated by:</b> <code>{esc_n}</code>",
            f"⏱ <b>Length:</b> <code>{esc_len}</code>",
            f"📅 <b>Release Date:</b> <code>{esc_rel}</code>",
            f"🏢 <b>Publisher:</b> <code>{esc_pub}</code>",
            "",
            f"📁 <b>File:</b> <code>{esc_fn}</code>",
            f"📦 <b>Size:</b> <code>{size_str}</code> | <b>Type:</b> <code>.{ext}</code>",
        ]
    else:
        esc_r = html.escape(meta.get("rating") or "N/A")
        esc_rc = html.escape(meta.get("ratings_count") or "0")
        esc_len = html.escape(meta.get("length_str") or "N/A")
        esc_rel = html.escape(meta.get("release_date") or "N/A")
        esc_s = html.escape(meta.get("series") or "")
        lines = [f"📚 <b>Book:</b> {t_disp}"]
        if esc_s:
            lines.append(f"📖 <b>Series:</b> <code>{esc_s}</code>")
        lines += [
            f"✍️ <b>Author:</b> <code>{esc_a}</code>",
            f"⭐ <b>Rating:</b> <code>{esc_r}</code> (<code>{esc_rc}</code> ratings)",
            f"📄 <b>Pages:</b> <code>{esc_len}</code> | 📅 <code>{esc_rel}</code>",
            "",
            f"📁 <b>File:</b> <code>{esc_fn}</code>",
            f"📦 <b>Size:</b> <code>{size_str}</code> | <b>Type:</b> <code>.{ext}</code>",
        ]
    return "\n".join(lines)[:1020]


def _calc_eta_and_pct() -> tuple:
    fetched = QUEUE_STATE["fetched"]
    rem = QUEUE_STATE["remaining"]
    total = max(1, fetched + rem)
    pct = int((fetched / total) * 100) if (fetched + rem) > 0 else 100
    elapsed = max(1.0, time.time() - (QUEUE_STATE["start_time"] or time.time()))
    rate = fetched / elapsed if fetched > 0 else 0.5
    eta_sec = int(rem / rate) if rate > 0 else 0
    days, rem_s = divmod(eta_sec, 86400)
    hrs, rem_s = divmod(rem_s, 3600)
    mins, _ = divmod(rem_s, 60)
    eta_str = f"{days}d, {hrs}h, {mins}m" if days > 0 else f"{hrs}h, {mins}m"
    return pct, eta_str


def render_progress_card_text() -> str:
    pct, _ = _calc_eta_and_pct()
    st = QUEUE_STATE
    return (
        "<pre>"
        "╭──────❪ FORWARD STATUS ❫──〇⚙️\n"
        "│╭─────────────────────────➤\n"
        f"│├─»◇ FECHED MESSAGES: {st['fetched']}\n"
        "││\n"
        f"│├─»◇ REMAINING MESSAGES: {st['remaining']}\n"
        "││\n"
        f"│├─»◇ SUCCEFULLY FORWARDED: {st['forwarded']}\n"
        "││\n"
        f"│├─»◇ DUPLICATE MESSAGES: {st['duplicates']}\n"
        "││\n"
        f"│├─»◇ DELETED MESSAGES: {st['deleted']}\n"
        "││\n"
        f"│├─»◇ SKIPPED MESSAGES: {st['skipped']}\n"
        "││\n"
        f"│├─»◇ FILTERED MESSAGES: {st['filtered']}\n"
        "││\n"
        f"│├─»◇ CURRENT STATUS: {st['status']}\n"
        "││\n"
        f"│├─»◇ PERCENTAGE: {pct} %\n"
        "│╰─────────────────────────➤\n"
        "╰─────────❪ PROGRESSING ❫──〇⚙️"
        "</pre>"
    )


def render_progress_card_keyboard() -> InlineKeyboardMarkup:
    pct, _ = _calc_eta_and_pct()
    filled = max(1, min(12, int((pct / 100) * 12)))
    bar = ("▬" * filled) + ("□" * (12 - filled))
    pause_btn = (
        InlineKeyboardButton("• RESUME", callback_data="idx_ctrl_resume")
        if QUEUE_STATE["paused"]
        else InlineKeyboardButton("• PAUSE", callback_data="idx_ctrl_pause")
    )
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(bar, callback_data="idx_ctrl_popup")],
        [pause_btn, InlineKeyboardButton("⏳ WAIT / HOLD", callback_data="idx_ctrl_wait")],
        [InlineKeyboardButton("• CANCEL", callback_data="idx_ctrl_cancel")],
    ])


async def _refresh_progress_card(bot):
    cid, mid = QUEUE_STATE["card_chat_id"], QUEUE_STATE["card_msg_id"]
    if not cid or not mid:
        return
    try:
        await bot.edit_message_text(
            chat_id=int(cid), message_id=int(mid),
            text=render_progress_card_text(), parse_mode="HTML",
            reply_markup=render_progress_card_keyboard(),
        )
    except Exception:
        pass


async def _index_single_file_obj(bot, file_id: str, file_unique_id: str, file_name: str, file_size: int, mime_type: str, user_id: int, user_title: str, orig_caption: str = "") -> str:
    storage_id = get_config("storage_channel_id", fallback_env="STORAGE_GROUP_ID")
    if not storage_id:
        return "filtered"

    _, ext = os.path.splitext((file_name or "").lower())
    if ext not in SUPPORTED_EXTENSIONS:
        return "filtered"

    if get_file_by_unique_id_db(file_unique_id):
        return "duplicate"

    is_audio = ext in AUDIO_EXTENSIONS
    if is_audio:
        meta = await fetch_comprehensive_book_metadata(file_name, ext=ext)
        cat = "audiobook"
    else:
        meta = await fetch_comprehensive_book_metadata(file_name, ext=ext)
        cat = "book"

    size_mb = (file_size or 0) / (1024 * 1024)
    size_str = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{(file_size or 0) / 1024:.1f} KB"

    caption_html = format_index_caption(file_name, size_str, ext.lstrip("."), mime_type, meta)
    community = get_config("community_url")
    comm_kb = InlineKeyboardMarkup([[InlineKeyboardButton("💬 Join our community", url=community)]]) if community else None
    target_msg = await bot.send_document(chat_id=int(storage_id), document=file_id, caption=caption_html, parse_mode="HTML", reply_markup=comm_kb)

    save_indexed_file_db(
        file_unique_id=file_unique_id,
        file_id=file_id,
        storage_message_id=target_msg.message_id,
        file_name=file_name,
        file_size=file_size or 0,
        duration=0,
        user_id=user_id,
        user_title=user_title,
        caption=orig_caption or caption_html,
        extension=ext,
        file_type=mime_type,
        category=cat,
        title=meta.get("title", file_name),
        author=meta.get("author", "Unknown Author"),
        narrator=meta.get("narrator", "N/A"),
        series=meta.get("series", ""),
        publisher=meta.get("publisher", ""),
        release_date=meta.get("release_date", ""),
        length_str=meta.get("length_str", ""),
        keywords=clean_filename_for_search(file_name),
    )

    log_label = "🎧 <b>Audiobook Indexed</b>" if is_audio else "📚 <b>Book Indexed</b>"
    log_txt = (
        f"{log_label}\n\n"
        f"📖 <b>Title:</b> {html.escape(meta.get('title', file_name))}\n"
        f"✍️ <b>Author:</b> {html.escape(meta.get('author', 'Unknown'))}\n"
        f"📂 <b>File:</b> <code>{html.escape(file_name)}</code>\n"
        f"🆔 <b>Unique ID:</b> <code>{file_unique_id}</code>\n"
        f"👤 <b>By:</b> {html.escape(user_title)} (<code>{user_id}</code>)"
    )
    await send_log_with_fallback(bot, log_txt, "general_log_group_id", "index_log_topic_id")
    return "forwarded"


async def process_global_indexing_queue(bot):
    if QUEUE_STATE["running"]:
        return
    QUEUE_STATE["running"] = True
    QUEUE_STATE["cancelled"] = False
    QUEUE_STATE["start_time"] = time.time()

    try:
        while not QUEUE_STATE["cancelled"]:
            while QUEUE_STATE["paused"] and not QUEUE_STATE["cancelled"]:
                QUEUE_STATE["status"] = "paused"
                await _refresh_progress_card(bot)
                await asyncio.sleep(2)

            if QUEUE_STATE["cancelled"]:
                break

            batch_limit = get_config_int("max_index_batch", 10)
            sleep_secs = get_config_int("index_sleep_seconds", 10)

            conn = get_file_conn()
            rows = conn.execute(
                "SELECT * FROM indexing_queue WHERE status = 'queued' ORDER BY priority DESC, id ASC LIMIT ?",
                (batch_limit,),
            ).fetchall()
            rem_row = conn.execute("SELECT COUNT(*) as c FROM indexing_queue WHERE status = 'queued'").fetchone()
            QUEUE_STATE["remaining"] = rem_row["c"] if rem_row else 0
            conn.close()

            if not rows:
                QUEUE_STATE["status"] = "completed"
                await _refresh_progress_card(bot)
                break

            QUEUE_STATE["status"] = "forwarding"
            for r in rows:
                if QUEUE_STATE["cancelled"] or QUEUE_STATE["paused"]:
                    break
                qid = r["id"]
                conn = get_file_conn()
                conn.execute("UPDATE indexing_queue SET status = 'processing' WHERE id = ?", (qid,))
                conn.commit()
                conn.close()

                QUEUE_STATE["fetched"] += 1
                QUEUE_STATE["remaining"] = max(0, QUEUE_STATE["remaining"] - 1)
                try:
                    res = await _index_single_file_obj(
                        bot, r["file_id"], r["file_unique_id"], r["file_name"],
                        r["file_size"], r["mime_type"], r["user_id"], r["user_title"], r["caption"]
                    )
                    if res == "forwarded":
                        QUEUE_STATE["forwarded"] += 1
                    elif res == "duplicate":
                        QUEUE_STATE["duplicates"] += 1
                    else:
                        QUEUE_STATE["filtered"] += 1
                    st_val = "completed"
                except Exception as idx_err:
                    logger.error(f"[INDEXING ERROR] File={r['file_name']}: {idx_err}", exc_info=True)
                    await send_log_with_fallback(bot, f"❌ <b>Indexing Error</b>\n📂 File: <code>{html.escape(str(r['file_name']))}</code>\n⚠️ Error: <code>{html.escape(str(idx_err))}</code>", "general_log_group_id", "error_log_topic_id")
                    QUEUE_STATE["filtered"] += 1
                    st_val = "failed"

                conn = get_file_conn()
                conn.execute("UPDATE indexing_queue SET status = ?, processed_at = CURRENT_TIMESTAMP WHERE id = ?", (st_val, qid))
                conn.commit()
                conn.close()

            await _refresh_progress_card(bot)

            conn = get_file_conn()
            still_left = conn.execute("SELECT COUNT(*) as c FROM indexing_queue WHERE status = 'queued'").fetchone()["c"]
            conn.close()
            if still_left > 0 and not QUEUE_STATE["cancelled"] and not QUEUE_STATE["paused"]:
                QUEUE_STATE["status"] = f"sleeping ({sleep_secs}s)"
                await _refresh_progress_card(bot)
                await asyncio.sleep(sleep_secs)
    finally:
        QUEUE_STATE["running"] = False


def enqueue_file_for_indexing(file_id, file_unique_id, file_name, file_size, mime_type, user_id, user_title, caption="", priority=10, source="upload"):
    conn = get_file_conn()
    conn.execute("""
        INSERT INTO indexing_queue (file_id, file_unique_id, file_name, file_size, mime_type, caption, user_id, user_title, source, priority, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued')
    """, (file_id, file_unique_id, file_name, file_size, mime_type, caption, user_id, user_title, source, priority))
    conn.commit()
    conn.close()


async def handle_book_indexing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.channel_post or update.effective_message
    if not msg:
        return
    # A file sent right after /convert belongs to the converter, not to the library.
    if await handle_convert_upload(update, context):
        return
    doc = msg.document or msg.audio
    if not doc:
        return

    file_id = doc.file_id
    file_unique_id = doc.file_unique_id
    file_name = getattr(doc, "file_name", None) or "audiobook.m4b"
    file_size = getattr(doc, "file_size", 0) or 0
    mime_type = getattr(doc, "mime_type", "document") or "document"
    _, ext = os.path.splitext(file_name.lower())

    if ext not in SUPPORTED_EXTENSIONS:
        if update.message and update.effective_chat.type == "private":
            await update.message.reply_text("❌ Unsupported file format.")
        return

    if get_file_by_unique_id_db(file_unique_id):
        if update.message and update.effective_chat.type == "private":
            await update.message.reply_text("📚 This file is already indexed in the database.")
        return

    user = msg.from_user
    uid = user.id if user else 0
    utitle = (user.full_name or user.username) if user else (msg.chat.title or "Channel")
    role = get_user_role_db(uid) if uid else "Admin"

    if role == "Banned":
        return

    if role in ("Volunteer", "Admin", "Owner"):
        enqueue_file_for_indexing(file_id, file_unique_id, file_name, file_size, mime_type, uid, utitle, msg.caption or "", priority=10, source="direct")
        if update.message and update.effective_chat.type == "private":
            await update.message.reply_text("📥 <b>File added to Priority Indexing Queue!</b>", parse_mode="HTML")
        asyncio.create_task(process_global_indexing_queue(context.bot))
    else:
        conn = get_file_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO indexing_queue (file_id, file_unique_id, file_name, file_size, mime_type, caption, user_id, user_title, source, priority, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending_approval', 10, 'pending_approval')
        """, (file_id, file_unique_id, file_name, file_size, mime_type, msg.caption or "", uid, utitle))
        qid = cur.lastrowid
        conn.commit()
        conn.close()

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve & Index", callback_data=f"idx_app_yes_{qid}"),
            InlineKeyboardButton("❌ Reject Upload", callback_data=f"idx_app_no_{qid}"),
        ]])
        app_txt = (
            f"📤 <b>New User Upload Pending Approval</b>\n\n"
            f"👤 <b>Uploader:</b> {html.escape(utitle)} (<code>{uid}</code> | <code>{role}</code>)\n"
            f"📁 <b>File:</b> <code>{html.escape(file_name)}</code>\n"
            f"📦 <b>Size:</b> <code>{file_size / (1024*1024):.2f} MB</code>"
        )
        await send_log_with_fallback(context.bot, app_txt, "admin_log_group_id", "index_log_topic_id", reply_markup=kb)
        if update.message:
            await update.message.reply_text("⏳ <b>Upload Received!</b> Sent to Admins for approval before indexing.", parse_mode="HTML")


def _parse_tme_link(link_str: str):
    m_priv = re.search(r"t\.me/c/(\d+)(?:/(\d+)(?:-(\d+))?)?", link_str)
    if m_priv:
        cid = int(f"-100{m_priv.group(1)}")
        m1 = int(m_priv.group(2)) if m_priv.group(2) else None
        m2 = int(m_priv.group(3)) if m_priv.group(3) else None
        return cid, m1, m2
    m_pub = re.search(r"t\.me/([A-Za-z0-9_]+)(?:/(\d+)(?:-(\d+))?)?", link_str)
    if m_pub:
        uname = f"@{m_pub.group(1)}"
        m1 = int(m_pub.group(2)) if m_pub.group(2) else None
        m2 = int(m_pub.group(3)) if m_pub.group(3) else None
        return uname, m1, m2
    return None, None, None


async def index_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    role = get_user_role_db(user.id)
    if role not in ("Volunteer", "Admin", "Owner"):
        await update.effective_message.reply_text("⛔ Access denied. Only Volunteers, Admins, and Owners can use /index.")
        return

    raw_args = " ".join(context.args).strip() if context.args else ""
    if not raw_args:
        context.user_data["index_wizard"] = {"step": "await_source"}
        await update.effective_message.reply_text(
            "<b>❪ Set Source Chat ❫</b>\n\nForward the last message or last message link of source chat.",
            parse_mode="HTML",
        )
        return

    links = re.findall(r"(?:https?://)?t\.me/[^\s]+", raw_args)
    chat_ref, start_id, end_id = (None, 1, 500)
    skip_range = None

    if len(links) >= 2:
        chat_ref, m1, _ = _parse_tme_link(links[0])
        _, m2, _ = _parse_tme_link(links[1])
        start_id, end_id = (m1 or 1), (m2 or (m1 or 100))
    elif len(links) == 1:
        chat_ref, m1, m2 = _parse_tme_link(links[0])
        if m1 and m2:
            start_id, end_id = m1, m2
        elif m1:
            start_id, end_id = 1, m1
    else:
        chat_ref = context.args[0]

    m_from = re.search(r"--from\s+(\d+)", raw_args)
    m_to = re.search(r"--to\s+(\d+)", raw_args)
    if m_from:
        start_id = int(m_from.group(1))
    if m_to:
        end_id = int(m_to.group(1))

    m_skip_rng = re.search(r"skip[=\s]+(\d+)-(\d+)", raw_args, re.IGNORECASE)
    m_skip_num = re.search(r"skip[=\s]+(\d+)", raw_args, re.IGNORECASE)
    if m_skip_rng:
        skip_range = (int(m_skip_rng.group(1)), int(m_skip_rng.group(2)))
    elif m_skip_num:
        start_id = int(m_skip_num.group(1)) + 1

    m_lim = re.search(r"limit[=\s]+(\d+)", raw_args, re.IGNORECASE)
    if m_lim:
        end_id = start_id + int(m_lim.group(1)) - 1

    context.user_data["index_wizard"] = {
        "step": "confirm", "source_chat": chat_ref,
        "start_id": start_id, "end_id": end_id,
        "skip_count": start_id - 1, "skip_range": skip_range,
    }
    await _send_double_check_card(update.effective_message, user.first_name, chat_ref, start_id - 1)


async def _send_double_check_card(msg, user_name, source_chat, skip_num):
    target_id = get_config("storage_channel_id") or "not set"
    txt = (
        "<b>ᴅᴏᴜʙʟᴇ ᴄʜᴇᴄᴋɪɴɢ 📋</b>\n\n"
        "ʙᴇꜰᴏʀᴇ ꜰᴏʀᴡᴀʀᴅɪɴɢ ᴛʜᴇ ᴍᴇssᴀɢᴇs ᴄʟɪᴄᴋ ᴛʜᴇ ʏᴇs ʙᴜᴛᴛᴏɴ ᴏɴʟʏ ᴀꜰᴛᴇʀ ᴄʜᴇᴄᴋɪɴɢ ᴛʜᴇ ꜰᴏʟʟᴏᴡɪɴɢ\n\n"
        f"★ <b>ʏᴏᴜʀ userbot/bot:</b> {html.escape(user_name)}\n"
        f"★ <b>sᴏᴜʀᴄᴇ ᴄʜᴀᴛ:</b> <code>{html.escape(str(source_chat))}</code>\n"
        f"★ <b>ᴛᴀʀɢᴇᴛ ᴄʜᴀᴛ:</b> <code>{html.escape(str(target_id))}</code>\n"
        f"★ <b>sᴋɪᴘ ᴍᴇssᴀɢᴇs:</b> <code>{skip_num}</code>\n\n"
        "° Bot ᴍᴜsᴛ ʙᴇ ᴀᴅᴍɪɴ ɪɴ ᴛᴀʀɢᴇᴛ ᴄʜᴀᴛ\n"
        "° ɪꜰ ᴛʜᴇ sᴏᴜʀᴄᴇ ᴄʜᴀᴛ ɪs ᴘʀɪᴠᴀᴛᴇ ʏᴏᴜʀ ʙᴏᴛ ᴍᴜsᴛ ʙᴇ ᴀᴅᴍɪɴ ɪɴ ᴛʜᴇʀᴇ ᴀʟsᴏ\n\n"
        "ɪꜰ ᴛʜᴇ ᴀʙᴏᴠᴇ ɪs ᴄʜᴇᴄᴋᴇᴅ ᴛʜᴇɴ ᴛʜᴇ ʏᴇs ʙᴜᴛᴛᴏɴ ᴄᴀɴ ʙᴇ ᴄʟɪᴄᴋᴇᴅ"
    )
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ YES", callback_data="idx_wiz_start_yes"),
        InlineKeyboardButton("❌ CANCEL", callback_data="idx_wiz_cancel"),
    ]])
    await msg.reply_text(txt, parse_mode="HTML", reply_markup=kb)


async def handle_index_wizard_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    wiz = context.user_data.get("index_wizard")
    if not wiz or not update.message:
        return False
    msg = update.message
    step = wiz.get("step")

    if step == "await_source":
        fwd_chat, fwd_mid = get_forward_chat(msg)
        if fwd_chat:
            wiz["source_chat"] = fwd_chat.id
            wiz["end_id"] = fwd_mid or 500
        elif msg.text and "t.me/" in msg.text:
            cid, m1, m2 = _parse_tme_link(msg.text.strip())
            if not cid:
                await msg.reply_text("⚠️ Invalid message link. Please forward the last message or paste a valid `https://t.me/...` link.")
                return True
            wiz["source_chat"] = cid
            wiz["end_id"] = m2 or m1 or 500
        else:
            return False

        wiz["step"] = "ask_skip"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Yes", callback_data="idx_wiz_skip_yes"),
            InlineKeyboardButton("❌ No", callback_data="idx_wiz_skip_no"),
        ]])
        await msg.reply_text("<b>Did You Want Skip Any Message's</b>", parse_mode="HTML", reply_markup=kb)
        return True

    if step == "await_skip_num" and msg.text and msg.text.strip().isdigit():
        skip_n = int(msg.text.strip())
        wiz["skip_count"] = skip_n
        wiz["start_id"] = skip_n + 1
        wiz["step"] = "confirm"
        await _send_double_check_card(msg, update.effective_user.first_name, wiz.get("source_chat"), skip_n)
        return True

    return False


async def indexing_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    d = q.data
    uid = q.from_user.id
    role = get_user_role_db(uid)

    if d == "idx_ctrl_popup":
        pct, eta_str = _calc_eta_and_pct()
        st = QUEUE_STATE
        alert_txt = (
            f"FORWARD BOT\n"
            f"📈 PERCENTAGE: {pct} %\n"
            f"♻️ FECHED: {st['fetched']}\n"
            f"♻️ FORWARDED: {st['forwarded']}\n"
            f"♻️ REMAINING: {st['remaining']}\n"
            f"♻️ STATUS: {st['status']}\n"
            f"⏳ ETA: {eta_str}"
        )
        await q.answer(alert_txt, show_alert=True)
        return

    if role not in ("Volunteer", "Admin", "Owner"):
        await q.answer("⛔ Access denied.", show_alert=True)
        return

    if d == "idx_ctrl_pause":
        QUEUE_STATE["paused"] = True
        QUEUE_STATE["status"] = "paused"
        await q.answer("⏸ Queue paused.")
        await _refresh_progress_card(context.bot)
    elif d == "idx_ctrl_resume":
        QUEUE_STATE["paused"] = False
        QUEUE_STATE["status"] = "forwarding"
        await q.answer("▶️ Queue resumed!")
        await _refresh_progress_card(context.bot)
        asyncio.create_task(process_global_indexing_queue(context.bot))
    elif d == "idx_ctrl_wait":
        await q.answer("⏳ Task held in queue.", show_alert=True)
    elif d == "idx_ctrl_cancel":
        QUEUE_STATE["cancelled"] = True
        QUEUE_STATE["paused"] = False
        QUEUE_STATE["status"] = "cancelled"
        conn = get_file_conn()
        conn.execute("UPDATE indexing_queue SET status = 'cancelled' WHERE status = 'queued'")
        conn.commit()
        conn.close()
        await q.answer("❌ Indexing cancelled.")
        await _refresh_progress_card(context.bot)
    elif d.startswith("idx_app_yes_") or d.startswith("idx_app_no_"):
        if role not in ("Admin", "Owner"):
            await q.answer("⛔ Only Admins and Owners can approve/reject uploads.", show_alert=True)
            return
        qid = int(d.split("_")[-1])
        conn = get_file_conn()
        row = conn.execute("SELECT * FROM indexing_queue WHERE id = ?", (qid,)).fetchone()
        if not row:
            conn.close()
            await q.answer("⚠️ Entry not found.", show_alert=True)
            return
        await q.answer()
        if d.startswith("idx_app_yes_"):
            conn.execute("UPDATE indexing_queue SET status = 'queued', priority = 10 WHERE id = ?", (qid,))
            conn.commit()
            conn.close()
            await q.message.edit_text(f"{html.escape(q.message.text or '')}\n\n✅ <b>Status: Approved & Queued for Indexing</b>", parse_mode="HTML")
            asyncio.create_task(process_global_indexing_queue(context.bot))
        else:
            conn.execute("UPDATE indexing_queue SET status = 'rejected' WHERE id = ?", (qid,))
            conn.commit()
            conn.close()
            await q.message.edit_text(f"{html.escape(q.message.text or '')}\n\n❌ <b>Status: Rejected</b>", parse_mode="HTML")
    elif d == "idx_wiz_skip_yes":
        await q.answer()
        wiz = context.user_data.get("index_wizard", {})
        wiz["step"] = "await_skip_num"
        await q.message.edit_text(
            "<b>❪ Set Skip Number ❫</b>\n\nYou can skip a certain number of messages and forward the rest.\n\n"
            "Default skip number is 0\nExample: If you enter 0, no messages will be skipped.\nIf you enter 5, the first 5 messages will be skipped",
            parse_mode="HTML",
        )
    elif d == "idx_wiz_skip_no":
        await q.answer()
        wiz = context.user_data.get("index_wizard", {})
        wiz["skip_count"] = 0
        wiz["start_id"] = 1
        wiz["step"] = "confirm"
        await q.message.delete()
        await _send_double_check_card(q.message, q.from_user.first_name, wiz.get("source_chat"), 0)
    elif d == "idx_wiz_cancel":
        await q.answer()
        context.user_data.pop("index_wizard", None)
        await q.message.edit_text("❌ Indexing setup cancelled.")
    elif d == "idx_wiz_start_yes":
        wiz = context.user_data.pop("index_wizard", None)
        if not wiz:
            await q.answer("⚠️ Session expired.", show_alert=True)
            return
        await q.answer("🚀 Indexing started!")
        QUEUE_STATE.update({
            "fetched": 0, "forwarded": 0, "duplicates": 0, "deleted": 0,
            "skipped": wiz.get("skip_count", 0), "filtered": 0,
            "remaining": max(0, int(wiz.get("end_id", 100)) - int(wiz.get("start_id", 1)) + 1),
            "status": "forwarding", "paused": False, "cancelled": False,
            "start_time": time.time(), "card_chat_id": q.message.chat_id, "card_msg_id": q.message.message_id,
        })
        await _refresh_progress_card(context.bot)
        asyncio.create_task(_run_channel_range_scan(context.bot, wiz, q.from_user))


async def _safe_delete(bot, chat_id, message_id):
    try:
        await bot.delete_message(chat_id=int(chat_id), message_id=int(message_id))
        return True
    except Exception:
        return False


async def _forward_with_retry(bot, chat_id, from_chat_id, message_id):
    """forward_message with one flood-wait retry."""
    try:
        return await bot.forward_message(chat_id=chat_id, from_chat_id=from_chat_id, message_id=message_id)
    except RetryAfter as e:
        await asyncio.sleep(float(getattr(e, "retry_after", 5)) + 1)
        return await bot.forward_message(chat_id=chat_id, from_chat_id=from_chat_id, message_id=message_id)


async def _run_channel_range_scan(bot, wiz: dict, user):
    """
    Walk a message range of the source chat and INDEX every ebook/audiobook found.

    Bot API bots cannot read message history, so each source message is forwarded into the
    storage chat once (that is the only way to learn its file_id / name), the temporary
    forward is deleted again, and the file is re-posted through the normal indexing path
    (_index_single_file_obj) which adds the metadata caption AND writes the row into the
    files database.  The old implementation used copy_message, which only put the file in
    storage and never saved it to the database - so it never showed up in search.
    """
    src = wiz.get("source_chat")
    start_id = int(wiz.get("start_id", 1))
    end_id = int(wiz.get("end_id", start_id))
    skip_range = wiz.get("skip_range")
    storage_id = get_config("storage_channel_id", fallback_env="STORAGE_GROUP_ID")
    batch_limit = get_config_int("max_index_batch", 10)
    sleep_secs = get_config_int("index_sleep_seconds", 10)
    uid = getattr(user, "id", 0) or 0
    utitle = (getattr(user, "full_name", None) or getattr(user, "username", None) or "Admin")

    if not storage_id:
        QUEUE_STATE["status"] = "failed: storage chat not set"
        await _refresh_progress_card(bot)
        return

    # Re-indexing the storage chat itself: the freshly captioned copy replaces the old message.
    same_chat = str(src).lstrip("@") == str(storage_id)

    processed_in_batch = 0
    for mid in range(start_id, end_id + 1):
        if QUEUE_STATE["cancelled"]:
            break
        while QUEUE_STATE["paused"] and not QUEUE_STATE["cancelled"]:
            QUEUE_STATE["status"] = "paused"
            await _refresh_progress_card(bot)
            await asyncio.sleep(2)

        if skip_range and skip_range[0] <= mid <= skip_range[1]:
            QUEUE_STATE["skipped"] += 1
            QUEUE_STATE["remaining"] = max(0, end_id - mid)
            continue

        QUEUE_STATE["fetched"] += 1
        QUEUE_STATE["remaining"] = max(0, end_id - mid)
        fwd = None
        try:
            fwd = await _forward_with_retry(bot, int(storage_id), src, mid)
            doc = getattr(fwd, "document", None) or getattr(fwd, "audio", None)
            if not doc:
                QUEUE_STATE["filtered"] += 1  # text / photo / service message
            else:
                res = await _index_single_file_obj(
                    bot,
                    doc.file_id,
                    doc.file_unique_id,
                    getattr(doc, "file_name", None) or "audiobook.m4b",
                    getattr(doc, "file_size", 0) or 0,
                    getattr(doc, "mime_type", "document") or "document",
                    uid,
                    utitle,
                    getattr(fwd, "caption", "") or "",
                )
                if res == "forwarded":
                    QUEUE_STATE["forwarded"] += 1
                    if same_chat:
                        await _safe_delete(bot, storage_id, mid)  # replaced by the indexed copy
                elif res == "duplicate":
                    QUEUE_STATE["duplicates"] += 1
                else:
                    QUEUE_STATE["filtered"] += 1
        except Exception as exc:
            logger.warning("Range index: message %s skipped: %s", mid, exc)
            QUEUE_STATE["deleted"] += 1  # missing / deleted / protected / not accessible
        finally:
            if fwd is not None:
                await _safe_delete(bot, storage_id, fwd.message_id)  # remove the temporary forward

        processed_in_batch += 1
        if processed_in_batch >= batch_limit:
            processed_in_batch = 0
            QUEUE_STATE["status"] = f"sleeping ({sleep_secs}s)"
            await _refresh_progress_card(bot)
            await asyncio.sleep(sleep_secs)
            QUEUE_STATE["status"] = "forwarding"

    if not QUEUE_STATE["cancelled"]:
        QUEUE_STATE["status"] = "completed"
    await _refresh_progress_card(bot)
