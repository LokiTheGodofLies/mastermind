import html
import logging
from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from config import creator_id, admin_ids
from modules.database.user_db import get_users_by_role_db
from modules.utility.rich_ui import styled_button, tg_button_html, tg_button_row_html

logger = logging.getLogger(__name__)


def _build_roster_view(header_title: str, entries: list[dict], empty_note: str, footer_note: str) -> str:
    if not entries:
        return f"{header_title} (0)\n\n<i>{empty_note}</i>\n\n<i>{footer_note}</i>"

    tr_rows = []
    btn_rows = []
    for idx, u in enumerate(entries, 1):
        uid = u["user_id"]
        name = html.escape(str(u.get("full_name") or f"User {uid}")[:24])
        username = u.get("username")
        uname_cell = f"@{html.escape(username)}" if username else "—"
        role = html.escape(str(u.get("role", "Member")))
        profile_url = f"https://t.me/{username}" if username else f"tg://user?id={uid}"
        tr_rows.append(
            f"<tr><td>{idx}</td><td><a href=\"{profile_url}\">{name}</a></td>"
            f"<td>{uname_cell}</td><td><code>{uid}</code></td><td><code>{role}</code></td></tr>"
        )
        btn_rows.append(
            tg_button_row_html(
                [
                    tg_button_html(f"👤 {name}", url=profile_url, style="success"),
                    tg_button_html(f"📋 Copy ID ({uid})", copy_text=str(uid), style="danger"),
                ],
                align="left",
            )
        )

    table_html = (
        "<table striped><tr><th>#</th><th>Name</th><th>Username</th><th>User ID</th><th>Role</th></tr>"
        + "".join(tr_rows)
        + "</table>"
    )
    return (
        f"{header_title} ({len(entries)})\n\n"
        f"{table_html}\n\n"
        + "\n".join(btn_rows)
        + f"\n\n<i>{footer_note}</i>"
    )


async def admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays all Admins and the Creator."""
    msg = update.effective_message
    if not msg:
        return

    users = get_users_by_role_db("Admin")
    seen_ids = set()
    entries: list[dict] = []

    oid = creator_id()
    if oid:
        seen_ids.add(int(oid))
        owner_entry = next((u for u in users if u["user_id"] == int(oid)), None)
        if owner_entry:
            entries.append({**owner_entry, "role": "Creator"})
        else:
            entries.append({"user_id": int(oid), "full_name": "Creator", "username": None, "role": "Creator"})

    for u in users:
        if u["user_id"] not in seen_ids:
            seen_ids.add(u["user_id"])
            entries.append(u)

    for aid in admin_ids():
        if int(aid) not in seen_ids:
            seen_ids.add(int(aid))
            entries.append({"user_id": int(aid), "full_name": "Admin", "username": None, "role": "Admin"})

    text = _build_roster_view(
        "🛡️ <b>Admin &amp; Owner Roster</b>",
        entries,
        "No administrators found.",
        "Use /help for administrative command permissions.",
    )
    markup = InlineKeyboardMarkup([[styled_button("📖 Open Help Hub", callback_data="help_main", style="success")]])
    await msg.reply_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


async def moderators_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays all Moderators."""
    msg = update.effective_message
    if not msg:
        return
    users = get_users_by_role_db("Moderator")
    text = _build_roster_view(
        "⚔️ <b>Moderator Roster</b>",
        users,
        "No moderators assigned yet.",
        "Moderators review incoming requests and curate library content.",
    )
    markup = InlineKeyboardMarkup([[styled_button("📖 Open Help Hub", callback_data="help_main", style="success")]])
    await msg.reply_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


async def volunteers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays all Volunteers."""
    msg = update.effective_message
    if not msg:
        return
    users = get_users_by_role_db("Volunteer")
    text = _build_roster_view(
        "🤝 <b>Volunteer Roster</b>",
        users,
        "No volunteers assigned yet.",
        "Volunteers help index and format books for the community.",
    )
    markup = InlineKeyboardMarkup([[styled_button("📖 Open Help Hub", callback_data="help_main", style="success")]])
    await msg.reply_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


async def promoters_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays all Promoters."""
    msg = update.effective_message
    if not msg:
        return
    users = get_users_by_role_db("Promoter")
    text = _build_roster_view(
        "📢 <b>Promoter Roster</b>",
        users,
        "No promoters assigned yet.",
        "Promoters share and expand the library reach.",
    )
    markup = InlineKeyboardMarkup([[styled_button("📖 Open Help Hub", callback_data="help_main", style="success")]])
    await msg.reply_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
