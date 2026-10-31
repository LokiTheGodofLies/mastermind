import asyncio
import html
from config import bot_name, creator_dm_link, creator_id, creator_username, referral_bonus_label
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from modules.database.user_db import add_or_update_user_db, record_bot_start_db
from modules.allowance.referral import process_referral_with_notification
from modules.utility.rich_ui import styled_button


_BG_TASKS: set = set()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Telegram command handler for /start, handles registration, referrals, request deep links, and welcome UI."""
    user = update.effective_user
    if not user:
        return

    target_message = update.effective_message
    if not target_message:
        return

    user_name = html.escape(user.first_name or "Friend")
    today_str = datetime.now().strftime("%Y-%m-%d")
    bot_username = context.bot.username

    add_or_update_user_db(user.id, user.username, user.full_name, today_str)

    args = context.args

    # New-user log (Logger Group -> USER topic): fires once per person, the first time they /start the main bot,
    # whatever the payload is (plain, referral, download or request deep link).
    if not update.callback_query:
        referrer_for_log = None
        if args and args[0].startswith("ref_"):
            try:
                _rid = int(args[0].split("_", 1)[1])
                if _rid != user.id:
                    referrer_for_log = _rid
            except ValueError:
                pass
        if record_bot_start_db(user.id, "main", bot_username or ""):
            from modules.log.startup_log import log_new_user_start
            _t = asyncio.create_task(
                log_new_user_start(context.bot, user, is_helper=False, referrer_id=referrer_for_log)
            )
            _BG_TASKS.add(_t)
            _t.add_done_callback(_BG_TASKS.discard)

    if args and (args[0].startswith("req_pick_") or args[0] == "req_manual"):
        from modules.request.handlers import request_deeplink_handler
        await request_deeplink_handler(update, context)
        return

    if args and args[0].startswith("dl_"):
        from modules.search.delivery import handle_deeplink_file_delivery
        await handle_deeplink_file_delivery(update, context, args[0])
        return

    referral_notice = ""
    if args and args[0].startswith("ref_"):
        try:
            referrer_id = int(args[0].split("_")[1])
            success, _ = await process_referral_with_notification(context, referrer_id, user.id, user.full_name)
            if success:
                referral_notice = f"\n\n🎉 <b>Referral Bonus Applied!</b> You and your referrer received <mark>{html.escape(referral_bonus_label())}</mark>."
        except ValueError:
            pass

    message = (
        f"Hi <b>{user_name}</b>, welcome to <mark>{html.escape(bot_name())} Bot</mark>! 👋\n\n"
        "I am your modular community library assistant. Tap the colorful buttons below to search books, explore the help hub, or reach out to the Creator."
        f"{referral_notice}"
    )

    my_referral_link = f"https://t.me/{bot_username}?start=ref_{user.id}"
    share_text = "try this amazing bot and let's earn bonus searches and requests !"
    share_url = f"https://t.me/share/url?url={my_referral_link}&text={share_text}"

    keyboard = [
        [
            styled_button("🔍 Search Books", callback_data="search_menu", style="success"),
            styled_button("📖 Help Menu", callback_data="help_button", style="primary"),
        ],
        [
            styled_button("📊 My Quota", callback_data="quota", style="primary"),
            styled_button("👑 Creator", callback_data="bot_owner", style="primary"),
        ],
        [
            styled_button("📤 Refer & Earn Bonus", url=share_url, style="success"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(message, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await target_message.reply_text(message, parse_mode="HTML", reply_markup=reply_markup)


async def menu_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return
    data = query.data

    if data in ("help_button", "help_menu"):
        await query.answer()
        from modules.help.handlers import help_command
        await help_command(update, context)
    elif data == "bot_owner":
        await query.answer()
        oid = creator_id()
        _un = creator_username()
        dm_url = creator_dm_link()
        _label = f"@{html.escape(_un)}" if _un else "Creator"
        rows = []
        if dm_url:
            rows.append([styled_button(f"💬 Message {_label}", url=dm_url, style="success")])
        rows.append([styled_button("📋 Copy Creator ID", copy_text=str(oid), style="primary")])
        rows.append([styled_button("« Back to Start", callback_data="start_menu", style="primary")])
        await query.message.edit_text(
            f"👑 <b>Bot Creator</b>\n\n"
            f"• <b>Creator:</b> <mark>{_label}</mark>\n"
            f"• <b>Creator ID:</b> <code>{oid}</code>\n\n"
            f"For support, inquiries, or partnership, tap the button below to contact the Creator directly.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(rows),
        )
    elif data == "search_menu":
        from modules.search.handlers import search_command
        await search_command(update, context)
    elif data == "request_menu":
        await query.answer()
        from modules.request.handlers import REQUEST_GUIDE_TEXT
        await query.message.reply_text(
            REQUEST_GUIDE_TEXT,
            parse_mode="HTML",
        )
    elif data == "stats_menu":
        await query.answer()
        from modules.stats.handlers import stats_command
        await stats_command(update, context)
    elif data == "start_menu":
        await start_command(update, context)
    elif data in ("quota", "quota_menu", "quota_shortcut"):
        from modules.allowance.allowance import quota_command
        await quota_command(update, context)
    elif data == "my_referrals_callback":
        from modules.allowance.referral import my_referrals_command
        await my_referrals_command(update, context)
    elif data == "refer_more_callback":
        from modules.allowance.allowance import refer_command
        await refer_command(update, context)


start_handler = start_command
