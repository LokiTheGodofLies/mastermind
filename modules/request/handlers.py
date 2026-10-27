import os
import html
import logging
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ApplicationHandlerStop
from modules.database.file_db import get_connection as get_db_conn
from modules.database.config_db import get_config
from modules.database.user_db import get_user_role_db
from modules.allowance.allowance import can_user_request, deduct_request_quota
from modules.log.startup_log import send_log_with_fallback

logger = logging.getLogger(__name__)


def fetch_audible_or_goodreads_options(query: str) -> list:
    """Queries Audible catalog API (with Goodreads fallback) for rich audiobook/book options."""
    results = []
    try:
        url = "https://api.audible.com/1.0/catalog/products"
        params = {
            "keywords": query,
            "num_results": 3,
            "products_sort_by": "Relevance",
            "response_groups": "contributors,product_attrs,product_desc,series",
        }
        resp = requests.get(url, params=params, timeout=8)
        if resp.status_code == 200:
            for p in resp.json().get("products", [])[:3]:
                title = p.get("title") or query
                authors = ", ".join(a.get("name", "") for a in p.get("authors", []) if a.get("name")) or "Unknown Author"
                narrators = ", ".join(n.get("name", "") for n in p.get("narrators", []) if n.get("name")) or "N/A"
                series_list = p.get("series") or []
                series_str = f"{series_list[0].get('title', '')}, #{series_list[0].get('sequence', '')}".strip(", #") if series_list else ""
                rel_year = (p.get("release_date") or p.get("issue_date") or "N/A")[:4]
                pub = p.get("publisher_name") or "Audible Studios"
                asin = p.get("asin") or ""
                link = f"https://www.audible.com/pd/{asin}" if asin else "https://www.audible.com"
                results.append({
                    "title": title, "author": authors, "narrator": narrators,
                    "series": series_str, "year": rel_year, "publisher": pub,
                    "url": link, "source": "Audible", "format": "Audiobook",
                })
    except Exception as e:
        logger.warning(f"Audible API lookup warning: {e}")

    if not results:
        try:
            g_url = f"https://www.goodreads.com/book/auto_complete?format=json&q={requests.utils.quote(query)}"
            r = requests.get(g_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
            if r.status_code == 200 and isinstance(r.json(), list):
                for item in r.json()[:3]:
                    a_obj = item.get("author") or {}
                    results.append({
                        "title": item.get("title") or query,
                        "author": a_obj.get("name") if isinstance(a_obj, dict) else "Unknown Author",
                        "narrator": "N/A", "series": "",
                        "year": str(item.get("publicationYear") or "N/A"),
                        "publisher": "Goodreads Catalog",
                        "url": "https://www.goodreads.com" + str(item.get("bookUrl", "")),
                        "source": "Goodreads", "format": "eBook / Audiobook",
                    })
        except Exception:
            pass
    return results


async def show_request_options(target_msg, user, query: str, context: ContextTypes.DEFAULT_TYPE, is_edit: bool = False):
    if not can_user_request(user.id):
        txt = "⚠️ <b>Daily request quota reached!</b> Use <code>/refer</code> to earn +10 bonus quota or wait for daily reset."
        if is_edit:
            await target_msg.edit_text(txt, parse_mode="HTML")
        else:
            await target_msg.reply_text(txt, parse_mode="HTML")
        return

    options = fetch_audible_or_goodreads_options(query)
    context.user_data["req_candidates"] = options
    context.user_data["req_raw_query"] = query

    kb = []
    if options:
        lines = ["📬 <b>Matching book options found for your request in Internet:</b>\n"]
        for i, opt in enumerate(options, start=1):
            t_esc = html.escape(opt["title"])
            a_esc = html.escape(opt["author"])
            s_part = f" [{html.escape(opt['series'])}]," if opt.get("series") else ""
            n_esc = html.escape(opt.get("narrator") or "N/A")
            y_esc = html.escape(opt.get("year") or "N/A")
            p_esc = html.escape(opt.get("publisher") or "N/A")
            u_esc = html.escape(opt.get("url") or "https://www.audible.com")
            src = html.escape(opt.get("source") or "Audible")
            lines.append(
                f"{i}. <b>{t_esc}</b> by {a_esc}\n"
                f"  {s_part} Narrated by: {n_esc}, Released {y_esc}, Publisher {p_esc}\n"
                f"  <a href=\"{u_esc}\">{src}</a>\n"
            )
            btn_lbl = f"📖 {i}. {opt['title'][:24]} — {opt['author'][:16]}"
            kb.append([InlineKeyboardButton(btn_lbl, callback_data=f"req_pick_opt_{i-1}")])
        lines.append('Select a book to attach it to your request, links in the message will help you, or choose "<b>None of these</b>" to send your original or manual request.')
        text = "\n".join(lines)
    else:
        text = f"📬 <b>Request Book:</b> <i>{html.escape(query)}</i>\n\nNo automatic Audible matches found. Choose how you would like to submit your request:"

    kb.append([InlineKeyboardButton("📋 None of these — Send original request", callback_data="req_send_original")])
    kb.append([InlineKeyboardButton("✍️ Enter Manual Details (Title/Author/Format/Series)", callback_data="req_start_manual")])
    kb.append([InlineKeyboardButton("❌ Cancel", callback_data="req_cancel")])

    if is_edit:
        await target_msg.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)
    else:
        await target_msg.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb), disable_web_page_preview=True)


