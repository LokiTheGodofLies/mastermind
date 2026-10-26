import os
import time
import subprocess
import resource
import shutil
from telegram import Update
from telegram.ext import ContextTypes

START_TIME = time.time()

def get_dir_size(path="."):
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            if ".git" in dirpath or "__pycache__" in dirpath:
                continue
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.exists(fp):
                    total_size += os.path.getsize(fp)
    except Exception:
        pass
    return total_size / (1024 * 1024)  # MB

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.from_user:
        return

    user_id = message.from_user.id
    
    # Replace or add your Telegram user ID as admin/owner
    ADMIN_USER_IDS = [7261537212]
    is_admin = user_id in ADMIN_USER_IDS

    # 1. Database Stats (Users & Files)
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

    total_channels = 1
    total_groups = 2
    admin_channels = 1
    admin_groups = 2

    if is_admin:
        # --- ADMIN / OWNER FULL STATS ---
        try:
            bot_ram_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
        except Exception:
            bot_ram_mb = 0.0

        sys_ram_total, sys_ram_used, sys_ram_percent = 0, 0, 0.0
        try:
            meminfo = {}
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        meminfo[parts[0].rstrip(":")] = int(parts[1])
            if "MemTotal" in meminfo and "MemAvailable" in meminfo:
                total_kb = meminfo["MemTotal"]
                avail_kb = meminfo["MemAvailable"]
                used_kb = total_kb - avail_kb
                sys_ram_total = total_kb / (1024 * 1024)
                sys_ram_used = used_kb / (1024 * 1024)
                sys_ram_percent = (used_kb / total_kb) * 100
        except Exception:
            pass

        try:
            disk_total, disk_used, disk_free = shutil.disk_usage("/")
            disk_total_gb = disk_total / (1024**3)
            disk_used_gb = disk_used / (1024**3)
            disk_percent = (disk_used / disk_total) * 100
        except Exception:
            disk_total_gb, disk_used_gb, disk_percent = 0, 0, 0

        source_code_mb = get_dir_size(".")
        db_path = "database.db"
        db_size_mb = os.path.getsize(db_path) / (1024 * 1024) if os.path.exists(db_path) else 0.0

        uptime_seconds = int(time.time() - START_TIME)
        days, rem = divmod(uptime_seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s" if days > 0 else f"{hours}h {minutes}m {seconds}s"

        try:
            deploy_time = subprocess.check_output(["git", "log", "-1", "--format=%cd"]).decode("utf-8").strip()
        except Exception:
            deploy_time = "Unknown"

        stats_text = (
            "📊 <b>Mastermind Admin System & Bot Statistics</b>\n\n"
            f"📱 <b>Tablet System RAM:</b> <code>{sys_ram_used:.2f} GB / {sys_ram_total:.2f} GB ({sys_ram_percent:.1f}%)</code>\n"
            f"💾 <b>Tablet Storage (Disk):</b> <code>{disk_used_gb:.2f} GB / {disk_total_gb:.2f} GB ({disk_percent:.1f}%)</code>\n"
            f"🤖 <b>Bot RAM Usage:</b> <code>{bot_ram_mb:.2f} MB</code>\n"
            f"📂 <b>Source Code Size:</b> <code>{source_code_mb:.2f} MB</code>\n"
            f"🗄️ <b>Database Storage:</b> <code>{db_size_mb:.2f} MB</code>\n\n"
            f"⏱️ <b>Bot Uptime:</b> <code>{uptime_str}</code>\n"
            f"🚀 <b>Last Deployment:</b> <code>{deploy_time}</code>\n\n"
            f"👥 <b>Registered Users:</b> <code>{total_users}</code>\n"
            f"📚 <b>Files in Index:</b> <code>{total_files}</code>\n"
            f"📢 <b>Total Channels:</b> <code>{total_channels}</code> (Admin: {admin_channels})\n"
            f"👥 <b>Total Groups:</b> <code>{total_groups}</code> (Admin: {admin_groups})"
        )
    else:
        # --- REGULAR USER PUBLIC STATS ---
        stats_text = (
            "📊 <b>Mastermind Bot Statistics</b>\n\n"
            f"👥 <b>Registered Users:</b> <code>{total_users}</code>\n"
            f"📚 <b>Files in Index:</b> <code>{total_files}</code>\n"
            f"📢 <b>Total Channels:</b> <code>{total_channels}</code>\n"
            f"👥 <b>Total Groups:</b> <code>{total_groups}</code>"
        )

    await message.reply_text(stats_text, parse_mode="HTML")
