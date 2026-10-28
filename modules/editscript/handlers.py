import os
import sys
import html
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.database.config_db import (
    get_config, get_config_bool, set_config, get_all_configs, reload_config_cache,
    get_template, list_templates, update_template_text, update_template_media,
    remove_template_media, add_template_button, remove_template_button,
    add_fsub_channel_db, remove_fsub_channel_db, get_fsub_channels_db,
    reset_channels_and_groups_db,
)
from modules.database.user_db import get_user_role_db, reset_user_db
from modules.database.file_db import reset_file_db
from modules.utility.tg_compat import get_forward_chat
from modules.database import persistence


def _is_admin(user_id: int) -> bool:
    return get_user_role_db(user_id) in ("Admin", "Owner")


def _build_main_dashboard() -> tuple:
    bot_title = get_config("bot_title", "Mastermind Library Bot")
    text = (
        f"🪄 <u><b>Customize Bot</b></u>\n\n"
        f"➢ <b>Name:</b> <i>{html.escape(bot_title)}</i> 💖✨\n\n"
        f"<i>Configure Your Bot Settings Using Given Buttons</i>"
    )
    kb = [
        [InlineKeyboardButton("START MSG", callback_data="cust_mod_start"), InlineKeyboardButton("FORCE SUB", callback_data="cust_fsub_menu")],
        [InlineKeyboardButton("HELP & ADMIN", callback_data="cust_mod_help"), InlineKeyboardButton("AUTO DELETE", callback_data="cust_autodel_menu")],
        [InlineKeyboardButton("SEARCH & DELIVERY", callback_data="cust_mod_search"), InlineKeyboardButton("REQUESTS & AUDIBLE", callback_data="cust_mod_request")],
        [InlineKeyboardButton("QUOTA & REFERRAL", callback_data="cust_mod_quota"), InlineKeyboardButton("INDEXING & QUEUE", callback_data="cust_mod_indexing")],
        [InlineKeyboardButton("ROLES & MODS", callback_data="cust_mod_roles"), InlineKeyboardButton("LOGS & CHANNELS", callback_data="cust_mod_logs")],
        [InlineKeyboardButton("VARIABLES / CONFIG", callback_data="cust_vars_menu"), InlineKeyboardButton("STATS", callback_data="stats_menu")],
        [InlineKeyboardButton("RESTART BOT", callback_data="cust_sys_restart"), InlineKeyboardButton("RESET USER DB", callback_data="cust_ask_rst_user")],
        [InlineKeyboardButton("RESET FILE DB", callback_data="cust_ask_rst_file"), InlineKeyboardButton("RESET CHANNELS DB", callback_data="cust_ask_rst_chan")],
        [InlineKeyboardButton("≼ BACK", callback_data="start_menu")],
    ]
    return text, InlineKeyboardMarkup(kb)


def _build_start_module_page() -> tuple:
    text = (
        "📝 <u><b>START MESSAGE:</b></u>\n\n"
        "<blockquote>START MESSAGE: WHEN USER GIVE START COMMAND OR START THE BOT THEN BOT REPLY START MESSAGE. "
        "IN START MESSAGE BOT OWNER CAN SET START MESSAGE TEXT, PICTURE AND BUTTON.</blockquote>"
    )
    kb = [
        [InlineKeyboardButton("START TEXT", callback_data="cust_edit_txt_start")],
        [InlineKeyboardButton("START PICTURE", callback_data="cust_edit_med_start")],
        [InlineKeyboardButton("START BUTTON", callback_data="cust_edit_btn_start")],
        [InlineKeyboardButton("HELP TEXT", callback_data="cust_edit_txt_help")],
        [InlineKeyboardButton("ABOUT TEXT", callback_data="cust_edit_txt_about")],
        [InlineKeyboardButton("≼ BACK", callback_data="cust_open_main")],
    ]
    return text, InlineKeyboardMarkup(kb)


