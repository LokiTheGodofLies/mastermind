"""Drop-in Telethon handler module for converting ebooks in your Telegram bot."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from random import sample
from string import digits
from time import monotonic

from telethon import Button, TelegramClient, events

from .converter import Converter

MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
QUEUE_TTL = 1800  # 30 minutes
DOWNLOAD_DIR = Path("/tmp/ebook_converter_bot")

HIGHLIGHTED_FORMATS = {"epub", "pdf", "mobi", "azw3", "docx", "kfx", "md"}


@dataclass
class PendingRequest:
    file_path: Path
    input_ext: str
    created_at: float
    force_rtl: bool = False


def _cleanup_expired(queue: dict[str, PendingRequest]) -> None:
    now = monotonic()
    for req_id, req in list(queue.items()):
        if now - req.created_at > QUEUE_TTL:
            queue.pop(req_id, None)
            req.file_path.unlink(missing_ok=True)


def _build_format_buttons(req_id: str, req: PendingRequest, converter: Converter) -> list[list]:
    formats = converter.get_output_formats(req.input_ext)
    buttons = [
        Button.inline(
            f"🔸 {fmt}" if fmt in HIGHLIGHTED_FORMATS else fmt,
            data=f"ebk_run|{fmt}|{req_id}",
        )
        for fmt in formats
    ]
    rows = [buttons[i : i + 3] for i in range(0, len(buttons), 3)]
    rtl_label = f"Force RTL: {'ON ✅' if req.force_rtl else 'OFF'}"
    rows.append([Button.inline(rtl_label, data=f"ebk_rtl|{req_id}")])
    rows.append([Button.inline("❌ Cancel", data=f"ebk_cancel|{req_id}")])
    return rows


def register_converter_handlers(
    bot: TelegramClient,
    *,
    max_file_size: int = MAX_FILE_SIZE,
) -> Converter:
    """Register ebook conversion message and callback handlers on an existing Telethon client."""
    converter = Converter()
    queue: dict[str, PendingRequest] = {}
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    @bot.on(events.NewMessage(func=lambda e: bool(e.message.file and e.is_private)))
    @bot.on(events.NewMessage(pattern=r"^/convert$", func=lambda e: e.is_reply))
    async def handle_ebook_file(event: events.NewMessage.Event) -> None:
        message = await event.get_reply_message() if event.pattern_match else event.message
        if not message or not message.file:
            await event.reply("Reply to a supported ebook file to convert it.")
            return

        file_name = message.file.name or ""
        input_ext = converter.get_input_type(file_name)
        if not converter.is_supported_input(file_name):
            await event.reply("Unsupported file format.")
            return

        if message.file.size and message.file.size > max_file_size:
            await event.reply("File is too large (max 25 MB).")
            return

        status_msg = await event.reply("Downloading file...")
        downloaded = await message.download_media(DOWNLOAD_DIR)
        if not downloaded:
            await status_msg.edit("Failed to download file. Please try again.")
            return

        _cleanup_expired(queue)
        req_id = "".join(sample(digits, 8))
        while req_id in queue:
            req_id = "".join(sample(digits, 8))

        queue[req_id] = PendingRequest(
            file_path=Path(downloaded),
            input_ext=input_ext,
            created_at=monotonic(),
        )
        buttons = _build_format_buttons(req_id, queue[req_id], converter)
        await status_msg.edit("Select the target format to convert to:", buttons=buttons)

    @bot.on(events.CallbackQuery(pattern=r"^ebk_rtl\|\d+$"))
    async def handle_toggle_rtl(event: events.CallbackQuery.Event) -> None:
        _, req_id = event.data.decode().split("|")
        _cleanup_expired(queue)
        req = queue.get(req_id)
        if not req or not req.file_path.exists():
            await event.answer("Request expired. Please send the file again.", alert=True)
            return
        req.force_rtl = not req.force_rtl
        buttons = _build_format_buttons(req_id, req, converter)
        await event.edit("Select the target format to convert to:", buttons=buttons)

    @bot.on(events.CallbackQuery(pattern=r"^ebk_cancel\|\d+$"))
    async def handle_cancel(event: events.CallbackQuery.Event) -> None:
        _, req_id = event.data.decode().split("|")
        req = queue.pop(req_id, None)
        if req:
            req.file_path.unlink(missing_ok=True)
        await event.edit("Conversion canceled.")

    @bot.on(events.CallbackQuery(pattern=r"^ebk_run\|[\w-]+\|\d+$"))
    async def handle_run_conversion(event: events.CallbackQuery.Event) -> None:
        _, output_type, req_id = event.data.decode().split("|")
        _cleanup_expired(queue)
        req = queue.pop(req_id, None)
        if not req or not req.file_path.exists():
            await event.answer("Request expired or file missing. Send the file again.", alert=True)
            return

        status_msg = await event.edit(f"Converting `{req.file_path.name}` to `{output_type}`...")
        try:
            result = await converter.convert(
                req.file_path,
                output_type,
                force_rtl=req.force_rtl,
            )
            if result.success and result.output_file and result.output_file.exists():
                await status_msg.edit("Uploading converted file...")
                await event.client.send_file(
                    event.chat_id,
                    result.output_file,
                    reply_to=status_msg,
                    force_document=True,
                )
                await status_msg.delete()
            else:
                err_detail = f"\n\n`{result.error}`" if result.error else ""
                await status_msg.edit(
                    f"Failed to convert `{req.file_path.name}` to `{output_type}`.{err_detail}"
                )
        finally:
            req.file_path.unlink(missing_ok=True)
            if "result" in locals() and result.output_file:
                result.output_file.unlink(missing_ok=True)

    return converter
