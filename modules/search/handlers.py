import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.database.config_db import get_config

DB_PATH = "database/files.db"
ITEMS_PER_PAGE = 10
SEARCH_GROUP_ID = -1004480538217

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE, search_term: str, page: int = 1):
    results = []
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        for (tname,) in cursor.fetchall():
            try:
                cursor.execute(f"SELECT * FROM {tname}")
                for row in cursor.fetchall():
                    row_id = row[0] if len(row) > 0 else 0
                    full_str = " ".join(str(v) for v in row if v is not None)
                    if search_term.lower() in full_str.lower():
                        label = str(row[1]) if len(row) > 1 else str(row[0])
                        for v in row:
                            if isinstance(v, str) and search_term.lower() in v.lower() and len(v) < 50:
                                label = v
                                break
                        if len(label) > 35:
                            label = label[:32] + "..."
                        if (row_id, tname, label) not in results:
                            results.append((row_id, tname, label))
            except Exception:
                pass
        conn.close()
    except Exception:
        pass

    total = len(results)
    keyboard = []
    if total > 0:
        tp = (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        page = max(1, min(page, tp))
        for row_id, tname, lbl in results[(page-1)*ITEMS_PER_PAGE : page*ITEMS_PER_PAGE]:
            keyboard.append([InlineKeyboardButton(f"📁 [{tname}] {lbl}", callback_data=f"file_dl_{row_id}")])
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton("« Prev", callback_data=f"search_page_{search_term}_{page-1}"))
        nav.append(InlineKeyboardButton(f"📄 {page}/{tp}", callback_data="noop"))
        if page < tp:
            nav.append(InlineKeyboardButton("Next »", callback_data=f"search_page_{search_term}_{page+1}"))
        if nav:
            keyboard.append(nav)
        txt = f"🔍 <b>Search Results for:</b> <code>{search_term}</code>\n\nFound {total} matching file(s). Page {page} of {tp}:"
    else:
        txt = f"🔍 <b>Search Results for:</b> <code>{search_term}</code>\n\n• No matching files found in the database.\n\n<i>(Storage Group ID: {SEARCH_GROUP_ID})</i>"

    keyboard.append([InlineKeyboardButton("« Back to Search Menu", callback_data="search_menu")])
    if update.callback_query:
        await update.callback_query.message.edit_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        await update.callback_query.answer()
    else:
        await update.message.reply_text(txt, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or (update.callback_query.message if update.callback_query else None)
    if not msg: return
    if context.args:
        await perform_search(update, context, " ".join(context.args).strip(), 1)
        return
    if update.message and update.message.reply_to_message and update.message.reply_to_message.text:
        await perform_search(update, context, update.message.reply_to_message.text.strip(), 1)
        return
    txt = get_config("search_script", default="🔍 <b>File Search Engine</b>\n\nYou can either join our search group to search there, or search right here in private chat by providing a keyword after the search command or replying to a message with /search.")
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("👥 Join Search Group", callback_data="join_search_group_quiz")], [InlineKeyboardButton("« Back to Start", callback_data="start_menu")]])
    if update.callback_query:
        await update.callback_query.message.edit_text(text=txt, reply_markup=kb, parse_mode="HTML")
        await update.callback_query.answer()
    else:
        await msg.reply_text(text=txt, reply_markup=kb, parse_mode="HTML")

async def search_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q: return
    d = q.data
    print(f"📥 [CALLBACK CLICKED] Data received: \"{d}\"")
    print(f"📥 [DEBUG CALLBACK] Received callback query data: '{d}' from user {q.from_user.id if q.from_user else 'unknown'}")
    if d == "join_search_group_quiz":
        await q.message.edit_text("📝 <b>Search Group Verification Quiz</b>\n\nDo you want to join our search group?", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Yes, Generate Invite Link", callback_data="generate_group_invite")], [InlineKeyboardButton("« Back", callback_data="search_menu")]]))
        await q.answer()
    elif d == "generate_group_invite":
        await q.answer("Generating invite link...")
        try:
            link = await context.bot.create_chat_invite_link(chat_id=SEARCH_GROUP_ID, member_limit=1)
            await q.message.edit_text(f"🎉 <b>Here is your single-use invite link:</b>\n\n{link.invite_link}", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Search Menu", callback_data="search_menu")]]))
        except Exception as e:
            await q.message.edit_text(f"❌ <b>Could not generate invite link.</b>\n\nReason: {e}", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Search Menu", callback_data="search_menu")]]))
    elif d == "search_menu":
        await search_command(update, context)
    elif d == "noop":
        await q.answer("Current Page")
    elif d.startswith("search_page_"):
        parts = d.replace("search_page_", "", 1).rsplit("_", 1)
        if len(parts) == 2: await perform_search(update, context, parts[0], int(parts[1]))
    elif d.startswith("file_dl_"):
        row_id = d.replace("file_dl_", "")
        await q.answer("Fetching file...")
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            found = None
            for (tname,) in cursor.fetchall():
                try:
                    cursor.execute(f"SELECT * FROM {tname} WHERE id = ?", (row_id,))
                    row = cursor.fetchone()
                    if row:
                        found = row
                        break
                except Exception: pass
            conn.close()
            if found:
                file_id = found[2]
                try:
                    await context.bot.send_document(chat_id=q.message.chat_id, document=file_id, caption="Here is your file!")
                except Exception as ex:
                    await q.message.reply_text(f"📦 <b>File Record Retrieved:</b>\n<code>{found}</code>", parse_mode="HTML")
            else:
                await q.message.reply_text("❌ File record no longer found.")
        except Exception as e:
            await q.message.reply_text(f"❌ Error: {e}")

async def search_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass

search_handler = search_command
