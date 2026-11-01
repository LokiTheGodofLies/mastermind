import json
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
        for col, ddl in (
            ("is_channel", "INTEGER DEFAULT 0"),
            ("helper_token", "TEXT"),
            ("skipped_range", "INTEGER DEFAULT 0"),
            ("stats_json", "TEXT"),
            ("assigned_worker", "TEXT"),
            ("orig_start_id", "INTEGER"),
            ("orig_end_id", "INTEGER"),
            ("excluded_range", "TEXT"),
            ("started_ts", "REAL"),
        ):
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
    "rid", "chat_id", "title", "start_id", "end_id", "current_mid", "priority_mode",
    "requester_id", "requester_name", "prompt_chat", "prompt_msg_id", "state",
    "is_channel", "helper_token", "skipped_range", "stats_json",
    "assigned_worker", "orig_start_id", "orig_end_id", "excluded_range", "started_ts",
)


def _default_stats() -> dict:
    return {
        "fetched": 0,
        "ok": 0,
        "dup": 0,
        "deleted": 0,
        "skipped": 0,
        "filtered": 0,
        "files_found": 0,
        "saved_db": 0,
        "stored_storage": 0,
        "enriched_captions": 0,
        "already_db": 0,
        "already_storage": 0,
        "caption_valid": 0,
        "enrich_failed": 0,
    }


def _ensure_stats(raw: dict | None) -> dict:
    base = _default_stats()
    if isinstance(raw, dict):
        base.update(raw)
    return base


def _persist_job(job: dict) -> None:
    """Saves a pending, queued, running, or paused /index job so its buttons, fleet dashboard,
    and ongoing loop survive restarts / Render redeploys."""
    try:
        _init_index_persistence()
        vals = []
        for col in _JOB_COLS:
            if col == "is_channel":
                v = 1 if job.get("is_channel") else 0
            elif col == "skipped_range":
                v = int(job.get("skipped_range") or 0)
            elif col == "stats_json":
                st = job.get("stats")
                v = json.dumps(st) if isinstance(st, dict) else (job.get("stats_json") or None)
            else:
                v = job.get(col)
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
    _GLOBAL_INDEX_JOBS.pop(rid, None)


def _row_to_job(row) -> dict | None:
    if not row:
        return None
    st = (row["state"] or "pending").lower()
    if st not in ("pending", "queued", "running", "paused"):
        return None
    keys = row.keys()
    job = {k: (row[k] if k in keys else None) for k in _JOB_COLS}
    job["is_channel"] = bool(job.get("is_channel"))
    job["skipped_range"] = int(job.get("skipped_range") or 0)
    raw_stats = job.get("stats_json")
    parsed_stats = None
    if raw_stats:
        try:
            parsed_stats = json.loads(raw_stats)
        except Exception:
            parsed_stats = None
    job["stats"] = _ensure_stats(parsed_stats)
    job.update(
        cancel=False,
        paused=(st == "paused"),
        dm_upload_paused=False,
        approval_chat=None,
        approval_msg_id=None,
        state=st,
    )
    job["requester_role"] = get_user_role_db(job["requester_id"]) if job.get("requester_id") else "Admin"
    return job


def _load_job(rid: str) -> dict | None:
    """Restores a pending, queued, running, or paused job from SQLite."""
    try:
        _init_index_persistence()
        conn = sqlite3.connect(users_db_path())
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM active_index_jobs WHERE rid = ?", (rid,)).fetchone()
        conn.close()
    except Exception:
        return None
    return _row_to_job(row)


def _load_all_fleet_jobs() -> list[dict]:
    """Loads all active (running, paused, queued) jobs across memory and SQLite."""
    by_rid: dict[str, dict] = {}
    try:
        _init_index_persistence()
        conn = sqlite3.connect(users_db_path())
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM active_index_jobs WHERE state IN ('running', 'paused', 'queued')"
        ).fetchall()
        conn.close()
        for r in rows:
            j = _row_to_job(r)
            if j:
                by_rid[j["rid"]] = j
    except Exception:
        pass
    for rid, j in list(_GLOBAL_INDEX_JOBS.items()):
        if j.get("state") in ("running", "paused", "queued") and not j.get("cancel"):
            by_rid[rid] = j
            _GLOBAL_INDEX_JOBS[rid] = j
    state_order = {"running": 0, "paused": 1, "queued": 2}
    return sorted(
        by_rid.values(),
        key=lambda x: (state_order.get(str(x.get("state")), 9), float(x.get("started_ts") or 0.0), str(x.get("rid"))),
    )


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
    creator_id,
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


def _fmt_hhmmss(seconds: float) -> str:
    sec = max(0, int(seconds))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _resolve_admin_dm_id(user) -> int:
    """Resolves the Admin DM chat ID where setup prompts and live progress cards must be sent.
    Never returns a group or channel ID."""
    if user and getattr(user, "id", None) and int(user.id) > 0 and int(user.id) != int(anon_admin_id()):
        return int(user.id)
    try:
        cid = creator_id()
        if cid:
            return int(cid)
    except Exception:
        pass
    aids = sorted(admin_ids())
    return int(aids[0]) if aids else 0


def _busy_helper_tokens(exclude_rid: str | None = None) -> set[str]:
    """Returns the set of helper bot tokens currently assigned to an active (running/paused) batch job."""
    busy: set[str] = set()
    for j in _load_all_fleet_jobs():
        if exclude_rid and j.get("rid") == exclude_rid:
            continue
        if j.get("state") in ("running", "paused") and j.get("helper_token"):
            busy.add(str(j["helper_token"]))
    return busy


def pause_worker_for_dm_upload(bot_identifier: str | int | None) -> list[str]:
    """Temporarily pauses any running batch job on a Helper Bot while it processes a user DM file upload."""
    if not bot_identifier:
        return []
    ident_str = str(bot_identifier).lstrip("@").lower()
    paused_rids: list[str] = []
    for rid, job in list(_GLOBAL_INDEX_JOBS.items()):
        if job.get("state") != "running" or job.get("cancel"):
            continue
        worker_lbl = str(job.get("assigned_worker") or "").lstrip("@").lower()
        tok = str(job.get("helper_token") or "")
        if (ident_str and ident_str == worker_lbl) or (ident_str and tok.startswith(f"{ident_str}:")):
            job["dm_upload_paused"] = True
            paused_rids.append(rid)
    return paused_rids


