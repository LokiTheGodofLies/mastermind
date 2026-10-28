"""Telegram front-end of the unified ebook converter: ``/convert`` plus inline format & option buttons.

Flow
----
1. ``/convert`` while replying to a file, or ``/convert`` and then sending a file.
2. The bot validates type (62 input formats) and size, and shows inline buttons for all compatible
   output formats (up to 31 formats) plus Force RTL and Compress Images toggles.
3. A tap downloads the file, converts it via Calibre / Pandoc / PyMuPDF / Shamela .bok / Anydoc,
   sends the result and cleans up temporary files.

Callback data (all start with ``cv|``):
    cv|menu                 open the convert screen (start menu button)
    cv|fmt|<format>|<token> convert the pending file to <format>
    cv|rtl|<token>          toggle Force RTL for the pending file
    cv|cmp|<token>          toggle Compress Images for the pending file
    cv|cancel|<token>       drop the pending file
    cv|wait_cancel          stop waiting for an upload
"""
import html
import logging
import secrets
import tempfile
import time
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from modules.converter.engine import (
    ConversionResult,
    convert_file,
    converter_available,
    get_semaphore,
    safe_output_name,
)
from modules.converter.formats import (
    BOT_DOWNLOAD_LIMIT_MB,
    BOT_UPLOAD_LIMIT_MB,
    HIGHLIGHTED_FORMATS,
    INPUT_FORMATS,
    detect_input_format,
    output_choices,
)
from modules.database.config_db import get_config_bool, get_config_int
from modules.database.user_db import get_user_role_db

logger = logging.getLogger(__name__)

JOB_TTL_SECONDS = 15 * 60       # a pending file is forgotten after 15 minutes
WAIT_TTL_SECONDS = 5 * 60       # /convert waits 5 minutes for the upload
MAX_PENDING_JOBS = 5            # per user
BUTTONS_PER_ROW = 4


# ----------------------------------------------------------------------------- state helpers
def _jobs(context: ContextTypes.DEFAULT_TYPE) -> dict:
    jobs = context.user_data.setdefault("convert_jobs", {})
    now = time.monotonic()
    for token in [t for t, j in jobs.items() if j["expires"] < now]:
        jobs.pop(token, None)
    return jobs


def _max_input_bytes() -> int:
    mb = min(get_config_int("convert_max_input_mb", BOT_DOWNLOAD_LIMIT_MB), BOT_DOWNLOAD_LIMIT_MB)
    return max(1, mb) * 1024 * 1024


def _supported_text() -> str:
    return ", ".join(sorted(INPUT_FORMATS))


def _format_keyboard(token: str, input_format: str, *, force_rtl: bool = False, compress_images: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            f"🔸 {fmt.upper()}" if fmt in HIGHLIGHTED_FORMATS else fmt.upper(),
            callback_data=f"cv|fmt|{fmt}|{token}",
        )
        for fmt in output_choices(input_format)
    ]
    rows = [buttons[i:i + BUTTONS_PER_ROW] for i in range(0, len(buttons), BUTTONS_PER_ROW)]
    rows.append([
        InlineKeyboardButton(f"Force RTL: {'ON ✅' if force_rtl else 'OFF'}", callback_data=f"cv|rtl|{token}"),
        InlineKeyboardButton(f"Compress: {'ON ✅' if compress_images else 'OFF'}", callback_data=f"cv|cmp|{token}"),
    ])
    rows.append([InlineKeyboardButton("❌ Cancel", callback_data=f"cv|cancel|{token}")])
    return InlineKeyboardMarkup(rows)


def _unavailable_reason() -> str:
    if not get_config_bool("convert_enabled", True):
        return "🔧 The converter is currently disabled by the bot admins."
    if not converter_available():
        return (
            "🔧 The converter is not available on this host (Calibre/Pandoc not installed). "
            "Ask the bot owner to deploy with the provided Dockerfile."
        )
    return ""


