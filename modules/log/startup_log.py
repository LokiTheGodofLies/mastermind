import os
import html
import logging
from modules.bot_manager import get_helper_bot_tokens, get_bot_info_by_token
from modules.database.config_db import get_config, get_config_int
from modules.database.user_db import get_owner_ids
from modules.log.logger import get_ist_str

logger = logging.getLogger(__name__)


def attach_ist_timestamp(text: str) -> str:
    if "IST" in text or "Deleted At:" in text:
        return text
    return f"{text}\n\n<b>Timestamp:</b> <code>{get_ist_str()}</code>"


async def _send_html(bot, cid, text, tid=0, rm=None):
    kwargs = {
        "chat_id": int(cid),
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if tid and int(tid) > 0:
        kwargs["message_thread_id"] = int(tid)
    if rm:
        kwargs["reply_markup"] = rm
    return await bot.send_message(**kwargs)


async def _notify_owners(bot, text: str):
    for oid in get_owner_ids():
        try:
            await _send_html(bot, oid, text)
        except Exception:
            pass


async def _chk(bot, lbl, cid):
    if not cid:
        return f"<b>{lbl}</b>: Not Set"
    try:
        chat = await bot.get_chat(int(cid))
        title = html.escape(chat.title or chat.username or "Chat")
        u = chat.invite_link or (f"https://t.me/{chat.username}" if chat.username else "")
        if not u:
            return f"<b>{lbl}</b>: <code>{cid}</code> ({title})"
        return f"<b>{lbl}</b>: <code>{cid}</code> ({title}) <a href=\"{html.escape(u)}\">Invite Link</a>"
    except Exception as e:
        return f"<b>{lbl}</b>: <code>{cid}</code> (<code>{html.escape(str(e))}</code>)"


async def send_startup_notification(app):
    try:
        bot = app.bot
        me = await bot.get_me()
        mt = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or "N/A"
        helper_tokens = get_helper_bot_tokens() or []
        helper_info = []

        for idx, htoken in enumerate(helper_tokens, 1):
            if not htoken:
                continue
            try:
                info = get_bot_info_by_token(htoken)
                username = info.get("username") if isinstance(info, dict) else None
                title = info.get("title") if isinstance(info, dict) else None
                bot_id = info.get("id") if isinstance(info, dict) else None
                if username:
                    helper_info.append(f"{idx}. <b>{html.escape(title or username)}</b> (@{html.escape(username)}) | <code>{bot_id}</code>")
                else:
                    helper_info.append(f"{idx}. <code>{htoken.split(':')[0]}</code>")
            except Exception:
                helper_info.append(f"{idx}. <code>{htoken.split(':')[0]}</code>")

        if not helper_info:
            helper_info.append("None")

        chat_checks = [
            ("Storage", "storage_channel_id"),
            ("Posting", "posting_channel_id"),
            ("Logs Group", "general_log_group_id"),
            ("Index Channel", "index_channel_id"),
            ("Request Channel", "request_channel_id"),
            ("Support", "support_chat_id"),
        ]

        lines = [
            "<b>Bot Restarted Successfully</b>",
            f"<b>Main Bot:</b> {html.escape(me.first_name or 'Bot')} (@{html.escape(me.username or 'bot')}) | <code>{me.id}</code>",
            f"<b>Token:</b> <code>{html.escape(mt[:10])}...</code>",
            "<b>Helper Bots:</b>",
            "\n".join(f"• {x}" for x in helper_info),
            "",
            "<b>Groups & Channels:</b>",
        ]

        for lbl, key in chat_checks:
            val = get_config(key, fallback_env=key.upper())
            if val:
                lines.append(await _chk(bot, lbl, val))
            else:
                lines.append(f"<b>{lbl}</b>: Not Set")

        body = "\n".join(lines)
        body = attach_ist_timestamp(body)

        log_group = get_config("general_log_group_id", fallback_env="LOGGER_GROUP_ID")
        if log_group:
            try:
                await _send_html(bot, log_group, body, tid=get_config_int("general_topic_id", 1))
            except Exception:
                pass

        try:
            await _notify_owners(bot, body)
        except Exception:
            pass

    except Exception as e:
        logger.exception("Startup notification failed: %s", e)