async def request_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return
    query = " ".join(context.args).strip() if context.args else ""
    if not query:
        await msg.reply_text(
            "📖 <b>How to Request a Book / Audiobook:</b>\n"
            "• <code>/request &lt;title&gt; &lt;author&gt;</code>\n"
            "• Or tap <b>✍️ Manual Request</b> below to fill in Title, Author, Format & Series step by step.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✍️ Start Manual Request", callback_data="req_start_manual")]]),
        )
        return
    await show_request_options(msg, update.effective_user, query, context, is_edit=False)


def _render_request_log_card(req_row: dict) -> str:
    return (
        f"📥 <b>Book / Audiobook Request #{req_row['id']}</b>\n\n"
        f"🏷 <b>Type:</b> <code>{html.escape(req_row.get('request_type', 'Book/Audiobook'))}</code>\n"
        f"📖 <b>Title:</b> <b>{html.escape(req_row.get('title', 'Unknown'))}</b>\n"
        f"✍️ <b>Author:</b> <code>{html.escape(req_row.get('author', 'N/A'))}</code>\n"
        f"📚 <b>Series:</b> <code>{html.escape(req_row.get('series') or 'N/A')}</code>\n"
        f"🎧 <b>Format:</b> <code>{html.escape(req_row.get('format') or 'Any')}</code>\n"
        f"🌐 <b>Source:</b> {html.escape(req_row.get('source', 'Manual'))}\n"
        f"📌 <b>Status:</b> <code>{html.escape(req_row.get('status', 'Pending'))}</code>\n"
        f"👤 <b>User:</b> {html.escape(req_row.get('user_name', 'User'))} (<code>{req_row.get('user_id')}</code>)\n"
        f"⏱ <b>Timestamp:</b> <code>{html.escape(str(req_row.get('created_at', '')))}</code>"
    )