def _build_generic_module_page(module_name: str) -> tuple:
    tpls = list_templates(module_name)
    text = (
        f"📝 <u><b>{module_name.upper()} MODULE TEMPLATES:</b></u>\n\n"
        f"<blockquote>CUSTOMIZE ALL BOT REPLY STRINGS, MEDIA PICTURES, AND INLINE BUTTONS FOR THE {module_name.upper()} MODULE.</blockquote>"
    )
    kb = []
    for t in tpls:
        tname = t["name"]
        lbl = t.get("title") or tname.upper()
        kb.append([InlineKeyboardButton(f"✏️ {lbl} (TEXT)", callback_data=f"cust_edit_txt_{tname}")])
        kb.append([
            InlineKeyboardButton(f"🖼 {tname.upper()} PIC", callback_data=f"cust_edit_med_{tname}"),
            InlineKeyboardButton(f"🔘 {tname.upper()} BTN", callback_data=f"cust_edit_btn_{tname}"),
        ])
    kb.append([InlineKeyboardButton("≼ BACK", callback_data="cust_open_main")])
    return text, InlineKeyboardMarkup(kb)


def _build_fsub_page() -> tuple:
    is_on = get_config_bool("fsub_enabled", False)
    status_line = "FORCE SUBSCRIBE - ON ✅" if is_on else "FORCE SUBSCRIBE - OFF ❌"
    toggle_lbl = "OFF FORCE SUBSCRIBE" if is_on else "ON FORCE SUBSCRIBE"
    text = (
        "📢 <u><b>FORCE SUBSCRIBE:</b></u>\n\n"
        "<blockquote>FORCE SUBSCRIBE:\n"
        "A TELEGRAM BOT FEATURE FORCING USERS TO SUBSCRIBE TO SPECIFIC CHANNELS BEFORE ACCESSING CONTENT.\n\n"
        "NORMAL FSUB:\n"
        "REQUIRES THE USER TO CLICK A JOIN BUTTON ON A CHANNEL OR GROUP, THEN BOT CHECKS MEMBERSHIP INSTANTLY TO UNLOCK RESTRICTED CONTENT OR CHAT ACCESS.\n\n"
        "JOIN REQUEST FSUB:\n"
        "REQUIRES THE USER TO SEND A REQUEST TO JOIN A PRIVATE CHANNEL OR GROUP THEN USER CAN ACCESS CONTENT.\n\n"
        "YOU CAN ADD MULTIPLE CHANNELS</blockquote>\n\n"
        f"<b>{status_line}</b>"
    )
    kb = []
    for ch in get_fsub_channels_db():
        cid = ch["channel_id"]
        mode_tag = "🔒 Req" if ch.get("mode") == "join_request" else "📢 Norm"
        kb.append([InlineKeyboardButton(f"{ch['title']} ({mode_tag})", callback_data=f"cust_fsub_ch_{cid}")])
    kb.append([InlineKeyboardButton("➕ ADD CHANNEL ➕", callback_data="cust_fsub_add")])
    kb.append([InlineKeyboardButton(toggle_lbl, callback_data="cust_fsub_toggle")])
    kb.append([InlineKeyboardButton("FORCE SUBSCRIBE MESSAGE", callback_data="cust_edit_txt_fsub_message")])
    kb.append([InlineKeyboardButton("≼ BACK", callback_data="cust_open_main")])
    return text, InlineKeyboardMarkup(kb)


