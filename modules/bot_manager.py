import os
import asyncio
from typing import List, Dict, Optional
from telegram import Bot
from modules.database.config_db import get_config

_BOT_CACHE: Dict[str, Dict] = {}


def _normalize_bot_tokens(raw_value: str | None) -> List[str]:
    if not raw_value:
        return []
    tokens: List[str] = []
    for part in raw_value.replace(";", ",").split(","):
        token = part.strip().strip('"').strip("'")
        if token and ":" in token:
            tokens.append(token)
    return tokens


def get_helper_bot_tokens() -> List[str]:
    candidates = [
        get_config("helper_bot_tokens", default=""),
        os.getenv("HELPER_BOT_TOKENS"),
        os.getenv("DELIVERY_BOT_TOKENS"),
        os.getenv("FILE_BOT_TOKENS"),
        os.getenv("BOT_TOKENS"),
    ]
    for raw in candidates:
        tokens = _normalize_bot_tokens(raw)
        if tokens:
            return tokens

    primary = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
    return [primary] if primary else []


async def get_bot_info_by_token(token: str) -> Dict:
    """Auto-fetches bot username and title via Telegram get_me() with in-memory caching."""
    if token in _BOT_CACHE:
        return _BOT_CACHE[token]
    bot = Bot(token=token)
    try:
        me = await bot.get_me()
        info = {
            "token": token,
            "id": me.id,
            "username": me.username or "",
            "title": me.first_name or "Helper Bot",
            "bot": bot,
        }
        _BOT_CACHE[token] = info
        return info
    except Exception as e:
        return {
            "token": token,
            "id": 0,
            "username": "",
            "title": "Helper Bot",
            "bot": bot,
            "error": str(e),
        }


def get_selected_helper_bot_token() -> str:
    tokens = get_helper_bot_tokens()
    if not tokens:
        return ""
    state = getattr(get_selected_helper_bot_token, "_state", 0)
    token = tokens[state % len(tokens)]
    get_selected_helper_bot_token._state = state + 1
    return token


async def get_selected_helper_bot_details() -> Dict:
    """Returns a dict with token, username, title, and live Bot instance for the chosen helper bot."""
    token = get_selected_helper_bot_token()
    if not token:
        raise ValueError("No helper bot token configured")
    return await get_bot_info_by_token(token)


def get_helper_bot() -> Bot:
    token = get_selected_helper_bot_token()
    if not token:
        raise ValueError("No helper bot token configured")
    return Bot(token=token)
