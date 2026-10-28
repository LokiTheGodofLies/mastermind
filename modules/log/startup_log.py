import logging
from modules.database.config_db import get_config, get_config_int, get_template, format_template_string
from modules.database.user_db import get_owner_ids
from modules.log.logger import get_ist_str

logger = logging.getLogger(__name__)

def attach_ist_timestamp(text: str) -> str:
    if "IST" in text or "Deleted At:" in text:
        return text
    ts = get_ist_str("%d-%m-%Y | %I:%M:%S %p IST")
    return f"{text}\n\n⏱ <b>Timestamp:</b> <code>{ts}</code>"

async def _notify_owners(bot, text: str):
    for oid in get_owner_ids():
        try:
            await bot.send_message(chat_id=int(oid), text=text, parse_mode="HTML")
        except Exception:
            pass

async def send_error_alert(bot, error_text: str):
    log_group = get_config("general_log_group_id", fallback_env="LOGGER_GROUP_ID") or get_config("admin_log_group_id")
    err_topic = get_config_int("error_log_topic_id", 0) or get_config_int("general_topic_id", 1)
    body = attach_ist_timestamp(f"🚨 <b>Bot Error / Configuration Alert</b>\n\n{error_text}")

    if log_group:
        try:
            kw = {"chat_id": int(log_group), "text": body, "parse_mode": "HTML"}
            if err_topic > 0:
                kw["message_thread_id"] = err_topic
            await bot.send_message(**kw)
        except Exception:
            try:
                await bot.send_message(chat_id=int(log_group), text=body, parse_mode="HTML")
            except Exception:
                pass
    await _notify_owners(bot, body)

async def send_log_with_fallback(bot, text: str, target_chat_key: str = "admin_log_group_id", topic_key: str = None, reply_markup=None):
    log_group = get_config("general_log_group_id", fallback_env="LOGGER_GROUP_ID") or get_config("admin_log_group_id")
    topic_id = get_config_int(topic_key, 0, fallback_env=topic_key.upper()) if topic_key else get_config_int("general_topic_id", 1)
    stamped_text = attach_ist_timestamp(text)
    sent_msg = None

    dedicated_channel = None
    if target_chat_key in ("request_log_chat_id", "request_channel_id") or topic_key == "request_log_topic_id":
        dedicated_channel = get_config("request_channel_id") or get_config("request_log_chat_id")
    elif topic_key == "index_log_topic_id" or target_chat_key == "index_channel_id":
        dedicated_channel = get_config("index_channel_id")

    if dedicated_channel and str(dedicated_channel) != str(log_group):
        try:
            kw = {"chat_id": int(dedicated_channel), "text": stamped_text, "parse_mode": "HTML"}
            if reply_markup: kw["reply_markup"] = reply_markup
            sent_msg = await bot.send_message(**kw)
        except Exception as e:
            logger.error(f"[LOG CHANNEL ERROR] {e}")

    if log_group:
        try:
            kw = {"chat_id": int(log_group), "text": stamped_text, "parse_mode": "HTML"}
            if topic_id > 0: kw["message_thread_id"] = topic_id
            if reply_markup: kw["reply_markup"] = reply_markup
            msg = await bot.send_message(**kw)
            if not sent_msg: sent_msg = msg
        except Exception:
            try:
                kw = {"chat_id": int(log_group), "text": f"⚠️ <i>[Fallback]</i>\n\n{stamped_text}", "parse_mode": "HTML"}
                if reply_markup: kw["reply_markup"] = reply_markup
                msg = await bot.send_message(**kw)
                if not sent_msg: sent_msg = msg
            except Exception as e2:
                await _notify_owners(bot, f"❌ <b>Log Delivery Failed:</b> <code>{e2}</code>\n\n{stamped_text}")

    return sent_msg
