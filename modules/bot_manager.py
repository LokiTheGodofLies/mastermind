import os
from typing import List

from telegram import Bot


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
    """Return the configured helper bot tokens, preferring a dedicated list.

    Supported environment variables: HELPER_BOT_TOKENS, DELIVERY_BOT_TOKENS,
    FILE_BOT_TOKENS, BOT_TOKENS.
    """
    candidates = [
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
    if primary:
        return [primary]

    return []


def get_selected_helper_bot_token() -> str:
    """Choose a helper bot token in round-robin order.

    This allows a list of helper bots to be configured and rotated automatically,
    while falling back to the primary bot if no helper-bot pool is configured.
    """
    tokens = get_helper_bot_tokens()
    if not tokens:
        return ""

    state = getattr(get_selected_helper_bot_token, "_state", 0)
    token = tokens[state % len(tokens)]
    get_selected_helper_bot_token._state = state + 1
    return token


def get_helper_bot() -> Bot:
    token = get_selected_helper_bot_token()
    if not token:
        raise ValueError("No helper bot token configured")
    return Bot(token=token)