# ----------------------------------------------------------------------------- command + upload
async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/convert - reply to a file, or run it and then send a file."""
    msg = update.effective_message
    if not msg:
        return
    reason = _unavailable_reason()
    if reason:
        await msg.reply_text(reason)
        return

    replied = msg.reply_to_message
    if replied and replied.document:
        await _offer_formats(msg, replied.document, context)
        return

    context.user_data["convert_wait"] = time.monotonic() + WAIT_TTL_SECONDS
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cv|wait_cancel")]])
    await msg.reply_text(
        "🔄 <b>Ebook Converter (62 Inputs → 31 Outputs)</b>\n\n"
        "Send me the ebook or document file you want to convert.\n"
        f"📏 Max size: <code>{_max_input_bytes() // (1024 * 1024)} MB</code>\n"
        f"📂 Reads (62 formats): <code>{html.escape(_supported_text())}</code>",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def handle_convert_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Called first by the upload handler. Returns True if the file was claimed by /convert."""
    msg = update.message
    if not msg or not msg.document:
        return False
    deadline = context.user_data.get("convert_wait")
    if not deadline:
        return False
    context.user_data.pop("convert_wait", None)
    if deadline < time.monotonic():
        return False  # waiting window expired -> normal upload handling continues
    await _offer_formats(msg, msg.document, context)
    return True


async def _offer_formats(msg, document, context: ContextTypes.DEFAULT_TYPE):
    file_name = document.file_name or "book"
    in_fmt = detect_input_format(file_name)
    if in_fmt not in INPUT_FORMATS:
        await msg.reply_text(
            f"❌ <b>Unsupported file type</b> (<code>.{html.escape(in_fmt or '?')}</code>).\n"
            f"Supported (62 formats): <code>{html.escape(_supported_text())}</code>",
            parse_mode="HTML",
        )
        return
    size = document.file_size or 0
    if size > _max_input_bytes():
        await msg.reply_text(
            f"❌ File is too large (<code>{size / 1048576:.1f} MB</code>). "
            f"Limit: <code>{_max_input_bytes() // 1048576} MB</code>.",
            parse_mode="HTML",
        )
        return

    jobs = _jobs(context)
    if len(jobs) >= MAX_PENDING_JOBS:
        oldest = min(jobs, key=lambda t: jobs[t]["expires"])
        jobs.pop(oldest, None)
    token = secrets.token_hex(4)
    jobs[token] = {
        "file_id": document.file_id,
        "file_name": file_name,
        "file_size": size,
        "format": in_fmt,
        "force_rtl": False,
        "compress_images": False,
        "expires": time.monotonic() + JOB_TTL_SECONDS,
    }
    await msg.reply_text(
        f"📘 <b>{html.escape(file_name)}</b>\n"
        f"📦 <code>{size / 1048576:.2f} MB</code> · <code>.{html.escape(in_fmt)}</code>\n\n"
        "Choose the format to convert to:",
        parse_mode="HTML",
        reply_markup=_format_keyboard(token, in_fmt),
    )


# ----------------------------------------------------------------------------- callbacks
async def convert_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.data:
        return
    if get_user_role_db(q.from_user.id) == "Banned":
        await q.answer("🚫 You are banned from using this bot.", show_alert=True)
        return

    parts = q.data.split("|")
    action = parts[1] if len(parts) > 1 else ""

    if action == "menu":
        reason = _unavailable_reason()
        if reason:
            await q.answer(reason, show_alert=True)
            return
        await q.answer()
        context.user_data["convert_wait"] = time.monotonic() + WAIT_TTL_SECONDS
        await q.message.edit_text(
            "🔄 <b>Ebook Converter (62 Inputs → 31 Outputs)</b>\n\n"
            "Send me the ebook or document file you want to convert.\n"
            f"📂 Reads: <code>{html.escape(_supported_text())}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("≼ Back to Start", callback_data="start_menu")]]),
        )
    elif action == "wait_cancel":
        context.user_data.pop("convert_wait", None)
        await q.answer("Cancelled")
        await q.message.edit_text("❌ Conversion cancelled.")
    elif action == "cancel" and len(parts) == 3:
        _jobs(context).pop(parts[2], None)
        await q.answer("Cancelled")
        await q.message.edit_text("❌ Conversion cancelled.")
    elif action in ("rtl", "cmp") and len(parts) == 3:
        token = parts[2]
        job = _jobs(context).get(token)
        if not job:
            await q.answer("⌛ This request expired. Send /convert again.", show_alert=True)
            return
        if action == "rtl":
            job["force_rtl"] = not job.get("force_rtl", False)
        else:
            job["compress_images"] = not job.get("compress_images", False)
        await q.answer()
        await q.message.edit_reply_markup(
            reply_markup=_format_keyboard(
                token,
                job["format"],
                force_rtl=job.get("force_rtl", False),
                compress_images=job.get("compress_images", False),
            )
        )
    elif action == "fmt" and len(parts) == 4:
        await _run_conversion(q, context, out_fmt=parts[2], token=parts[3])
    else:
        await q.answer()


