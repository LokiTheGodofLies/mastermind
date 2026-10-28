"""Process-wide python-telegram-bot patches.

Telegram answers ``BadRequest: Message is not modified`` whenever a menu is re-rendered
with identical content (for example a double tap on an inline button).  That is harmless,
so the edit helpers are wrapped once here and the error is swallowed everywhere.
"""
import logging

import telegram
from telegram.error import BadRequest

logger = logging.getLogger(__name__)
_APPLIED = False


def _is_not_modified(exc: BadRequest) -> bool:
    return "message is not modified" in str(exc).lower()


def apply_patches() -> None:
    """Install the patches (idempotent)."""
    global _APPLIED
    if _APPLIED:
        return
    _APPLIED = True

    orig_msg_edit_text = telegram.Message.edit_text
    orig_msg_edit_rm = telegram.Message.edit_reply_markup
    orig_bot_edit_text = telegram.Bot.edit_message_text

    async def safe_msg_edit_text(self, *args, **kwargs):
        try:
            return await orig_msg_edit_text(self, *args, **kwargs)
        except BadRequest as exc:
            if _is_not_modified(exc):
                return self
            raise

    async def safe_msg_edit_rm(self, *args, **kwargs):
        try:
            return await orig_msg_edit_rm(self, *args, **kwargs)
        except BadRequest as exc:
            if _is_not_modified(exc):
                return self
            raise

    async def safe_bot_edit_text(self, *args, **kwargs):
        try:
            return await orig_bot_edit_text(self, *args, **kwargs)
        except BadRequest as exc:
            if _is_not_modified(exc):
                return None
            raise

    telegram.Message.edit_text = safe_msg_edit_text
    telegram.Message.edit_reply_markup = safe_msg_edit_rm
    telegram.Bot.edit_message_text = safe_bot_edit_text


async def global_error_handler(update, context) -> None:
    """Application-level error handler: log everything except the harmless case above."""
    err = context.error
    if isinstance(err, BadRequest) and _is_not_modified(err):
        return
    logger.error("Unhandled exception: %s", err, exc_info=err)
