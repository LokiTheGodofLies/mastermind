import html
import logging
from telegram import Update
from telegram.ext import ContextTypes
from config import creator_id, admin_ids
from modules.database.user_db import get_users_by_role_db

logger = logging.getLogger(__name__)


def _format_user_roster_line(user: dict) -> str:
    uid = user["user_id"]
    name = html.escape(user.get("full_name") or f"User {uid}")
    username = user.get("username")
    uname_str = f" (@{username})" if username else ""
    role = user.get("role", "Member")
    return f"• <a href=\"tg://user?id={uid}\">{name}</a>{uname_str} [<code>{uid}</code>] - <b>{role}</b>"


async def admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays all Admins and the Creator."""
    msg = update.effective_message
    if not msg:
        return

    users = get_users_by_role_db("Admin")
    seen_ids = set()
    formatted_list = []

    oid = creator_id()
    if oid:
        seen_ids.add(int(oid))
        owner_entry = next((u for u in users if u["user_id"] == int(oid)), None)
        if owner_entry:
            formatted_list.append(_format_user_roster_line(owner_entry))
        else:
            formatted_list.append(f"• <a href=\"tg://user?id={oid}\">Owner</a> [<code>{oid}</code>] - <b>Creator</b>")

    for u in users:
        if u["user_id"] not in seen_ids:
            seen_ids.add(u["user_id"])
            formatted_list.append(_format_user_roster_line(u))

    for aid in admin_ids():
        if int(aid) not in seen_ids:
            seen_ids.add(int(aid))
            formatted_list.append(f"• <a href=\"tg://user?id={aid}\">Admin</a> [<code>{aid}</code>] - <b>Admin</b>")

    total = len(formatted_list)
    text = (
        f"🛡️ <b>Admin & Owner Roster ({total})</b>\n\n"
        + ("\n".join(formatted_list) if formatted_list else "<i>No administrators found.</i>")
        + "\n\n<i>Use /help for administrative command permissions.</i>"
    )
    await msg.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)


async def moderators_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays all Moderators."""
    msg = update.effective_message
    if not msg:
        return
    users = get_users_by_role_db("Moderator")
    total = len(users)
    lines = [_format_user_roster_line(u) for u in users]
    text = (
        f"⚔️ <b>Moderator Roster ({total})</b>\n\n"
        + ("\n".join(lines) if lines else "<i>No moderators assigned yet.</i>")
        + "\n\n<i>Moderators review incoming requests and curate library content.</i>"
    )
    await msg.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)


async def volunteers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays all Volunteers."""
    msg = update.effective_message
    if not msg:
        return
    users = get_users_by_role_db("Volunteer")
    total = len(users)
    lines = [_format_user_roster_line(u) for u in users]
    text = (
        f"🤝 <b>Volunteer Roster ({total})</b>\n\n"
        + ("\n".join(lines) if lines else "<i>No volunteers assigned yet.</i>")
        + "\n\n<i>Volunteers help index and format books for the community.</i>"
    )
    await msg.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)


async def promoters_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays all Promoters."""
    msg = update.effective_message
    if not msg:
        return
    users = get_users_by_role_db("Promoter")
    total = len(users)
    lines = [_format_user_roster_line(u) for u in users]
    text = (
        f"📢 <b>Promoter Roster ({total})</b>\n\n"
        + ("\n".join(lines) if lines else "<i>No promoters assigned yet.</i>")
        + "\n\n<i>Promoters share and expand the library reach.</i>"
    )
    await msg.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)