async def _run_conversion(q, context: ContextTypes.DEFAULT_TYPE, out_fmt: str, token: str):
    job = _jobs(context).get(token)
    if not job:
        await q.answer("⌛ This request expired or belongs to someone else. Send /convert again.", show_alert=True)
        return
    if out_fmt not in output_choices(job["format"]):
        await q.answer("Unsupported target format.", show_alert=True)
        return
    reason = _unavailable_reason()
    if reason:
        await q.answer(reason, show_alert=True)
        return
    if context.user_data.get("convert_busy"):
        await q.answer("⏳ Your previous conversion is still running.", show_alert=True)
        return

    context.user_data["convert_busy"] = True
    _jobs(context).pop(token, None)
    await q.answer("🔄 Converting...")
    started = time.monotonic()
    name = html.escape(job["file_name"])
    try:
        semaphore = get_semaphore(get_config_int("convert_max_concurrent", 2))
        if semaphore.locked():
            await q.message.edit_text(
                f"🕒 <b>Queued</b> — waiting for a free converter slot…\n📘 <code>{name}</code>",
                parse_mode="HTML",
            )
        async with semaphore:
            await q.message.edit_text(
                f"⏳ <b>Converting to {out_fmt.upper()}…</b>\n📘 <code>{name}</code>",
                parse_mode="HTML",
            )
            with tempfile.TemporaryDirectory(prefix="mm_convert_") as tmp:
                src = Path(tmp) / f"input.{job['format']}"
                tg_file = await context.bot.get_file(job["file_id"])
                await tg_file.download_to_drive(custom_path=src)
                result = await convert_file(
                    src,
                    out_fmt,
                    timeout=get_config_int("convert_timeout_seconds", 300),
                    force_rtl=job.get("force_rtl", False),
                    compress_images=job.get("compress_images", False),
                )
                await _deliver(q, context, job, out_fmt, result, started)
    except Exception as exc:  # network / Telegram errors must not leave the button hanging
        logger.exception("Conversion failed for user %s", q.from_user.id)
        await q.message.edit_text(
            f"❌ <b>Conversion failed</b>\n<code>{html.escape(str(exc)[:300])}</code>",
            parse_mode="HTML",
        )
    finally:
        context.user_data.pop("convert_busy", None)


async def _deliver(q, context, job: dict, out_fmt: str, result: ConversionResult, started: float):
    name = html.escape(job["file_name"])
    if not result.ok:
        await q.message.edit_text(
            f"❌ <b>Conversion failed</b>\n📘 <code>{name}</code>\n\n<pre>{html.escape(result.error[:500])}</pre>",
            parse_mode="HTML",
        )
        return

    size = result.path.stat().st_size
    if size > BOT_UPLOAD_LIMIT_MB * 1024 * 1024 - 1024 * 1024:
        await q.message.edit_text(
            f"❌ The converted file is <code>{size / 1048576:.1f} MB</code>, over Telegram's "
            f"{BOT_UPLOAD_LIMIT_MB} MB bot upload limit. Try a lighter format such as EPUB.",
            parse_mode="HTML",
        )
        return

    elapsed = time.monotonic() - started
    thread_id = q.message.message_thread_id if q.message.is_topic_message else None
    with result.path.open("rb") as handle:
        await context.bot.send_document(
            chat_id=q.message.chat_id,
            document=handle,
            filename=safe_output_name(job["file_name"], out_fmt),
            caption=(
                f"✅ <b>Converted</b> <code>.{job['format']}</code> → <code>.{out_fmt}</code>\n"
                f"📦 <code>{size / 1048576:.2f} MB</code> · ⏱ <code>{elapsed:.1f}s</code>"
            ),
            parse_mode="HTML",
            message_thread_id=thread_id,
        )
    logger.info("[CONVERT] user=%s %s->%s %.1fs %d bytes", q.from_user.id, job["format"], out_fmt, elapsed, size)
    await q.message.edit_text(
        f"✅ <b>Done!</b> Your <code>.{out_fmt}</code> file is below.\n📘 <code>{name}</code>",
        parse_mode="HTML",
    )
