import asyncio
import html
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.database.user_db import DB_FILE as USER_DB, get_user_role_db
from modules.database.file_db import get_connection as get_file_conn
from modules.database import persistence


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return

    uconn = sqlite3.connect(USER_DB)
    total_users = uconn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_refs = uconn.execute("SELECT COUNT(*) FROM referrals").fetchone()[0]
    uconn.close()

    fconn = get_file_conn()
    total_files = fconn.execute("SELECT COUNT(*) FROM indexed_files").fetchone()[0]
    queued_files = fconn.execute("SELECT COUNT(*) FROM indexing_queue WHERE status = 'queued'").fetchone()[0]
    total_reqs = fconn.execute("SELECT COUNT(*) FROM requests_queue").fetchone()[0]
    pending_reqs = fconn.execute("SELECT COUNT(*) FROM requests_queue WHERE status = 'Pending'").fetchone()[0]
    total_deliveries = fconn.execute("SELECT COUNT(*) FROM delivery_logs").fetchone()[0]
    fconn.close()

    role = get_user_role_db(user.id)
    txt = (
        f"📊 <b>Mastermind Library Statistics</b>\n\n"
        f"📚 <b>Total Indexed Books/Audiobooks:</b> <code>{total_files}</code>\n"
        f"⏳ <b>Files in Indexing Queue:</b> <code>{queued_files}</code>\n"
        f"📤 <b>Temporary Deliveries Served:</b> <code>{total_deliveries}</code>\n"
        f"📥 <b>Total Book Requests:</b> <code>{total_reqs}</code> (Pending: <code>{pending_reqs}</code>)\n"
        f"👥 <b>Registered Users:</b> <code>{total_users}</code>\n"
        f"🔗 <b>Completed Referrals:</b> <code>{total_refs}</code>\n"
        f"🛡 <b>Your Role:</b> <code>{role}</code>"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("≼ Back to Start", callback_data="start_menu")]])
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)
    else:
        await msg.reply_text(txt, parse_mode="HTML", reply_markup=kb)


async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/backup - (Admin/Owner) snapshot all databases to the backup chat right now and show status."""
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    if get_user_role_db(user.id) not in ("Admin", "Owner"):
        await msg.reply_text("⛔ Access denied. Only Admins and Owners can run /backup.")
        return

    wait = await msg.reply_text("💾 Backing up databases...")
    ok, detail = await asyncio.to_thread(persistence.backup_now, "manual /backup")
    st = persistence.get_status()
    txt = (
        f"{'✅ <b>Backup saved</b>' if ok else '❌ <b>Backup failed</b>'}\n"
        f"{html.escape(detail)}\n\n"
        f"{persistence.status_line_html()}\n"
        f"💬 <b>Backup chat:</b> <code>{html.escape(str(st.get('backup_chat') or 'not set'))}</code>"
    )
    await wait.edit_text(txt, parse_mode="HTML")
