import os
from telegram import Update
from telegram.ext import ContextTypes
from modules.database.user_db import get_user_role_db
from modules.log.logger import get_logs_by_count, get_logs_by_time, setup_in_memory_logger

# Initialize memory logging on module load
setup_in_memory_logger()

async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Admin/Owner command to fetch logs from memory:
    - /log (defaults to last 10 logs)
    - /log 100 (last 100 logs)
    - /log 15m (last 15 minutes logs)
    """
    user_id = update.effective_user.id
    role = get_user_role_db(user_id)
    
    if role not in ['Admin', 'Owner']:
        await update.message.reply_text("⛔ You do not have permission to access system logs.")
        return
        
    args = context.args
    log_content = ""
    filename = "mastermind_logs.txt"
    
    # Default behavior: Last 10 logs
    if not args:
        log_content = get_logs_by_count(10)
        filename = "logs_last_10.txt"
    else:
        param = args[0].lower()
        if param.endswith('m'):
            try:
                mins = int(param[:-1])
                log_content = get_logs_by_time(mins)
                filename = f"logs_last_{mins}_min.txt"
            except ValueError:
                await update.message.reply_text("⚠️ Invalid time format. Use e.g., `/log 10m`", parse_mode="Markdown")
                return
        else:
            try:
                count = int(param)
                if count > 1000:
                    count = 1000
                log_content = get_logs_by_count(count)
                filename = f"logs_last_{count}.txt"
            except ValueError:
                await update.message.reply_text("⚠️ Invalid argument. Use a number (e.g., `/log 50`) or duration (e.g., `/log 10m`).", parse_mode="Markdown")
                return

    # Write temporarily to RAM/temp space, send document, and delete immediately
    temp_file_path = f"/tmp/{filename}"
    with open(temp_file_path, "w") as f:
        f.write(log_content)
        
    with open(temp_file_path, "rb") as f:
        await update.message.reply_document(
            document=f,
            filename=filename,
            caption=f"📋 <b>Memory Logs Generated Successfully</b>\nRequested by: <code>{role}</code>",
            parse_mode="HTML"
        )
        
    if os.path.exists(temp_file_path):
        os.remove(temp_file_path)
