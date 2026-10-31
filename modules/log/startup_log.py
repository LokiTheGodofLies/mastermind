import html
import sqlite3
import time
import asyncio
import logging
import datetime
import traceback
from zoneinfo import ZoneInfo

from telegram import Bot
from telegram.error import TelegramError, Conflict
from config import (
    admin_ids,
    bot_mode,
    bot_name,
    helper_bot_tokens,
    logger_group_id,
    log_topic,
    general_topic_id,
    config_db_path,
    files_db_path,
    users_db_path,
)

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")

DB_STATUS = "initialized (no backup restored)"
DB_STATUS_OK = True

CHAT_SLOTS = [
    ("Storage", "STORAGE_GROUP_ID", "Storage group"),
    ("Posting", "POSTING_CHANNEL_ID", "Posting channel"),
    ("Logs Group", "LOGGER_GROUP_ID", "Logs group"),
    ("Index Ch", "INDEX_CHANNEL_ID", "Index channel"),
    ("Request Ch", "REQUEST_CHANNEL_ID", "Request channel"),
    ("Support", "SUPPORT_CHAT_ID", "Support chat"),
]

TOPIC_SLOTS = [
    ("Gen", None),
    ("Usr", "USER_LOG_TOPIC_ID"),
    ("Idx", "INDEX_LOG_TOPIC_ID"),
    ("Grp", "GROUP_LOG_TOPIC_ID"),
    ("Ch", "CHANNEL_LOG_TOPIC_ID"),
    ("Req", "REQUEST_LOG_TOPIC_ID"),
    ("Err", "ERROR_LOG_TOPIC_ID"),
]


def _esc(text):
    return html.escape(str(text or ""), quote=False)


_last_sent = {}


def _cfg(env_name):
    """Resolve a chat/topic ID through config.py (PUBLIC_/TESTING_ env only, no DB/env fallbacks)."""
    import config as _config
    if env_name.endswith("_LOG_TOPIC_ID"):
        return _config.log_topic(env_name[: -len("_LOG_TOPIC_ID")])
    return getattr(_config, env_name.lower())()


def _count(db_path, query):
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        n = conn.execute(query).fetchone()[0]
        conn.close()
        return n
    except Exception:
        return 0


def _db_counts():
    return (
        _count(files_db_path(), "SELECT COUNT(*) FROM indexed_files"),
        _count(users_db_path(), "SELECT COUNT(*) FROM users"),
        _count(config_db_path(), "SELECT COUNT(*) FROM config"),
    )


def _bot_line(bot_info):
    uname = f"@{bot_info.username}" if bot_info.username else "no username"
    return f"{_esc(bot_info.first_name)} ({uname}) | {bot_info.id}"


async def _helper_bots():
    return helper_bot_tokens()


def _table(headers, rows) -> str:
    """Rich `<table>`; every cell is already-escaped HTML. Falls back to a monospace block in plain mode."""
    head = "<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>"
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table striped>{head}{body}</table>"


async def _helper_rows(problems):
    rows = []
    for i, token in enumerate(await _helper_bots(), 1):
        try:
            async with Bot(token) as hb:
                me = await hb.get_me()
            uname = f"@{me.username}" if me.username else "no username"
            rows.append([str(i), "✅", _esc(me.first_name), _esc(uname), f"<code>{me.id}</code>"])
        except Exception as e:
            logger.warning("Helper bot %d check failed: %s", i, e)
            rows.append([str(i), "❌", "Unreachable", f"token …{_esc(token[-4:])}", "—"])
            problems.append(f"Helper bot {i} unreachable (token ends …{token[-4:]}): {e}")
    return rows


async def _chat_row(bot, me_id, label, chat_id_raw, default_name, problems):
    """[Slot, status icon, chat name, chat id, invite link] for the Groups & Channels table."""
    if not chat_id_raw:
        return [_esc(label), "⚠️", "Not set", "—", "—"]
    try:
        chat_id = int(chat_id_raw)
    except ValueError:
        problems.append(f"{label}: invalid chat ID {chat_id_raw}")
        return [_esc(label), "❌", "Invalid ID", f"<code>{_esc(chat_id_raw)}</code>", "—"]
    try:
        chat = await bot.get_chat(chat_id)
        name = chat.title or default_name
        try:
            from modules.database.user_db import register_chat_db
            register_chat_db(chat.id, chat.type, name, getattr(chat, "username", ""))
        except Exception:
            pass
        link = chat.invite_link or (f"https://t.me/{chat.username}" if chat.username else None)
        if not link:
            try:
                link = await bot.export_chat_invite_link(chat_id)
            except Exception:
                link = None
        is_admin = True
        try:
            member = await bot.get_chat_member(chat_id, me_id)
            is_admin = member.status in ("administrator", "creator")
        except Exception:
            pass
        icon = "✅" if is_admin else "⚠️"
        if not is_admin:
            problems.append(f"{label} ({name}, {chat_id}): bot is not an admin")
        link_cell = f'<a href="{html.escape(link, quote=True)}">Invite Link</a>' if link else "—"
        status = icon if is_admin else "⚠️ not admin"
        return [_esc(label), status, _esc(name), f"<code>{chat_id}</code>", link_cell]
    except Exception as e:
        logger.warning("Startup check for %s (%s) failed: %s", label, chat_id, e)
        problems.append(f"{label} ({chat_id}): not accessible — {e}")
        return [_esc(label), "❌", "Not accessible", f"<code>{chat_id}</code>", "—"]


