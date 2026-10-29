from configs import max_index_batch, index_sleep_seconds, log_topic
import os
import re
import html
import uuid
import asyncio
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, TelegramError, RetryAfter
from telegram.ext import ContextTypes

from modules.database.user_db import get_user_role_db, ADMIN_IDS
from modules.database.file_db import get_file_by_unique_id_db, save_indexed_file_db
from modules.indexing.book_index import (
    SUPPORTED_EBOOK_EXTENSIONS,
    fetch_goodreads_metadata,
    format_index_channel_caption,
)

logger = logging.getLogger(__name__)

FULL_ACCESS = {"Owner", "Admin"}
APPROVAL_ACCESS = {"Moderator", "Volunteer"}
ANON_ADMIN_ID = 1087968824  # Telegram's "GroupAnonymousBot"

PRIVATE_LINK_RE = re.compile(r"t\.me/c/(\d+)/(?:\d+/)?(\d+)")
PUBLIC_LINK_RE = re.compile(r"t\.me/([A-Za-z][A-Za-z0-9_]{3,})/(?:\d+/)?(\d+)")


def _parse_args(tokens):
    """Returns (links, skip). links = [(chat_ref, message_id)], skip = int or None."""
    links, skip = [], None
    for t in tokens:
        m = PRIVATE_LINK_RE.search(t)
        if m:
            links.append((int("-100" + m.group(1)), int(m.group(2))))
            continue
        m = PUBLIC_LINK_RE.search(t)
        if m:
            links.append(("@" + m.group(1).lower(), int(m.group(2))))
            continue
        if t.isdigit():
            skip = int(t)
    return links, skip


def _range_from_links(links):
    """One link = 1..link. Two links = first..last. Returns (chat, start, end) or None."""
    if not links:
        return None
    if len(links) == 1:
        return links[0][0], 1, links[0][1]
    if links[0][0] != links[1][0]:
        raise ValueError("different chats")
    a, b = links[0][1], links[1][1]
    return links[0][0], min(a, b), max(a, b)


def _link_from_forward(msg):
    origin = getattr(msg, "forward_origin", None)
    chat = getattr(origin, "chat", None)
    mid = getattr(origin, "message_id", None)
    if chat is not None and mid:
        return (chat.id, mid)
    return None


def _jobs(context) -> dict:
    return context.application.bot_data.setdefault("idx_jobs", {})


def _seconds(value) -> float:
    return value.total_seconds() if hasattr(value, "total_seconds") else float(value)


async def _edit(bot, chat_id, message_id, text, markup=None):
    try:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text,
            parse_mode="HTML", reply_markup=markup,
        )
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            logger.warning(f"[INDEX] edit failed: {e}")
    except TelegramError as e:
        logger.warning(f"[INDEX] edit failed: {e}")


async def _edit_prompt(context, job, text, markup=None):
    await _edit(context.bot, job["prompt_chat"], job["prompt_msg_id"], text, markup)


async def _edit_approval(context, job, text):
    if job.get("approval_msg_id"):
        await _edit(context.bot, job["approval_chat"], job["approval_msg_id"], text, None)


