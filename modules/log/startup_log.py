import logging
from modules.database.config_db import get_config, get_config_int, get_template, format_template_string
from modules.database.user_db import get_owner_ids

logger = logging.getLogger(__name__)


async def _notify_owners(bot, text: str):
    for oid in get_owner_ids():
        try:
            await bot.send_message(chat_id=int(oid), text=text, parse_mode="HTML")
        except Exception:
            pass


async def send_error_alert(bot, error_text: str):
    """Sends deployment/runtime configuration errors to the Errors Topic of the Log Group AND Owner PM."""
    log_group = get_config("general_log_group_id", fallback_env="LOGGER_GROUP_ID") or get_config("admin_log_group_id")
    err_topic = get_config_int("error_log_topic_id", 0) or get_config_int("general_topic_id", 1)
    formatted = f"🚨 <b>Bot Configuration / Deployment Alert</b>\n\n{error_text}"

    if log_group:
        try:
            kwargs = {"chat_id": int(log_group), "text": formatted, "parse_mode": "HTML"}
            if err_topic > 0:
                kwargs["message_thread_id"] = err_topic
            await bot.send_message(**kwargs)
        except Exception:
            try:
                await bot.send_message(chat_id=int(log_group), text=formatted, parse_mode="HTML")
            except Exception:
                pass
    await _notify_owners(bot, formatted)


async def send_log_with_fallback(bot, text: str, target_chat_key: str = "admin_log_group_id", topic_key: str = None, reply_markup=None):
    """Supports dual-routing (Log Group Topic + Dedicated Channel for request/index) and fallback to General Topic (1) & Owner PM."""
    log_group = get_config("general_log_group_id", fallback_env="LOGGER_GROUP_ID") or get_config("admin_log_group_id")
    topic_id = get_config_int(topic_key, 0, fallback_env=topic_key.upper()) if topic_key else get_config_int("general_topic_id", 1)
    sent_msg = None

    # Check dual routing for Request Logs and Index Logs
    dedicated_channel = None
    if target_chat_key in ("request_log_chat_id", "request_channel_id") or topic_key == "request_log_topic_id":
        dedicated_channel = get_config("request_channel_id") or get_config("request_log_chat_id")
        if not topic_key:
            topic_id = get_config_int("request_log_topic_id", 0)
    elif topic_key == "index_log_topic_id" or target_chat_key == "index_channel_id":
        dedicated_channel = get_config("index_channel_id")

    # 1. Send to dedicated channel if configured
    if dedicated_channel and str(dedicated_channel) != str(log_group):
        try:
            kw = {"chat_id": int(dedicated_channel), "text": text, "parse_mode": "HTML"}
            if reply_markup:
                kw["reply_markup"] = reply_markup
            sent_msg = await bot.send_message(**kw)
        except Exception as e:
            await send_error_alert(bot, f"Failed sending to dedicated channel <code>{dedicated_channel}</code>: <code>{e}</code>")

    # 2. Send to Log Group topic if configured (or if no dedicated channel was used)
    if log_group and (topic_id > 0 or not dedicated_channel):
        try:
            kw = {"chat_id": int(log_group), "text": text, "parse_mode": "HTML"}
            if topic_id > 0:
                kw["message_thread_id"] = topic_id
            if reply_markup:
                kw["reply_markup"] = reply_markup
            msg = await bot.send_message(**kw)
            if not sent_msg:
                sent_msg = msg
        except Exception as e:
            # Fallback to General Topic (1) or plain group
            try:
                kw = {"chat_id": int(log_group), "text": f"⚠️ <i>[Fallback General Topic]</i>\n\n{text}", "parse_mode": "HTML"}
                if reply_markup:
                    kw["reply_markup"] = reply_markup
                msg = await bot.send_message(**kw)
                if not sent_msg:
                    sent_msg = msg
            except Exception as e2:
                await _notify_owners(bot, f"❌ <b>Log Delivery Failed:</b> <code>{e2}</code>\n\n{text}")

    if not log_group and not dedicated_channel:
        await _notify_owners(bot, f"⚠️ <b>No Log Destination Configured!</b>\n\n{text}")
    return sent_msg


async def validate_deployment_and_topics(bot):
    """Checks required variables and verifies Log Group forum topics on startup."""
    missing_vars = []
    for req_key in ("storage_channel_id", "posting_channel_id", "general_log_group_id"):
        if not get_config(req_key):
            missing_vars.append(req_key)

    log_group = get_config("general_log_group_id", fallback_env="LOGGER_GROUP_ID")
    topic_warnings = []

    if log_group:
        try:
            chat = await bot.get_chat(int(log_group))
            if not getattr(chat, "is_forum", False):
                topic_warnings.append(
                    "⚠️ <b>Topics are NOT enabled in your Log Group!</b>\n"
                    "Please enable <b>Topics</b> in the Log Group settings and use <code>/settopic</code> inside each topic to configure:\n"
                    "• <code>/settopic general</code> (Topic ID 1)\n"
                    "• <code>/settopic index logs</code>\n"
                    "• <code>/settopic user logs</code>\n"
                    "• <code>/settopic group logs</code>\n"
                    "• <code>/settopic channel logs</code>\n"
                    "• <code>/settopic request logs</code>\n"
                    "• <code>/settopic errors</code>"
                )
            else:
                req_chan = get_config("request_channel_id")
                idx_chan = get_config("index_channel_id")
                for t_key, label in [
                    ("user_log_topic_id", "User Logs (/settopic user logs)"),
                    ("group_log_topic_id", "Group Logs (/settopic group logs)"),
                    ("channel_log_topic_id", "Channel Logs (/settopic channel logs)"),
                    ("error_log_topic_id", "Error Logs (/settopic errors)"),
                ]:
                    if get_config_int(t_key, 0) <= 0:
                        topic_warnings.append(f"• Missing topic: <b>{label}</b>")
                if not idx_chan and get_config_int("index_log_topic_id", 0) <= 0:
                    topic_warnings.append("• Missing <b>Index Logs topic</b> (and no Index Channel set)")
                if not req_chan and get_config_int("request_log_topic_id", 0) <= 0:
                    topic_warnings.append("• Missing <b>Request Logs topic</b> (and no Request Channel set)")
        except Exception as e:
            topic_warnings.append(f"⚠️ Bot cannot access Log Group (<code>{log_group}</code>): <code>{e}</code>")

    if missing_vars or topic_warnings:
        parts = []
        if missing_vars:
            parts.append("❌ <b>Missing Required Variables:</b>\n" + "\n".join(f"• <code>{k}</code>" for k in missing_vars))
        if topic_warnings:
            parts.append("📋 <b>Log Group Topic Checks:</b>\n" + "\n".join(topic_warnings))
        await send_error_alert(bot, "\n\n".join(parts))


async def send_startup_notification(application):
    try:
        bot_info = await application.bot.get_me()
        tpl = get_template("startup_log")
        raw = tpl.get("text") or "🔄 <b>Bot Restarted Successfully</b>\n🤖 <b>{bot_title}</b> (@{bot_username}) is online at {date} {time}"
        startup_text = format_template_string(raw, {"bot_title": bot_info.first_name or "Mastermind", "bot_username": bot_info.username or "Bot"})
        await send_log_with_fallback(application.bot, startup_text, "general_log_group_id", "general_topic_id")
        await validate_deployment_and_topics(application.bot)
    except Exception as e:
        print(f"[STARTUP LOG WARNING]: {e}")
