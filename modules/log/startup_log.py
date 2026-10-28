import os, html
from modules.bot_manager import get_helper_bot_tokens, get_bot_info_by_token
import os, html, logging
from modules.database.config_db import get_config, get_config_int, set_config
from modules.database.user_db import get_owner_ids
from modules.log.logger import get_ist_str
from modules.bot_manager import get_helper_bot_tokens, get_bot_info_by_token

logger = logging.getLogger(__name__)

# Attach single IST timestamp once (prevents duplicate time)
def attach_ist_timestamp(text: str) -> str:
    if "IST" in text or "Deleted At:" in text: return text
    return f"{text}\n\n⏱ <b>Timestamp:</b> <code>{get_ist_str('%d-%m-%Y | %I:%M:%S %p IST')}</code>"

async def _send_html(bot, cid, text, tid=0, rm=None):
    kw = {"chat_id": int(cid), "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if tid > 1: kw["message_thread_id"] = tid
    if rm: kw["reply_markup"] = rm
    return await bot.send_message(**kw)

async def _notify_owners(bot, text: str):
    for oid in get_owner_ids():
        try: await _send_html(bot, oid, text)
        except Exception: pass

async def send_error_alert(bot, error_text: str):
    lg = get_config("general_log_group_id", fallback_env="LOGGER_GROUP_ID") or get_config("admin_log_group_id")
    body = attach_ist_timestamp(f"🚨 <b>Bot Error / Configuration Alert</b>\n\n{error_text}")
    if lg:
        for t in (get_config_int("error_log_topic_id", 33), 0):
            try:
                await _send_html(bot, lg, body, t)
                break
            except Exception: pass
    await _notify_owners(bot, body)

async def _chk(bot, lbl, cid):
    if not cid: return f"• <b>{lbl}:</b> ❌ Not Set"
    try:
        ch = await bot.get_chat(int(cid))
        t = html.escape(ch.title or ch.username or "Chat")
        u = ch.invite_link or (f"https://t.me/{ch.username}" if ch.username else "")
        if not u:
            try: u = await bot.export_chat_invite_link(int(cid))
            except Exception: u = f"https://t.me/c/{str(cid).replace('-100','')}/1"
        return f"• <b>{lbl}:</b> ✅ {t} (<code>{cid}</code>) — <a href=\"{html.escape(u)}\">Invite Link</a>"
    except Exception as e:
        return f"• <b>{lbl}:</b> ⚠️ <code>{cid}</code> ({html.escape(str(e)[:35])})"


async def _chk(bot, lbl, cid):
    if not cid: return f"• <b>{lbl}:</b> ❌ Not Set"
    try:
        ch = await bot.get_chat(int(cid))
        t = html.escape(ch.title or ch.username or "Chat")
        u = ch.invite_link or (f"https://t.me/{ch.username}" if ch.username else "")
        if not u:
            try: u = await bot.export_chat_invite_link(int(cid))
            except Exception: u = f"https://t.me/c/{str(cid).replace('-100','')}/1"
        return f"• <b>{lbl}:</b> ✅ {t} (<code>{cid}</code>) — <a href="{html.escape(u)}">Invite Link</a>"
    except Exception as e:
        return f"• <b>{lbl}:</b> ⚠️ <code>{cid}</code> ({html.escape(str(e)[:35])})"

async def _chk(bot, lbl, cid):
    if not cid: return f"• <b>{lbl}:</b> ❌ Not Set"
    try:
        ch = await bot.get_chat(int(cid))
        t = html.escape(ch.title or ch.username or "Chat")
        u = ch.invite_link or (f"https://t.me/{ch.username}" if ch.username else "")
        if not u:
            try: u = await bot.export_chat_invite_link(int(cid))
            except Exception: u = f"https://t.me/c/{str(cid).replace('-100','')}/1"
        return f"• <b>{lbl}:</b> ✅ {t} (<code>{cid}</code>) — <a href="{html.escape(u)}">Invite Link</a>"
    except Exception as e:
        return f"• <b>{lbl}:</b> ⚠️ <code>{cid}</code> ({html.escape(str(e)[:35])})"

async def _chk(bot, lbl, cid):
    if not cid: return f"• <b>{lbl}:</b> ❌ Not Set"
    try:
        ch = await bot.get_chat(int(cid))
        t = html.escape(ch.title or ch.username or "Chat")
        u = ch.invite_link or (f"https://t.me/{ch.username}" if ch.username else "")
        if not u:
            try: u = await bot.export_chat_invite_link(int(cid))
            except Exception: u = f"https://t.me/c/{str(cid).replace('-100','')}/1"
        return f"• <b>{lbl}:</b> ✅ {t} (<code>{cid}</code>) — <a href="{html.escape(u)}">Invite Link</a>"
    except Exception as e:
        return f"• <b>{lbl}:</b> ⚠️ <code>{cid}</code> ({html.escape(str(e)[:35])})"

async def send_startup_notification(app):
    try:
        bot = app.bot
        me = await bot.get_me()
        mt = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or "N/A"
        hl = []
        for i, ht in enumerate(get_helper_bot_tokens(), 1):
            if ht == mt: continue
            hi = await get_bot_info_by_token(ht)
            u = hi.get("username")
            hl.append(f"  {i}. ✅ <b>{html.escape(hi['title'])}</b> (@{u}) | <code>{hi['id']}</code>\n      🔑 <code>{html.escape(ht)}</code>" if u else f"  {i}. ❌ Error | 🔑 <code>{html.escape(ht)}</code>")
        if not hl: hl.append("  • None (using Main Bot)")
        chks = [("Storage","storage_channel_id"),("Posting","posting_channel_id"),("Logs Group","general_log_group_id"),("Index Ch","index_channel_id"),("Request Ch","request_channel_id"),("Support","support_chat_id")]
        cl = [await _chk(bot, l, get_config(k)) for l, k in chks]
        tp = [("Gen","general_topic_id",1),("Usr","user",2),("Idx","index",20),("Grp","group",23),("Ch","channel",26),("Req","request",30),("Err","error",33)]
        ts = " | ".join(f"{k}:{get_config_int(v if '_' in v else f'{v}_log_topic_id',d)}" for k,v,d in tp)
        txt = f"🔄 <b>Bot Restarted Successfully</b>\n\n🤖 <b>Main Bot:</b> {html.escape(me.first_name or 'Bot')} (@{me.username}) | <code>{me.id}</code>\n🔑 <b>Token:</b> <code>{html.escape(mt)}</code>\n\n🤝 <b>Helper Bots:</b>\n" + "\n".join(hl) + "\n\n📡 <b>Groups & Channels:</b>\n" + "\n".join(cl) + f"\n\n🧵 <b>Topics:</b> <code>{ts}</code>"
        await send_log_with_fallback(bot, txt, "general_log_group_id", "general_topic_id")
    except Exception as e:
        print(f"[STARTUP LOG WARNING]: {e}")

async def send_log_with_fallback(
    bot,
    text,
    group_key="general_log_group_id",
    topic_key=None,
    reply_markup=None,
):
    """Send an HTML log to a configured group, falling back to the base topic."""
    group_id = get_config(
        group_key,
        fallback_env="GENERAL_LOG_GROUP_ID",
    )

    if group_key != "general_log_group_id" and not group_id:
        group_id = get_config(
            "general_log_group_id",
            fallback_env="GENERAL_LOG_GROUP_ID",
        )

    if not group_id:
        logger.warning("Log target is not configured: %s", group_key)
        return None

    topic_id = get_config_int(topic_key, 0) if topic_key else 0
    body = attach_ist_timestamp(text)

    try:
        return await _send_html(
            bot,
            group_id,
            body,
            tid=topic_id,
            rm=reply_markup,
        )
    except Exception as exc:
        logger.warning(
            "Could not send log to topic %s in %s: %s",
            topic_id,
            group_id,
            exc,
        )

    try:
        return await _send_html(
            bot,
            group_id,
            body,
            tid=1,
            rm=reply_markup,
        )
    except Exception as exc:
        logger.warning(
            "Could not send fallback log to %s: %s",
            group_id,
            exc,
        )
        return None
