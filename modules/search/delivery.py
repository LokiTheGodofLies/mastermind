"""Dual file delivery via Helper Bots (Posting Channel with Auto-Delete + Helper Bot PM)."""
import asyncio
import html
import logging
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import (
    auto_delete_seconds,
    helper_bot_tokens,
    posting_channel_id,
    storage_group_id,
)
from modules.database.file_db import get_file_by_id_db, update_storage_message_id_db
from modules.log.startup_log import report_error

logger = logging.getLogger(__name__)

_HELPER_META_CACHE: dict[str, dict] = {}
_POSTING_CHAT_CACHE: dict[int, str | None] = {}
_rr_counter = 0


async def _get_helper_bot_meta(token: str) -> dict | None:
    """Resolves and caches helper bot username and id from its token via get_me()."""
    if token in _HELPER_META_CACHE:
        return _HELPER_META_CACHE[token]
    try:
        async with Bot(token) as hb:
            me = await hb.get_me()
        meta = {
            "token": token,
            "id": me.id,
            "username": me.username or "",
            "first_name": me.first_name or "Helper Bot",
        }
        _HELPER_META_CACHE[token] = meta
        return meta
    except Exception as exc:
        logger.warning("Failed to resolve helper bot token (…%s): %s", token[-4:], exc)
        return None


async def select_helper_bot(fallback_bot) -> dict:
    """Selects one reachable helper bot (round-robin) and returns its token and username."""
    global _rr_counter
    tokens = helper_bot_tokens()
    if tokens:
        n = len(tokens)
        start = _rr_counter % n
        _rr_counter += 1
        for offset in range(n):
            tok = tokens[(start + offset) % n]
            meta = await _get_helper_bot_meta(tok)
            if meta and meta.get("username"):
                return meta

    # Fallback to main bot if no helper bot tokens are configured or reachable
    username = getattr(fallback_bot, "username", None)
    if not username:
        try:
            me = await fallback_bot.get_me()
            username = me.username
        except Exception:
            username = ""
    return {
        "token": None,
        "id": getattr(fallback_bot, "id", 0),
        "username": username or "",
        "first_name": "Main Bot",
    }


def build_channel_message_link(chat_id: int, message_id: int, chat_username: str | None = None) -> str:
    """Builds a direct Telegram deep link to a specific message inside the posting channel."""
    if chat_username:
        return f"https://t.me/{chat_username.lstrip('@')}/{message_id}"
    cid_str = str(chat_id)
    if cid_str.startswith("-100"):
        internal_id = cid_str[4:]
    else:
        internal_id = cid_str.lstrip("-")
    return f"https://t.me/c/{internal_id}/{message_id}"


async def _get_posting_channel_username(bot, chat_id: int) -> str | None:
    if chat_id in _POSTING_CHAT_CACHE:
        return _POSTING_CHAT_CACHE[chat_id]
    try:
        chat = await bot.get_chat(chat_id)
        uname = getattr(chat, "username", None)
        _POSTING_CHAT_CACHE[chat_id] = uname
        return uname
    except Exception:
        return None


async def _auto_delete_message(token: str | None, fallback_bot, chat_id: int, message_id: int, delay: int):
    """Deletes a message from the posting channel after `delay` seconds using the same helper bot."""
    await asyncio.sleep(max(1, delay))
    try:
        if token:
            async with Bot(token) as hb:
                await hb.delete_message(chat_id=chat_id, message_id=message_id)
        elif fallback_bot:
            await fallback_bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as exc:
        logger.warning("Auto-delete failed in chat %s for msg %s: %s", chat_id, message_id, exc)


