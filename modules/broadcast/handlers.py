import asyncio
import html
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden, BadRequest
from telegram.ext import ContextTypes
from config import logger_group_id, log_topic
from modules.database.user_db import (
    is_admin_or_god,
    get_all_users_for_broadcast_db,
    get_all_chats_db,
    get_users_by_role_db,
    record_user_blocked_bot_db,
)
from modules.database.config_db import get_config_bool
from modules.log.startup_log import report_error, _report_user_block

logger = logging.getLogger(__name__)

# Active broadcast cancellation token
_active_broadcast_cancelled = False


async def cancelbroadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _active_broadcast_cancelled
    user_id = update.effective_user.id
    if not is_admin_or_god(user_id):
        await update.effective_message.reply_text("⛔ Access denied. Only Admins and Owners can stop broadcasts.")
        return
    _active_broadcast_cancelled = True
    await update.effective_message.reply_text("🛑 <b>Cancellation requested.</b> The current broadcast loop will halt after the current batch.", parse_mode="HTML")


async def _execute_broadcast(context: ContextTypes.DEFAULT_TYPE, sender_id: int, target: str, msg_text: str, should_pin: bool, status_msg):
    global _active_broadcast_cancelled
    _active_broadcast_cancelled = False

    # Collect target recipient list
    recipients = []
    target_lower = target.lower()

    if target_lower in ("groups", "group"):
        chats = get_all_chats_db()
        recipients = [c["chat_id"] for c in chats if c["chat_type"] in ("group", "supergroup")]
    elif target_lower in ("channels", "channel"):
        chats = get_all_chats_db("channel")
        recipients = [c["chat_id"] for c in chats]
    elif target_lower in ("everyone", "all_users", "users", "all"):
        users = get_all_users_for_broadcast_db()
        recipients = [u["user_id"] for u in users]
    elif target_lower in ("moderators", "mods"):
        users = get_users_by_role_db("Moderator")
        recipients = [u["user_id"] for u in users]
    elif target_lower in ("volunteers", "vols"):
        users = get_users_by_role_db("Volunteer")
        recipients = [u["user_id"] for u in users]
    elif target_lower in ("promoters", "promos"):
        users = get_users_by_role_db("Promoter")
        recipients = [u["user_id"] for u in users]
    else:
        users = get_all_users_for_broadcast_db()
        recipients = [u["user_id"] for u in users]

    total = len(recipients)
    if total == 0:
        await status_msg.edit_text(f"⚠️ No recipients found for target: <code>{html.escape(target)}</code>", parse_mode="HTML")
        return

    sent = 0
    failed = 0
    pinned = 0
    bot = context.bot
    bot_user = await bot.get_me()

    for idx, chat_id in enumerate(recipients, 1):
        if _active_broadcast_cancelled:
            await status_msg.edit_text(
                f"🛑 <b>Broadcast Cancelled by Admin</b>\n\n"
                f"🎯 <b>Target:</b> <code>{html.escape(target)}</code>\n"
                f"👥 <b>Processed:</b> <code>{idx - 1}/{total}</code>\n"
                f"✅ <b>Delivered:</b> <code>{sent}</code>\n"
                f"❌ <b>Failed:</b> <code>{failed}</code>\n"
                f"📌 <b>Pinned:</b> <code>{pinned}</code>",
                parse_mode="HTML",
            )
            return

        try:
            sent_msg = await bot.send_message(chat_id=chat_id, text=msg_text, parse_mode="HTML", disable_web_page_preview=True)
            sent += 1
            if should_pin:
                try:
                    await bot.pin_chat_message(chat_id=chat_id, message_id=sent_msg.message_id, disable_notification=False)
                    pinned += 1
                except Exception as pin_err:
                    logger.debug("Could not pin broadcast in %s: %s", chat_id, pin_err)
        except Forbidden as f_err:
            failed += 1
            record_user_blocked_bot_db(chat_id, bot_user.username)
            if "blocked by the user" in str(f_err).lower():
                try:
                    await _report_user_block(context.application, chat_id, "Unknown", None, bot_user.first_name, bot_user.username)
                except Exception:
                    pass
        except Exception as send_err:
            failed += 1
            logger.debug("Broadcast send error to %s: %s", chat_id, send_err)

        if idx % 10 == 0 or idx == total:
            try:
                await status_msg.edit_text(
                    f"📡 <b>Broadcasting in Progress...</b>\n\n"
                    f"🎯 <b>Target:</b> <code>{html.escape(target)}</code>\n"
                    f"⏳ <b>Progress:</b> <code>{idx}/{total}</code> ({(idx / total) * 100:.1f}%)\n"
                    f"✅ <b>Sent:</b> <code>{sent}</code> | ❌ <b>Failed:</b> <code>{failed}</code>"
                    + (f" | 📌 <b>Pinned:</b> <code>{pinned}</code>" if should_pin else ""),
                    parse_mode="HTML",
                )
            except Exception:
                pass

        await asyncio.sleep(0.05)

    summary = (
        f"📢 <b>Broadcast Completed</b>\n\n"
        f"🎯 <b>Target:</b> <code>{html.escape(target)}</code>\n"
        f"👥 <b>Total Recipients:</b> <code>{total}</code>\n"
        f"✅ <b>Delivered:</b> <code>{sent}</code>\n"
        f"❌ <b>Failed:</b> <code>{failed}</code>\n"
        f"📌 <b>Pinned:</b> <code>{pinned}</code>"
    )
    await status_msg.edit_text(summary, parse_mode="HTML")


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user_id = update.effective_user.id
    if not is_admin_or_god(user_id):
        await msg.reply_text("⛔ Access denied. Only Admins and Owners can broadcast.")
        return

    if not get_config_bool("is_broadcast_enabled", True):
        await msg.reply_text("⚠️ Broadcasting is currently disabled in config (<code>is_broadcast_enabled=false</code>).", parse_mode="HTML")
        return

    cmd = msg.text.split()[0].lstrip("/").lower()
    is_pin = "pin" in cmd

    if not context.args:
        help_text = (
            "📢 <b>Broadcast Engine</b>\n\n"
            "<b>Usage:</b>\n"
            "• <code>/broadcast &lt;target&gt; &lt;message&gt;</code>\n"
            "• <code>/pinbroadcast &lt;target&gt; &lt;message&gt;</code>\n"
            "• <code>/cancelbroadcast</code> - Stop active broadcast\n\n"
            "<b>Targets:</b>\n"
            "• <code>everyone</code> or <code>users</code> - All registered bot users\n"
            "• <code>groups</code> - All registered groups\n"
            "• <code>channels</code> - All registered channels\n"
            "• <code>moderators</code>, <code>volunteers</code>, <code>promoters</code>"
        )
        await msg.reply_text(help_text, parse_mode="HTML")
        return

    target = context.args[0].lower()
    broadcast_text = " ".join(context.args[1:])

    # Support replied-to message text if none provided in args
    if not broadcast_text and msg.reply_to_message:
        broadcast_text = msg.reply_to_message.text or msg.reply_to_message.caption or ""

    if not broadcast_text:
        await msg.reply_text("⚠️ Please provide a message text or reply to a message to broadcast.")
        return

    context.user_data["pending_broadcast"] = {
        "target": target,
        "text": broadcast_text,
        "pin": is_pin,
    }

    pin_label = " (With Pin)" if is_pin else ""
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm Broadcast" + pin_label, callback_data="bc_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="bc_cancel"),
        ]
    ])
    preview = (
        f"📢 <b>Broadcast Preview{pin_label}</b>\n\n"
        f"🎯 <b>Target:</b> <code>{html.escape(target)}</code>\n"
        f"📌 <b>Pin Message:</b> <code>{Yes if is_pin else No}</code>\n\n"
        f"💬 <b>Message Preview:</b>\n<blockquote>{html.escape(broadcast_text)}</blockquote>\n\n"
        f"<i>Press Confirm to begin broadcasting.</i>"
    )
    await msg.reply_text(preview, parse_mode="HTML", reply_markup=kb)


async def broadcast_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return

    user_id = q.from_user.id
    if not is_admin_or_god(user_id):
        await q.answer("⛔ Access denied.", show_alert=True)
        return

    await q.answer()
    data = q.data

    if data == "bc_cancel":
        context.user_data.pop("pending_broadcast", None)
        await q.message.edit_text("❌ Broadcast cancelled.")
        return

    if data == "bc_confirm":
        pending = context.user_data.pop("pending_broadcast", None)
        if not pending:
            await q.message.edit_text("⚠️ No pending broadcast found or it has expired.")
            return

        status_msg = await q.message.edit_text("⏳ Initializing broadcast...")
        asyncio.create_task(
            _execute_broadcast(
                context=context,
                sender_id=user_id,
                target=pending["target"],
                msg_text=pending["text"],
                should_pin=pending.get("pin", False),
                status_msg=status_msg,
            )
        )
