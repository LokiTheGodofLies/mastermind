import html
from datetime import datetime, timedelta, timezone
from configs import referral_search_bonus, referral_request_bonus, referral_earned_label
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.database.user_db import (
    record_referral_db,
    add_quota_limits_db,
    get_referred_users_db,
)
from modules.utility.rich_ui import styled_button


def process_referral(referrer_id: int, new_user_id: int):
    """Processes a referral when a new user starts the bot via a referral link."""
    if referrer_id == new_user_id:
        return False, "⚠️ You cannot refer yourself."

    success = record_referral_db(referrer_id, new_user_id)
    if not success:
        return False, "⚠️ You have already claimed a referral bonus."

    add_quota_limits_db(referrer_id, search_bonus=referral_search_bonus(), request_bonus=referral_request_bonus())
    add_quota_limits_db(new_user_id, search_bonus=referral_search_bonus(), request_bonus=referral_request_bonus())
    return True, "Success"


def get_user_referral_stats(user_id: int):
    """Fetches total invite count and details of invited users for a given user ID."""
    referred_rows = get_referred_users_db(user_id)
    total_invites = len(referred_rows)
    return {"total_invites": total_invites, "referred_list": referred_rows}


async def process_referral_with_notification(*args, **kwargs):
    """Compatibility wrapper for both older and newer referral call patterns."""
    context = None
    referrer_id = None
    new_user_id = None
    new_user_name = "A user"

    if args and hasattr(args[0], "bot"):
        context = args[0]
        args = args[1:]

    if len(args) >= 2 and isinstance(args[0], int) and isinstance(args[1], int):
        referrer_id, new_user_id = args[:2]

    if len(args) >= 3:
        if hasattr(args[2], "bot"):
            context = args[2]
        elif isinstance(args[2], str) and args[2].strip():
            new_user_name = args[2].strip()  # 3rd positional arg = the new user's full name

    if kwargs:
        referrer_id = kwargs.get("referrer_id", referrer_id)
        new_user_id = kwargs.get("new_user_id", new_user_id)
        new_user_name = kwargs.get("new_user_name", new_user_name)
        context = kwargs.get("context", context)

    if referrer_id is None or new_user_id is None:
        return False, "⚠️ Missing referral arguments."

    success, msg = process_referral(referrer_id, new_user_id)
    if not success:
        return False, msg

    if context is not None and hasattr(context, "bot"):
        referrer_text = (
            f"👤 <b>New Referral Joined!</b>\n\n"
            f"🔗 <a href=\"tg://user?id={int(new_user_id)}\">{html.escape(str(new_user_name))}</a> joined using your referral link.\n"
            f"🎁 You have been awarded <mark>+{referral_search_bonus()} Search</mark> and <mark>+{referral_request_bonus()} Request</mark> allowance bonuses!"
        )
        referrer_keyboard = [[
            styled_button("📋 See my referrals", callback_data="my_referrals_callback", style="primary"),
            styled_button("🔗 Refer more", callback_data="refer_more_callback", style="success"),
        ]]
        try:
            await context.bot.send_message(
                chat_id=referrer_id,
                text=referrer_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(referrer_keyboard),
            )
        except Exception:
            pass

        new_user_text = (
            "🎁 <b>Referral Bonus Claimed!</b>\n\n"
            f"Since you joined from a referral link, you got <mark>+{referral_search_bonus()} bonus search and +{referral_request_bonus()} bonus request</mark> allowances!"
        )
        new_user_keyboard = [[styled_button("🚀 Refer and earn more bonus", callback_data="refer_more_callback", style="success")]]
        try:
            await context.bot.send_message(
                chat_id=new_user_id,
                text=new_user_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(new_user_keyboard),
            )
        except Exception:
            pass

    return True, msg


_IST = timezone(timedelta(hours=5, minutes=30))
REFERRALS_PER_PAGE = 10