async def _submit_final_request(bot, user, chat_msg, title, author, series="", fmt="Any", source="Manual", url=""):
    if not can_user_request(user.id):
        await chat_msg.edit_text("⚠️ Daily request quota exhausted.")
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO requests_queue (user_id, user_name, request_type, title, author, series, format, source, audible_url, status, created_at)
        VALUES (?, ?, 'Book/Audiobook', ?, ?, ?, ?, ?, ?, 'Pending', ?)
    """, (user.id, user.full_name or user.username or "User", title, author, series, fmt, source, url, now_str))
    req_id = cur.lastrowid
    conn.commit()
    row = dict(cur.execute("SELECT * FROM requests_queue WHERE id = ?", (req_id,)).fetchone())
    conn.close()

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Show Options", callback_data=f"req_opts_{req_id}")]])
    log_msg = await send_log_with_fallback(bot, _render_request_log_card(row), "request_log_chat_id", None, reply_markup=kb)

    if log_msg:
        deduct_request_quota(user.id)
        conn = get_db_conn()
        conn.execute("UPDATE requests_queue SET log_chat_id = ?, log_message_id = ? WHERE id = ?", (log_msg.chat_id, log_msg.message_id, req_id))
        conn.commit()
        conn.close()
        summary = f"{title} by {author}" if author and author != "N/A" else title
        await chat_msg.edit_text(
            f"✅ <b>Request received!</b>\n\n<b>{html.escape(summary)}</b>\n\nYour request has been noted. Admins will review it soon!",
            parse_mode="HTML",
        )
    else:
        await chat_msg.edit_text("❌ Could not post request to Request Log. No quota was deducted.")

STATUS_LABELS = {
    "added": "Added to Database ✅",
    "notavail": "Not Available ❌",
    "notrel": "Not Released ⏳",
    "reqagain": "Request Again 🔄",
    "already": "Already Available 📚",
}


async def handle_manual_request_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    wiz = context.user_data.get("manual_req_wizard")
    if not wiz or not update.message or not update.message.text:
        return False
    txt = update.message.text.strip()
    step = wiz.get("step")

    if step == "title":
        wiz["title"] = txt
        wiz["step"] = "author"
        await update.message.reply_text("✍️ <b>Step 2/4:</b> Enter the <b>Author Name</b>:", parse_mode="HTML")
        return True
    if step == "author":
        wiz["author"] = txt
        wiz["step"] = "format"
        await update.message.reply_text("🎧 <b>Step 3/4:</b> Enter the <b>Format</b> (e.g. <code>Audiobook</code>, <code>eBook</code>, or <code>Both</code>):", parse_mode="HTML")
        return True
    if step == "format":
        wiz["format"] = txt
        wiz["step"] = "series"
        await update.message.reply_text("📚 <b>Step 4/4:</b> Enter the <b>Series Name</b> (or type <code>None</code> if standalone):", parse_mode="HTML")
        return True
    if step == "series":
        context.user_data.pop("manual_req_wizard", None)
        series_val = "" if txt.lower() == "none" else txt
        status_msg = await update.message.reply_text("⏳ Submitting your manual request...")
        await _submit_final_request(
            context.bot, update.effective_user, status_msg,
            wiz.get("title", "Unknown"), wiz.get("author", "Unknown"),
            series=series_val, fmt=wiz.get("format", "Any"), source="Manual",
        )
        return True
    return False


async def request_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    d = q.data
    user = q.from_user

    if d == "req_cancel":
        context.user_data.pop("manual_req_wizard", None)
        await q.answer("Cancelled")
        await q.message.edit_text("❌ Request cancelled. No quota was used.")
    elif d.startswith("req_from_search_"):
        await q.answer()
        query = d.replace("req_from_search_", "", 1)
        await show_request_options(q.message, user, query, context, is_edit=True)
    elif d.startswith("req_pick_opt_"):
        await q.answer("Submitting selected book...")
        idx = int(d.replace("req_pick_opt_", ""))
        opts = context.user_data.get("req_candidates", [])
        if 0 <= idx < len(opts):
            o = opts[idx]
            await _submit_final_request(context.bot, user, q.message, o["title"], o["author"], o.get("series", ""), o.get("format", "Audiobook"), o.get("source", "Audible"), o.get("url", ""))
    elif d == "req_send_original":
        await q.answer("Submitting original request...")
        raw_q = context.user_data.get("req_raw_query") or "Book Request"
        await _submit_final_request(context.bot, user, q.message, raw_q, "As Requested", "", "Any", "Original Query", "")
    elif d == "req_start_manual":
        await q.answer()
        context.user_data["manual_req_wizard"] = {"step": "title"}
        await q.message.edit_text("📖 <b>Manual Request — Step 1/4:</b>\nPlease reply with the <b>Book / Audiobook Title</b>:", parse_mode="HTML")
    elif d.startswith("req_opts_"):
        role = get_user_role_db(user.id)
        if role not in ("Moderator", "Admin", "Owner"):
            await q.answer("⛔ Only Moderators, Admins, and Owners can manage request status.", show_alert=True)
            return
        req_id = int(d.replace("req_opts_", ""))
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Added to Database", callback_data=f"req_st_{req_id}_added")],
            [InlineKeyboardButton("📚 Already Available", callback_data=f"req_st_{req_id}_already"), InlineKeyboardButton("❌ Not Available", callback_data=f"req_st_{req_id}_notavail")],
            [InlineKeyboardButton("⏳ Not Released", callback_data=f"req_st_{req_id}_notrel"), InlineKeyboardButton("🔄 Request Again", callback_data=f"req_st_{req_id}_reqagain")],
            [InlineKeyboardButton("≼ Hide Options", callback_data=f"req_hide_{req_id}")],
        ])
        await q.answer()
        await q.message.edit_reply_markup(reply_markup=kb)
    elif d.startswith("req_hide_"):
        req_id = int(d.replace("req_hide_", ""))
        await q.answer()
        await q.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Show Options", callback_data=f"req_opts_{req_id}")]]))
    elif d.startswith("req_st_"):
        role = get_user_role_db(user.id)
        if role not in ("Moderator", "Admin", "Owner"):
            await q.answer("⛔ Access denied.", show_alert=True)
            return
        _, _, req_id_str, st_code = d.split("_", 3)
        req_id = int(req_id_str)
        new_status = STATUS_LABELS.get(st_code, st_code)
        conn = get_db_conn()
        conn.execute("UPDATE requests_queue SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_status, req_id))
        conn.commit()
        row = conn.execute("SELECT * FROM requests_queue WHERE id = ?", (req_id,)).fetchone()
        conn.close()
        if row:
            rdict = dict(row)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Show Options", callback_data=f"req_opts_{req_id}")]])
            await q.message.edit_text(_render_request_log_card(rdict), parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
            try:
                await context.bot.send_message(
                    chat_id=int(rdict["user_id"]),
                    text=f"📬 <b>Request Status Updated!</b>\n\n📖 <b>Title:</b> {html.escape(rdict['title'])}\n📌 <b>New Status:</b> <code>{new_status}</code>",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        await q.answer(f"Status updated to: {new_status}")


async def request_deeplink_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return

STATUS_LABELS = {
    "added": "Added to Database ✅",
    "notavail": "Not Available ❌",
    "notrel": "Not Released ⏳",
    "reqagain": "Request Again 🔄",
    "already": "Already Available 📚",
}


async def handle_manual_request_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    wiz = context.user_data.get("manual_req_wizard")
    if not wiz or not update.message or not update.message.text:
        return False
    txt = update.message.text.strip()
    step = wiz.get("step")

    if step == "title":
        wiz["title"] = txt
        wiz["step"] = "author"
        await update.message.reply_text("✍️ <b>Step 2/4:</b> Enter the <b>Author Name</b>:", parse_mode="HTML")
        return True
    if step == "author":
        wiz["author"] = txt
        wiz["step"] = "format"
        await update.message.reply_text("🎧 <b>Step 3/4:</b> Enter the <b>Format</b> (e.g. <code>Audiobook</code>, <code>eBook</code>, or <code>Both</code>):", parse_mode="HTML")
        return True
    if step == "format":
        wiz["format"] = txt
        wiz["step"] = "series"
        await update.message.reply_text("📚 <b>Step 4/4:</b> Enter the <b>Series Name</b> (or type <code>None</code> if standalone):", parse_mode="HTML")
        return True
    if step == "series":
        context.user_data.pop("manual_req_wizard", None)
        series_val = "" if txt.lower() == "none" else txt
        status_msg = await update.message.reply_text("⏳ Submitting your manual request...")
        await _submit_final_request(
            context.bot, update.effective_user, status_msg,
            wiz.get("title", "Unknown"), wiz.get("author", "Unknown"),
            series=series_val, fmt=wiz.get("format", "Any"), source="Manual",
        )
        return True
    return False


async def request_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    d = q.data
    user = q.from_user

    if d == "req_cancel":
        context.user_data.pop("manual_req_wizard", None)
        await q.answer("Cancelled")
        await q.message.edit_text("❌ Request cancelled. No quota was used.")
    elif d.startswith("req_from_search_"):
        await q.answer()
        query = d.replace("req_from_search_", "", 1)
        await show_request_options(q.message, user, query, context, is_edit=True)
    elif d.startswith("req_pick_opt_"):
        await q.answer("Submitting selected book...")
        idx = int(d.replace("req_pick_opt_", ""))
        opts = context.user_data.get("req_candidates", [])
        if 0 <= idx < len(opts):
            o = opts[idx]
            await _submit_final_request(context.bot, user, q.message, o["title"], o["author"], o.get("series", ""), o.get("format", "Audiobook"), o.get("source", "Audible"), o.get("url", ""))
    elif d == "req_send_original":
        await q.answer("Submitting original request...")
        raw_q = context.user_data.get("req_raw_query") or "Book Request"
        await _submit_final_request(context.bot, user, q.message, raw_q, "As Requested", "", "Any", "Original Query", "")
    elif d == "req_start_manual":
        await q.answer()
        context.user_data["manual_req_wizard"] = {"step": "title"}
        await q.message.edit_text("📖 <b>Manual Request — Step 1/4:</b>\nPlease reply with the <b>Book / Audiobook Title</b>:", parse_mode="HTML")
    elif d.startswith("req_opts_"):
        role = get_user_role_db(user.id)
        if role not in ("Moderator", "Admin", "Owner"):
            await q.answer("⛔ Only Moderators, Admins, and Owners can manage request status.", show_alert=True)
            return
        req_id = int(d.replace("req_opts_", ""))
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Added to Database", callback_data=f"req_st_{req_id}_added")],
            [InlineKeyboardButton("📚 Already Available", callback_data=f"req_st_{req_id}_already"), InlineKeyboardButton("❌ Not Available", callback_data=f"req_st_{req_id}_notavail")],
            [InlineKeyboardButton("⏳ Not Released", callback_data=f"req_st_{req_id}_notrel"), InlineKeyboardButton("🔄 Request Again", callback_data=f"req_st_{req_id}_reqagain")],
            [InlineKeyboardButton("≼ Hide Options", callback_data=f"req_hide_{req_id}")],
        ])
        await q.answer()
        await q.message.edit_reply_markup(reply_markup=kb)
    elif d.startswith("req_hide_"):
        req_id = int(d.replace("req_hide_", ""))
        await q.answer()
        await q.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Show Options", callback_data=f"req_opts_{req_id}")]]))
    elif d.startswith("req_st_"):
        role = get_user_role_db(user.id)
        if role not in ("Moderator", "Admin", "Owner"):
            await q.answer("⛔ Access denied.", show_alert=True)
            return
        _, _, req_id_str, st_code = d.split("_", 3)
        req_id = int(req_id_str)
        new_status = STATUS_LABELS.get(st_code, st_code)
        conn = get_db_conn()
        conn.execute("UPDATE requests_queue SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_status, req_id))
        conn.commit()
        row = conn.execute("SELECT * FROM requests_queue WHERE id = ?", (req_id,)).fetchone()
        conn.close()
        if row:
            rdict = dict(row)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Show Options", callback_data=f"req_opts_{req_id}")]])
            await q.message.edit_text(_render_request_log_card(rdict), parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
            try:
                await context.bot.send_message(
                    chat_id=int(rdict["user_id"]),
                    text=f"📬 <b>Request Status Updated!</b>\n\n📖 <b>Title:</b> {html.escape(rdict['title'])}\n📌 <b>New Status:</b> <code>{new_status}</code>",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        await q.answer(f"Status updated to: {new_status}")


async def request_deeplink_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return
