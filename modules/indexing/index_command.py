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
        for col, ddl in (("is_channel", "INTEGER DEFAULT 0"), ("helper_token", "TEXT")):
            try:
                c.execute(f"ALTER TABLE active_index_jobs ADD COLUMN {col} {ddl}")
            except Exception:
                pass  # column already exists
        conn.commit()
        conn.close()
    except Exception:
        pass


_init_index_persistence()

_JOB_COLS = (
    "rid", "chat_id", "title", "start_id", "end_id", "priority_mode", "requester_id", "requester_name",
    "prompt_chat", "prompt_msg_id", "state", "is_channel", "helper_token",
)


def _persist_job(job: dict) -> None:
    """Saves a not-yet-running /index job so its buttons still work after a restart / Render sleep
    (the in-memory job store is empty then, which used to answer every tap with "request expired")."""
    try:
        vals = []
        for col in _JOB_COLS:
            v = job.get(col)
            if col == "is_channel":
                v = 1 if v else 0
            vals.append(v)
        conn = sqlite3.connect(users_db_path())
        conn.execute(
            f"INSERT OR REPLACE INTO active_index_jobs ({', '.join(_JOB_COLS)}) VALUES ({', '.join('?' * len(_JOB_COLS))})",
            vals,
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logging.getLogger(__name__).debug("index job persist failed: %s", exc)


def _forget_job(rid: str) -> None:
    try:
        conn = sqlite3.connect(users_db_path())
        conn.execute("DELETE FROM active_index_jobs WHERE rid = ?", (rid,))
        conn.commit()
        conn.close()
    except Exception:
        pass


def _load_job(rid: str) -> dict | None:
    """Restores a pending job (setup stage) from SQLite; running/finished jobs are not restored."""
    try:
        conn = sqlite3.connect(users_db_path())
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM active_index_jobs WHERE rid = ?", (rid,)).fetchone()
        conn.close()
    except Exception:
        return None
    if not row or (row["state"] or "pending") != "pending":
        return None
    job = {k: row[k] for k in _JOB_COLS}
    job["is_channel"] = bool(job.get("is_channel"))
    job.update(cancel=False, approval_chat=None, approval_msg_id=None, state="pending")
    job["requester_role"] = get_user_role_db(job["requester_id"]) if job.get("requester_id") else "Admin"
    return job

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
    index_channel_id,
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
    _ist_now_str,
    _make_storage_msg_link,
    enrich_book_metadata,
    extract_media_info,
    fetch_goodreads_metadata,
    format_index_channel_caption,
    send_index_file_logs,
    send_index_topic_log,
    send_media_to_storage,
    user_link_html,
    verify_and_heal_indexed_file,
)
from modules.utility.rich_ui import styled_button, tg_button_html, tg_button_row_html

logger = logging.getLogger(__name__)

INDEX_COMMAND_ACCESS = {"Admin", "Administrator", "Creator", "Owner"}
FULL_ACCESS = {"Admin", "Administrator", "Creator", "Owner"}
APPROVAL_ACCESS = set()

# Shared job store and channel command deduplication across Main Bot and Helper Bots
_GLOBAL_INDEX_JOBS: dict[str, dict] = {}
_SEEN_CHANNEL_CMDS: set[tuple[int, int]] = set()