async def editscript_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not _is_admin(q.from_user.id):
        if q:
            await q.answer("⛔ Access denied.", show_alert=True)
        return
    d = q.data
    uid = q.from_user.id

    if d in ("cust_open_main", "es_menu_main"):
        await q.answer()
        txt, kb = _build_main_dashboard()
        await q.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)
    elif d == "cust_mod_start":
        await q.answer()
        txt, kb = _build_start_module_page()
        await q.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)
    elif d.startswith("cust_mod_"):
        await q.answer()
        mod = d.replace("cust_mod_", "")
        txt, kb = _build_generic_module_page(mod)
        await q.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)
    elif d == "cust_fsub_menu":
        await q.answer()
        txt, kb = _build_fsub_page()
        await q.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)
    elif d == "cust_fsub_toggle":
        cur = get_config_bool("fsub_enabled", False)
        set_config("fsub_enabled", "false" if cur else "true", "bool", uid)
        await q.answer(f"Force Subscribe {'Disabled ❌' if cur else 'Enabled ✅'}")
        txt, kb = _build_fsub_page()
        await q.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)
    elif d == "cust_fsub_add":
        await q.answer()
        context.user_data["cust_prompt"] = {"action": "add_fsub"}
        await q.message.edit_text(
            "➕ <b>Add Force Subscribe Channel</b>\n\n"
            "1. Make sure the bot is an <b>Admin</b> in the target channel/group.\n"
            "2. Reply with the <b>Channel ID</b> (e.g. <code>-100123456789</code>) or forward a message from the channel.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("≼ BACK", callback_data="cust_fsub_menu")]]),
        )
    elif d.startswith("cust_fsub_ch_"):
        cid = int(d.replace("cust_fsub_ch_", ""))
        await q.answer()
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Set Normal FSub", callback_data=f"cust_fsub_mode_norm_{cid}"), InlineKeyboardButton("🔒 Set Join Request FSub", callback_data=f"cust_fsub_mode_req_{cid}")],
            [InlineKeyboardButton("🗑 Remove Channel", callback_data=f"cust_fsub_del_{cid}")],
            [InlineKeyboardButton("≼ BACK", callback_data="cust_fsub_menu")],
        ])
        await q.message.edit_text(f"⚙️ <b>Manage FSub Channel:</b> <code>{cid}</code>", parse_mode="HTML", reply_markup=kb)
    elif d.startswith("cust_fsub_mode_"):
        parts = d.split("_")
        mode = "join_request" if parts[3] == "req" else "normal"
        cid = int(parts[4])
        existing = next((c for c in get_fsub_channels_db() if int(c["channel_id"]) == cid), None)
        add_fsub_channel_db(cid, (existing or {}).get("title") or f"Channel {cid}", "", mode, uid)
        await q.answer(f"Updated mode to {mode}")
        txt, kb = _build_fsub_page()
        await q.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)
    elif d.startswith("cust_fsub_del_"):
        cid = int(d.replace("cust_fsub_del_", ""))
        remove_fsub_channel_db(cid)
        await q.answer("Channel removed.")
        txt, kb = _build_fsub_page()
        await q.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)
    elif d == "cust_autodel_menu":
        await q.answer()
        secs = get_config("file_delete_after_seconds", "120")
        on = get_config_bool("auto_delete_enabled", True)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"Auto-Delete: {'ON ✅' if on else 'OFF ❌'}", callback_data="cust_autodel_toggle")],
            [InlineKeyboardButton("⏱ Set 60s", callback_data="cust_autodel_set_60"), InlineKeyboardButton("⏱ Set 120s (2m)", callback_data="cust_autodel_set_120"), InlineKeyboardButton("⏱ Set 300s (5m)", callback_data="cust_autodel_set_300")],
            [InlineKeyboardButton("≼ BACK", callback_data="cust_open_main")],
        ])
        await q.message.edit_text(f"⏳ <b>Temporary File Auto-Delete Settings</b>\n\n• <b>Current Timer:</b> <code>{secs} seconds</code>", parse_mode="HTML", reply_markup=kb)
    elif d == "cust_autodel_toggle":
        cur = get_config_bool("auto_delete_enabled", True)
        set_config("auto_delete_enabled", "false" if cur else "true", "bool", uid)
        await q.answer("Updated Auto-Delete state")
        q.data = "cust_autodel_menu"
        await editscript_callback(update, context)
    elif d.startswith("cust_autodel_set_"):
        s = d.replace("cust_autodel_set_", "")
        set_config("file_delete_after_seconds", s, "int", uid)
        await q.answer(f"Timer set to {s}s")
        q.data = "cust_autodel_menu"
        await editscript_callback(update, context)
    else:
        await _handle_cust_template_and_db_callbacks(q, d, uid, context)


