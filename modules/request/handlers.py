import re
import logging
import html
import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ApplicationHandlerStop
import config
from modules.database.file_db import search_files_db
from modules.allowance.allowance import can_user_request, deduct_request_quota
from modules.utility.rich_ui import styled_button, tg_button_html, tg_button_row_html
from modules.utility.small_caps import from_small_caps, to_small_caps

logger = logging.getLogger(__name__)


REQUEST_GUIDE_TEXT = (
    "📖 <b>How to Request Books &amp; Audiobooks</b>\n\n"
    "<table striped>"
    "<tr><th>Option</th><th>Syntax / Fields</th></tr>"
    "<tr><td>⚡ <b>Quick Request</b></td><td><code>/request The Striker Ana Huang</code></td></tr>"
    "<tr><td>📗 <b>Single Book</b></td><td>Title, Author, Format (EPUB / Audio)</td></tr>"
    "<tr><td>📚 <b>Book Series</b></td><td>Title 1..N, Series, Author, Format</td></tr>"
    "</table>\n\n"
    "<b>Option 1: Standalone Book</b>\n"
    "<code>/request\n"
    "Title: The Striker\n"
    "Author: Ana Huang\n"
    "Format: Audiobook / EPUB / PDF</code>\n\n"
    "<b>Option 2: Book Series</b>\n"
    "<code>/request\n"
    "Title 1: King of Wrath\n"
    "Title 2: King of Pride\n"
    "Title 3: King of Greed\n"
    "Series: Kings of Sin\n"
    "Author: Ana Huang\n"
    "Format: EPUB / PDF</code>"
)


def fetch_goodreads_metadata(query):
    try:
        base_url = config.goodreads_base_url()
        search_url = f"{base_url}/search?q={requests.utils.quote(query)}"
        headers = {"User-Agent": config.scraper_user_agent()}
        resp = requests.get(search_url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        rows = soup.select("tr[itemtype='http://schema.org/Book']")[:5]
        for row in rows:
            title_tag = row.select_one("span[itemprop='name']")
            author_tag = row.select_one("span[itemprop='author']")
            link_tag = row.select_one("a.bookTitle")
            rating_tag = row.select_one("span.minirating")

            if title_tag and link_tag:
                title = title_tag.get_text(strip=True)
                author = author_tag.get_text(strip=True) if author_tag else "Unknown Author"
                url = base_url + link_tag["href"]
                rating = rating_tag.get_text(strip=True) if rating_tag else ""
                results.append({"title": title, "author": author, "url": url, "rating": rating})
        return results
    except Exception as e:
        logger.error(f"Error fetching Goodreads metadata: {e}")
        return []


async def request_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    if not message:
        return

    if user and not can_user_request(user.id):
        await message.reply_text(
            "⚠️ <b>Daily request quota reached!</b>\n\n"
            "Use <code>/quota</code> to view your limits or <code>/refer</code> to invite friends and earn bonus requests.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    styled_button("📊 Check Quota", callback_data="quota", style="danger"),
                    styled_button("🎁 Refer & Earn", callback_data="refer_more_callback", style="success"),
                ]
            ]),
        )
        return

    raw_text = message.text or message.caption or ""
    query = re.sub(r"^/(?:request|req)(?:@\w+)?\s*", "", raw_text, count=1, flags=re.IGNORECASE | re.DOTALL).strip()
    if not query and context.args:
        query = " ".join(context.args).strip()
    query = from_small_caps(query)  # titles pasted from the bot's own small-caps text
    if not query:
        await message.reply_text(
            REQUEST_GUIDE_TEXT,
            parse_mode="HTML",
        )
        return

    q_esc = html.escape(query)
    status_msg = await message.reply_text(f"🔎 Searching local database for <mark>{q_esc}</mark>...", parse_mode="HTML")

    rows = search_files_db(query, limit=5)
    if rows:
        tr_list = []
        for idx, row in enumerate(rows, 1):
            fname = html.escape(str(row["file_name"] or "Unknown")[:36])
            ext = html.escape(str(row.get("extension") or ""))
            if ext and not ext.startswith("."):
                ext = f".{ext}"
            tr_list.append(f"<tr><td>{idx}</td><td><code>{fname}</code></td><td><code>{ext or '-'}</code></td></tr>")

        table_html = (
            "<table striped><tr><th>#</th><th>File Name</th><th>Ext</th></tr>"
            + "".join(tr_list)
            + "</table>"
        )
        text = (
            f"📁 <b>Local Library Matches Found!</b>\n"
            f"Query: <mark>{q_esc}</mark>\n\n"
            f"{table_html}\n\n"
            "<b>Would you like to search our library first or submit a new request?</b>"
        )

        safe_q = query[:30]
        keyboard = [
            [styled_button("🔍 Search in Library", callback_data=f"search_direct_{safe_q}", style="success")],
            [styled_button("📤 Request Anyway", callback_data=f"req_sub_orig_{query[:40]}", style="success")],
            [styled_button("❌ Cancel", callback_data="req_join_no", style="danger")],
        ]
        await status_msg.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await process_goodreads_or_request(status_msg, query, context)