def resume_worker_after_dm_upload(rids: list[str]) -> None:
    """Automatically resumes the Helper Bot's channel batch loop after finishing a user DM file upload."""
    for rid in rids or []:
        job = _GLOBAL_INDEX_JOBS.get(rid)
        if job:
            job["dm_upload_paused"] = False


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
    """Builds the Live Progress Card (in Admin's DM) matching Screenshot 4 (`1000095651.jpg`) inside `<table striped>`."""
    st = _ensure_stats(stats)
    total = max(1, int(job["end_id"]) - int(job["start_id"]) + 1)
    done = int(st["fetched"])
    pct = min(100, int((done / total) * 100))
    bar_len = 12
    filled = int(bar_len * (pct / 100))
    bar = "█" * filled + "▒" * (bar_len - filled)

    skipped_range = int(job.get("skipped_range", 0) or 0)
    skipped_total = skipped_range + int(st.get("skipped", 0) or 0)
    excl_desc = str(job.get("excluded_range") or "")
    if not excl_desc:
        excl_desc = f"{skipped_range} msgs skipped" if skipped_range > 0 else "None (0 msgs skipped)"
    elif "skipped" not in excl_desc:
        excl_desc = f"{excl_desc} ({skipped_range} msgs skipped)"

    orig_s = int(job.get("orig_start_id") or job["start_id"])
    orig_e = int(job.get("orig_end_id") or job["end_id"])
    worker_lbl = str(job.get("assigned_worker") or job.get("priority_mode") or "direct")
    batch_sz = max(1, int(max_index_batch() or 25))
    rem_total = max(0, total - done)
    pending_in_batch = min(rem_total, (batch_sz - (done % batch_sz)) % batch_sz or (batch_sz if rem_total > 0 else 0))

    started_ts = float(job.get("started_ts") or time.time())
    elapsed_s = max(0.0, time.time() - started_ts)
    if done > 0 and rem_total > 0:
        eta_s = (elapsed_s / done) * rem_total
        eta_str = f"~{_fmt_hhmmss(eta_s)}"
    elif rem_total == 0:
        eta_str = "00:00:00"
    else:
        eta_str = "Calculating..."

    p_low = str(phase).lower()
    if "pause" in p_low:
        hdr = "⏸ <b>INDEXING PAUSED</b>"
    elif "cancel" in p_low:
        hdr = "⛔ <b>INDEXING CANCELLED</b>"
    elif "complete" in p_low:
        hdr = "✅ <b>INDEXING COMPLETED</b>"
    else:
        hdr = "📚 <b>INDEXING IN PROGRESS</b>"

    main_rows = [
        f"<tr><td>📂 <b>Target</b></td><td>{html.escape(str(job.get('title') or 'Chat'))[:26]} (<code>{job.get('chat_id')}</code>)</td></tr>",
        f"<tr><td>🤖 <b>Assigned Worker</b></td><td><code>{html.escape(worker_lbl)}</code></td></tr>",
        f"<tr><td>🎯 <b>Scanning Range</b></td><td><code>{orig_s} → {orig_e}</code></td></tr>",
        f"<tr><td>✂️ <b>Excluded Range</b></td><td><code>{html.escape(excl_desc)}</code></td></tr>",
        f"<tr><td>⚙️ <b>Phase</b></td><td><code>{html.escape(str(phase))}</code></td></tr>",
        f"<tr><td>📊 <b>Progress</b></td><td><code>[{bar}] {pct}%</code></td></tr>",
        f"<tr><td>🔢 <b>Messages Scanned</b></td><td><code>{done} / {total}</code></td></tr>",
        f"<tr><td>📦 <b>Total Files Found</b></td><td><code>{st['files_found']}</code></td></tr>",
        f"<tr><td>💾 <b>Saved to Database</b></td><td><code>{st['saved_db']}</code></td></tr>",
        f"<tr><td>📥 <b>Stored in Storage</b></td><td><code>{st['stored_storage']}</code></td></tr>",
        f"<tr><td>✨ <b>Enriched Captions</b></td><td><code>{st['enriched_captions']}</code></td></tr>",
        f"<tr><td>🏁 <b>Total Files Indexed</b></td><td><code>{st['ok']}</code></td></tr>",
        f"<tr><td>⏳ <b>Pending in Batch</b></td><td><code>{pending_in_batch}</code></td></tr>",
    ]

    breakdown_rows = [
        f"<tr><td>• <b>Already in Database</b></td><td><code>{st['already_db']}</code></td></tr>",
        f"<tr><td>• <b>Already in Storage</b></td><td><code>{st['already_storage']}</code></td></tr>",
        f"<tr><td>• <b>Caption Already Valid</b></td><td><code>{st['caption_valid']}</code></td></tr>",
        f"<tr><td>• <b>Enrichment Failed (No Match)</b></td><td><code>{st['enrich_failed']}</code></td></tr>",
        f"<tr><td>♻️ <b>Duplicates</b></td><td><code>{st['dup']}</code></td></tr>",
        f"<tr><td>⏭ <b>Skipped</b></td><td><code>{skipped_total}</code></td></tr>",
        f"<tr><td>🚫 <b>Filtered</b></td><td><code>{st['filtered']}</code></td></tr>",
        f"<tr><td>🗑 <b>Deleted</b></td><td><code>{st['deleted']}</code></td></tr>",
        f"<tr><td>⚠️ <b>Errors</b></td><td><code>{st['skipped']}</code></td></tr>",
        f"<tr><td>⏱ <b>Time Elapsed</b></td><td><code>{_fmt_hhmmss(elapsed_s)}</code></td></tr>",
        f"<tr><td>⌛ <b>Estimated ETA</b></td><td><code>{eta_str}</code></td></tr>",
    ]

    return (
        f"{hdr}\n\n"
        "<table striped><tr><th>Metric</th><th>Value</th></tr>"
        + "".join(main_rows)
        + "</table>\n\n"
        "⏭ <b>Granular Breakdown &amp; Timing</b>\n"
        "<table striped><tr><th>Stage / Counter</th><th>Value</th></tr>"
        + "".join(breakdown_rows)
        + "</table>"
    )


def _running_markup(rid: str, paused: bool = False) -> InlineKeyboardMarkup:
    toggle_btn = (
        styled_button("▶️ Resume", callback_data=f"idx_resume_{rid}", style="success")
        if paused
        else styled_button("⏸ Pause", callback_data=f"idx_pause_{rid}", style="success")
    )
    return InlineKeyboardMarkup([
        [
            toggle_btn,
            styled_button("⛔ Cancel Indexing", callback_data=f"idx_cancel_{rid}", style="danger"),
        ],
        [
            styled_button("📋 Ongoing Tasks", callback_data="idx_ongoing_menu", style="success"),
        ],
    ])


def _cancel_markup(rid):
    return _running_markup(rid, paused=False)