async def customize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not _is_admin(update.effective_user.id):
        if msg:
            await msg.reply_text("⛔ Access denied. Only Admins and Owners can customize bot settings.")
        return
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🤖 CUSTOMIZE YOUR BOT SETTINGS 🤖", callback_data="cust_open_main")]])
    await msg.reply_text("<b>ʏᴏᴜ ᴄᴀɴ ᴄᴜsᴛᴏᴍɪsᴇ ʏᴏᴜʀ ʙᴏᴛ sᴇᴛᴛɪɴɢs ғʀᴏᴍ ʙᴇʟᴏᴡ ʙᴜᴛᴛᴏɴ</b>", parse_mode="HTML", reply_markup=kb)


editscript_command = customize_command


async def handle_customize_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Processes conversational text/photo replies when admin is editing a template, variable, or FSub channel."""
    state = context.user_data.get("cust_prompt")
    if not state or not update.message or not _is_admin(update.effective_user.id):
        return False
    msg = update.message
    uid = update.effective_user.id
    action = state.get("action")

    if action == "set_text" and msg.text:
        tname = state["target"]
        update_template_text(tname, msg.text, uid)
        context.user_data.pop("cust_prompt", None)
        await msg.reply_text(f"✅ Updated text for template <code>{tname}</code>!", parse_mode="HTML")
        return True

    if action == "set_media":
        tname = state["target"]
        if msg.photo:
            update_template_media(tname, "photo", msg.photo[-1].file_id, uid)
        elif msg.video:
            update_template_media(tname, "video", msg.video.file_id, uid)
        elif msg.text and msg.text.strip().lower() == "none":
            remove_template_media(tname, uid)
        elif msg.text:
            update_template_media(tname, "photo", msg.text.strip(), uid)
        else:
            return False
        context.user_data.pop("cust_prompt", None)
        await msg.reply_text(f"✅ Updated picture/media for <code>{tname}</code>!", parse_mode="HTML")
        return True

    if action == "add_btn" and msg.text and "|" in msg.text:
        tname = state["target"]
        lbl, tgt = [x.strip() for x in msg.text.split("|", 1)]
        add_template_button(tname, lbl, tgt, uid)
        context.user_data.pop("cust_prompt", None)
        await msg.reply_text(f"✅ Added button <b>{html.escape(lbl)}</b> to <code>{tname}</code>!", parse_mode="HTML")
        return True

    if action == "set_var" and msg.text:
        k = state["target"]
        set_config(k, msg.text.strip(), updated_by=uid)
        context.user_data.pop("cust_prompt", None)
        await msg.reply_text(f"✅ Config <code>{k}</code> updated to <code>{html.escape(msg.text.strip())}</code> (Hot-reloaded!)", parse_mode="HTML")
        return True

    if action == "add_fsub":
        cid, title = None, "FSub Channel"
        fwd_chat, _ = get_forward_chat(msg)
        if fwd_chat:
            cid, title = fwd_chat.id, fwd_chat.title or "Channel"
        elif msg.text and msg.text.strip().lstrip("-").isdigit():
            cid = int(msg.text.strip())
            try:
                ch_obj = await context.bot.get_chat(cid)
                title = ch_obj.title or f"Channel {cid}"
            except Exception:
                title = f"Channel {cid}"
        if cid:
            add_fsub_channel_db(cid, title, "", "normal", uid)
            context.user_data.pop("cust_prompt", None)
            await msg.reply_text(f"✅ Added Force Subscribe channel: <b>{html.escape(title)}</b> (<code>{cid}</code>)", parse_mode="HTML")
            return True
    return False


async def _handle_cust_template_and_db_callbacks(q, d: str, uid: int, context: ContextTypes.DEFAULT_TYPE):
    if d.startswith("cust_edit_txt_"):
        tname = d.replace("cust_edit_txt_", "")
        tpl = get_template(tname)
        context.user_data["cust_prompt"] = {"action": "set_text", "target": tname}
        await q.answer()
        await q.message.edit_text(
            f"✏️ <b>Editing Text for:</b> <code>{tname}</code>\n\n"
            f"<b>Current Text:</b>\n<pre>{html.escape(tpl.get('text') or '(Default)')}</pre>\n\n"
            f"Reply with the new text message (supports placeholders like <code>{{bot_title}}</code>, <code>{{date}}</code>, <code>**bold**</code>, <code>*italic*</code>, <code>||spoiler||</code>):",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("≼ BACK", callback_data="cust_open_main")]]),
        )
    elif d.startswith("cust_edit_med_"):
        tname = d.replace("cust_edit_med_", "")
        context.user_data["cust_prompt"] = {"action": "set_media", "target": tname}
        await q.answer()
        await q.message.edit_text(
            f"🖼 <b>Editing Picture/Media for:</b> <code>{tname}</code>\n\nSend a photo/video or reply <code>none</code> to remove media:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("≼ BACK", callback_data="cust_open_main")]]),
        )
    elif d.startswith("cust_edit_btn_"):
        tname = d.replace("cust_edit_btn_", "")
        context.user_data["cust_prompt"] = {"action": "add_btn", "target": tname}
        await q.answer()
        await q.message.edit_text(
            f"🔘 <b>Add Inline Button to:</b> <code>{tname}</code>\n\nReply in format:\n<code>Button Label | https://t.me/link_or_callback</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("≼ BACK", callback_data="cust_open_main")]]),
        )
    elif d == "cust_vars_menu":
        await q.answer()
        cfgs = get_all_configs()
        kb = [[InlineKeyboardButton(f"{c['key']} = {str(c['value'])[:18]}", callback_data=f"cust_var_{c['key']}")] for c in cfgs[:20]]
        kb.append([InlineKeyboardButton("≼ BACK", callback_data="cust_open_main")])
        await q.message.edit_text("⚙️ <b>Select a Variable to Edit Live:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
    elif d.startswith("cust_var_"):
        k = d.replace("cust_var_", "")
        val = get_config(k, "")
        context.user_data["cust_prompt"] = {"action": "set_var", "target": k}
        await q.answer()
        await q.message.edit_text(
            f"⚙️ <b>Variable:</b> <code>{k}</code>\n<b>Current Value:</b> <code>{html.escape(str(val))}</code>\n\nReply with the new value:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("≼ BACK", callback_data="cust_vars_menu")]]),
        )
    elif d == "cust_sys_restart":
        reload_config_cache()
        await q.answer("Restart & Redeploy Menu")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Hot-Reload Configs", callback_data="cust_do_hotreload")],
            [InlineKeyboardButton("🚀 Redeploy on Render (Webhook)", callback_data="cust_do_redeploy")],
            [InlineKeyboardButton("♻️ Hard Restart Bot Process", callback_data="cust_do_hardrestart")],
            [InlineKeyboardButton("🔗 Edit Deploy Hook URL", callback_data="cust_var_render_deploy_hook_url")],
            [InlineKeyboardButton("≼ BACK", callback_data="cust_open_main")],
        ])
        await q.message.edit_text("⚙️ <b>Restart & Render Redeploy Hub</b>\n\nSelect how you want to reload or redeploy the bot:", parse_mode="HTML", reply_markup=kb)
    elif d == "cust_do_hotreload":
        reload_config_cache()
        await q.answer("✅ Configurations & templates hot-reloaded!", show_alert=True)
    elif d.startswith("cust_refresh_dep_"):
        dep_id = d.replace("cust_refresh_dep_", "")
        await q.answer("🔄 Refreshing deploy status & logs...")
        details = await get_render_deploy_details(dep_id)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh Deploy Logs & Status", callback_data=f"cust_refresh_dep_{dep_id}")],
            [InlineKeyboardButton("≼ BACK", callback_data="cust_sys_restart")],
        ])
        await q.message.edit_text(f"📡 <b>Render Deployment Status & Live Logs</b>\n\n{details}", parse_mode="HTML", reply_markup=kb)
    elif d == "cust_do_redeploy":
        await q.answer("🚀 Saving backup & calling Render Deploy Hook...")
        await asyncio.to_thread(persistence.backup_now, "before redeploy")
        ok, msg, dep_id = await trigger_render_redeploy()
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh Deploy Logs & Status", callback_data=f"cust_refresh_dep_{dep_id}")],
            [InlineKeyboardButton("≼ BACK", callback_data="cust_sys_restart")],
        ])
        await q.message.edit_text(msg, parse_mode="HTML", reply_markup=kb)
    elif d == "cust_do_hardrestart":
        await q.answer("♻️ Restarting bot process...", show_alert=True)
        await q.message.edit_text("♻️ <b>Saving backup & restarting bot process now...</b>", parse_mode="HTML")
        await asyncio.to_thread(persistence.backup_now, "before restart")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    elif d.startswith("cust_ask_rst_"):
        kind = d.replace("cust_ask_rst_", "")
        await q.answer()
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ YES, RESET NOW", callback_data=f"cust_do_rst_{kind}"),
            InlineKeyboardButton("❌ CANCEL", callback_data="cust_open_main"),
        ]])
        await q.message.edit_text(f"⚠️ <b>Are you sure you want to reset the <code>{kind.upper()}</code> database?</b>", parse_mode="HTML", reply_markup=kb)
    elif d.startswith("cust_do_rst_"):
        kind = d.replace("cust_do_rst_", "")
        if kind == "user":
            reset_user_db()
        elif kind == "file":
            reset_file_db()
        elif kind == "chan":
            reset_channels_and_groups_db()
        await q.answer(f"✅ {kind.upper()} database has been reset!", show_alert=True)
        txt, kb = _build_main_dashboard()
        await q.message.edit_text(txt, parse_mode="HTML", reply_markup=kb)


async def reloadconfig_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Access denied.")
        return
    reload_config_cache()
    await update.effective_message.reply_text("🔄 <b>Configuration reloaded live from database!</b>", parse_mode="HTML")


async def setconfig_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Access denied.")
        return
    if len(context.args) < 2:
        await update.effective_message.reply_text("⚠️ <b>Usage:</b> <code>/setconfig &lt;key&gt; &lt;value&gt;</code>", parse_mode="HTML")
        return
    k, v = context.args[0].lower(), " ".join(context.args[1:])
    set_config(k, v, updated_by=update.effective_user.id)
    if k in ("logger_group_id", "general_log_group_id", "admin_log_group_id"):
        for alias in ("logger_group_id", "general_log_group_id", "admin_log_group_id"):
            set_config(alias, v, updated_by=update.effective_user.id)
    reload_config_cache()
    await update.effective_message.reply_text(f"✅ Set <code>{html.escape(k)}</code> = <code>{html.escape(v)}</code>", parse_mode="HTML")


async def getconfig_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Access denied.")
        return
    if not context.args:
        cfgs = get_all_configs()
        lines = ["⚙️ <b>Current Configuration:</b>"] + [f"• <code>{c['key']}</code> = <code>{html.escape(str(c['value']))}</code>" for c in cfgs]
        await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")
        return
    k = context.args[0]
    await update.effective_message.reply_text(f"🔍 <code>{html.escape(k)}</code> = <code>{html.escape(str(get_config(k, '(Not set)')))}</code>", parse_mode="HTML")


async def template_cli_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /edittext, /setmedia, /removemedia, /addbutton, /removebutton, /listtemplates, /showtemplate."""
    if not _is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Access denied.")
        return
    msg = update.effective_message
    cmd = msg.text.split()[0].lstrip("/").split("@")[0].lower()
    args = context.args
    uid = update.effective_user.id

    if cmd == "listtemplates":
        tpls = list_templates()
        txt = "📋 <b>Templates:</b>\n" + "\n".join(f"• <code>{t['name']}</code> ({t['module']})" for t in tpls)
        await msg.reply_text(txt, parse_mode="HTML")
    elif cmd == "showtemplate" and args:
        t = get_template(args[0])
        await msg.reply_text(f"📄 <b>Template:</b> <code>{t['name']}</code>\n<b>Media:</b> <code>{t['media_type']}</code>\n<b>Buttons:</b> <code>{len(t['buttons'])}</code>\n\n{t['text']}", parse_mode="HTML")
    elif cmd == "edittext" and len(args) >= 2:
        update_template_text(args[0], " ".join(args[1:]), uid)
        await msg.reply_text(f"✅ Updated text for <code>{args[0]}</code>.", parse_mode="HTML")
    elif cmd == "setmedia" and len(args) >= 2:
        update_template_media(args[0], "photo", args[1], uid)
        await msg.reply_text(f"✅ Updated media for <code>{args[0]}</code>.", parse_mode="HTML")
    elif cmd == "removemedia" and args:
        remove_template_media(args[0], uid)
        await msg.reply_text(f"✅ Removed media from <code>{args[0]}</code>.", parse_mode="HTML")
    elif cmd == "addbutton" and len(args) >= 3:
        add_template_button(args[0], args[1], args[2], uid)
        await msg.reply_text(f"✅ Added button to <code>{args[0]}</code>.", parse_mode="HTML")
    elif cmd == "removebutton" and len(args) >= 2 and args[1].isdigit():
        remove_template_button(args[0], int(args[1]), uid)
        await msg.reply_text(f"✅ Removed button #{args[1]} from <code>{args[0]}</code>.", parse_mode="HTML")
    else:
        await customize_command(update, context)