async def process_goodreads_or_request(status_msg, query, context):
    q_esc = html.escape(query)
    await status_msg.edit_text(
        f"🔎 Not found in local database. Fetching Goodreads metadata for <mark>{q_esc}</mark>...",
        parse_mode="HTML",
    )
    matches = fetch_goodreads_metadata(query)
    if matches:
        bot_username = context.bot.username or (await context.bot.get_me()).username
        if "goodreads_cache" not in context.bot_data:
            context.bot_data["goodreads_cache"] = {}
        context.bot_data["goodreads_cache"][status_msg.chat_id] = matches
        context.bot_data["goodreads_last_matches"] = matches
        context.bot_data["goodreads_last_query"] = query

        tr_rows = []
        btn_rows = []
        for idx, book in enumerate(matches):
            title = html.escape(str(book["title"])[:32])
            author = html.escape(str(book["author"])[:24])
            url = book["url"]
            rating = html.escape(str(book.get("rating", "") or "—")[:18])
            cmd_link = f"https://t.me/{bot_username}?start=req_pick_{idx}"
            tr_rows.append(
                f"<tr><td>{idx + 1}</td><td><b>{title}</b></td><td><code>{author}</code></td><td>{rating}</td></tr>"
            )
            btn_rows.append(
                tg_button_row_html(
                    [
                        tg_button_html(f"📥 Select #{idx + 1}", url=cmd_link, style="success"),
                        tg_button_html(f"📖 Goodreads #{idx + 1}", url=url, style="danger"),
                    ],
                    align="left",
                )
            )

        table_html = (
            "<table striped><tr><th>#</th><th>Title</th><th>Author</th><th>Rating</th></tr>"
            + "".join(tr_rows)
            + "</table>"
        )
        lines = [
            f"📖 <b>Goodreads Matches Found for:</b> <mark>{q_esc}</mark>",
            "",
            table_html,
            "",
            "Tap a button below to select and request your book:",
            *btn_rows,
        ]

        manual_link = f"https://t.me/{bot_username}?start=req_manual"
        kb = InlineKeyboardMarkup([
            [styled_button(f"✍️ Request Manually (\"{query[:28]}\")", url=manual_link, style="success")],
            [styled_button("❌ Cancel", callback_data="req_join_no", style="danger")],
        ])
        text = "\n".join(lines).strip()
        await status_msg.edit_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
    else:
        text = (
            f"📖 <b>Book Request:</b> <mark>{q_esc}</mark>\n\n"
            "<table striped>"
            "<tr><th>Field</th><th>Details</th></tr>"
            f"<tr><td>📖 <b>Query</b></td><td><code>{q_esc[:36]}</code></td></tr>"
            "<tr><td>🌐 <b>Goodreads</b></td><td>No direct match found</td></tr>"
            "</table>\n\n"
            "Would you like to submit this request directly to the Request Channel?"
        )
        keyboard = [
            [
                styled_button("📤 Submit Request", callback_data=f"req_sub_orig_{query[:40]}", style="success"),
                styled_button("❌ Cancel", callback_data="req_join_no", style="danger"),
            ]
        ]
        await status_msg.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))


