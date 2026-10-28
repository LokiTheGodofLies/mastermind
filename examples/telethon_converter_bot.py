"""Minimal standalone Telethon bot that reuses the converter engine (see telethon_adapter.py).

    pip install -r requirements.txt -r requirements-telethon.txt
    API_ID=... API_HASH=... BOT_TOKEN=... python examples/telethon_converter_bot.py
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from telethon import TelegramClient  # noqa: E402

from modules.converter.telethon_adapter import register_converter_handlers  # noqa: E402


def main() -> None:
    bot = TelegramClient("converter_bot", int(os.environ["API_ID"]), os.environ["API_HASH"])
    bot.start(bot_token=os.environ["BOT_TOKEN"])
    register_converter_handlers(bot)
    bot.run_until_disconnected()


if __name__ == "__main__":
    main()
