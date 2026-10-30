"""Search topic: the one forum topic where members search by simply typing.

Public bot  -> topic PUBLIC_SEARCH_TOPIC_ID inside PUBLIC_SUPPORT_CHAT_ID
Testing bot -> topic TESTING_SEARCH_TOPIC_ID inside TESTING_LOGGER_GROUP_ID

Inside the topic: any plain text message is a search query; any command is
deleted and the sender is told the topic is for searching only.
"""
import asyncio
import html
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, filters

from modules.search.handlers import is_search_topic_message, perform_search

logger = logging.getLogger(__name__)

NOTICE_SECONDS = 12
_bg_tasks = set()


class _SearchTopicFilter(filters.MessageFilter):
    """Matches human messages posted in the configured search topic."""

    def __init__(self):
        super().__init__(name="SearchTopic")

    def filter(self, message):
        if message is None or not is_search_topic_message(message):
            return False
        sender = message.from_user
        if sender is None or sender.is_bot:
            return False
        return True


SEARCH_TOPIC_FILTER = _SearchTopicFilter()


async def _delete_later(bot, chat_id: int, message_id: int, delay: int):
    try:
        await asyncio.sleep(delay)
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


def _spawn(coro):
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def search_topic_command_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes any command sent in the search topic and prompts: topic is for search only."""
    msg = update.effective_message
    user = update.effective_user
    if not msg:
        return
    try:
        await msg.delete()
    except Exception as e:
        logger.warning("Could not delete command in search topic (bot needs Delete Messages right): %s", e)
    name = html.escape(user.first_name or "there") if user else "there"
    try:
        notice = await context.bot.send_message(
            chat_id=msg.chat_id,
            message_thread_id=msg.message_thread_id,
            text=(
                f"🔍 <b>{name}</b>, this topic is for <b>book search only</b>.\n"
                "Commands are not allowed here. Just type the book title or author."
            ),
            parse_mode=ParseMode.HTML,
        )
        _spawn(_delete_later(context.bot, notice.chat_id, notice.message_id, NOTICE_SECONDS))
    except Exception as e:
        logger.warning("Could not send search-topic notice: %s", e)


async def search_topic_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Any plain text in the search topic is treated as the search query."""
    msg = update.effective_message
    if not msg or not msg.text:
        return
    query = msg.text.strip()
    if not query:
        return
    await perform_search(update, context, query, 1)
