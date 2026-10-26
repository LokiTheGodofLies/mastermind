import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.database.config_db import get_config

DB_PATH = "configuration.db"
ITEMS_PER_PAGE = 10

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE, search_term: str, page: int = 1):
    results = []
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type=\"table\";")
        tables = cursor.fetchall()
        for (table_name,) in tables:
            try:
                cursor.execute(f"SELECT * FROM {table_name} WHERE id LIKE ? OR key LIKE ? OR value LIKE ? OR name LIKE ? OR file_name LIKE ?",
                               (f"%{search_term}%", f"%{search_term}%", f"%{search_term}%", f"%{search_term}%", f"%{search_term}%"))
                rows = cursor.fetchall()
                for row in rows:
                    row_id = row[0] if len(row) > 0 else 0
                    label = str(row[1]) if len(row) > 1 else str(row[0])
                    if len(label) > 35:
                        label = label[:32] + "..."
                    results.append((row_id, table_name, label))
            except Exception:
                pass
        conn.close()
    except Exception:
        pass

    storage_group_id = "-1003936877675"
    total_results = len(results)
    keyboard = []

    if total_results > 0:
        total_pages = (total_results + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * ITEMS_PER_PAGE
        end_idx = start_idx + ITEMS_PER_PAGE
        page_results = results[start_idx:end_idx]

        response_text = (
            f"🔍 <b>Search Results for:</b> <code>{search_term}</code>\n\n"
            f"Found {total_results} matching file(s). Page {page} of {total_pages}:"
        )
        for row_id, table_name, label in page_results:
            keyboard.append([InlineKeyboardButton(f"📁 [{table_name}] {label}", callback_data=f"file_dl_{row_id}")])

        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton("« Prev", callback_data=f"search_page_{search_term}_{page-1}"))
        nav_row.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton("Next »", callback_data=f"search_page_{search_term}_{page+1}"))
        if nav_row:
            keyboard.append(nav_row)
    else:
        response_text = (
            f"🔍 <b>Search Results for:</b> <code>{search_term}</code>\n\n"
            "• No matching files found in the database.\n\n"
            f"<i>(Storage Group ID: {storage_group_id})</i>"
        )

    keyboard.append([InlineKeyboardButton("🔍 New Search", callback_data="search_start_quiz")])
    keyboard.append([InlineKeyboardButton("« Back to Start", callback_data="start_menu")])

    if update.callback_query:
        await update.callback_query.message.edit_text(response_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        await update.callback_query.answer()
    else:
        await update.message.reply_text(response_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or (update.callback_query.message if update.callback_query else None)
    if not message:
        return

    if context.args:
        search_term = " ".join(context.args).strip()
        await perform_search(update, context, search_term, page=1)
        return

    if update.message and update.message.reply_to_message and update.message.reply_to_message.text:
        search_term = update.message.reply_to_message.text.strip()
        await perform_search(update, context, search_term, page=1)
        return

    if context.user_data:
        context.user_data.pop("waiting_for_search", None)

    default_text = (
        "🔍 <b>Mastermind Search Hub</b>\n\n"
        "Welcome to the file and database search engine.\n"
        "Send <code>/search &lt;keyword&gt;</code>, reply to a message with <code>/search</code>, or click below:"
    )
    search_text = get_config("search_script", default=default_text)

    keyboard = [
        [InlineKeyboardButton("🚀 Start Search Quiz", callback_data="search_start_quiz")],
        [InlineKeyboardButton("« Back to Start", callback_data="start_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.message.edit_text(text=search_text, reply_markup=reply_markup, parse_mode="HTML")
        await update.callback_query.answer()
    else:
        await message.reply_text(text=search_text, reply_markup=reply_markup, parse_mode="HTML")

async def search_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    data = query.data

    if data == "search_start_quiz":
        context.user_data["waiting_for_search"] = True
        await query.message.edit_text(
            "🔍 <b>Search Quiz Started</b>\n\nPlease type and send the keyword or file name you want to search...",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data="search_menu")]])
        )
        await query.answer()
    elif data == "search_menu":
        await search_command(update, context)
    elif data == "noop":
        await query.answer("Current Page", show_alert=False)
    elif data.startswith("search_page_"):
        parts = data.replace("search_page_", "", 1).rsplit("_", 1)
        if len(parts) == 2:
            sterm, spage = parts[0], int(parts[1])
            await perform_search(update, context, sterm, page=spage)
        else:
            await query.answer()
    elif data.startswith("file_dl_"):
        row_id = data.replace("file_dl_", "")
        await query.answer("Fetching file...")
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type=\"table\";")
            tables = cursor.fetchall()
            found_data = None
            for (table_name,) in tables:
                try:
                    cursor.execute(f"SELECT * FROM {table_name} WHERE id = ?", (row_id,))
                    row = cursor.fetchone()
                    if row:
                        found_data = row
                        break
                except Exception:
                    pass
            conn.close()

            if found_data:
                await query.message.reply_text(f"📦 <b>File Record Retrieved:</b>\n<code>{found_data}</code>", parse_mode="HTML")
            else:
                await query.message.reply_text("❌ File record no longer found in the database.")
        except Exception as e:
            await query.message.reply_text(f"❌ Error retrieving file: {e}")

async def search_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_for_search"):
        return
    search_term = update.message.text.strip()
    context.user_data["waiting_for_search"] = False
    await perform_search(update, context, search_term, page=1)

search_handler = search_command