def _jobs(context: ContextTypes.DEFAULT_TYPE) -> dict:
    if hasattr(context, "bot_data") and isinstance(context.bot_data, dict):
        context.bot_data["index_jobs"] = _GLOBAL_INDEX_JOBS
    return _GLOBAL_INDEX_JOBS


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
        f"╭─────────❪ <b>INDEXING</b> ❫──〇\n"
        f"│ 📂 <b>Chat:</b> {html.escape(job['title'])}\n"
        f"│ 🔢 <b>Range:</b> <mark>{job['start_id']} → {job['end_id']}</mark>\n"
        f"│ ⚙️ <b>Phase:</b> <mark>{html.escape(phase)}</mark>\n"
        f"│ 📊 <b>Progress:</b> <code>[{bar}] {pct}%</code>\n"
        f"│\n"
        f"│ 📥 Fetched: <code>{stats['fetched']}/{total}</code>\n"
        f"│ ✅ Indexed / Healed: <code>{stats['ok']}</code>\n"
        f"│ ♻️ Verified Duplicates: <code>{stats['dup']}</code>\n"
        f"│ 🚫 Filtered: <code>{stats['filtered']}</code>\n"
        f"│ 🗑 Deleted: <code>{stats['deleted']}</code>\n"
        f"│ ⚠️ Errors: <code>{stats['skipped']}</code>\n"
        f"│╰─────────────────────────➤\n"
        f"╰─────────❪ <b>PROGRESSING</b> ❫──〇⚙️"
    )


