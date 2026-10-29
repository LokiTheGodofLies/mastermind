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
    bot_name,
    helper_bot_tokens,
    logger_group_id,
    log_topic,
    general_topic_id,
    config_db_path,
    files_db_path,
    users_db_path,
)
from modules.database.config_db import get_config

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
    return get_config(env_name.lower(), fallback_env=env_name)


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


async def _helper_lines(problems):
    lines = []
    for i, token in enumerate(await _helper_bots(), 1):
        try:
            async with Bot(token) as hb:
                me = await hb.get_me()
            lines.append(f"  {i}. ✅ {_bot_line(me)}")
        except Exception as e:
            logger.warning("Helper bot %d check failed: %s", i, e)
            lines.append(f"  {i}. ❌ Unreachable (token ends …{token[-4:]})")
            problems.append(f"Helper bot {i} unreachable (token ends …{token[-4:]}): {e}")
    return lines


async def _chat_line(bot, me_id, label, chat_id_raw, default_name, problems):
    if not chat_id_raw:
        return f"• {label}: ⚠️ Not set"
    try:
        chat_id = int(chat_id_raw)
    except ValueError:
        problems.append(f"{label}: invalid chat ID {chat_id_raw}")
        return f"• {label}: ❌ Invalid ID ({_esc(chat_id_raw)})"
    try:
        chat = await bot.get_chat(chat_id)
        name = chat.title or default_name
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
        line = f"• {label}: {icon} {_esc(name)} ({chat_id})"
        if not is_admin:
            line += " — bot is not admin"
            problems.append(f"{label} ({name}, {chat_id}): bot is not an admin")
        if link:
            line += f' — <a href="{html.escape(link, quote=True)}">Invite Link</a>'
        return line
    except Exception as e:
        logger.warning("Startup check for %s (%s) failed: %s", label, chat_id, e)
        problems.append(f"{label} ({chat_id}): not accessible — {e}")
        return f"• {label}: ❌ Not accessible ({chat_id})"


async def build_startup_text(application, problems):
    bot = application.bot
    me = await bot.get_me()
    gen_topic = str(general_topic_id())

    parts = ["🔄 <b>Bot Restarted Successfully</b>", ""]
    parts.append(f"🤖 <b>Main Bot:</b> {_bot_line(me)}")

    helpers = await _helper_lines(problems)
    if helpers:
        parts += ["", "🤝 <b>Helper Bots:</b>", *helpers]

    chat_lines = [
        await _chat_line(bot, me.id, label, _cfg(env), default, problems)
        for label, env, default in CHAT_SLOTS
    ]
    parts += ["", "📡 <b>Groups &amp; Channels:</b>", *chat_lines]

    topics = " | ".join(
        f"{label}:{(_cfg(env) if env else gen_topic) or '—'}" for label, env in TOPIC_SLOTS
    )
    parts += ["", f"🧵 <b>Topics:</b> {topics}"]

    files, users, templates = _db_counts()
    icon = "✅" if DB_STATUS_OK else "⚠️"
    parts += [
        "",
        f"💾 <b>Database:</b> {icon} {_esc(DB_STATUS)} "
        f"(📚 files: {files} | 👥 users: {users} | 🧩 templates: {templates})",
    ]

    now = datetime.datetime.now(IST).strftime("%d-%m-%Y | %I:%M:%S %p IST")
    parts += ["", f"⏱ <b>Timestamp:</b> {now}"]
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
    group = _cfg("LOGGER_GROUP_ID") or _cfg("STORAGE_GROUP_ID")
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
    from modules.database.user_db import record_user_blocked_bot_db
    record_user_blocked_bot_db(uid, bot_uname)
    log_gid = logger_group_id()
    topic = log_topic("USER_LOG_TOPIC_ID") or 2
    if not log_gid:
        return
    text = (
        "🚫 <b>Bot Blocked by User</b>\n\n"
        f"• <b>User:</b> <a href=\"tg://user?id={uid}\">{html.escape(name or 'User')}</a> (@{html.escape(uname or 'none')}) [<code>{uid}</code>]\n"
        f"• <b>Blocked Bot:</b> {html.escape(bot_title)} (@{html.escape(bot_uname)})\n"
        f"• <b>Timestamp:</b> {datetime.datetime.now(IST).strftime('%d-%m-%Y | %I:%M:%S %p IST')}"
    )
    try:
        await app.bot.send_message(chat_id=int(log_gid), message_thread_id=int(topic), text=text, parse_mode="HTML")
    except Exception:
        pass