async def build_startup_text(application, problems):
    """Restart card as Field | Value tables (rich message; plain monospace blocks as fallback)."""
    bot = application.bot
    me = await bot.get_me()
    gen_topic = str(general_topic_id())

    mode_str = "🧪 TESTING MAIN BOT (test branch)" if bot_mode() == "testing" else "🌐 PUBLIC MAIN BOT (main branch)"
    uname = f"@{me.username}" if me.username else "no username"
    files, users, templates = _db_counts()
    db_icon = "✅" if DB_STATUS_OK else "⚠️"
    now = datetime.datetime.now(IST).strftime("%d-%m-%Y | %I:%M:%S %p IST")

    parts = ["🔄 <b>Bot Restarted Successfully</b>", ""]
    parts.append(_table(["Field", "Value"], [
        ["🏷️ <i>Environment</i>", f"<code>{_esc(mode_str)}</code>"],
        ["🤖 <i>Main Bot</i>", f"{_esc(me.first_name)} ({_esc(uname)}) | <code>{me.id}</code>"],
        ["💾 <i>Database</i>", f"{db_icon} {_esc(DB_STATUS)}"],
        ["📚 <i>Files</i> | 👥 <i>Users</i> | 🧩 <i>Templates</i>", f"<code>{files}</code> | <code>{users}</code> | <code>{templates}</code>"],
        ["⏱ <i>Timestamp</i>", f"<code>{_esc(now)}</code>"],
    ]))

    helpers = await _helper_rows(problems)
    if helpers:
        parts += ["", "🤝 <b>Helper Bots</b>", _table(["#", "", "Name", "Username", "ID"], helpers)]

    chat_rows = [
        await _chat_row(bot, me.id, label, _cfg(env), default, problems)
        for label, env, default in CHAT_SLOTS
    ]
    parts += ["", "📡 <b>Groups &amp; Channels</b>", _table(["Slot", "", "Name", "ID", "Link"], chat_rows)]

    topic_rows = [[_esc(label), f"<code>{_esc((_cfg(env) if env else gen_topic) or '—')}</code>"] for label, env in TOPIC_SLOTS]
    parts += ["", "🧵 <b>Topics</b>", _table(["Topic", "ID"], topic_rows)]

    parts += [
        "",
        "📌 <b>Reminder:</b> check that no other bot instance is running "
        "(Termux: <code>pkill -f \"python.*main.py\"</code>)",
    ]
    return "\n".join(parts)


async def _send_chain(bots, text, topic):
    """Try to deliver `text`, falling back step by step:
    log group topic -> log group General topic -> log group (no topic) -> owner PM.
    Each bot in `bots` is tried in order (main first, then helpers)."""
    group = logger_group_id()
    gen_topic = str(general_topic_id())
    targets = []
    if group:
        g = int(group)
        for t in (topic, gen_topic, None):
            t = int(t) if t else None
            if (g, t) not in targets:
                targets.append((g, t))
    targets += [(uid, None) for uid in sorted(admin_ids())]

    for bot in bots:
        for chat_id, thread in targets:
            kwargs = dict(chat_id=chat_id, text=text, parse_mode="HTML", disable_web_page_preview=True)
            if thread:
                kwargs["message_thread_id"] = thread
            try:
                await bot.send_message(**kwargs)
                return True
            except TelegramError as e:
                logger.warning("Log delivery to %s (topic %s) failed: %s", chat_id, thread, e)
    return False


async def _bots_for(application):
    return [application.bot] if application is not None else []


async def report_error(application, text, title="Error"):
    """Send an error report: Err topic -> General -> group -> owner PM.
    If the main bot cannot deliver, helper bots try."""
    key = (title, text[:200])
    now = time.time()
    if now - _last_sent.get(key, 0) < 60:
        return
    _last_sent[key] = now

    body = f"🚨 <b>{_esc(title)}</b>\n\n<pre>{_esc(text)[:3400]}</pre>"
    bots = await _bots_for(application)
    helper_ctx = []
    try:
        for token in await _helper_bots():
            helper_ctx.append(Bot(token))
        ok = await _send_chain(bots + helper_ctx, body, _cfg("ERROR_LOG_TOPIC_ID"))
    finally:
        for hb in helper_ctx:
            try:
                await hb.shutdown()
            except Exception:
                pass
    if not ok:
        print(f"❌ [ERROR REPORT NOT DELIVERED] {title}: {text}")