def build_ongoing_tasks_dashboard() -> tuple[str, InlineKeyboardMarkup]:
    """Builds the `📋 FLEET INDEXING TASKS` dashboard (`1000095652.jpg`, `1000095654.jpg`) with `<table striped>`
    and dynamic per-task Pause / Resume / Run Queued / Cancel + Refresh buttons."""
    tasks = _load_all_fleet_jobs()
    sections = ["📋 <b>FLEET INDEXING TASKS</b>"]
    btn_rows: list[list[InlineKeyboardButton]] = []

    if not tasks:
        idle_rows = []
        toks = helper_bot_tokens()
        if toks:
            for idx, _ in enumerate(toks, 1):
                idle_rows.append(f"<tr><td>🤖 <b>Helper Worker #{idx}</b></td><td>🟢 Idle &amp; Ready</td></tr>")
        else:
            idle_rows.append("<tr><td>🤖 <b>Main / Helper Fleet</b></td><td>🟢 Idle &amp; Ready</td></tr>")
        sections.append(
            "\n<table striped><tr><th>Fleet Worker</th><th>Status</th></tr>"
            + "".join(idle_rows)
            + "</table>\n\n"
            "<i>No active or queued indexing tasks right now. Send <code>/index</code> in any channel or tap ➕ New Index Task below!</i>"
        )
    else:
        q_pos = 0
        action_pair: list[InlineKeyboardButton] = []
        for idx, t in enumerate(tasks, 1):
            rid = t["rid"]
            st = _ensure_stats(t.get("stats"))
            total = max(1, int(t["end_id"]) - int(t["start_id"]) + 1)
            done = int(st["fetched"])
            pct = min(100, int((done / total) * 100))
            bar_len = 10
            filled = int(bar_len * (pct / 100))
            bar = "█" * filled + "▒" * (bar_len - filled)

            state_raw = str(t.get("state") or "running").lower()
            if state_raw == "queued":
                q_pos += 1
                icon = "⏳"
                state_lbl = f"⏳ Queued (Position #{q_pos})"
                worker_lbl = "⏳ Waiting for a bot to be free"
                ctrl_btn = styled_button(f"▶️ Run Queued #{idx}", callback_data=f"idx_fl_prio_{rid}", style="success")
            elif state_raw == "paused" or t.get("paused"):
                icon = "🟡"
                state_lbl = "🟡 Paused"
                worker_lbl = str(t.get("assigned_worker") or "Helper Bot")
                ctrl_btn = styled_button(f"▶️ Resume #{idx}", callback_data=f"idx_fl_resume_{rid}", style="success")
            elif t.get("dm_upload_paused"):
                icon = "🟡"
                state_lbl = "🟡 Paused (User DM upload in progress)"
                worker_lbl = str(t.get("assigned_worker") or "Helper Bot")
                ctrl_btn = styled_button(f"⏸ Pause #{idx}", callback_data=f"idx_fl_pause_{rid}", style="success")
            else:
                icon = "🟢"
                state_lbl = "🟢 Active (Running)"
                worker_lbl = str(t.get("assigned_worker") or "Helper Bot")
                ctrl_btn = styled_button(f"⏸ Pause #{idx}", callback_data=f"idx_fl_pause_{rid}", style="success")

            cid = t.get("chat_id")
            cid_str = str(cid or "")
            link_str = f"https://t.me/c/{cid_str[4:]}/{t['start_id']}" if cid_str.startswith("-100") else "Private / No Link"
            req_name = html.escape(str(t.get("requester_name") or "Admin"))
            req_id = t.get("requester_id") or 0

            t_table = (
                "<table striped>"
                f"<tr><th>{icon} [Task #{idx}]</th><th>{html.escape(str(t.get('title') or 'Chat'))[:28]}</th></tr>"
                f"<tr><td>🎯 <b>Target</b></td><td><code>{cid}</code> ({link_str})</td></tr>"
                f"<tr><td>🤖 <b>Assigned Bot</b></td><td><code>{html.escape(worker_lbl)}</code></td></tr>"
                f"<tr><td>👤 <b>Initiated By</b></td><td>{req_name} (<code>{req_id}</code>)</td></tr>"
                f"<tr><td>📊 <b>Progress</b></td><td><code>[{bar}] {pct}% ({done}/{total})</code></td></tr>"
                f"<tr><td>⚙️ <b>State</b></td><td>{state_lbl}</td></tr>"
                "</table>"
            )
            sections.append(f"\n{t_table}")

            action_pair.append(ctrl_btn)
            action_pair.append(styled_button(f"⛔ Cancel #{idx}", callback_data=f"idx_fl_cancel_{rid}", style="danger"))
            btn_rows.append(action_pair)
            action_pair = []

    btn_rows.append([
        styled_button("🔄 Refresh Menu", callback_data="idx_ongoing_menu", style="success"),
        styled_button("➕ New Index Task", callback_data="idx_new_wizard", style="danger"),
    ])
    return "\n".join(sections), InlineKeyboardMarkup(btn_rows)