async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command /restart showing Hot-Reload, Render Redeploy, and Process Restart options."""
    if not _is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Access denied. Only Admins and Owners can restart or redeploy.")
        return
    reload_config_cache()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Hot-Reload Configs & Templates", callback_data="cust_do_hotreload")],
        [InlineKeyboardButton("🚀 Redeploy on Render (Deploy Hook)", callback_data="cust_do_redeploy")],
        [InlineKeyboardButton("♻️ Hard Restart Bot Process", callback_data="cust_do_hardrestart")],
        [InlineKeyboardButton("🔗 Edit Render Deploy Hook URL", callback_data="cust_var_render_deploy_hook_url")],
    ])
    await update.effective_message.reply_text(
        "⚙️ <b>Restart & Render Deployment Control</b>\n\n"
        "✅ In-memory configuration cache has been refreshed.\n"
        "Choose an action below:",
        parse_mode="HTML",
        reply_markup=kb,
    )


# Helper to fetch latest commit being deployed + Render API deploy status/logs + local memory logs
async def get_render_deploy_details(deploy_id: str = "") -> str:
    import aiohttp
    import json
    from modules.log.logger import get_logs_by_count

    srv_id = get_config("render_service_id", "srv-dbgi9nflk1mc73c0abmg")
    api_key = get_config("render_api_key", fallback_env="RENDER_API_KEY")
    lines = []

    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # 1. Fetch latest commit on LokiTheGodofLies/mastermind being deployed
        try:
            gh_url = "https://api.github.com/repos/LokiTheGodofLies/mastermind/commits/main"
            async with session.get(gh_url, headers={"User-Agent": "MastermindBot"}) as gresp:
                if gresp.status == 200:
                    gdata = await gresp.json()
                    sha = (gdata.get("sha") or "")[:7]
                    cmsg = (gdata.get("commit", {}).get("message") or "").splitlines()[0]
                    cauthor = gdata.get("commit", {}).get("author", {}).get("name") or "GitHub"
                    lines.append(f"📦 <b>Target Commit:</b> <code>{sha}</code> — <i>{html.escape(cmsg[:60])}</i> (by {html.escape(cauthor)})")
        except Exception:
            pass

        # 2. If RENDER_API_KEY is configured, query Render REST API v1 for exact deploy status & build logs
        if api_key and srv_id:
            headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
            try:
                dep_url = f"https://api.render.com/v1/services/{srv_id}/deploys"
                if deploy_id:
                    dep_url = f"{dep_url}/{deploy_id}"
                else:
                    dep_url = f"{dep_url}?limit=1"
                async with session.get(dep_url, headers=headers) as rresp:
                    if rresp.status == 200:
                        rdata = await rresp.json()
                        dep_obj = rdata[0].get("deploy", rdata[0]) if isinstance(rdata, list) and rdata else rdata.get("deploy", rdata)
                        st = dep_obj.get("status", "unknown")
                        did = dep_obj.get("id", deploy_id or "N/A")
                        started = dep_obj.get("createdAt", "")[:19].replace("T", " ")
                        finished = (dep_obj.get("finishedAt") or "In Progress")[:19].replace("T", " ")
                        lines.append(
                            f"🆔 <b>Deploy ID:</b> <code>{html.escape(str(did))}</code>\n"
                            f"📡 <b>Render Status:</b> <code>{html.escape(str(st).upper())}</code>\n"
                            f"⏱ <b>Started:</b> <code>{started}</code> | <b>Finished:</b> <code>{finished}</code>"
                        )
                    else:
                        err_txt = await rresp.text()
                        lines.append(f"⚠️ <b>Render API Status ({rresp.status}):</b> <code>{html.escape(err_txt[:150])}</code>")
            except Exception as e:
                lines.append(f"⚠️ <b>Render API Check Error:</b> <code>{html.escape(str(e))}</code>")
        else:
            lines.append("💡 <i>Tip: Set <code>/setconfig render_api_key rnd_...</code> to stream live Render build status.</i>")

    # 3. Append latest runtime/deploy logs & any errors captured in memory
    recent_logs = get_logs_by_count(12)
    lines.append(f"\n📋 <b>Latest Bot & Deploy Logs:</b>\n<pre>{html.escape(recent_logs[-900:])}</pre>")
    return "\n".join(lines)


async def trigger_render_redeploy() -> tuple:
    """Triggers Render Deploy Hook and returns (success, formatted_message, deploy_id)."""
    import aiohttp
    import json
    hook_url = get_config("render_deploy_hook_url", fallback_env="RENDER_DEPLOY_HOOK_URL")
    if not hook_url or not hook_url.startswith("http"):
        return False, "⚠️ No valid <code>render_deploy_hook_url</code> configured.", ""
    try:
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(hook_url) as resp:
                body = await resp.text()
                deploy_id = ""
                try:
                    j = json.loads(body)
                    deploy_id = (j.get("deploy") or {}).get("id") or j.get("id") or ""
                except Exception:
                    pass
                details = await get_render_deploy_details(deploy_id)
                if resp.status in (200, 201, 202):
                    msg = (
                        f"🚀 <b>Render Redeploy Triggered Successfully! (HTTP {resp.status})</b>\n"
                        f"Render is now pulling the latest commit and redeploying your service.\n\n"
                        f"{details}"
                    )
                    return True, msg, deploy_id
                msg = (
                    f"❌ <b>Render Deploy Hook Error (HTTP {resp.status})</b>\n"
                    f"<b>Response:</b> <pre>{html.escape(body[:300])}</pre>\n\n"
                    f"{details}"
                )
                return False, msg, deploy_id
    except Exception as e:
        details = await get_render_deploy_details("")
        return False, f"❌ <b>Failed calling Render Deploy Hook:</b> <code>{html.escape(str(e))}</code>\n\n{details}", ""


async def redeploy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command /redeploy showing deploy status, commit info, and live logs."""
    if not _is_admin(update.effective_user.id):
        await update.effective_message.reply_text("⛔ Access denied.")
        return
    status_msg = await update.effective_message.reply_text("⏳ Triggering Render Deploy Hook & fetching deploy logs...")
    ok, msg, dep_id = await trigger_render_redeploy()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh Deploy Logs & Status", callback_data=f"cust_refresh_dep_{dep_id}")],
        [InlineKeyboardButton("≼ Open Customize Menu", callback_data="cust_open_main")],
    ])
    await status_msg.edit_text(msg, parse_mode="HTML", reply_markup=kb)