def _to_ist(ts) -> str:
    """SQLite CURRENT_TIMESTAMP (UTC, `YYYY-MM-DD HH:MM:SS`) -> `DD Mon YYYY, HH:MM IST`."""
    if not ts:
        return "—"
    try:
        dt = datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.astimezone(_IST).strftime("%d %b %Y, %H:%M IST")
    except ValueError:
        return html.escape(str(ts), quote=False)


def build_referrals_table_html(rows, start_index: int = 1) -> str:
    """`<table striped>`: # | User (profile link) | Username | User ID | Joined (IST).
    `rows` = (user_id, full_name, username, timestamp) tuples from `get_referred_users_db()`."""
    esc = lambda v: html.escape(str(v or ""), quote=False)
    head = "<tr>" + "".join(f"<th>{h}</th>" for h in ("#", "User", "Username", "User ID", "Joined")) + "</tr>"
    body = []
    for n, (uid, name, uname, ts) in enumerate(rows, start=start_index):
        title = esc(name) or f"User {uid}"
        body.append(
            "<tr>"
            f"<td>{n}</td>"
            f'<td><a href="tg://user?id={int(uid)}">{title}</a></td>'
            f"<td>{'@' + esc(uname) if uname else '—'}</td>"
            f"<td><code>{int(uid)}</code></td>"
            f"<td>{_to_ist(ts)}</td>"
            "</tr>"
        )
    return f"<table striped>{head}{''.join(body)}</table>"


def render_my_referrals(user_id: int, page: int = 1):
    """Returns (text, markup) of the paginated referral dashboard for `user_id`."""
    stats = get_user_referral_stats(user_id)
    total = stats["total_invites"]
    rows = stats["referred_list"]
    pages = max(1, (total + REFERRALS_PER_PAGE - 1) // REFERRALS_PER_PAGE)
    page = max(1, min(int(page), pages))
    start = (page - 1) * REFERRALS_PER_PAGE

    text = (
        "📋 <b>Your Referral Statistics</b>\n\n"
        f"• <b>Total Invites:</b> <mark>{total}</mark> users\n"
        f"• <b>Total Bonus Earned:</b> <mark>{html.escape(str(referral_earned_label(total)))}</mark>\n\n"
    )
    if rows:
        text += "👥 <b>Invited Users</b>\n" + build_referrals_table_html(rows[start:start + REFERRALS_PER_PAGE], start + 1) + "\n\n"
    else:
        text += "💡 <i>You haven't invited anyone yet. Share your link to start earning bonuses!</i>\n\n"
    text += "Keep sharing your link using <code>/refer</code> to earn more allowances!"

    keyboard = []
    if pages > 1:
        nav = []
        if page > 1:
            nav.append(styled_button("◀️ Prev", callback_data=f"myref_p_{page - 1}", style="primary"))
        nav.append(styled_button(f"📄 {page}/{pages}", callback_data="noop", disabled=True))
        if page < pages:
            nav.append(styled_button("Next ▶️", callback_data=f"myref_p_{page + 1}", style="primary"))
        keyboard.append(nav)
    keyboard.append([styled_button("📤 Refer More Friends", callback_data="refer_more_callback", style="success")])
    keyboard.append([styled_button("« Back to Start", callback_data="start_menu", style="primary")])
    return text, InlineKeyboardMarkup(keyboard)


async def my_referrals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the user's referral statistics and the table of invited users."""
    user = update.effective_user
    msg = update.effective_message
    if not user or not msg:
        return
    text, markup = render_my_referrals(user.id, 1)
    if update.callback_query:
        await update.callback_query.answer()
    await msg.reply_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)


async def my_referrals_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """`myref_p_<page>` pagination: edits the referral card in place."""
    q = update.callback_query
    if not q or not q.data or not q.message:
        return
    try:
        page = int(q.data.rsplit("_", 1)[1])
    except (ValueError, IndexError):
        page = 1
    text, markup = render_my_referrals(q.from_user.id, page)
    try:
        await q.message.edit_text(text, parse_mode="HTML", reply_markup=markup, disable_web_page_preview=True)
    except Exception:
        pass
    await q.answer()