async def error_handler(update, context):
    """Global handler: report uncaught handler errors."""
    err = context.error
    if isinstance(err, Conflict):
        logger.warning("Telegram polling Conflict (likely overlapping deploy): %s", err)
        return
    tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
    logger.error("Unhandled error: %s", err)
    await report_error(context.application, tb, title="Unhandled error")


def report_fatal_sync(text, title="Main bot failed to start"):
    """Used when the main bot cannot run at all (e.g. token revoked):
    helper bots deliver the report."""
    async def _run():
        helpers = [Bot(t) for t in await _helper_bots()]
        try:
            body = f"🚨 <b>{_esc(title)}</b>\n\n<pre>{_esc(text)[:3400]}</pre>"
            ok = await _send_chain(helpers, body, _cfg("ERROR_LOG_TOPIC_ID"))
        finally:
            for hb in helpers:
                try:
                    await hb.shutdown()
                except Exception:
                    pass
        return ok
    try:
        if not asyncio.run(_run()):
            print(f"❌ [FATAL NOT DELIVERED] {title}: {text}")
    except Exception as e:
        print(f"❌ [FATAL REPORT FAILED] {e}: {title}: {text}")


async def send_startup_notification(application):
    problems = []
    try:
        text = await build_startup_text(application, problems)
        if not await _send_chain([application.bot], text, str(general_topic_id())):
            print("❌ [STARTUP] Could not deliver startup log anywhere.")
            return
        print("✅ [STARTUP] Restart notification sent successfully!")
    except Exception as e:
        print(f"❌ [STARTUP ERROR]: {e}")
        await report_error(application, f"Startup log failed: {e}", title="Startup error")
        return
    if problems:
        await report_error(application, "\n".join(problems), title="Startup check problems")


async def _dispatch_lifecycle_notices(app):
    """Sends auto-delete notices to registered groups/channels and audits blocked users."""
    try:
        from modules.database.user_db import get_all_chats_db, get_all_users_for_broadcast_db, record_user_blocked_bot_db
        chats = get_all_chats_db()
        helpers = await _helper_bots()

        # 1. Main bot startup notice (auto-deletes in 5s)
        for c in chats:
            cid = c["chat_id"]
            try:
                sent = await app.bot.send_message(cid, f"🔄 <b>{bot_name()} is online and ready!</b>", parse_mode="HTML")
                asyncio.create_task(_auto_delete_msg(app.bot, cid, sent.message_id, 5))
            except Exception:
                pass

        # 2. Helper bot startup notices (auto-delete in 1s)
        for tok in helpers:
            try:
                async with Bot(tok) as hb:
                    me = await hb.get_me()
                    for c in chats:
                        cid = c["chat_id"]
                        try:
                            sent = await hb.send_message(cid, f"🤖 @{me.username} helper delivery is online!", parse_mode="HTML")
                            asyncio.create_task(_auto_delete_msg(hb, cid, sent.message_id, 1))
                        except Exception:
                            pass
            except Exception:
                pass

        # 3. Proactive user block detection (sample batch)
        users = get_all_users_for_broadcast_db()[:50]
        for u in users:
            uid = u["user_id"]
            try:
                await app.bot.send_chat_action(uid, "typing")
            except Exception as exc:
                if "blocked" in str(exc).lower():
                    await _report_user_block(app, uid, u.get("full_name", ""), u.get("username", ""), app.bot.first_name, app.bot.username or "")
    except Exception as exc:
        logger.debug("Lifecycle dispatch notice: %s", exc)