async def _ensure_storage_message_id(main_bot, row) -> int | None:
    """Ensures the file has a valid message inside STORAGE_GROUP_ID so helper bots can copy_message it."""
    storage_id = storage_group_id()
    storage_msg_id = row["storage_message_id"]
    if storage_msg_id and storage_id:
        return int(storage_msg_id)

    file_id = row["file_id"]
    if not file_id or not storage_id:
        return None

    try:
        cap = f"📁 <b>{html.escape(row['file_name'] or 'File')}</b>"
        sent = await main_bot.send_document(
            chat_id=int(storage_id),
            document=file_id,
            caption=cap,
            parse_mode="HTML",
        )
        update_storage_message_id_db(row["id"], sent.message_id)
        return sent.message_id
    except Exception as exc:
        logger.warning("Could not backfill storage_message_id for row %s: %s", row["id"], exc)
        return None


async def _copy_with_bot(token: str | None, fallback_bot, target_chat_id: int, from_chat_id: int, message_id: int):
    """Copies a message from STORAGE_GROUP_ID to target_chat_id using the selected helper bot."""
    if token:
        async with Bot(token) as hb:
            return await hb.copy_message(
                chat_id=int(target_chat_id),
                from_chat_id=int(from_chat_id),
                message_id=int(message_id),
            )
    return await fallback_bot.copy_message(
        chat_id=int(target_chat_id),
        from_chat_id=int(from_chat_id),
        message_id=int(message_id),
    )


async def deliver_file_dual(update: Update, context: ContextTypes.DEFAULT_TYPE, row_id: int):
    """
    Executes dual file delivery when a user clicks a search result:
      1. Selects ONE helper bot (resolving its @username dynamically from HELPER_BOT_TOKENS).
      2. Sends the file via that helper bot to POSTING_CHANNEL_ID with 5-minute auto-delete.
      3. Sends the file via that SAME helper bot to the user's PM (if they have started that helper bot).
      4. Replies via the main bot with instructions to start that helper bot (@username) or
         click the link to get the file from the posting channel, reminding them to forward
         the file to Saved Messages before it is auto-deleted in 5 minutes.
    """
    query = update.callback_query
    user = update.effective_user
    msg = update.effective_message
    if not msg or not user:
        return

    row = get_file_by_id_db(int(row_id))
    if not row:
        await msg.reply_text("❌ File record no longer found in database.")
        return

    storage_id = storage_group_id()
    post_chan_id = posting_channel_id()
    delete_secs = auto_delete_seconds()
    delete_mins = max(1, round(delete_secs / 60))

    storage_msg_id = await _ensure_storage_message_id(context.bot, row)
    if not storage_msg_id or not storage_id:
        await msg.reply_text("❌ Storage group or file message is not available.")
        return

    helper = await select_helper_bot(context.bot)
    helper_token = helper.get("token")
    helper_username = (helper.get("username") or "").lstrip("@")

    # 1. Send file to Posting Channel with auto-delete using the selected helper bot
    posting_link = None
    if post_chan_id:
        try:
            posted_msg = await _copy_with_bot(
                helper_token,
                context.bot,
                int(post_chan_id),
                int(storage_id),
                int(storage_msg_id),
            )
            chan_uname = await _get_posting_channel_username(context.bot, int(post_chan_id))
            posting_link = build_channel_message_link(int(post_chan_id), posted_msg.message_id, chan_uname)
            asyncio.create_task(
                _auto_delete_message(
                    helper_token,
                    context.bot,
                    int(post_chan_id),
                    posted_msg.message_id,
                    delete_secs,
                )
            )
        except Exception as exc:
            logger.error("Helper bot posting channel delivery failed: %s", exc)
            err_details = f"🚨 <b>Posting Channel Delivery Error</b>

• Target Channel: <code>{post_chan_id}</code>
• Error: <code>{html.escape(str(exc))}</code>
• Helper Bot: @{helper_username}