async def ongoing_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler for `/ongoing`, `/tasks`, `/indextasks` — opens the Fleet Indexing Tasks Dashboard in DM."""
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    role = get_user_role_db(user.id)
    if role not in INDEX_COMMAND_ACCESS:
        await msg.reply_text("⛔ Only Administrators and the Creator can access the Ongoing Tasks Dashboard.")
        return
    text, markup = build_ongoing_tasks_dashboard()
    await msg.reply_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


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
    """Deletes temporary messages if needed."""
    await asyncio.sleep(max(1, delay_s))
    cid = job.get("prompt_chat")
    mid = job.get("prompt_msg_id")
    if cid and mid and int(cid) < 0:
        try:
            await bot.delete_message(chat_id=cid, message_id=mid)
        except Exception:
            pass


async def _build_helper_pool_bots(tokens: list[str] | None = None) -> list[tuple[Bot, str]]:
    """Initializes reachable helper Bot instances for indexing."""
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


async def _report_index_permission_failure(bot, chat_ref, error_reason: str, admin_dm_id: int):
    """Dispatches an immediate error report to the Error Logs topic in the Logs Group + alerts the Admin in DM."""
    log_gid = logger_group_id()
    err_topic = log_topic("ERROR")
    err_card = (
        "🚨 <b>Index Permission Check Failed</b>\n\n"
        "<table striped>"
        "<tr><th>Field</th><th>Details</th></tr>"
        f"<tr><td>📂 <b>Target Chat</b></td><td><code>{html.escape(str(chat_ref))}</code></td></tr>"
        f"<tr><td>👤 <b>Admin ID</b></td><td><code>{admin_dm_id}</code></td></tr>"
        f"<tr><td>⚠️ <b>Reason</b></td><td><code>{html.escape(str(error_reason)[:80])}</code></td></tr>"
        "<tr><td>🤖 <b>Bot Status</b></td><td>❌ Missing Access / Admin Rights</td></tr>"
        "</table>"
    )
    if log_gid:
        try:
            kwargs = {"chat_id": int(log_gid), "text": err_card, "parse_mode": "HTML"}
            if err_topic:
                kwargs["message_thread_id"] = int(err_topic)
            await bot.send_message(**kwargs)
        except Exception:
            pass


async def _start_next_queued_job(context) -> None:
    """Checks if any queued job can now be assigned to a newly freed Helper Bot."""
    for j in _load_all_fleet_jobs():
        if j.get("state") == "queued" and not j.get("cancel"):
            rid = j["rid"]
            _GLOBAL_INDEX_JOBS[rid] = j
            _begin(context, rid, j)
            break


async def _run_index(context, rid, job):
    bot = context.bot
    storage = storage_group_id()
    batch = max_index_batch()
    sleep_s = index_sleep_seconds()

    stats = _ensure_stats(job.get("stats"))
    job["stats"] = stats
    if not job.get("started_ts"):
        job["started_ts"] = time.time()
    final_state = "completed ✅"

    if not storage:
        await _edit_prompt(context, job, "❌ PUBLIC_/TESTING_STORAGE_GROUP_ID is not set. Cannot index.")
        job["state"] = "done"
        _forget_job(rid)
        return

    log_group_id = logger_group_id()
    error_log_topic_id = log_topic("ERROR")

    # Determine active bot label and Assigned Helper Worker
    default_bot_label = f"@{bot.username}" if getattr(bot, "username", None) else "Bot"
    if default_bot_label == "Bot":
        try:
            me = await bot.get_me()
            if me and me.username:
                default_bot_label = f"@{me.username}"
        except Exception:
            pass

    helper_pool: list[tuple[Bot, str]] = []
    only_helper = bool(job.get("helper_token"))
    if only_helper:
        helper_pool = await _build_helper_pool_bots([job["helper_token"]])
        if not helper_pool and getattr(bot, "_post", None) is None:
            await _edit_prompt(context, job, "❌ The helper bot assigned to this chat is unreachable. Try again later.")
            job["state"] = "done"
            _forget_job(rid)
            return
    elif job.get("priority_mode") == "helpers":
        helper_pool = await _build_helper_pool_bots()

    # If a dedicated Helper Worker is in helper_pool, use that Worker Bot for DM progress updates!
    worker_bot = helper_pool[0][0] if helper_pool else bot
    worker_label = helper_pool[0][1] if helper_pool else (job.get("assigned_worker") or default_bot_label)
    job["assigned_worker"] = worker_label
    job["_worker_bot_inst"] = worker_bot

    # Resolve safe source link using worker_bot
    source_info = await _get_safe_source_link(worker_bot, job["chat_id"], job["title"])

    start_mid = max(int(job["start_id"]), int(job.get("current_mid") or job["start_id"]))
    is_resumed_after_restart = start_mid > int(job["start_id"]) and stats["fetched"] > 0

    await _log_lifecycle(
        context,
        job,
        "resumed" if is_resumed_after_restart else "started",
        worker_label,
        stats=stats if is_resumed_after_restart else None,
        source_info=source_info,
    )

    # Immediately show the ongoing progress table & controls in Admin's DM before iterating
    initial_phase = "paused ⏸" if job.get("paused") else "running"
    await _edit_prompt(
        context,
        job,
        _status_text(job, stats, initial_phase),
        _running_markup(rid, bool(job.get("paused"))),
    )
    last_ui_update = time.monotonic()

    try:
        for mid in range(start_mid, job["end_id"] + 1):
            while (job.get("paused") or job.get("dm_upload_paused")) and not job.get("cancel"):
                await asyncio.sleep(0.5)

            if job.get("cancel"):
                final_state = "cancelled ⛔"
                break

            job["current_mid"] = mid
            stats["fetched"] += 1
            active_bot = worker_bot
            active_bot_label = worker_label
            if len(helper_pool) > 1:
                active_bot, active_bot_label = helper_pool[(stats["fetched"] - 1) % len(helper_pool)]
                job["assigned_worker"] = active_bot_label

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
                        stats["files_found"] += 1
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

                        if res.get("was_in_db"):
                            stats["already_db"] += 1
                        elif res.get("db_ok"):
                            stats["saved_db"] += 1

                        if res.get("was_in_storage"):
                            stats["already_storage"] += 1
                        else:
                            stats["stored_storage"] += 1

                        if res.get("already_enriched"):
                            stats["caption_valid"] += 1
                        elif res.get("is_success_enrichment"):
                            stats["enriched_captions"] += 1
                        else:
                            stats["enrich_failed"] += 1

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
                                        style="success",
                                    )
                                ])
                                err_table = (
                                    "<table striped>"
                                    "<tr><th>Field</th><th>Details</th></tr>"
                                    f"<tr><td>📁 <b>File</b></td><td><code>{html.escape(info['file_name'])}</code></td></tr>"
                                    f"<tr><td>🔑 <b>Unique ID</b></td><td><code>{html.escape(info['file_unique_id'])}</code></td></tr>"
                                    f"<tr><td>🤖 <b>Indexed By</b></td><td><code>{html.escape(active_bot_label)}</code></td></tr>"
                                    f"<tr><td>🌐 <b>Source</b></td><td>{source_info}</td></tr>"
                                    f"<tr><td>1. 🗄 <b>Database</b></td><td>{res['db_badge']}</td></tr>"
                                    f"<tr><td>2. 📦 <b>Storage</b></td><td>{res['storage_badge']}</td></tr>"
                                    f"<tr><td>3. 📝 <b>Caption</b></td><td>{res['caption_badge']}</td></tr>"
                                    "</table>"
                                )
                                err_text = (
                                    f"⚠️ <b>Caption Enrichment Failed (&lt;2 Parameters Matched)</b>\n\n"
                                    f"{err_table}\n\n"
                                    f"<i>Admins please edit the storage message caption via ✏️ Edit Caption.</i>\n\n"
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

            job["current_mid"] = mid + 1
            job["stats"] = stats
            _persist_job(job)

            now_mono = time.monotonic()
            if stats["fetched"] % batch == 0 and mid < job["end_id"]:
                await _edit_prompt(
                    context, job,
                    _status_text(job, stats, f"sleeping ({sleep_s}s)"),
                    _running_markup(rid, bool(job.get("paused"))),
                )
                last_ui_update = time.monotonic()
                await asyncio.sleep(sleep_s)
            elif (stats["fetched"] == 1 or stats["fetched"] % 5 == 0 or (now_mono - last_ui_update) >= 4.0) and mid < job["end_id"]:
                cur_phase = (
                    "paused (DM upload) ⏸"
                    if job.get("dm_upload_paused")
                    else ("paused ⏸" if job.get("paused") else f"running (#{mid})")
                )
                await _edit_prompt(
                    context, job,
                    _status_text(job, stats, cur_phase),
                    _running_markup(rid, bool(job.get("paused"))),
                )
                last_ui_update = time.monotonic()
    except Exception as e:
        logger.exception("[INDEX] job crashed")
        final_state = f"stopped: {e}"
    finally:
        job.pop("_worker_bot_inst", None)
        for hb, _ in helper_pool:
            try:
                await hb.shutdown()
            except Exception:
                pass

    job["state"] = "done"
    _forget_job(rid)
    done_kb = InlineKeyboardMarkup([[styled_button("📋 Ongoing Tasks", callback_data="idx_ongoing_menu", style="success")]])
    await _edit_prompt(context, job, _status_text(job, stats, final_state), done_kb)
    await _log_summary(context, job, stats, final_state, worker_label, source_info=source_info)
    await _start_next_queued_job(context)


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
        f"<tr><td>🤖 <b>Assigned Worker</b></td><td><code>{html.escape(str(job.get('assigned_worker') or bot_label))}</code></td></tr>",
        f"<tr><td>🕒 <b>Time</b></td><td>{html.escape(_ist_now_str())}</td></tr>",
    ]
    if stats is not None:
        st = _ensure_stats(stats)
        total = max(1, job["end_id"] - job["start_id"] + 1)
        skipped_total = int(job.get("skipped_range", 0) or 0) + int(st.get("skipped", 0) or 0)
        rows += [
            f"<tr><td>📥 <b>Fetched</b></td><td><code>{st['fetched']}/{total}</code></td></tr>",
            f"<tr><td>📦 <b>Files Found</b></td><td><code>{st['files_found']}</code></td></tr>",
            f"<tr><td>✅ <b>Indexed / Healed</b></td><td><code>{st['ok']}</code></td></tr>",
            f"<tr><td>♻️ <b>Verified Duplicates</b></td><td><code>{st['dup']}</code></td></tr>",
            f"<tr><td>⏭ <b>Skipped</b></td><td><code>{skipped_total}</code></td></tr>",
            f"<tr><td>🚫 <b>Filtered</b></td><td><code>{st['filtered']}</code></td></tr>",
            f"<tr><td>🗑 <b>Deleted</b></td><td><code>{st['deleted']}</code></td></tr>",
            f"<tr><td>⚠️ <b>Errors</b></td><td><code>{st['skipped']}</code></td></tr>",
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
        "🔔 <b>Index Approval Request</b>\n\n"
        "<table striped>"
        "<tr><th>Field</th><th>Details</th></tr>"
        f"<tr><td>👤 <b>Requested By</b></td><td>{html.escape(job['requester_name'])} (<code>{job['requester_id']}</code>)</td></tr>"
        f"<tr><td>🛡 <b>Role</b></td><td><code>{html.escape(job['requester_role'])}</code></td></tr>"
        f"<tr><td>📂 <b>Chat</b></td><td><b>{html.escape(job['title'])}</b></td></tr>"
        f"<tr><td>🔢 <b>Messages</b></td><td><code>{job['start_id']} → {job['end_id']}</code></td></tr>"
        "</table>"
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
    total_msgs = max(1, job["end_id"] - job["start_id"] + 1)
    worker_lbl = str(job.get("assigned_worker") or "Auto-Assign Idle Helper")
    markup = InlineKeyboardMarkup([
        [styled_button("⏩ No Skip (Index All)", callback_data=f"idx_sk_none_{rid}", style="success")],
        [
            styled_button("⏭ Skip Top 10", callback_data=f"idx_sk_top_{rid}", style="success"),
            styled_button("⏮ Skip Bottom 10", callback_data=f"idx_sk_bot_{rid}", style="danger"),
        ],
        [
            styled_button("✂️ Custom Range", callback_data=f"idx_sk_custom_{rid}", style="success"),
            styled_button("📋 Ongoing Tasks", callback_data="idx_ongoing_menu", style="success"),
        ],
        [styled_button("⛔ Cancel", callback_data=f"idx_cancel_{rid}", style="danger")],
    ])
    await _edit_prompt(
        context, job,
        f"🔢 <b>Message Skip &amp; Range Selection</b>\n\n"
        f"<table striped>"
        f"<tr><th>Field</th><th>Value</th></tr>"
        f"<tr><td>📂 <b>Target</b></td><td>{html.escape(job['title'])[:32]} (<code>{job['chat_id']}</code>)</td></tr>"
        f"<tr><td>🤖 <b>Assigned Worker</b></td><td><code>{html.escape(worker_lbl)}</code></td></tr>"
        f"<tr><td>🎯 <b>Scanning Range</b></td><td><code>{job['start_id']} → {job['end_id']}</code></td></tr>"
        f"<tr><td>📊 <b>Total Messages</b></td><td><code>{total_msgs}</code></td></tr>"
        f"</table>\n\n"
        f"Select an option below to filter messages before starting:",
        markup,
    )


async def _open_prompt(context, prompt_chat, user, chat_ref, start_id, end_id, skip=None, is_channel: bool = False):
    """Probes source chat permissions across Helper Bot Fleet, assigns an idle Helper Bot worker,
    and ALWAYS sends the setup prompt to the Admin's DM (never inside the source channel/group)."""
    admin_dm_id = _resolve_admin_dm_id(user) if (is_channel or int(prompt_chat or 0) < 0) else int(prompt_chat)
    if admin_dm_id <= 0:
        admin_dm_id = _resolve_admin_dm_id(user)

    source_chat = None
    probe_token = None
    probe_uname = None
    first_error: Exception | None = None
    busy_tokens = _busy_helper_tokens()

    # 1. Prefer an IDLE Helper Bot that can access the source chat (so the Helper Bot DM handles the task)
    all_helper_toks = helper_bot_tokens()
    ordered_toks = [t for t in all_helper_toks if t not in busy_tokens] + [t for t in all_helper_toks if t in busy_tokens]
    for tok in ordered_toks:
        try:
            async with Bot(tok) as hb:
                sc_chat = await hb.get_chat(chat_ref)
                me = await hb.get_me()
            source_chat = sc_chat
            probe_token = tok
            probe_uname = f"@{me.username}" if me.username else (me.first_name or "HelperBot")
            break
        except Exception as e:
            if first_error is None:
                first_error = e
            continue

    # 2. Fallback to context.bot (e.g. if context.bot is already the Helper Bot or in offline tests)
    if source_chat is None:
        try:
            source_chat = await context.bot.get_chat(chat_ref)
            probe_uname = f"@{context.bot.username}" if getattr(context.bot, "username", None) else "Bot"
        except TelegramError as e:
            if first_error is None:
                first_error = e

    if source_chat is None:
        await _report_index_permission_failure(context.bot, chat_ref, str(first_error), admin_dm_id)
        try:
            await context.bot.send_message(
                chat_id=admin_dm_id,
                text=(
                    f"❌ <b>Index Permission Check Failed</b>\n\n"
                    f"Could not access <code>{html.escape(str(chat_ref))}</code> ({html.escape(str(first_error))}).\n"
                    "Make sure a Helper Bot is a member / administrator in that chat."
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    title = source_chat.title or source_chat.username or str(chat_ref)
    cid = source_chat.id

    rid = uuid.uuid4().hex[:8]
    orig_s = max(1, start_id)
    orig_e = max(1, end_id)
    s_id = orig_s
    e_id = orig_e
    skipped_cnt = 0
    excl_str = "None (0 msgs skipped)"
    if skip is not None and skip > 0:
        new_start = min(e_id, s_id + skip)
        skipped_cnt = max(0, new_start - s_id)
        if skipped_cnt > 0:
            excl_str = f"{s_id} → {new_start - 1} ({skipped_cnt} msgs skipped)"
        s_id = new_start

    job = {
        "rid": rid,
        "chat_id": cid,
        "title": title,
        "start_id": s_id,
        "end_id": e_id,
        "orig_start_id": orig_s,
        "orig_end_id": orig_e,
        "excluded_range": excl_str,
        "current_mid": s_id,
        "skipped_range": skipped_cnt,
        "requester_id": user.id if (user and getattr(user, "id", 0) > 0) else admin_dm_id,
        "requester_name": user.full_name if user else (f"{title} (Channel Admin)" if is_channel else "Admin"),
        "requester_role": get_user_role_db(user.id) if user else "Admin",
        # ALWAYS send setup prompts and live progress cards to Admin's DM (never the source channel!)
        "prompt_chat": admin_dm_id,
        "prompt_msg_id": None,
        "approval_chat": None,
        "approval_msg_id": None,
        "is_channel": is_channel,
        "helper_token": probe_token,
        "assigned_worker": probe_uname or "HelperBot",
        "cancel": False,
        "paused": False,
        "dm_upload_paused": False,
        "state": "pending",
        "stats": _default_stats(),
    }
    _jobs(context)[rid] = job
    _persist_job(job)

    if skip is not None:
        await _show_priority_menu(context, rid, job)
    else:
        await _show_skip_menu(context, rid, job)


async def _show_priority_menu(context, rid: str, job: dict):
    total_msgs = max(1, job["end_id"] - job["start_id"] + 1)
    skipped_cnt = int(job.get("skipped_range", 0) or 0)
    excl_str = str(job.get("excluded_range") or (f"{skipped_cnt} msgs skipped" if skipped_cnt else "None (0 msgs skipped)"))
    worker_lbl = str(job.get("assigned_worker") or "HelperBot")
    markup = InlineKeyboardMarkup([
        [styled_button("🚀 Priority Mode (Direct)", callback_data=f"idx_pr_dir_{rid}", style="success")],
        [styled_button("🤝 Helper Pool (Round-Robin)", callback_data=f"idx_pr_hlp_{rid}", style="success")],
        [styled_button("📋 Ongoing Tasks", callback_data="idx_ongoing_menu", style="success")],
        [styled_button("⛔ Cancel", callback_data=f"idx_cancel_{rid}", style="danger")],
    ])
    await _edit_prompt(
        context, job,
        f"⚡ <b>Delivery &amp; Indexing Priority Setup</b>\n\n"
        f"<table striped>"
        f"<tr><th>Field</th><th>Value</th></tr>"
        f"<tr><td>📂 <b>Target</b></td><td>{html.escape(job['title'])[:32]} (<code>{job['chat_id']}</code>)</td></tr>"
        f"<tr><td>🤖 <b>Assigned Worker</b></td><td><code>{html.escape(worker_lbl)}</code></td></tr>"
        f"<tr><td>🎯 <b>Scanning Range</b></td><td><code>{job['start_id']} → {job['end_id']}</code></td></tr>"
        f"<tr><td>✂️ <b>Excluded Range</b></td><td><code>{html.escape(excl_str)}</code></td></tr>"
        f"<tr><td>📊 <b>Messages Queued</b></td><td><code>{total_msgs}</code></td></tr>"
        f"</table>\n\n"
        f"Select indexing mode:",
        markup,
    )


async def _edit_prompt(context, job, text, markup=None):
    """Sends or edits the setup/progress message in the Admin's DM using the assigned Helper Bot
    (falling back to context.bot if the Admin has not started that Helper Bot in DM yet)."""
    cid = int(job["prompt_chat"])
    if cid < 0:
        # Safety guard: never post index prompts or progress cards inside a group or channel
        cid = _resolve_admin_dm_id(None)
        job["prompt_chat"] = cid

    mid = job.get("prompt_msg_id")
    worker_inst = job.get("_worker_bot_inst")
    helper_tok = job.get("helper_token")

    # Try sending/editing via the assigned Helper Bot DM first so the progress lives in the Helper Bot's DM
    if worker_inst is not None:
        try:
            if mid is None:
                m = await worker_inst.send_message(chat_id=cid, text=text, parse_mode="HTML", reply_markup=markup)
                job["prompt_msg_id"] = m.message_id
            else:
                await worker_inst.edit_message_text(
                    chat_id=cid, message_id=mid, text=text, parse_mode="HTML", reply_markup=markup
                )
            if job.get("state") in ("pending", "queued", "running", "paused"):
                _persist_job(job)
            return
        except Exception:
            pass
    elif helper_tok and getattr(context.bot, "token", None) != helper_tok:
        try:
            async with Bot(helper_tok) as hb:
                if mid is None:
                    m = await hb.send_message(chat_id=cid, text=text, parse_mode="HTML", reply_markup=markup)
                    job["prompt_msg_id"] = m.message_id
                else:
                    await hb.edit_message_text(
                        chat_id=cid, message_id=mid, text=text, parse_mode="HTML", reply_markup=markup
                    )
            if job.get("state") in ("pending", "queued", "running", "paused"):
                _persist_job(job)
            return
        except Exception:
            pass

    # Fallback to context.bot in Admin's DM
    if mid is None:
        m = await context.bot.send_message(chat_id=cid, text=text, parse_mode="HTML", reply_markup=markup)
        job["prompt_msg_id"] = m.message_id
        if job.get("state") in ("pending", "queued", "running", "paused"):
            _persist_job(job)
    else:
        try:
            await context.bot.edit_message_text(
                chat_id=cid, message_id=mid, text=text, parse_mode="HTML", reply_markup=markup
            )
        except TelegramError:
            try:
                m = await context.bot.send_message(chat_id=cid, text=text, parse_mode="HTML", reply_markup=markup)
                job["prompt_msg_id"] = m.message_id
            except Exception:
                pass
        if job.get("state") in ("pending", "queued", "running", "paused"):
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
    if chat.type != "private":
        await _safe_delete(msg)

    admin_dm_id = _resolve_admin_dm_id(user) if chat.type != "private" else int(chat.id)

    if rng:
        await _open_prompt(context, admin_dm_id, user, rng[0], rng[1], rng[2], skip, is_channel=is_channel)
    elif chat.type != "private":
        await _open_prompt(context, admin_dm_id, user, chat.id, 1, cmd_end_id, skip, is_channel=is_channel)
    else:
        context.user_data["idx_flow"] = {"step": "link", "skip": skip}
        active_cnt = len(_load_all_fleet_jobs())
        wiz_kb = InlineKeyboardMarkup([
            [styled_button(f"📋 Ongoing Tasks ({active_cnt})", callback_data="idx_ongoing_menu", style="success")],
        ])
        await msg.reply_text(
            "📚 <b>Index Setup Wizard</b>\n\n"
            "<table striped>"
            "<tr><th>Option</th><th>How to Use</th></tr>"
            "<tr><td>🔗 <b>Single Link</b></td><td>Send last message link (indexes from #1)</td></tr>"
            "<tr><td>🔢 <b>Custom Range</b></td><td>Send first link and last link together</td></tr>"
            "<tr><td>📨 <b>Forward</b></td><td>Forward the last message from the source chat</td></tr>"
            "<tr><td>📢 <b>In-Channel</b></td><td>Send <code>/index</code> inside the source channel</td></tr>"
            "</table>\n\n"
            "• Example: <mark>https://t.me/c/1234567890/150</mark>\n"
            "• Tap <b>📋 Ongoing Tasks</b> below to inspect or control running fleet tasks.",
            parse_mode="HTML",
            reply_markup=wiz_kb,
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


def _begin(context, rid, job, force_run: bool = False):
    """Assigns the job to an idle Helper Bot (1 batch job per Helper Bot) or places it in the
    Pending Index Queue (`state='queued'`) if all Helper Bots are currently busy."""
    all_toks = helper_bot_tokens()
    busy = _busy_helper_tokens(exclude_rid=rid)

    if not force_run and all_toks:
        cur_tok = job.get("helper_token")
        if cur_tok and cur_tok in busy:
            idle_toks = [t for t in all_toks if t not in busy]
            if idle_toks:
                job["helper_token"] = idle_toks[0]
            else:
                # All helper bots are busy -> place in Pending Index Queue!
                job["state"] = "queued"
                job["assigned_worker"] = "⏳ Waiting for a bot to be free"
                job["started_ts"] = time.time()
                _persist_job(job)
                q_tasks = [t for t in _load_all_fleet_jobs() if t.get("state") == "queued"]
                q_pos = next((i for i, t in enumerate(q_tasks, 1) if t["rid"] == rid), len(q_tasks) or 1)
                q_kb = InlineKeyboardMarkup([
                    [
                        styled_button("▶️ Run Now", callback_data=f"idx_fl_prio_{rid}", style="success"),
                        styled_button("⛔ Cancel", callback_data=f"idx_cancel_{rid}", style="danger"),
                    ],
                    [styled_button("📋 Ongoing Tasks", callback_data="idx_ongoing_menu", style="success")],
                ])
                q_text = (
                    "⏳ <b>Added to Pending Index Queue</b>\n\n"
                    "<table striped>"
                    "<tr><th>Field</th><th>Value</th></tr>"
                    f"<tr><td>📂 <b>Target</b></td><td>{html.escape(job['title'])[:32]} (<code>{job['chat_id']}</code>)</td></tr>"
                    f"<tr><td>🎯 <b>Scanning Range</b></td><td><code>{job['start_id']} → {job['end_id']}</code></td></tr>"
                    "<tr><td>🤖 <b>Assigned Bot</b></td><td>⏳ Waiting for a bot to be free</td></tr>"
                    f"<tr><td>⚙️ <b>State</b></td><td>⏳ Queued (Position #{q_pos})</td></tr>"
                    "</table>"
                )
                context.application.create_task(_edit_prompt(context, job, q_text, q_kb))
                return

    job["state"] = "running"
    job.setdefault("paused", False)
    job.setdefault("dm_upload_paused", False)
    job.setdefault("current_mid", job["start_id"])
    job.setdefault("started_ts", time.time())
    _persist_job(job)
    context.application.create_task(_run_index(context, rid, job))


async def resume_active_index_jobs(application) -> int:
    """Resumes any running or paused /index jobs persisted in SQLite after a bot restart."""
    resumed = 0
    try:
        _init_index_persistence()
        conn = sqlite3.connect(users_db_path())
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM active_index_jobs WHERE state IN ('running', 'paused', 'queued')"
        ).fetchall()
        conn.close()
    except Exception as exc:
        logger.debug("Could not query active_index_jobs on startup: %s", exc)
        return 0

    from types import SimpleNamespace
    for row in rows:
        job = _row_to_job(row)
        if not job:
            continue
        rid = job["rid"]
        if rid in _GLOBAL_INDEX_JOBS:
            continue
        _GLOBAL_INDEX_JOBS[rid] = job
        if job.get("state") in ("running", "paused"):
            ctx = SimpleNamespace(bot=application.bot, application=application, bot_data=application.bot_data)
            application.create_task(_run_index(ctx, rid, job))
            resumed += 1
    return resumed


async def index_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = getattr(q, "data", None) or ""
    user = getattr(q, "from_user", None)
    role = get_user_role_db(user.id) if user else "Admin"
    full = (role in FULL_ACCESS) or (user and user.id == anon_admin_id())
    partial = role in APPROVAL_ACCESS

    # 1. Static Fleet Dashboard ("📋 Ongoing Tasks") & New Wizard buttons (no rid suffix)
    if data == "idx_ongoing_menu":
        if not full:
            await q.answer("⛔ Only Administrators and the Creator can view Ongoing Tasks.", show_alert=True)
            return
        await q.answer("📋 Ongoing Tasks Updated")
        text, markup = build_ongoing_tasks_dashboard()
        try:
            await q.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        except Exception:
            await context.bot.send_message(
                chat_id=user.id if user else q.message.chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=markup,
                disable_web_page_preview=True,
            )
        return

    if data == "idx_new_wizard":
        if not full:
            await q.answer("⛔ Only Administrators and the Creator can start batch indexing.", show_alert=True)
            return
        await q.answer()
        if hasattr(context, "user_data") and isinstance(context.user_data, dict):
            context.user_data["idx_flow"] = {"step": "link", "skip": None}
        wiz_kb = InlineKeyboardMarkup([[styled_button("📋 Ongoing Tasks", callback_data="idx_ongoing_menu", style="success")]])
        await q.message.edit_text(
            "📚 <b>Index Setup Wizard</b>\n\n"
            "<table striped>"
            "<tr><th>Option</th><th>How to Use</th></tr>"
            "<tr><td>🔗 <b>Single Link</b></td><td>Send last message link (indexes from #1)</td></tr>"
            "<tr><td>🔢 <b>Custom Range</b></td><td>Send first link and last link together</td></tr>"
            "<tr><td>📨 <b>Forward</b></td><td>Forward the last message from the source chat</td></tr>"
            "</table>\n\n"
            "• Example: <mark>https://t.me/c/1234567890/150</mark>",
            parse_mode="HTML",
            reply_markup=wiz_kb,
        )
        return

    # 2. Per-job callbacks: idx_<action>_<rid>
    m = re.match(r"^idx_(.+)_([0-9a-f]{8})$", data)
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
        if action.startswith("fl_"):
            await q.answer("Task already finished or removed.")
            text, markup = build_ongoing_tasks_dashboard()
            try:
                await q.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
            except Exception:
                pass
            return
        await q.answer("⌛ This request has expired. Send /index again.", show_alert=True)
        return

    # Fleet dashboard per-task controls (fl_pause, fl_resume, fl_prio, fl_cancel)
    if action.startswith("fl_"):
        if not full:
            await q.answer("⛔ Only Administrators can control fleet tasks.", show_alert=True)
            return
        sub = action[3:]
        bot_lbl = str(job.get("assigned_worker") or "Bot")
        if sub == "pause":
            job["paused"] = True
            job["state"] = "paused"
            _persist_job(job)
            await q.answer("⏸ Task paused.")
            await _log_lifecycle(context, job, "paused", bot_lbl, stats=job.get("stats"))
        elif sub == "resume":
            job["paused"] = False
            job["state"] = "running"
            _persist_job(job)
            await q.answer("▶️ Task resumed.")
            await _log_lifecycle(context, job, "resumed", bot_lbl, stats=job.get("stats"))
        elif sub == "prio":
            await q.answer("🚀 Starting queued task...")
            _begin(context, rid, job, force_run=True)
        elif sub == "cancel":
            job["cancel"] = True
            job["paused"] = False
            _forget_job(rid)
            await q.answer("⛔ Task cancelled.")
            await _log_lifecycle(context, job, "cancelled", bot_lbl, stats=job.get("stats"))
            await _start_next_queued_job(context)
        text, markup = build_ongoing_tasks_dashboard()
        try:
            await q.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
        except Exception:
            pass
        return

    if action == "cancel":
        job["cancel"] = True
        job["paused"] = False
        _forget_job(rid)
        await q.answer("Indexing cancelled.")
        cancel_kb = InlineKeyboardMarkup([[styled_button("📋 Ongoing Tasks", callback_data="idx_ongoing_menu", style="success")]])
        await _edit_prompt(context, job, f"⛔ Indexing of <b>{html.escape(job['title'])}</b> was cancelled.", cancel_kb)
        await _start_next_queued_job(context)
        return

    if action == "pause":
        if not full:
            await q.answer("Only Administrators can pause indexing.", show_alert=True)
            return
        job["paused"] = True
        job["state"] = "paused"
        _persist_job(job)
        stats = _ensure_stats(job.get("stats"))
        await q.answer("⏸ Indexing paused.")
        await _edit_prompt(context, job, _status_text(job, stats, "paused ⏸"), _running_markup(rid, True))
        bot_lbl = str(job.get("assigned_worker") or getattr(context.bot, "username", None) or "Bot")
        await _log_lifecycle(context, job, "paused", bot_lbl, stats=stats)
        return

    if action == "resume":
        if not full:
            await q.answer("Only Administrators can resume indexing.", show_alert=True)
            return
        job["paused"] = False
        job["state"] = "running"
        _persist_job(job)
        stats = _ensure_stats(job.get("stats"))
        await q.answer("▶️ Indexing resumed.")
        await _edit_prompt(context, job, _status_text(job, stats, "running"), _running_markup(rid, False))
        bot_lbl = str(job.get("assigned_worker") or getattr(context.bot, "username", None) or "Bot")
        await _log_lifecycle(context, job, "resumed", bot_lbl, stats=stats)
        return

    if action.startswith("sk_"):
        mode = action[3:]
        if mode == "none":
            await _show_priority_menu(context, rid, job)
        elif mode == "top":
            old_start = job["start_id"]
            job["start_id"] = min(job["end_id"], job["start_id"] + 10)
            job["current_mid"] = job["start_id"]
            delta = max(0, job["start_id"] - old_start)
            job["skipped_range"] = int(job.get("skipped_range", 0) or 0) + delta
            orig_s = int(job.get("orig_start_id") or old_start)
            job["excluded_range"] = f"{orig_s} → {job['start_id'] - 1} ({job['skipped_range']} msgs skipped)"
            _persist_job(job)
            await _show_priority_menu(context, rid, job)
        elif mode == "bot":
            old_end = job["end_id"]
            job["end_id"] = max(job["start_id"], job["end_id"] - 10)
            delta = max(0, old_end - job["end_id"])
            job["skipped_range"] = int(job.get("skipped_range", 0) or 0) + delta
            orig_e = int(job.get("orig_end_id") or old_end)
            job["excluded_range"] = f"{job['end_id'] + 1} → {orig_e} ({job['skipped_range']} msgs skipped)"
            _persist_job(job)
            await _show_priority_menu(context, rid, job)
        elif mode == "custom":
            await _edit_prompt(
                context,
                job,
                "Send <code>/index &lt;first_link&gt; &lt;last_link&gt;</code> for custom ranges.",
                InlineKeyboardMarkup([[styled_button("📋 Ongoing Tasks", callback_data="idx_ongoing_menu", style="success")]]),
            )
        return

    if action.startswith("pr_"):
        mode = "direct" if action == "pr_dir" else "helpers"
        job["priority_mode"] = mode
        _persist_job(job)
        if full:
            await q.answer("Starting index...")
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
