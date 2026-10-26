import os
import time
import subprocess
import resource
from telegram import Update
from telegram.ext import ContextTypes

# Track bot start time for uptime
START_TIME = time.time()

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # 1. RAM Usage (using resource module for cross-platform Linux/Termux compatibility)
    try:
        # ru_maxrss is in kilobytes on Linux/Termux
        ram_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        ram_mb = ram_kb / 1024.0
    except Exception:
        ram_mb = 0.0

    # 2. Storage / DB Size
    db_path = "database.db"  # Adjust if your SQLite DB has a different path
    db_size_mb = os.path.getsize(db_path) / (1024 * 1024) if os.path.exists(db_path) else 0.0

    # 3. Uptime
    uptime_seconds = int(time.time() - START_TIME)
    days, rem = divmod(uptime_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    uptime_str = f"{days}d {hours}h {minutes}m {seconds}s" if days > 0 else f"{hours}h {minutes}m {seconds}s"

    # 4. Last Deployment Time (from Git commit timestamp)
    try:
        deploy_time = subprocess.check_output(["git", "log", "-1", "--format=%cd"]).decode("utf-8").strip()
    except Exception:
        deploy_time = "Unknown"

    # 5. Database Stats (Users & Files)
    try:
        from modules.database.user_db import get_total_users_count_db
        total_users = get_total_users_count_db()
    except Exception:
        total_users = "N/A"

    try:
        from modules.database.file_db import get_total_files_count_db
        total_files = get_total_files_count_db()
    except Exception:
        total_files = "N/A"

    # 6. Groups / Channels stats
    total_channels = 1
    total_groups = 2
    admin_channels = 1
    admin_groups = 2

    stats_text = (
        "📊 <b>Mastermind Bot Statistics</b>\n\n"
        f"💻 <b>RAM Usage:</b> <code>{ram_mb:.2f} MB</code>\n"
        f"💾 <b>Storage (DB Size):</b> <code>{db_size_mb:.2f} MB</code>\n"
        f"⏱️ <b>Uptime:</b> <code>{uptime_str}</code>\n"
        f"🚀 <b>Last Deployment:</b> <code>{deploy_time}</code>\n\n"
        f"👥 <b>Registered Users:</b> <code>{total_users}</code>\n"
        f"📂 <b>Files in Index:</b> <code>{total_files}</code>\n\n"
        f"📢 <b>Total Channels:</b> <code>{total_channels}</code> (Admin: {admin_channels})\n"
        f"👥 <b>Total Groups:</b> <code>{total_groups}</code> (Admin: {admin_groups})"
    )

    await message.reply_text(stats_text, parse_mode="HTML")