<i>Ensure @{helper_username} is an Administrator with Post & Delete rights in the posting channel!</i>"
            try:
                await report_error(context.application, err_details, title="Posting Channel Delivery Error")
            except Exception:
                pass

    # 2. Send file to User's Bot PM using the SAME selected helper bot
    pm_delivered = False
    try:
        await _copy_with_bot(
            helper_token,
            context.bot,
            int(user.id),
            int(storage_id),
            int(storage_msg_id),
        )
        pm_delivered = True
    except Exception as exc:
        logger.info("Helper bot PM delivery pending user /start (%s): %s", user.id, exc)

    # 3. Send Main Bot notification message with helper bot @username & posting channel link
    file_name_esc = html.escape(row["file_name"] or f"File #{row_id}")
    helper_start_url = (
        f"https://t.me/{helper_username}?start=dl_{row_id}"
        if helper_username
        else None
    )

    pm_status_line = (
        f"✅ <b>Sent to your PM via @{html.escape(helper_username)}!</b>\n\n"
        if (pm_delivered and helper_username)
        else ""
    )

    if helper_username and posting_link:
        text = (
            f"📁 <b>File:</b> <code>{file_name_esc}</code>\n\n"
            f"{pm_status_line}"
            f"🤖 You can start the below bot (<a href=\"{helper_start_url}\">@{html.escape(helper_username)}</a>) "
            f"if you haven't started it already to get the file in PM, or you can "
            f"<a href=\"{posting_link}\"><b>click here</b></a> and get the file from the posting channel.\n\n"
            f"⚠️ <b>Don't forget to forward the files to your Saved Messages — "
            f"it will be automatically deleted in {delete_mins} mins!</b>"
        )
    elif helper_username:
        text = (
            f"📁 <b>File:</b> <code>{file_name_esc}</code>\n\n"
            f"{pm_status_line}"
            f"🤖 You can start the below bot (<a href=\"{helper_start_url}\">@{html.escape(helper_username)}</a>) "
            f"if you haven't started it already to receive your file in PM.\n\n"
            f"⚠️ <b>Don't forget to forward the files to your Saved Messages — "
            f"it will be automatically deleted in {delete_mins} mins!</b>"
        )
    elif posting_link:
        text = (
            f"📁 <b>File:</b> <code>{file_name_esc}</code>\n\n"
            f"📢 You can <a href=\"{posting_link}\"><b>click here</b></a> and get the file from the posting channel.\n\n"
            f"⚠️ <b>Don't forget to forward the files to your Saved Messages — "
            f"it will be automatically deleted in {delete_mins} mins!</b>"
        )
    else:
        text = (
            "❌ Could not deliver the file. Please ensure HELPER_BOT_TOKENS and POSTING_CHANNEL_ID "
            "are configured and the helper bot is an admin in the Storage Group and Posting Channel."
        )

    buttons = []
    if helper_username and helper_start_url:
        buttons.append([InlineKeyboardButton(f"🤖 Start @{helper_username}", url=helper_start_url)])
    if posting_link:
        buttons.append([InlineKeyboardButton("📥 Click Here (Get File from Posting Channel)", url=posting_link)])

    markup = InlineKeyboardMarkup(buttons) if buttons else None
    await msg.reply_text(
        text,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=markup,
    )


async def handle_deeplink_file_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: str):
    """Handles `/start dl_<row_id>` on helper bots (or main bot) to immediately send the requested file in PM."""
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return

    try:
        row_id = int(payload.replace("dl_", "", 1))
    except ValueError:
        await msg.reply_text("⚠️ Invalid file link.")
        return

    row = get_file_by_id_db(row_id)
    if not row:
        await msg.reply_text("❌ File record no longer found in database.")
        return

    storage_id = storage_group_id()
    storage_msg_id = row["storage_message_id"]
    delete_mins = max(1, round(auto_delete_seconds() / 60))

    if storage_id and storage_msg_id:
        try:
            await context.bot.copy_message(
                chat_id=user.id,
                from_chat_id=int(storage_id),
                message_id=int(storage_msg_id),
            )
            await msg.reply_text(
                f"✅ Here is your requested file!\n\n"
                f"⚠️ <i>Don't forget to forward the files to your <b>Saved Messages</b> "
                f"(posting channel copies are automatically deleted in {delete_mins} mins).</i>",
                parse_mode="HTML",
            )
            return
        except Exception as exc:
            logger.warning("Deep-link copy_message failed: %s", exc)

    await msg.reply_text("❌ Could not retrieve the file from storage. Please try clicking the search result again.")