def _status_text(job, stats, state):
    total = job["end_id"] - job["start_id"] + 1
    fetched = stats["fetched"]
    remaining = max(total - fetched, 0)
    pct = int(fetched * 100 / total) if total else 100
    return (
        "<pre>"
        "╭──────❪ INDEX STATUS ❫──〇⚙️\n"
        "│╭─────────────────────────➤\n"
        f"│├─»◇ CHAT: {html.escape(job['title'])}\n││\n"
        f"│├─»◇ FETCHED MESSAGES: {fetched}\n││\n"
        f"│├─»◇ REMAINING MESSAGES: {remaining}\n││\n"
        f"│├─»◇ SUCCESSFULLY INDEXED: {stats['ok']}\n││\n"
        f"│├─»◇ DUPLICATE FILES: {stats['dup']}\n││\n"
        f"│├─»◇ DELETED MESSAGES: {stats['deleted']}\n││\n"
        f"│├─»◇ SKIPPED (ERRORS): {stats['skipped']}\n││\n"
        f"│├─»◇ FILTERED (NOT EBOOKS): {stats['filtered']}\n││\n"
        f"│├─»◇ CURRENT STATUS: {html.escape(state)}\n││\n"
        f"│├─»◇ PERCENTAGE: {pct} %\n"
        "│╰─────────────────────────➤\n"
        "╰─────────❪ PROGRESSING ❫──〇⚙️"
        "</pre>"
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
    storage = os.getenv("STORAGE_GROUP_ID")
    batch = max_index_batch()
    sleep_s = index_sleep_seconds()

    stats = {"fetched": 0, "ok": 0, "dup": 0, "deleted": 0, "skipped": 0, "filtered": 0}
    final_state = "completed ✅"

    if not storage:
        await _edit_prompt(context, job, "❌ STORAGE_GROUP_ID is not set. Cannot index.")
        job["state"] = "done"
        return

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
                    doc = fwd.document
                    ext = os.path.splitext((doc.file_name or "").lower())[1] if doc else ""
                    if not doc or ext not in SUPPORTED_EBOOK_EXTENSIONS:
                        stats["filtered"] += 1
                        await _safe_delete(fwd)
                    elif get_file_by_unique_id_db(doc.file_unique_id):
                        stats["dup"] += 1
                        await _safe_delete(fwd)
                    else:
                        meta = await fetch_goodreads_metadata(doc.file_name)
                        size = doc.file_size or 0
                        size_mb = size / (1024 * 1024)
                        size_str = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{size / 1024:.2f} KB"
                        caption = format_index_channel_caption(
                            file_name=doc.file_name,
                            file_size_str=size_str,
                            extension=ext.lstrip("."),
                            file_type=doc.mime_type or "document",
                            book_meta=meta,
                        )
                        sent = await bot.send_document(
                            chat_id=int(storage), document=doc.file_id,
                            caption=caption, parse_mode="HTML",
                        )
                        await _safe_delete(fwd)
                        save_indexed_file_db(
                            file_unique_id=doc.file_unique_id,
                            file_id=doc.file_id,
                            storage_message_id=sent.message_id,
                            file_name=doc.file_name,
                            file_size=size,
                            duration=0,
                            user_id=job["requester_id"],
                            user_title=job["requester_name"],
                            caption=f"{fwd.caption or ''} {meta.get('book_title', '')} {meta.get('book_author', '')}".strip(),
                            extension=ext,
                            file_type=doc.mime_type or "document",
                            category="book",
                        )
                        stats["ok"] += 1
            except BadRequest:
                stats["deleted"] += 1  # message missing, empty, or not forwardable
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
    logger_id = os.getenv("LOGGER_GROUP_ID")
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

    logger_id = os.getenv("LOGGER_GROUP_ID")
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

    for admin_id in ADMIN_IDS:
        try:
            m = await context.bot.send_message(
                chat_id=admin_id, text=text, parse_mode="HTML", reply_markup=markup
            )
            job["approval_chat"], job["approval_msg_id"] = m.chat_id, m.message_id
            return True
        except TelegramError:
            continue
    return False


async def _open_prompt(context, reply_chat_id, user, source_ref, start_id, end_id, skip):
    skip = skip or 0
    first = start_id + skip
    if first > end_id:
        await context.bot.send_message(
            chat_id=reply_chat_id,
            text="❌ Nothing to index: the skip number covers the whole range.",
        )
        return

    try:
        src = await context.bot.get_chat(source_ref)
    except TelegramError:
        await context.bot.send_message(
            chat_id=reply_chat_id,
            text="❌ I can't access that chat. Add me there first.",
        )
        return

    title = src.title or src.username or str(src.id)
    rid = uuid.uuid4().hex[:8]
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Yes, index", callback_data=f"idx_yes_{rid}"),
        InlineKeyboardButton("❌ No", callback_data=f"idx_no_{rid}"),
    ]])
    skip_note = f" (skipping first {skip})" if skip else ""
    sent = await context.bot.send_message(
        chat_id=reply_chat_id,
        text=(
            "📚 <b>Do you want to index this chat?</b>\n\n"
            f"📂 <b>{html.escape(title)}</b>\n"
            f"🔢 Messages: {first} → {end_id}{skip_note}"
        ),
        parse_mode="HTML",
        reply_markup=markup,
    )
    _jobs(context)[rid] = {
        "chat_id": src.id,
        "start_id": first,
        "end_id": end_id,
        "title": title,
        "state": "prompt",
        "cancel": False,
        "requester_id": user.id if user else 0,
        "requester_name": user.full_name if user else "Channel admin",
        "requester_role": "",
        "prompt_chat": sent.chat_id,
        "prompt_msg_id": sent.message_id,
    }