def _cancel_markup(rid):
    return InlineKeyboardMarkup(
        [[styled_button("⛔ Cancel Indexing", callback_data=f"idx_cancel_{rid}", style="danger")]]
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
    except Exception:
        pass


async def _auto_delete_prompt(bot, job: dict, delay_s: int = 15):
    """Deletes temporary progress card inside a source channel after indexing completes."""
    await asyncio.sleep(max(1, delay_s))
    cid = job.get("prompt_chat")
    mid = job.get("prompt_msg_id")
    if cid and mid:
        try:
            await bot.delete_message(chat_id=cid, message_id=mid)
        except Exception:
            pass


async def _build_helper_pool_bots(tokens: list[str] | None = None) -> list[tuple[Bot, str]]:
    """Initializes reachable helper Bot instances for round-robin indexing (all helpers, or only `tokens`)."""
    pool: list[tuple[Bot, str]] = []
    for tok in (tokens if tokens is not None else helper_bot_tokens()):
        try:
            hb = Bot(tok)
            await hb.initialize()
            me = await hb.get_me()
            uname = f"@{me.username}" if me.username else (me.first_name or "Helper Bot")
            pool.append((hb, uname))
        except Exception as exc:
            logger.debug("Could not initialize helper bot for indexing pool: %s", exc)
    return pool


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
    error_log_topic_id = log_topic("ERROR")

    # Resolve safe source link
    source_info = await _get_safe_source_link(bot, job["chat_id"], job["title"])

    # Determine active bot label and optional Helper Bot Round-Robin Pool
    default_bot_label = f"@{bot.username}" if getattr(bot, "username", None) else "Bot"
    if default_bot_label == "Bot":
        try:
            me = await bot.get_me()
            if me and me.username:
                default_bot_label = f"@{me.username}"
        except Exception:
            pass

    helper_pool: list[tuple[Bot, str]] = []
    only_helper = bool(job.get("helper_token"))  # main bot cannot see the source chat: helper does ALL the work
    if only_helper:
        helper_pool = await _build_helper_pool_bots([job["helper_token"]])
        if not helper_pool:
            await _edit_prompt(context, job, "❌ The helper bot that can read this chat is unreachable. Try again later.")
            job["state"] = "done"
            _forget_job(rid)
            return
    elif job.get("priority_mode") == "helpers":
        helper_pool = await _build_helper_pool_bots()

    await _log_lifecycle(context, job, "started", default_bot_label, source_info=source_info)

    try:
        for mid in range(job["start_id"], job["end_id"] + 1):
            if job["cancel"]:
                final_state = "cancelled ⛔"
                break

            stats["fetched"] += 1
            active_bot = bot
            active_bot_label = default_bot_label
            if helper_pool:
                active_bot, active_bot_label = helper_pool[(stats["fetched"] - 1) % len(helper_pool)]

            try:
                fwd = await _forward(active_bot, int(storage), job["chat_id"], mid)
                if fwd is None and active_bot is not bot and not only_helper:
                    active_bot = bot
                    active_bot_label = default_bot_label
                    fwd = await _forward(bot, int(storage), job["chat_id"], mid)

                if fwd is None:
                    stats["skipped"] += 1
                else:
                    info = extract_media_info(fwd)
                    if not info or not info["is_supported"]:
                        stats["filtered"] += 1
                        await _safe_delete(fwd)
                    else:
                        # Remove temporary forward immediately after extracting media info
                        await _safe_delete(fwd)

                        # Run 3-Stage Ordered Verification & Self-Healing (1. DB -> 2. Storage -> 3. Caption)
                        res = await verify_and_heal_indexed_file(
                            bot=active_bot,
                            info=info,
                            storage_id=int(storage),
                            user_id=job["requester_id"],
                            user_title=job["requester_name"],
                            source_info=source_info,
                        )

                        if res["status"] == "duplicate":
                            stats["dup"] += 1
                        else:
                            stats["ok"] += 1

                        storage_link = res["storage_link"]
                        is_matched = res["is_success_enrichment"]

                        # Post Error Log if any stage failed or enrichment failed (< 2 parameters)
                        if (not is_matched or not res["db_ok"]) and error_log_topic_id and log_group_id:
                            try:
                                storage_btn_row = tg_button_row_html([
                                    tg_button_html(
                                        f"📦 Open Storage Message #{res['storage_message_id']}",
                                        url=storage_link,
                                        style="primary",
                                    )
                                ])
                                err_text = (
                                    f"⚠️ <b>Caption Enrichment Failed (&lt;2 Parameters Matched)</b>\n\n"
                                    f"📁 <b>File:</b> <code>{html.escape(info['file_name'])}</code>\n"
                                    f"🔑 <b>Unique ID:</b> <mark>{info['file_unique_id']}</mark>\n"
                                    f"🤖 <b>Indexed By:</b> <code>{html.escape(active_bot_label)}</code>\n"
                                    f"🌐 <b>Source:</b> {source_info}\n\n"
                                    f"<b>3-Stage Check:</b>\n"
                                    f"1. 🗄 <b>Database:</b> {res['db_badge']}\n"
                                    f"2. 📦 <b>Storage:</b> {res['storage_badge']}\n"
                                    f"3. 📝 <b>Caption:</b> {res['caption_badge']}\n\n"
                                    f"<i>Admins please edit the storage message caption manually. The bot will automatically capture your edit and update the database.</i>\n\n"
                                    f"{storage_btn_row}"
                                )
                                await active_bot.send_message(
                                    chat_id=int(log_group_id),
                                    text=err_text,
                                    parse_mode="HTML",
                                    message_thread_id=int(error_log_topic_id),
                                )
                            except Exception:
                                pass

                        # Index Audit Card -> Index Logs TOPIC (always); curated card -> Index Logs CHANNEL (enriched only)
                        try:
                            await send_index_file_logs(
                                active_bot,
                                info=info,
                                res=res,
                                user_id=job["requester_id"],
                                user_title=job["requester_name"],
                                source_info=f"{source_info} | Msg <code>#{mid}</code>",
                                indexed_by_bot=active_bot_label,
                                fallback_bot=bot,
                                original_caption=info.get("raw_caption") or "",
                            )
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
    finally:
        for hb, _ in helper_pool:
            try:
                await hb.shutdown()
            except Exception:
                pass

    job["state"] = "done"
    _forget_job(rid)
    await _edit_prompt(context, job, _status_text(job, stats, final_state))
    await _log_summary(context, job, stats, final_state, default_bot_label, source_info=source_info)
    if job.get("is_channel"):
        asyncio.create_task(_auto_delete_prompt(bot, job, 15))


_LIFECYCLE = {
    "started": ("🟢", "Indexing Task Started"),
    "paused": ("⏸", "Indexing Task Paused"),
    "resumed": ("▶️", "Indexing Task Resumed"),
    "cancelled": ("⛔", "Indexing Task Cancelled"),
    "completed": ("✅", "Indexing Task Completed"),
    "stopped": ("🛑", "Indexing Task Stopped (Error)"),
}


async def _log_lifecycle(context, job, kind: str, bot_label: str = "Bot", stats: dict | None = None,
                         source_info: str | None = None, detail: str = ""):
    """Task lifecycle event -> Index Logs TOPIC only (never the Index Logs channel), formatted as `<table striped>`."""
    emoji, title = _LIFECYCLE[kind]
    chat_line = source_info or html.escape(job["title"])
    started_by = user_link_html(job["requester_id"], job["requester_name"]) + (
        f" (<code>{job['requester_id']}</code>)" if job["requester_id"] else ""
    )
    rows = [
        f"<tr><td>📂 <b>Chat</b></td><td>{chat_line}</td></tr>",
        f"<tr><td>🔢 <b>Range</b></td><td><code>{job['start_id']} → {job['end_id']}</code></td></tr>",
        f"<tr><td>⚙️ <b>Mode</b></td><td><code>{html.escape(str(job.get('priority_mode') or 'direct'))}</code></td></tr>",
        f"<tr><td>👤 <b>Started By</b></td><td>{started_by}</td></tr>",
        f"<tr><td>🤖 <b>Bot</b></td><td><code>{html.escape(bot_label)}</code></td></tr>",
        f"<tr><td>🕒 <b>Time</b></td><td>{html.escape(_ist_now_str())}</td></tr>",
    ]
    if stats is not None:
        total = max(1, job["end_id"] - job["start_id"] + 1)
        rows += [
            f"<tr><td>📥 <b>Fetched</b></td><td><code>{stats['fetched']}/{total}</code></td></tr>",
            f"<tr><td>✅ <b>Indexed / Healed</b></td><td><code>{stats['ok']}</code></td></tr>",
            f"<tr><td>♻️ <b>Verified Duplicates</b></td><td><code>{stats['dup']}</code></td></tr>",
            f"<tr><td>🚫 <b>Filtered</b></td><td><code>{stats['filtered']}</code></td></tr>",
            f"<tr><td>🗑 <b>Deleted</b></td><td><code>{stats['deleted']}</code></td></tr>",
            f"<tr><td>⚠️ <b>Errors</b></td><td><code>{stats['skipped']}</code></td></tr>",
        ]
    table_html = "<table striped><tr><th>Field</th><th>Details</th></tr>" + "".join(rows) + "</table>"
    parts = [f"{emoji} <b>{title}</b>", "", table_html]
    if detail:
        parts += ["", f"<i>{html.escape(detail)}</i>"]
    try:
        await send_index_topic_log(context.bot, "\n".join(parts))
    except Exception as exc:
        logger.warning("Index lifecycle log failed: %s", exc)


async def _log_summary(context, job, stats, final_state, bot_label: str = "Bot", source_info: str | None = None):
    fs = str(final_state)
    if fs.startswith("cancelled"):
        kind, detail = "cancelled", ""
    elif fs.startswith("stopped"):
        kind, detail = "stopped", fs
    else:
        kind, detail = "completed", ""
    await _log_lifecycle(context, job, kind, bot_label, stats=stats, source_info=source_info, detail=detail)


async def _send_approval(context, rid, job):
    text = (
        "🔔 <b>Index approval request</b>\n\n"
        f"👤 By: {html.escape(job['requester_name'])} (<code>{job['requester_id']}</code>) — {html.escape(job['requester_role'])}\n"
        f"📂 Chat: <b>{html.escape(job['title'])}</b>\n"
        f"🔢 Messages: <mark>{job['start_id']} → {job['end_id']}</mark>"
    )
    markup = InlineKeyboardMarkup([[
        styled_button("✅ Approve", callback_data=f"idx_apr_{rid}", style="success"),
        styled_button("❌ Reject", callback_data=f"idx_rej_{rid}", style="danger"),
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
        [styled_button("⏩ No Skip (Index All)", callback_data=f"idx_sk_none_{rid}", style="success")],
        [
            styled_button("⏭ Skip Top 10", callback_data=f"idx_sk_top_{rid}", style="primary"),
            styled_button("⏮ Skip Bottom 10", callback_data=f"idx_sk_bot_{rid}", style="primary"),
        ],
        [styled_button("✂️ Custom Range", callback_data=f"idx_sk_custom_{rid}", style="primary")],
        [styled_button("⛔ Cancel", callback_data=f"idx_cancel_{rid}", style="danger")],
    ])
    await _edit_prompt(
        context, job,
        f"🔢 <b>Message Skip &amp; Range Selection</b>\n\n"
        f"📂 <b>Chat:</b> <b>{html.escape(job['title'])}</b>\n"
        f"🔢 <b>Range:</b> <mark>{job['start_id']} → {job['end_id']}</mark>\n\n"
        f"Select an option below to filter messages before starting:",
        markup,
    )


async def _open_prompt(context, prompt_chat, user, chat_ref, start_id, end_id, skip=None, is_channel: bool = False):
    source_chat = None
    probe_token = None
    first_error: Exception | None = None
    try:
        source_chat = await context.bot.get_chat(chat_ref)
    except TelegramError as e:
        first_error = e
        # The bot that received the command may not be in the source chat while a helper bot is:
        # probe every helper bot and let the first one that can read the chat do the indexing.
        for tok in helper_bot_tokens():
            try:
                async with Bot(tok) as hb:
                    source_chat = await hb.get_chat(chat_ref)
                probe_token = tok
                break
            except Exception:
                continue
    if source_chat is None:
        await context.bot.send_message(
            chat_id=prompt_chat,
            text=(
                f"❌ I can't reach that chat ({first_error}). Make sure the Main Bot or a Helper Bot "
                "is a member / admin there."
            ),
        )
        return
    title = source_chat.title or source_chat.username or str(chat_ref)
    cid = source_chat.id

    rid = uuid.uuid4().hex[:8]
    job = {
        "rid": rid,
        "chat_id": cid,
        "title": title,
        "start_id": max(1, start_id),
        "end_id": max(1, end_id),
        "requester_id": user.id if user else 0,
        "requester_name": user.full_name if user else (f"{title} (Channel Admin)" if is_channel else "Anon Admin"),
        "requester_role": get_user_role_db(user.id) if user else "Admin",
        "prompt_chat": prompt_chat,
        "prompt_msg_id": None,
        "approval_chat": None,
        "approval_msg_id": None,
        "is_channel": is_channel,
        "helper_token": probe_token,
        "cancel": False,
        "state": "pending",
    }
    _jobs(context)[rid] = job
    _persist_job(job)

    if skip is not None:
        if skip > 0:
            job["start_id"] = min(job["end_id"], job["start_id"] + skip)
        await _show_priority_menu(context, rid, job)
    else:
        await _show_skip_menu(context, rid, job)


async def _show_priority_menu(context, rid: str, job: dict):
    markup = InlineKeyboardMarkup([
        [styled_button("🚀 Priority Mode (Direct)", callback_data=f"idx_pr_dir_{rid}", style="success")],
        [styled_button("🤝 Helper Pool (Round-Robin)", callback_data=f"idx_pr_hlp_{rid}", style="primary")],
        [styled_button("⛔ Cancel", callback_data=f"idx_cancel_{rid}", style="danger")],
    ])
    await _edit_prompt(
        context, job,
        f"⚡ <b>Delivery &amp; Indexing Priority Setup</b>\n\n"
        f"📂 <b>Chat:</b> <b>{html.escape(job['title'])}</b>\n"
        f"🔢 <b>Range:</b> <mark>{job['start_id']} → {job['end_id']}</mark>\n\n"
        f"Select indexing mode:",
        markup,
    )


async def _edit_prompt(context, job, text, markup=None):
    cid = job["prompt_chat"]
    mid = job.get("prompt_msg_id")
    if mid is None:
        m = await context.bot.send_message(chat_id=cid, text=text, parse_mode="HTML", reply_markup=markup)
        job["prompt_msg_id"] = m.message_id
        if job.get("state") == "pending":
            _persist_job(job)
    else:
        try:
            await context.bot.edit_message_text(
                chat_id=cid, message_id=mid, text=text, parse_mode="HTML", reply_markup=markup
            )
        except TelegramError:
            pass
        if job.get("state") == "pending":
            _persist_job(job)


async def index_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not msg or not chat:
        return

    is_channel = (chat.type == "channel")

    # Deduplicate if both Main Bot and a Helper Bot are admins in the same channel/group
    if chat.type != "private":
        cmd_key = (int(chat.id), int(msg.message_id))
        if cmd_key in _SEEN_CHANNEL_CMDS:
            return
        _SEEN_CHANNEL_CMDS.add(cmd_key)
        if len(_SEEN_CHANNEL_CMDS) > 500:
            _SEEN_CHANNEL_CMDS.clear()

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

    raw_text = msg.text or msg.caption or ""
    links, skip = _parse_args(raw_text.split()[1:])
    try:
        rng = _range_from_links(links)
    except ValueError:
        await msg.reply_text("❌ Both links must be from the same chat.")
        return

    # Capture end_id before deleting the /index command message in channels/groups
    cmd_end_id = max(1, (msg.message_id or 2) - 1)
    if is_channel:
        await _safe_delete(msg)

    if rng:
        await _open_prompt(context, chat.id, user, rng[0], rng[1], rng[2], skip, is_channel=is_channel)
    elif chat.type != "private":
        await _open_prompt(context, chat.id, user, chat.id, 1, cmd_end_id, skip, is_channel=is_channel)
    else:
        context.user_data["idx_flow"] = {"step": "link", "skip": skip}
        await msg.reply_text(
            "📚 <b>Index Setup Wizard</b>\n\n"
            "Send the <b>last message link</b> of the source chat, or forward its last message.\n"
            "To index a range, send <b>two links</b>: first message, then last message.\n\n"
            "• Example: <mark>https://t.me/c/1234567890/150</mark>\n"
            "• Send <code>/index</code> again to restart.",
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
    _forget_job(rid)  # running jobs are not restored after a restart
    context.application.create_task(_run_index(context, rid, job))


async def index_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    # Callback data = idx_<action>_<rid>; actions contain underscores themselves (sk_none, pr_dir, ...),
    # so the 8-hex request id is taken from the END (a plain split("_", 2) glued it onto the action).
    m = re.match(r"^idx_(.+)_([0-9a-f]{8})$", (getattr(q, "data", None) or ""))
    if not m:
        await q.answer()
        return
    action, rid = m.group(1), m.group(2)

    job = _jobs(context).get(rid)
    if not job:
        job = _load_job(rid)  # bot restarted since the prompt was sent
        if job:
            _jobs(context)[rid] = job
    if not job:
        await q.answer("⌛ This request has expired. Send /index again.", show_alert=True)
        return

    user = q.from_user
    role = get_user_role_db(user.id) if user else "Admin"
    full = (role in FULL_ACCESS) or (user and user.id == anon_admin_id())
    partial = role in APPROVAL_ACCESS

    if action == "cancel":
        job["cancel"] = True
        _forget_job(rid)
        await q.answer("Indexing cancelled.")
        await _edit_prompt(context, job, f"⛔ Indexing of <b>{html.escape(job['title'])}</b> was cancelled.")
        if job.get("is_channel"):
            asyncio.create_task(_auto_delete_prompt(context.bot, job, 10))
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
        _persist_job(job)
        if full:
            await q.answer("Starting index...")
            await _edit_prompt(context, job, f"🚀 Starting index in <mark>{mode}</mark> mode...")
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
        _forget_job(rid)
        await q.answer("Rejected.")
        await _edit_prompt(context, job, f"❌ Index request for <b>{html.escape(job['title'])}</b> was rejected.")
        return
