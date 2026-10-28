import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.editscript.handlers import handle_customize_input
from modules.indexing.book_index import handle_index_wizard_message
from modules.request.handlers import handle_manual_request_message
from modules.search.handlers import perform_search
from modules.database.config_db import get_group_topics_db
from modules.log.logger import get_ist_str

logger = logging.getLogger(__name__)

async def handle_normal_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    chat = update.effective_chat
    user = update.effective_user
    uid = user.id if user else 0
    text = (msg.text or "").strip()

    logger.info(f"[TEXT] Chat={chat.id} ({chat.type}) | User={uid} | Text='{text[:40]}' | IST={get_ist_str()}")

    if await handle_customize_input(update, context):
        return
    if await handle_index_wizard_message(update, context):
        return
    if await handle_manual_request_message(update, context):
        return

    # Photos / videos / forwards only matter to the wizards above; nothing else to do with them.
    if not text:
        return

    is_search_group = False
    if chat.type in ("group", "supergroup"):
        g_cfg = get_group_topics_db(chat.id)
        if g_cfg:
            s_tid = int(g_cfg.get("search_topic_id") or 0)
            if s_tid > 0 and (msg.message_thread_id or 1) == s_tid:
                is_search_group = True

    # Search directly in DM or inside the registered Group Search Topic
    if (chat.type == "private" or is_search_group) and len(text) >= 2 and not text.startswith("/"):
        await perform_search(update, context, text, 1)
        return

    if chat.type == "private":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 Search Library", callback_data="search_menu"), InlineKeyboardButton("📖 Help Menu", callback_data="help_button")],
            [InlineKeyboardButton("🛡️ Support", callback_data="support_start_quiz")],
        ])
        await msg.reply_text("🤖 Use <code>/search &lt;title&gt;</code>, <code>/request &lt;title&gt;</code>, or <code>/help</code>.", parse_mode="HTML", reply_markup=kb)
