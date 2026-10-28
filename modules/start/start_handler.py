from datetime import datetime
from urllib.parse import quote
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.database.user_db import add_or_update_user_db, get_user_role_db, set_helper_started_db, get_owner_ids
from modules.database.config_db import get_template, format_template_string, get_config, get_config_int
from modules.database.file_db import get_file_by_start_payload_db
from modules.allowance.referral import process_referral_with_notification
from modules.allowance.allowance import get_user_quota_summary


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    target_msg = update.message or (update.callback_query.message if update.callback_query else None)
    if not user or not target_msg:
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    is_private = update.effective_chat and update.effective_chat.type == "private"
    is_new = add_or_update_user_db(user.id, user.username, user.full_name, today_str, helper_started=True if is_private else None)
    if is_private:
        set_helper_started_db(user.id, True)

    referral_notice = ""
    args = context.args or []

    if args and args[0].startswith(("dl_", "file_")):
        try:
            payload = args[0]
            tail = payload.split("_", 1)[1]
            if tail.isdigit():
                file_row_id = int(tail)
            else:
                file_row = get_file_by_start_payload_db(payload)
                if not file_row:
                    await target_msg.reply_text("❌ File no longer exists in database.")
                    return
                file_row_id = int(file_row["id"])
            from modules.search.handlers import deliver_file_to_user
            await deliver_file_to_user(target_msg, user, file_row_id, context)
            return
        except Exception as e:
            await target_msg.reply_text(f"❌ Error delivering file: {e}")
            return

    if args and args[0].startswith("ref_"):
        try:
            ref_id = int(args[0].split("_", 1)[1])
            ok, msg = await process_referral_with_notification(context, ref_id, user.id, user.full_name or user.first_name, is_first_time=is_new)
            if ok:
                s_bon, r_bon = get_config_int("referral_bonus_search", 10), get_config_int("referral_bonus_request", 10)
                referral_notice = f"\n\n🎁 <b>Referral bonus applied: +{s_bon} search quota, +{r_bon} request quota!</b>"
            else:
                referral_notice = f"\n\n<i>{msg}</i>"
        except ValueError:
            pass
    elif args and args[0] == "helper_init":
        referral_notice = "\n\n✅ <b>Helper Bot Activated!</b> You can now click any search result to receive files in the posting channel and DM."

    tpl = get_template("start")
    raw_txt = tpl.get("text") or "Hi <b>{user_name}</b>, welcome to <b>{bot_title}</b>! 👋"
    text = format_template_string(raw_txt, {"user_name": user.first_name or "User"}) + referral_notice

    bot_uname = context.bot.username or "Bot"
    ref_link = f"https://t.me/{bot_uname}?start=ref_{user.id}"
    share_url = (
        "https://t.me/share/url?"
        f"url={quote(ref_link, safe='')}"
        f"&text={quote('Join and earn +10 bonus quota', safe='')}"
    )

    kb = [
        [InlineKeyboardButton("🔍 Search Library", callback_data="search_menu"), InlineKeyboardButton("📖 Help Menu", callback_data="help_button")],
        [InlineKeyboardButton("📊 My Quota", callback_data="quota_menu"), InlineKeyboardButton("🔄 Convert Ebook", callback_data="cv|menu")],
        [InlineKeyboardButton(f"📤 Refer & Earn +{get_config_int('referral_bonus_search', 10)}", url=share_url)],
    ]
    community = get_config("community_url")
    if community:
        kb.append([InlineKeyboardButton("💬 Join Community", url=community)])

    for b in tpl.get("buttons", []):
        if b.get("type") == "url":
            kb.append([InlineKeyboardButton(b["label"], url=b["target"])])
        else:
            kb.append([InlineKeyboardButton(b["label"], callback_data=b["target"])])

    role = get_user_role_db(user.id)
    if role in ("Admin", "Owner"):
        kb.append([InlineKeyboardButton("🪄 Customize Bot", callback_data="cust_open_main"), InlineKeyboardButton("👑 Admin Help", callback_data="help_open_admin")])

    markup = InlineKeyboardMarkup(kb)
    if update.callback_query:
        await update.callback_query.answer()
        await target_msg.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        if tpl.get("media_type") == "photo" and tpl.get("media_id"):
            await target_msg.reply_photo(photo=tpl["media_id"], caption=text, parse_mode="HTML", reply_markup=markup)
        else:
            await target_msg.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def menu_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    d = q.data
    if d in ("help_button", "help_menu", "help_open_admin") or d.startswith(("help_sec_", "adm_sec_")):
        from modules.help.handlers import help_button_callback
        await help_button_callback(update, context)
    elif d == "start_menu":
        await start_command(update, context)
    elif d == "search_menu":
        from modules.search.handlers import search_command
        await search_command(update, context)
    elif d == "stats_menu":
        from modules.stats.handlers import stats_command
        await stats_command(update, context)
    elif d in ("quota", "quota_menu"):
        await q.answer()
        s = get_user_quota_summary(q.from_user.id)
        txt = (
            f"📊 <b>Your Quota Status</b>\n\n"
            f"🛡 <b>Role:</b> <code>{s['role']}</code>\n"
            f"🔍 <b>Searches Remaining:</b> <code>{s['searches_left']} / {s['searches_limit']}</code>\n"
            f"📥 <b>Requests Remaining:</b> <code>{s['requests_left']} / {s['requests_limit']}</code>"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("≼ Back to Start", callback_data="start_menu")]])
        await q.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)
    elif d == "bot_owner":
        await q.answer()
        owners = ", ".join(f"<code>{o}</code>" for o in sorted(get_owner_ids())) or "<i>not configured</i>"
        await q.message.edit_text(f"👑 <b>Bot Owner:</b> {owners}", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("≼ Back", callback_data="start_menu")]]))
