import html
import os
import time
from config import bot_name
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.database.config_db import get_config
from modules.database.user_db import is_admin_or_creator, get_user_role_db, is_creator, get_db_stats_counts
from modules.database.file_db import get_file_stats_counts_db


def _get_ram_usage() -> str:
    """Reads system RAM usage from /proc/meminfo or returns unavailable."""
    try:
        with open("/proc/meminfo", "r") as f:
            lines = f.readlines()
        mem = {}
        for l in lines:
            parts = l.split(":")
            if len(parts) == 2:
                mem[parts[0].strip()] = int(parts[1].split()[0])
        total_mb = mem.get("MemTotal", 0) / 1024
        avail_mb = mem.get("MemAvailable", 0) / 1024
        used_mb = total_mb - avail_mb
        return f"{used_mb:.1f} MB / {total_mb:.1f} MB ({used_mb * 100 / total_mb:.1f}%)"
    except Exception:
        return "N/A"


def _get_db_sizes() -> str:
    """Calculates disk sizes of SQLite databases."""
    total_bytes = 0
    for name in ("config.db", "files.db", "mastermind_users.db"):
        if os.path.exists(name):
            total_bytes += os.path.getsize(name)
    mb = total_bytes / (1024 * 1024)
    return f"{mb:.2f} MB" if mb >= 1 else f"{total_bytes / 1024:.1f} KB"


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    role = get_user_role_db(user.id)
    is_admin = is_admin_or_creator(user.id)
    is_creator_user = is_creator(user.id)

    default_header = f"📊 <b>{bot_name()} Bot Statistics & Status</b>"
    header_text = get_config("stats_header_script", default=default_header)

    f_stats = get_file_stats_counts_db()
    u_stats = get_db_stats_counts()

    lines = [
        f"{header_text}\n",
        "📚 <b>Library Catalog:</b>",
        f"• Total Files: <code>{f_stats['total']}</code>",
        f"• Ebooks: <code>{f_stats['ebooks']}</code>",
        f"• Audiobooks: <code>{f_stats['audiobooks']}</code>\n",
        "👥 <b>Community Reach:</b>",
        f"• Unique Users: <code>{u_stats['users']}</code>",
        f"• Connected Groups: <code>{u_stats['groups']}</code>",
        f"• Connected Channels: <code>{u_stats['channels']}</code>",
    ]

    if is_admin:
        lines.append("")
        lines.append(f"👑 <b>{role} System Diagnostic:</b>")
        lines.append(f"• Active Access Role: <code>{role}</code>")
        lines.append(f"• Database Storage: <code>{_get_db_sizes()}</code>")
        lines.append(f"• Server RAM Usage: <code>{_get_ram_usage()}</code>")

        # Measure round-trip ping latency
        t0 = time.time()
        try:
            await context.bot.get_me()
            ping_ms = round((time.time() - t0) * 1000)
            lines.append(f"• Telegram API Ping: <code>{ping_ms} ms</code>")
        except Exception:
            lines.append("• Telegram API Ping: <code>Error</code>")

    stats_text = "\n".join(lines)

    media_type = get_config("stats_media_type", default="none")
    media_url = get_config("stats_media_url", default="")

    keyboard = [[InlineKeyboardButton("« Back to Start", callback_data="start_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if media_type == "photo" and media_url:
        await message.reply_photo(photo=media_url, caption=stats_text, reply_markup=reply_markup, parse_mode="HTML")
    elif media_type == "video" and media_url:
        await message.reply_video(video=media_url, caption=stats_text, reply_markup=reply_markup, parse_mode="HTML")
    elif media_type == "animation" and media_url:
        await message.reply_animation(animation=media_url, caption=stats_text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await message.reply_text(text=stats_text, reply_markup=reply_markup, parse_mode="HTML")