async def request_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("req_sub_orig_") or data.startswith("req_sub_gb_"):
        user = query.from_user
        if user and not can_user_request(user.id):
            await query.edit_message_text(
                "⚠️ <b>Daily request quota reached!</b>\n\n"
                "Use <code>/quota</code> to view your limits or <code>/refer</code> to earn bonus requests.",
                parse_mode="HTML",
            )
            return

        book_query = data.split("_", 3)[-1]
        request_channel_id = config.request_channel_id()
        if request_channel_id is None:
            logger.error("PUBLIC_/TESTING_REQUEST_CHANNEL_ID is not configured")
            await query.edit_message_text("❌ Requests are not configured right now. Please try again later.")
            return

        user_mention = f"<a href='tg://user?id={user.id}'>{html.escape(user.full_name)}</a>"
        bq_esc = html.escape(book_query)

        req_text = (
            f"📥 <b>New Book Request</b>\n\n"
            f"<table striped>"
            f"<tr><th>Field</th><th>Details</th></tr>"
            f"<tr><td>👤 <b>Requested By</b></td><td>{user_mention}</td></tr>"
            f"<tr><td>🆔 <b>User ID</b></td><td><code>{user.id}</code></td></tr>"
            f"<tr><td>📖 <b>Book / Query</b></td><td><code>{bq_esc}</code></td></tr>"
            f"</table>\n\n"
            f"<b>Status:</b> <mark>⏳ Pending Review</mark>"
        )
        status_markup = InlineKeyboardMarkup([
            [
                styled_button("⏳ In Progress", callback_data=f"req_stat_prog_{user.id}", style="success"),
                styled_button("✅ Completed", callback_data=f"req_stat_done_{user.id}", style="success"),
                styled_button("❌ Rejected", callback_data=f"req_stat_rej_{user.id}", style="danger"),
            ]
        ])
        try:
            await context.bot.send_message(
                chat_id=request_channel_id,
                text=req_text,
                parse_mode="HTML",
                reply_markup=status_markup,
            )
            deduct_request_quota(user.id)

            logger_group = config.logger_group_id()
            req_topic = config.log_topic("REQUEST")
            if logger_group and int(logger_group) != int(request_channel_id):
                log_kwargs = {"chat_id": int(logger_group), "text": req_text, "parse_mode=":"HTML", "reply_markup": status_markup}
                log_kwargs = {"chat_id": int(logger_group), "text": req_text, "parse_mode": "HTML", "reply_markup": status_markup}
                if req_topic:
                    log_kwargs["message_thread_id"] = int(req_topic)
                try:
                    await context.bot.send_message(**log_kwargs)
                except Exception:
                    pass

            await query.edit_message_text(
                f"✅ <b>Request Submitted Successfully!</b>\n\n"
                f"<table striped>"
                f"<tr><th>Field</th><th>Details</th></tr>"
                f"<tr><td>📖 <b>Requested Book</b></td><td><code>{bq_esc}</code></td></tr>"
                f"<tr><td>📢 <b>Destination</b></td><td>Request Channel</td></tr>"
                f"<tr><td>📌 <b>Status</b></td><td>⏳ Pending Review</td></tr>"
                f"</table>",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Failed to send request to channel: {e}")
            await query.edit_message_text("❌ Failed to submit request to channel. Please try again later.")
    elif data.startswith("req_stat_"):
        user = query.from_user
        user_id = user.id if user else 0
        from modules.database.user_db import get_user_role_db
        role = get_user_role_db(user_id)
        if role not in ("Moderator", "Admin", "Creator", "Owner"):
            await query.answer("⛔ Only Moderators, Admins, and the Creator can change request status.", show_alert=True)
            return

        parts = data.split("_")
        action = parts[2] if len(parts) > 2 else "done"
        status_labels = {
            "prog": "⏳ In Progress",
            "done": "✅ Completed",
            "rej": "❌ Rejected",
        }
        label = status_labels.get(action, "Updated")
        actor_name = f"@{user.username}" if user.username else html.escape(user.first_name)

        orig_text = query.message.text_html or query.message.text or ""
        # The card was sent in small caps, so the old "Status" line is matched in both spellings.
        status_word = f"(?:Status|{re.escape(to_small_caps('Status'))})"
        clean_text = re.sub(rf"\n\n<b>{status_word}:</b>.*", "", orig_text, flags=re.DOTALL)
        new_text = f"{clean_text}\n\n<b>Status:</b> <mark>{label}</mark> (by {actor_name})"

        try:
            await query.edit_message_text(new_text, parse_mode="HTML", reply_markup=query.message.reply_markup)
            await query.answer(f"Status changed to {label}!")
        except Exception as exc:
            logger.warning(f"Failed to update request status message: {exc}")
            await query.answer("Status updated.")
    elif data == "req_join_no":
        await query.edit_message_text("❌ Request cancelled.")


async def request_deeplink_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not context.args:
        return
    payload = context.args[0]
    if payload.startswith("req_pick_"):
        try:
            idx = int(payload.split("req_pick_")[1])
        except ValueError:
            return
        matches = context.bot_data.get("goodreads_cache", {}).get(
            message.chat_id,
            context.bot_data.get("goodreads_last_matches", []),
        )
        orig_query = context.bot_data.get("goodreads_last_query", "")
        if 0 <= idx < len(matches):
            book_data = matches[idx]
            title = html.escape(book_data["title"])
            author = html.escape(book_data["author"])
            rating = html.escape(book_data.get("rating", "No rating") or "No rating")
            url = book_data["url"]
            text = (
                f"📖 <b>Goodreads Book Selected</b>\n\n"
                f"<table striped>"
                f"<tr><th>Field</th><th>Details</th></tr>"
                f"<tr><td>📌 <b>Title</b></td><td><b>{title}</b></td></tr>"
                f"<tr><td>✍️ <b>Author</b></td><td><code>{author}</code></td></tr>"
                f"<tr><td>⭐ <b>Rating</b></td><td>{rating}</td></tr>"
                f"</table>\n\n"
                f"Is this the book you are looking for?"
            )
            encoded_title = book_data["title"][:40]
            fallback_q = (orig_query or book_data["title"])[:40]
            keyboard = [
                [styled_button("📖 Open on Goodreads", url=url, style="success")],
                [styled_button("✅ Yes (Submit Goodreads)", callback_data=f"req_sub_gb_{encoded_title}", style="success")],
                [styled_button("❌ No (Submit Original)", callback_data=f"req_sub_orig_{fallback_q}", style="danger")],
            ]
            await message.reply_text(
                text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            raise ApplicationHandlerStop
    elif payload == "req_manual":
        orig_query = context.bot_data.get("goodreads_last_query", "Book Request")
        oq_esc = html.escape(orig_query)
        text = (
            f"📖 <b>Book Request:</b> <mark>{oq_esc}</mark>\n\n"
            f"<table striped>"
            f"<tr><th>Field</th><th>Details</th></tr>"
            f"<tr><td>📖 <b>Query</b></td><td><code>{oq_esc}</code></td></tr>"
            f"<tr><td>📌 <b>Mode</b></td><td>Manual Request</td></tr>"
            f"</table>\n\n"
            "Would you like to submit this request directly to the Request Channel?"
        )
        keyboard = [
            [
                styled_button("📤 Submit Request", callback_data=f"req_sub_orig_{orig_query[:40]}", style="success"),
                styled_button("❌ Cancel", callback_data="req_join_no", style="danger"),
            ]
        ]
        await message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        raise ApplicationHandlerStop