async def _auto_delete_msg(bot_inst, chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await bot_inst.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def _report_user_block(app, uid, name, uname, bot_title, bot_uname):
    from modules.database.user_db import record_user_blocked_bot_db, _db_file
    import sqlite3
    record_user_blocked_bot_db(uid, bot_uname)
    if not name or name == "Unknown":
        try:
            conn = sqlite3.connect(_db_file())
            row = conn.execute("SELECT full_name, username FROM users WHERE user_id = ?", (int(uid),)).fetchone()
            conn.close()
            if row:
                name = row[0] or name
                uname = row[1] or uname
        except Exception:
            pass
    log_gid = logger_group_id()
    topic = log_topic("USER") or 2
    if not log_gid:
        return
    uname_part = f" (@{html.escape(uname)})" if uname and uname.lower() != "none" else ""
    name_part = f"{html.escape(name)}{uname_part} " if name and name != "Unknown" else f"{uname_part.strip()} " if uname_part else ""
    text = (
        "🚫 <b>Bot Blocked by User</b>\n\n"
        f"• <b>User ID:</b> {name_part}[<code>{uid}</code>]\n"
        f"• <b>Blocked Bot:</b> {html.escape(bot_title)} (@{html.escape(bot_uname)})\n"
        f"• <b>Timestamp:</b> {datetime.datetime.now(IST).strftime('%d-%m-%Y | %I:%M:%S %p IST')}"
    )
    try:
        await app.bot.send_message(chat_id=int(log_gid), message_thread_id=int(topic), text=text, parse_mode="HTML")
    except Exception:
        pass


def _ist_stamp() -> str:
    """`DD Mon YYYY, HH:MM IST` (true IST, independent of the server clock)."""
    return datetime.datetime.now(IST).strftime("%d %b %Y, %H:%M IST")


def _user_link(user_id, title) -> str:
    return f'<a href="tg://user?id={int(user_id)}">{_esc(title or "User")}</a>'


def build_new_user_log_text(
    *,
    user_id,
    user_title,
    username,
    bot_title,
    bot_username,
    is_helper: bool = False,
    referrer_id=None,
    referrer_title=None,
) -> str:
    """`New user started the bot` card (Field | Details table) for the Logger Group USER topic."""
    uname = f"@{_esc(username)}" if username else "—"
    bot_kind = "Helper Bot" if is_helper else "Main Bot"
    bot_label = f"{_esc(bot_title)} (@{_esc(bot_username)}) · <i>{bot_kind}</i>" if bot_username else f"{_esc(bot_title)} · <i>{bot_kind}</i>"
    rows = [
        ["👤 <i>User</i>", _user_link(user_id, user_title)],
        ["🆔 <i>User ID</i>", f"<code>{int(user_id)}</code>"],
        ["🏷 <i>Username</i>", uname],
        ["🤖 <i>Bot</i>", bot_label],
    ]
    if referrer_id:
        rows.append([
            "🔗 <i>Referred By</i>",
            f"{_user_link(referrer_id, referrer_title or f'User {referrer_id}')} (<code>{int(referrer_id)}</code>)",
        ])
    rows.append(["🕒 <i>Time</i>", _esc(_ist_stamp())])
    return "🆕 <b>New User Started the Bot</b>\n\n" + _table(["Field", "Details"], rows)


async def send_new_user_log(bots, text: str) -> bool:
    """Posts the new-user card to Logger Group -> USER topic. `bots` are tried in order (the log is
    NOT forwarded to admin PMs on failure, unlike error reports, so a missing topic never spams people)."""
    group = logger_group_id()
    if not group:
        return False
    topic = log_topic("USER")
    targets = []
    for t in (topic, None):
        if (int(group), t) not in targets:
            targets.append((int(group), t))
    for bot in bots:
        if bot is None:
            continue
        for chat_id, thread in targets:
            kwargs = dict(chat_id=chat_id, text=text, parse_mode="HTML", disable_web_page_preview=True)
            if thread:
                kwargs["message_thread_id"] = int(thread)
            try:
                await bot.send_message(**kwargs)
                return True
            except TelegramError as e:
                logger.warning("New-user log to %s (topic %s) failed: %s", chat_id, thread, e)
    return False


async def log_new_user_start(
    context_bot,
    user,
    *,
    is_helper: bool,
    referrer_id=None,
):
    """Builds and sends the new-user card. Helper bots are usually not members of the Logger Group,
    so the MAIN bot (own token) sends it first; the calling bot is the fallback. Never raises."""
    try:
        from config import bot_token
        from modules.database.user_db import get_user_info_db

        me = context_bot
        bot_username = getattr(me, "username", None) or ""
        bot_title = getattr(me, "first_name", None) or bot_name()
        if not bot_username:
            try:
                info = await me.get_me()
                bot_username, bot_title = info.username or "", info.first_name or bot_title
            except Exception:
                pass

        ref_title = None
        if referrer_id:
            info = get_user_info_db(int(referrer_id))
            ref_title = (info or {}).get("full_name") or None

        text = build_new_user_log_text(
            user_id=user.id,
            user_title=user.full_name,
            username=user.username,
            bot_title=bot_title,
            bot_username=bot_username,
            is_helper=is_helper,
            referrer_id=referrer_id,
            referrer_title=ref_title,
        )

        if is_helper:
            main_token = bot_token()
            if main_token:
                async with Bot(main_token) as main_bot:
                    if await send_new_user_log([main_bot, context_bot], text):
                        return True
                return False
        return await send_new_user_log([context_bot], text)
    except Exception as exc:  # logging must never break /start
        logger.warning("New-user log failed: %s", exc)
        return False
