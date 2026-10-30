import sqlite3
from config import users_db_path

def _init_index_persistence():
    try:
        conn = sqlite3.connect(users_db_path())
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS active_index_jobs (
                rid TEXT PRIMARY KEY,
                chat_id INTEGER,
                title TEXT,
                start_id INTEGER,
                end_id INTEGER,
                current_mid INTEGER,
                priority_mode TEXT,
                requester_id INTEGER,
                requester_name TEXT,
                prompt_chat INTEGER,
                prompt_msg_id INTEGER,
                state TEXT
            )
        ''')
        conn.commit()
        conn.close()
    except Exception:
        pass

_init_index_persistence()

from telegram import Bot
import time
import re
import html
import uuid
import asyncio
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, TelegramError, RetryAfter
from telegram.ext import ContextTypes

from config import (
    admin_ids,
    anon_admin_id,
    index_sleep_seconds,
    log_topic,
    logger_group_id,
    max_index_batch,
    storage_group_id,
    helper_bot_tokens,
)
from modules.database.user_db import get_user_role_db
from modules.database.file_db import get_file_by_unique_id_db, save_indexed_file_db
from modules.indexing.book_index import (
    _format_duration,
    _make_storage_msg_link,
    enrich_book_metadata,
    extract_media_info,
    fetch_goodreads_metadata,
    format_index_channel_caption,
    format_index_log_message,
    send_media_to_storage,
)

logger = logging.getLogger(__name__)

INDEX_COMMAND_ACCESS = {"Admin", "Administrator", "Creator", "Owner"}
FULL_ACCESS = {"Admin", "Administrator", "Creator", "Owner"}
APPROVAL_ACCESS = set()


def _jobs(context: ContextTypes.DEFAULT_TYPE) -> dict:
    if "index_jobs" not in context.bot_data:
        context.bot_data["index_jobs"] = {}
    return context.bot_data["index_jobs"]


def _seconds(val) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 1.0


async def _get_safe_source_link(bot, chat_id: int, title: str) -> str:
    """
    Safely generates source chat info for the index log:
    - If public: hyperlinks using official https://t.me/username link.
    - If private and bot has invite permission: attempts export_chat_invite_link.
    - If private without permission or on error: falls back gracefully to title (chat_id) with ZERO exceptions.
    """
    esc_title = html.escape(title or "Source Chat")
    try:
        chat = await bot.get_chat(chat_id)
        if chat.username:
            return f'<a href="https://t.me/{chat.username}">{esc_title}</a> (<code>{chat_id}</code>)'

        member = await bot.get_chat_member(chat_id, bot.id)
        if getattr(member, "can_invite_users", False) or getattr(member, "status", "") in ("creator", "administrator"):
            inv = await bot.export_chat_invite_link(chat_id)
            if inv:
                return f'<a href="{inv}">{esc_title}</a> (<code>{chat_id}</code>)'
    except Exception:
        pass
    return f'{esc_title} (<code>{chat_id}</code>)'


def _parse_args(args: list[str]) -> tuple[list[str], int | None]:
    links = []
    skip = None
    for a in args:
        if a.isdigit():
            skip = int(a)
        elif "t.me/" in a:
            links.append(a)
    return links, skip


def _parse_link(link: str) -> tuple[int, int] | None:
    m = re.search(r"t\.me/(?:c/(\d+)|([a-zA-Z0-9_]+))/(\d+)", link)
    if not m:
        return None
    cid, uname, mid = m.groups()
    if cid:
        return -1000000000000 - int(cid) if not cid.startswith("100") else -int(f"100{cid}"), int(mid)
    return uname, int(mid)


def _range_from_links(links: list[str]) -> tuple[int | str, int, int] | None:
    if not links:
        return None
    if len(links) == 1:
        p = _parse_link(links[0])
        return (p[0], 1, p[1]) if p else None
    p1 = _parse_link(links[0])
    p2 = _parse_link(links[1])
    if not p1 or not p2:
        return None
    if p1[0] != p2[0]:
        raise ValueError("different chats")
    start, end = sorted([p1[1], p2[1]])
    return p1[0], start, end


def _link_from_forward(msg) -> str | None:
    fwd = getattr(msg, "forward_from_chat", None)
    fwd_mid = getattr(msg, "forward_from_message_id", None)
    if not fwd or not fwd_mid:
        return None
    if fwd.username:
        return f"https://t.me/{fwd.username}/{fwd_mid}"
    cid_str = str(fwd.id).replace("-100", "")
    return f"https://t.me/c/{cid_str}/{fwd_mid}"


def _status_text(job: dict, stats: dict, phase: str = "running") -> str:
    total = max(1, job["end_id"] - job["start_id"] + 1)
    done = stats["fetched"]
    pct = min(100, int((done / total) * 100))
    bar_len = 16
    filled = int(bar_len * (pct / 100))
    bar = "█" * filled + "▒" * (bar_len - filled)

    return (
        f"╭─────────❪ INDEXING ❫──〇\n"
        f"│ 📂 <b>Chat:</b> {html.escape(job['title'])}\n"
        f"│ 🔢 <b>Range:</b> <code>{job['start_id']} → {job['end_id']}</code>\n"
        f"│ ⚙️ <b>Phase:</b> <code>{html.escape(phase)}</code>\n"
        f"│ 📊 <b>Progress:</b> <code>[{bar}] {pct}%</code>\n"
        f"│\n"
        f"│ 📥 Fetched: <code>{stats['fetched']}/{total}</code>\n"
        f"│ ✅ Indexed: <code>{stats['ok']}</code>\n"
        f"│ ♻️ Duplicates: <code>{stats['dup']}</code>\n"
        f"│ 🚫 Filtered: <code>{stats['filtered']}</code>\n"
        f"│ 🗑 Deleted: <code>{stats['deleted']}</code>\n"
        f"│ ⚠️ Errors: <code>{stats['skipped']}</code>\n"
        f"│╰─────────────────────────➤\n"
        f"╰─────────❪ PROGRESSING ❫──〇⚙️"
    )


def _cancel_markup(rid):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⛔ Cancel Indexing", callback_data=f"idx_cancel_{rid}")]]
    )


async def _forward(bot, to_chat, from_chat, message_id):
    for _ in range(5):
        try:
            return await bot.forward_message(
                chat_id=to_chat, from_chat_id=from_chat,
                message_id=message_id, disable_notification=True,
            )
        except RetryAfter as e:
            await asyncio.sleep(_seconds(e.retry_after) + 1)
    return None


async def _safe_delete(msg):
    try:
        await msg.delete()
    except TelegramError:
        pass


async def _run_index(context, rid, job):
    bot = context.bot
    storage = storage_group_id()
    batch = max_index_batch()
    sleep_s = index_sleep_seconds()

    stats = {"fetched": 0, "ok": 0, "dup": 0, "deleted": 0, "skipped": 0, "filtered": 0}
    final_state = "completed ✅"

    if not storage:
        await _edit_prompt(context, job, "❌ PUBLIC_/TESTING_STORAGE_GROUP_ID is not set. Cannot index.")
        job["state"] = "done"
        return

    log_group_id = logger_group_id()
    index_log_topic_id = log_topic("INDEX")
    error_log_topic_id = log_topic("ERROR")

    # Resolve safe source link
    source_info = await _get_safe_source_link(bot, job["chat_id"], job["title"])

    try:
        for mid in range(job["start_id"], job["end_id"] + 1):
            if job["cancel"]:
                final_state = "cancelled ⛔"
                break

            stats["fetched"] += 1
            try:
                fwd = await _forward(bot, int(storage), job["chat_id"], mid)
                if fwd is None:
                    stats["skipped"] += 1
                else:
                    info = extract_media_info(fwd)
                    if not info or not info["is_supported"]:
                        stats["filtered"] += 1
                        await _safe_delete(fwd)
                    elif get_file_by_unique_id_db(info["file_unique_id"]):
                        stats["dup"] += 1
                        await _safe_delete(fwd)
                    else:
                        meta = await enrich_book_metadata(info["file_name"], category=info["category"])
                        is_matched = meta.get("is_matched", False)

                        for k, v in (info.get("caption_meta") or {}).items():
                            if v and k in ("book_title", "book_author", "narrator", "length", "book_published"):
                                meta[k] = v

                        if info["category"] == "audiobook" and (not meta.get("length")) and info["duration"] > 0:
                            meta["length"] = _format_duration(info["duration"])

                        size = info["file_size"]
                        size_mb = size / (1024 * 1024)
                        size_str = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{size / 1024:.2f} KB"

                        caption = format_index_channel_caption(
                            file_name=info["file_name"],
                            file_size_str=size_str,
                            extension=info["extension"].lstrip("."),
                            file_type=info["mime_type"],
                            book_meta=meta,
                            category=info["category"],
                        )

                        sent = await send_media_to_storage(bot, int(storage), info, caption)
                        await _safe_delete(fwd)

                        storage_link = _make_storage_msg_link(int(storage), sent.message_id)

                        save_indexed_file_db(
                            file_unique_id=info["file_unique_id"],
                            file_id=info["file_id"],
                            storage_message_id=sent.message_id,
                            file_name=info["file_name"],
                            file_size=size,
                            duration=info["duration"],
                            user_id=job["requester_id"],
                            user_title=job["requester_name"],
                            caption=(
                                f"{caption} {info['file_name']} {meta.get('title', '')} "
                                f"{meta.get('author', '')} {meta.get('series', '')}"
                            ).strip(),
                            extension=info["extension"],
                            file_type=info["mime_type"],
                            category=info["category"],
                            is_enriched=1 if is_matched else 0,
                        )
                        stats["ok"] += 1

                        caption_badge = "📝 caption enriched" if is_matched else "🚧 info not found reported to error logs"

                        # Post Error Log if enrichment failed (< 2 parameters)
                        if not is_matched and error_log_topic_id and log_group_id:
                            try:
                                err_text = (
                                    f"⚠️ <b>Caption Enrichment Failed (&lt;2 Parameters Matched)</b>\n\n"
                                    f"📁 <b>File:</b> <code>{html.escape(info['file_name'])}</code>\n"
                                    f"🔗 <b>Storage Message:</b> <a href=\"{storage_link}\">Message #{sent.message_id}</a>\n"
                                    f"🔑 <b>Unique ID:</b> <code>{info['file_unique_id']}</code>\n"
                                    f"🌐 <b>Source:</b> {source_info}\n\n"
                                    f"<i>Admins please edit the storage message caption manually. The bot will automatically capture your edit and update the database.</i>"
                                )
                                await context.bot.send_message(
                                    chat_id=int(log_group_id),
                                    text=err_text,
                                    parse_mode="HTML",
                                    message_thread_id=int(error_log_topic_id),
                                )
                            except Exception:
                                pass

                        # Post Standardized Index Log for this file
                        if log_group_id:
                            try:
                                log_msg = format_index_log_message(
                                    file_name=info["file_name"],
                                    file_size_str=size_str,
                                    file_unique_id=info["file_unique_id"],
                                    storage_link=storage_link,
                                    user_id=job["requester_id"],
                                    user_title=job["requester_name"],
                                    db_badge="✅ updated",
                                    storage_badge="🗃️ added to storage group",
                                    caption_badge=caption_badge,
                                    source_info=source_info,
                                )
                                log_kwargs = {
                                    "chat_id": int(log_group_id),
                                    "text": log_msg,
                                    "parse_mode": "HTML",
                                }
                                if index_log_topic_id:
                                    log_kwargs["message_thread_id"] = int(index_log_topic_id)
                                await context.bot.send_message(**log_kwargs)
                            except Exception:
                                pass

            except BadRequest:
                stats["deleted"] += 1
            except Exception as e:
                logger.warning(f"[INDEX] message {mid} failed: {e}")
                stats["skipped"] += 1

            if stats["fetched"] % batch == 0 and mid < job["end_id"]:
                await _edit_prompt(
                    context, job,
                    _status_text(job, stats, f"sleeping ({sleep_s}s)"),
                    _cancel_markup(rid),
                )
                await asyncio.sleep(sleep_s)
    except Exception as e:
        logger.exception("[INDEX] job crashed")
        final_state = f"stopped: {e}"

    job["state"] = "done"
    await _edit_prompt(context, job, _status_text(job, stats, final_state))
    await _log_summary(context, job, stats, final_state)


async def _log_summary(context, job, stats, final_state):
    logger_id = logger_group_id()
    if not logger_id:
        return
    text = (
        f"📥 <b>Indexing {html.escape(final_state)}</b>\n\n"
        f"📂 Chat: <b>{html.escape(job['title'])}</b>\n"
        f"👤 By: {html.escape(job['requester_name'])} (<code>{job['requester_id']}</code>)\n"
        f"✅ Indexed: {stats['ok']} | ♻️ Duplicates: {stats['dup']} | "
        f"🚫 Filtered: {stats['filtered']} | 🗑 Deleted: {stats['deleted']} | ⚠️ Errors: {stats['skipped']}"
    )
    kwargs = {"chat_id": int(logger_id), "text": text, "parse_mode": "HTML"}
    topic = log_topic("INDEX")
    if topic:
        kwargs["message_thread_id"] = int(topic)
    try:
        await context.bot.send_message(**kwargs)
    except Exception as e:
        logger.warning(f"[INDEX] summary log failed: {e}")


async def _send_approval(context, rid, job):
    text = (
        "🔔 <b>Index approval request</b>\n\n"
        f"👤 By: {html.escape(job['requester_name'])} (<code>{job['requester_id']}</code>) — {html.escape(job['requester_role'])}\n"
        f"📂 Chat: <b>{html.escape(job['title'])}</b>\n"
        f"🔢 Messages: {job['start_id']} → {job['end_id']}"
    )
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"idx_apr_{rid}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"idx_rej_{rid}"),
    ]])

    logger_id = logger_group_id()
    if logger_id:
        kwargs = {"chat_id": int(logger_id), "text": text, "parse_mode": "HTML", "reply_markup": markup}
        topic = log_topic("INDEX")
        if topic:
            kwargs["message_thread_id"] = int(topic)
        try:
            m = await context.bot.send_message(**kwargs)
            job["approval_chat"], job["approval_msg_id"] = m.chat_id, m.message_id
            return True
        except TelegramError as e:
            logger.warning(f"[INDEX] approval to logger group failed: {e}")

    for aid in sorted(admin_ids()):
        try:
            m = await context.bot.send_message(
                chat_id=aid, text=text, parse_mode="HTML", reply_markup=markup
            )
            job["approval_chat"], job["approval_msg_id"] = m.chat_id, m.message_id
            return True
        except TelegramError:
            continue
    return False


async def _show_skip_menu(context, rid: str, job: dict):
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏩ No Skip", callback_data=f"idx_sk_none_{rid}")],
        [
            InlineKeyboardButton("⏭ Skip Top N", callback_data=f"idx_sk_top_{rid}"),
            InlineKeyboardButton("⏮ Skip Bottom N", callback_data=f"idx_sk_bot_{rid}"),
        ],
        [InlineKeyboardButton("✂️ Custom Range", callback_data=f"idx_sk_custom_{rid}")],
        [InlineKeyboardButton("⛔ Cancel", callback_data=f"idx_cancel_{rid}")],
    ])
    await _edit_prompt(
        context, job,
        f"🔢 <b>Message Skip & Range Selection</b>\n\n"
        f"📂 Chat: <b>{html.escape(job['title'])}</b>\n"
        f"🔢 Range: <code>{job['start_id']} → {job['end_id']}</code>\n\n"
        f"Select an option below to filter messages before starting:",
        markup,
    )


async def _open_prompt(context, prompt_chat, user, chat_ref, start_id, end_id, skip=None):
    try:
        source_chat = await context.bot.get_chat(chat_ref)
        title = source_chat.title or source_chat.username or str(chat_ref)
        cid = source_chat.id
    except TelegramError as e:
        await context.bot.send_message(
            chat_id=prompt_chat,
            text=f"❌ I can't reach that chat ({e}). Make sure I am a member / admin there.",
        )
        return

    rid = uuid.uuid4().hex[:8]
    job = {
        "rid": rid,
        "chat_id": cid,
        "title": title,
        "start_id": start_id,
        "end_id": end_id,
        "requester_id": user.id if user else 0,
        "requester_name": user.full_name if user else "Anon Admin",
        "requester_role": get_user_role_db(user.id) if user else "Admin",
        "prompt_chat": prompt_chat,
        "prompt_msg_id": None,
        "approval_chat": None,
        "approval_msg_id": None,
        "cancel": False,
        "state": "pending",
    }
    _jobs(context)[rid] = job

    if skip is not None:
        if skip > 0:
            job["start_id"] = min(job["end_id"], job["start_id"] + skip)
        await _show_priority_menu(context, rid, job)
    else:
        await _show_skip_menu(context, rid, job)


async def _show_priority_menu(context, rid: str, job: dict):
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Priority Mode (Direct)", callback_data=f"idx_pr_dir_{rid}")],
        [InlineKeyboardButton("🤝 Helper Pool (Round-Robin)", callback_data=f"idx_pr_hlp_{rid}")],
        [InlineKeyboardButton("⛔ Cancel", callback_data=f"idx_cancel_{rid}")],
    ])
    await _edit_prompt(
        context, job,
        f"⚡ <b>Delivery Priority Setup</b>\n\n"
        f"📂 Chat: <b>{html.escape(job['title'])}</b>\n"
        f"🔢 Range: <code>{job['start_id']} → {job['end_id']}</code>\n\n"
        f"Select delivery mode:",
        markup,
    )


async def _edit_prompt(context, job, text, markup=None):
    cid = job["prompt_chat"]
    mid = job.get("prompt_msg_id")
    if mid is None:
        m = await context.bot.send_message(chat_id=cid, text=text, parse_mode="HTML", reply_markup=markup)
        job["prompt_msg_id"] = m.message_id
    else:
        try:
            await context.bot.edit_message_text(
                chat_id=cid, message_id=mid, text=text, parse_mode="HTML", reply_markup=markup
            )
        except TelegramError:
            pass


async def index_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not msg or not chat:
        return

    if user and user.id != anon_admin_id():
        role = get_user_role_db(user.id)
        if role not in INDEX_COMMAND_ACCESS:
            if role in ("Volunteer", "Moderator"):
                await msg.reply_text(
                    "⛔ The <code>/index</code> batch command is exclusive to Administrators and the Creator only.\n\n"
                    "💡 <i>As a Volunteer or Moderator, you can index files directly without approvals by sending them to Helper Bot DMs!</i>",
                    parse_mode="HTML",
                )
            else:
                await msg.reply_text("⛔ You don't have access to the Index command.")
            return

    links, skip = _parse_args((msg.text or "").split()[1:])
    try:
        rng = _range_from_links(links)
    except ValueError:
        await msg.reply_text("❌ Both links must be from the same chat.")
        return

    if rng:
        await _open_prompt(context, chat.id, user, rng[0], rng[1], rng[2], skip)
    elif chat.type != "private":
        await _open_prompt(context, chat.id, user, chat.id, 1, msg.message_id - 1, skip)
    else:
        context.user_data["idx_flow"] = {"step": "link", "skip": skip}
        await msg.reply_text(
            "📚 <b>Index setup</b>\n\n"
            "Send the <b>last message link</b> of the source chat, or forward its last message.\n"
            "To index a range, send <b>two links</b>: first message, then last message.\n\n"
            "Example: <code>https://t.me/c/1234567890/150</code>\n"
            "Send /index again to restart.",
            parse_mode="HTML",
        )


async def index_flow_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    flow = (context.user_data or {}).get("idx_flow")
    msg = update.effective_message
    user = update.effective_user
    if not flow or not msg or not user:
        return

    if get_user_role_db(user.id) not in INDEX_COMMAND_ACCESS:
        context.user_data.pop("idx_flow", None)
        return

    if flow["step"] == "link":
        links, skip = _parse_args((msg.text or "").split())
        fwd = _link_from_forward(msg)
        if fwd and not links:
            links = [fwd]
        try:
            rng = _range_from_links(links)
        except ValueError:
            await msg.reply_text("❌ Both links must be from the same chat.")
            return
        if not rng:
            await msg.reply_text(
                "❌ I couldn't read that. Send a message link like https://t.me/c/1234567890/150, "
                "two links for a range, or forward the last message."
            )
            return
        flow.update(source=rng[0], start=rng[1], end=rng[2])
        if skip is None:
            skip = flow.get("skip")
        if skip is None:
            flow["step"] = "skip"
            await msg.reply_text(
                "🔢 How many messages should I skip from the start? Send a number (0 to skip none)."
            )
            return
        flow["skip"] = skip
    else:
        text = (msg.text or "").strip()
        if not text.isdigit():
            await msg.reply_text("Please send a number (0 to skip none).")
            return
        flow["skip"] = int(text)

    context.user_data.pop("idx_flow", None)
    await _open_prompt(
        context, msg.chat_id, user,
        flow["source"], flow["start"], flow["end"], flow["skip"],
    )


def _begin(context, rid, job):
    job["state"] = "running"
    context.application.create_task(_run_index(context, rid, job))


async def index_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        _, action, rid = q.data.split("_", 2)
    except (ValueError, AttributeError):
        await q.answer()
        return

    job = _jobs(context).get(rid)
    if not job:
        await q.answer("⌛ This request has expired. Send /index again.", show_alert=True)
        return

    user = q.from_user
    role = get_user_role_db(user.id)
    full = role in FULL_ACCESS
    partial = role in APPROVAL_ACCESS

    if action == "cancel":
        job["cancel"] = True
        await q.answer("Indexing cancelled.")
        await _edit_prompt(context, job, f"⛔ Indexing of <b>{html.escape(job['title'])}</b> was cancelled.")
        return

    if action.startswith("sk_"):
        mode = action[3:]
        if mode == "none":
            await _show_priority_menu(context, rid, job)
        elif mode == "top":
            job["start_id"] = min(job["end_id"], job["start_id"] + 10)
            await _show_priority_menu(context, rid, job)
        elif mode == "bot":
            job["end_id"] = max(job["start_id"], job["end_id"] - 10)
            await _show_priority_menu(context, rid, job)
        elif mode == "custom":
            await _edit_prompt(context, job, "Send <code>/index &lt;first_link&gt; &lt;last_link&gt;</code> for custom ranges.")
        return

    if action.startswith("pr_"):
        mode = "direct" if action == "pr_dir" else "helpers"
        job["priority_mode"] = mode
        if full:
            await q.answer("Starting index...")
            await _edit_prompt(context, job, f"🚀 Starting index in {mode} mode...")
            _begin(context, rid, job)
        elif partial:
            sent = await _send_approval(context, rid, job)
            if sent:
                await q.answer("Submitted for approval.")
                await _edit_prompt(context, job, "⌛ Index request submitted to Admins for approval.")
            else:
                await q.answer("No admins available.", show_alert=True)
        else:
            await q.answer("Access denied.", show_alert=True)
        return

    if action == "apr":
        if not full:
            await q.answer("Only Administrators can approve.", show_alert=True)
            return
        await q.answer("Approved!")
        _begin(context, rid, job)
        return

    if action == "rej":
        if not full:
            await q.answer("Only Administrators can reject.", show_alert=True)
            return
        job["cancel"] = True
        await q.answer("Rejected.")
        await _edit_prompt(context, job, f"❌ Index request for <b>{html.escape(job['title'])}</b> was rejected.")
        return
