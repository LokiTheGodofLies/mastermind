"""Optional Telethon front-end for the ebook converter.

The main bot is built on python-telegram-bot (``handlers.py``).  This adapter is the Telethon
equivalent - handy if you run a *separate* Telethon bot (MTProto: files up to 2 GB instead of the
Bot API's 20 MB) and want the same conversion engine.  It is NOT imported by ``main.py`` and
Telethon is not a dependency of the main bot; install it with::

    pip install -r requirements-telethon.txt

Usage::

    from telethon import TelegramClient
    from modules.converter.telethon_adapter import register_converter_handlers

    bot = TelegramClient("bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)
    register_converter_handlers(bot)
    bot.run_until_disconnected()
"""
from __future__ import annotations

import secrets
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from telethon import Button, TelegramClient, events

from modules.converter.engine import available_output_choices, convert_file, missing_dependency_hint
from modules.converter.formats import HIGHLIGHTED_FORMATS, detect_input_format, is_supported_input

MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB (raise it freely: MTProto allows up to 2 GB)
QUEUE_TTL = 1800  # seconds a pending request is kept


@dataclass
class PendingRequest:
    workdir: Path
    file_path: Path
    input_fmt: str
    file_name: str
    created_at: float
    force_rtl: bool = False

    def discard(self) -> None:
        shutil.rmtree(self.workdir, ignore_errors=True)


def _cleanup_expired(queue: Dict[str, PendingRequest]) -> None:
    now = time.monotonic()
    for req_id, req in list(queue.items()):
        if now - req.created_at > QUEUE_TTL:
            queue.pop(req_id, None)
            req.discard()


def _build_buttons(req_id: str, req: PendingRequest, enable_kfx: bool) -> List[list]:
    formats = available_output_choices(req.input_fmt, kfx=enable_kfx)
    buttons = [
        Button.inline(f"🔸 {fmt}" if fmt in HIGHLIGHTED_FORMATS else fmt, data=f"ebk_run|{fmt}|{req_id}")
        for fmt in formats
    ]
    rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    rows.append([Button.inline(f"Force RTL: {'ON ✅' if req.force_rtl else 'OFF'}", data=f"ebk_rtl|{req_id}")])
    rows.append([Button.inline("❌ Cancel", data=f"ebk_cancel|{req_id}")])
    return rows


def register_converter_handlers(bot: TelegramClient, *, max_file_size: int = MAX_FILE_SIZE,
                                enable_kfx: bool = False, timeout: int = 300) -> Dict[str, PendingRequest]:
    """Attach the converter handlers to an existing Telethon client; returns the pending queue."""
    queue: Dict[str, PendingRequest] = {}

    @bot.on(events.NewMessage(func=lambda e: bool(e.message.file and e.is_private)))
    @bot.on(events.NewMessage(pattern=r"^/convert$", func=lambda e: e.is_reply))
    async def handle_ebook_file(event):
        message = await event.get_reply_message() if event.pattern_match else event.message
        if not message or not message.file:
            await event.reply("Reply to a supported ebook file with /convert, or send the file here.")
            return

        file_name = message.file.name or ""
        input_fmt = detect_input_format(file_name)
        if not is_supported_input(file_name):
            await event.reply("Unsupported file format.")
            return
        hint = "" if available_output_choices(input_fmt, kfx=enable_kfx) else missing_dependency_hint(input_fmt)
        if hint:
            await event.reply(f"Cannot convert this file here: {hint}")
            return
        if message.file.size and message.file.size > max_file_size:
            await event.reply(f"File is too large (max {max_file_size // (1024 * 1024)} MB).")
            return

        status = await event.reply("Downloading file...")
        workdir = Path(tempfile.mkdtemp(prefix="mm_convert_tg_"))
        downloaded = await message.download_media(workdir / f"input.{input_fmt}")
        if not downloaded:
            shutil.rmtree(workdir, ignore_errors=True)
            await status.edit("Failed to download the file. Please try again.")
            return

        _cleanup_expired(queue)
        req_id = secrets.token_hex(4)
        queue[req_id] = PendingRequest(workdir, Path(downloaded), input_fmt, file_name, time.monotonic())
        await status.edit("Select the target format:", buttons=_build_buttons(req_id, queue[req_id], enable_kfx))

    @bot.on(events.CallbackQuery(pattern=rb"^ebk_rtl\|[0-9a-f]+$"))
    async def handle_toggle_rtl(event):
        req_id = event.data.decode().split("|")[1]
        _cleanup_expired(queue)
        req = queue.get(req_id)
        if not req or not req.file_path.exists():
            await event.answer("Request expired. Please send the file again.", alert=True)
            return
        req.force_rtl = not req.force_rtl
        await event.edit("Select the target format:", buttons=_build_buttons(req_id, req, enable_kfx))

    @bot.on(events.CallbackQuery(pattern=rb"^ebk_cancel\|[0-9a-f]+$"))
    async def handle_cancel(event):
        req = queue.pop(event.data.decode().split("|")[1], None)
        if req:
            req.discard()
        await event.edit("Conversion canceled.")

    @bot.on(events.CallbackQuery(pattern=rb"^ebk_run\|[\w-]+\|[0-9a-f]+$"))
    async def handle_run(event):
        _, out_fmt, req_id = event.data.decode().split("|")
        _cleanup_expired(queue)
        req = queue.pop(req_id, None)
        if not req or not req.file_path.exists():
            await event.answer("Request expired or file missing. Send the file again.", alert=True)
            return
        try:
            status = await event.edit(f"Converting `{req.file_name}` to `{out_fmt}`...")
            result = await convert_file(req.file_path, out_fmt, timeout=timeout,
                                        force_rtl=req.force_rtl, enable_kfx=enable_kfx)
            if result.ok and result.path:
                await status.edit("Uploading converted file...")
                await event.client.send_file(event.chat_id, result.path, reply_to=status, force_document=True)
                await status.delete()
            else:
                await status.edit(f"Failed to convert `{req.file_name}` to `{out_fmt}`.\n\n`{result.error}`")
        finally:
            req.discard()

    return queue