async def index_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not chat:
        return

    if user and user.id != ANON_ADMIN_ID:
        if get_user_role_db(user.id) not in (FULL_ACCESS | APPROVAL_ACCESS):
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
        # /index or /index <skip> inside a group/channel: index everything before this command
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
    """Private-chat follow-up: collects the link(s), then the skip number."""
    flow = (context.user_data or {}).get("idx_flow")
    msg = update.effective_message
    user = update.effective_user
    if not flow or not msg or not user:
        return

    if get_user_role_db(user.id) not in (FULL_ACCESS | APPROVAL_ACCESS):
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

    if action == "yes":
        if job["state"] != "prompt":
            await q.answer("Already handled.", show_alert=True)
            return
        if not (full or partial):
            await q.answer("⛔ You don't have access to the Index command.", show_alert=True)
            return
        job.update(requester_id=user.id, requester_name=user.full_name, requester_role=role)
        if full:
            await q.answer("Starting…")
            await _edit_prompt(context, job, _status_text(job, {"fetched": 0, "ok": 0, "dup": 0, "deleted": 0, "skipped": 0, "filtered": 0}, "starting"), _cancel_markup(rid))
            _begin(context, rid, job)
        else:
            job["state"] = "approval"
            if await _send_approval(context, rid, job):
                await q.answer("Sent for approval")
                await _edit_prompt(context, job, "⏳ <b>Sent to admins for approval.</b>\nYou'll see progress here once approved.")
            else:
                job["state"] = "prompt"
                await q.answer("❌ Couldn't reach any admin. Try again later.", show_alert=True)

    elif action == "no":
        if not (full or partial):
            await q.answer("⛔ You don't have access to the Index command.", show_alert=True)
            return
        job["state"] = "done"
        await q.answer("Cancelled")
        await _edit_prompt(context, job, "❌ Indexing cancelled.")

    elif action in ("apr", "rej"):
        if not full:
            await q.answer("⛔ Only admins can approve.", show_alert=True)
            return
        if job["state"] != "approval":
            await q.answer("Already handled.", show_alert=True)
            return
        who = html.escape(user.full_name)
        if action == "apr":
            await q.answer("Approved")
            await _edit_approval(context, job, f"✅ <b>Approved</b> by {who}\n📂 {html.escape(job['title'])} — requested by {html.escape(job['requester_name'])}")
            await _edit_prompt(context, job, _status_text(job, {"fetched": 0, "ok": 0, "dup": 0, "deleted": 0, "skipped": 0, "filtered": 0}, "starting"), _cancel_markup(rid))
            _begin(context, rid, job)
        else:
            job["state"] = "done"
            await q.answer("Rejected")
            await _edit_approval(context, job, f"❌ <b>Rejected</b> by {who}\n📂 {html.escape(job['title'])} — requested by {html.escape(job['requester_name'])}")
            await _edit_prompt(context, job, f"❌ Index request rejected by {who}.")

    elif action == "cancel":
        if not full:
            await q.answer("⛔ Only admins can cancel.", show_alert=True)
            return
        if job["state"] == "running":
            job["cancel"] = True
            await q.answer("Cancelling…")
        else:
            await q.answer("Not running.", show_alert=True)
