import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ApplicationHandlerStop
from config import users_db_path
from modules.database.user_db import get_user_role_db, set_user_role_db
from modules.ban.ban import set_ban_db, remove_ban_db, check_user_access


async def resolve_target_identifier(update: Update, context: ContextTypes.DEFAULT_TYPE, target_arg: str):
    """Resolves target ID whether it's a numeric ID, chat ID, or @username."""
    target_arg = target_arg.strip()

    if target_arg.lstrip("-").isdigit():
        return int(target_arg), target_arg

    if target_arg.startswith("@"):
        username = target_arg[1:]
        conn = sqlite3.connect(users_db_path())
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return row[0], target_arg

        try:
            chat = await context.bot.get_chat(target_arg)
            return chat.id, chat.title or chat.username
        except Exception:
            pass

    return None, target_arg


async def _process_ban(update: Update, context: ContextTypes.DEFAULT_TYPE, ban_type: str):
    """Internal helper to process ban types with role validation."""
    admin_id = update.effective_user.id
    admin_role = get_user_role_db(admin_id)

    if admin_role not in ["Admin", "GOD", "Owner"]:
        await update.message.reply_text("⛔ You do not have permission to use this command.")
        return

    args = context.args
    target_id = None
    target_display = ""
    reason = ""

    reply_message = update.message.reply_to_message
    if reply_message and reply_message.from_user:
        target_id = reply_message.from_user.id
        target_display = f"@{reply_message.from_user.username}" if reply_message.from_user.username else reply_message.from_user.first_name
        reason = " ".join(args) if args else ""
    else:
        if not args:
            await update.message.reply_text(
                "⚠️ **Usage:** `/ban <id|@username> [reason]` (or `/ban_pm`, `/ban_support`)",
                parse_mode="Markdown"
            )
            return

        resolved_id, display_str = await resolve_target_identifier(update, context, args[0])
        if not resolved_id:
            await update.message.reply_text(f"⚠️ Could not resolve target: `{args[0]}`", parse_mode="Markdown")
            return

        target_id = resolved_id
        target_display = display_str
        reason = " ".join(args[1:]) if len(args) > 1 else ""

    if admin_role not in ("GOD", "Owner") and not reason:
        await update.message.reply_text("⚠️ **Reason Required:** Admins must provide a reason.", parse_mode="Markdown")
        return

    if not reason:
        reason = "No reason provided (GOD action)"

    set_ban_db(target_id, ban_type, reason)

    if str(target_id).startswith("-"):
        support_url = f"https://t.me/{context.bot.username}"

        keyboard = [[InlineKeyboardButton("💬 Contact Support", url=support_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        warning_msg = (
            "❌ <b>This chat is banned from using the bot.</b>\n"
            f"📝 <b>Reason:</b> {reason}\n\n"
            "Please contact support to know the reason and appeal for unban."
        )

        try:
            await context.bot.send_message(chat_id=target_id, text=warning_msg, parse_mode="HTML", reply_markup=reply_markup)
            await context.bot.leave_chat(target_id)
        except Exception as e:
            print(f"Could not leave chat {target_id}: {e}")

    type_descriptions = {
        "all": "Banned from everywhere",
        "pm": "Banned from bot private message",
        "support": "Banned everywhere except support chat",
    }

    await update.message.reply_text(
        f"✅ Ban applied to <b>{target_display}</b> (<code>{target_id}</code>).\n"
        f"🔒 <b>Type:</b> {type_descriptions.get(ban_type, ban_type.upper())}\n"
        f"📝 <b>Reason:</b> {reason}",
        parse_mode="HTML"
    )


async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _process_ban(update, context, "all")


async def ban_pm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _process_ban(update, context, "pm")


async def ban_support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _process_ban(update, context, "support")


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    admin_role = get_user_role_db(admin_id)

    if admin_role not in ["Admin", "GOD", "Owner"]:
        await update.message.reply_text("⛔ You do not have permission to use this command.")
        return

    reply_message = update.message.reply_to_message
    if reply_message and reply_message.from_user and not context.args:
        resolved_id = reply_message.from_user.id
        display_str = f"@{reply_message.from_user.username}" if reply_message.from_user.username else reply_message.from_user.first_name
    else:
        args = context.args
        if not args:
            await update.message.reply_text("⚠️ **Usage:** `/unban <target_id|@username>`", parse_mode="Markdown")
            return

        resolved_id, display_str = await resolve_target_identifier(update, context, args[0])
        if not resolved_id:
            await update.message.reply_text("⚠️ Could not resolve target ID.")
            return

    remove_ban_db(resolved_id)
    await update.message.reply_text(f"✅ Target <b>{display_str}</b> (<code>{resolved_id}</code>) has been unbanned.", parse_mode="HTML")


async def addadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """GOD-only command to grant Admin role (/addadmin <user_id|@username> or reply)."""
    caller = update.effective_user
    msg = update.effective_message
    if not caller or not msg:
        return
    if get_user_role_db(caller.id) not in ("GOD", "Owner"):
        await msg.reply_text("⛔ Only GOD can add administrators.")
        return

    reply_msg = msg.reply_to_message
    if reply_msg and reply_msg.from_user and not context.args:
        target_id = reply_msg.from_user.id
        display = f"@{reply_msg.from_user.username}" if reply_msg.from_user.username else reply_msg.from_user.first_name
    else:
        if not context.args:
            await msg.reply_text("⚠️ <b>Usage:</b> <code>/addadmin &lt;user_id|@username&gt;</code>", parse_mode="HTML")
            return
        target_id, display = await resolve_target_identifier(update, context, context.args[0])
        if not target_id:
            await msg.reply_text(f"⚠️ Could not resolve user: <code>{context.args[0]}</code>", parse_mode="HTML")
            return

    set_user_role_db(target_id, "Admin")
    await msg.reply_text(f"✅ Promoted <b>{display}</b> (<code>{target_id}</code>) to <b>Admin</b>.", parse_mode="HTML")


async def removeadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """GOD-only command to revoke Admin role (/removeadmin <user_id|@username> or reply)."""
    caller = update.effective_user
    msg = update.effective_message
    if not caller or not msg:
        return
    if get_user_role_db(caller.id) not in ("GOD", "Owner"):
        await msg.reply_text("⛔ Only GOD can remove administrators.")
        return

    reply_msg = msg.reply_to_message
    if reply_msg and reply_msg.from_user and not context.args:
        target_id = reply_msg.from_user.id
        display = f"@{reply_msg.from_user.username}" if reply_msg.from_user.username else reply_msg.from_user.first_name
    else:
        if not context.args:
            await msg.reply_text("⚠️ <b>Usage:</b> <code>/removeadmin &lt;user_id|@username&gt;</code>", parse_mode="HTML")
            return
        target_id, display = await resolve_target_identifier(update, context, context.args[0])
        if not target_id:
            await msg.reply_text(f"⚠️ Could not resolve user: <code>{context.args[0]}</code>", parse_mode="HTML")
            return

    set_user_role_db(target_id, "Normal User")
    await msg.reply_text(f"✅ Demoted <b>{display}</b> (<code>{target_id}</code>) to <b>Normal User</b>.", parse_mode="HTML")




async def _process_role_change(update: Update, context: ContextTypes.DEFAULT_TYPE, new_role: str, action_label: str):
    """Internal helper to assign or revoke user roles (Moderator, Volunteer, Promoter)."""
    caller = update.effective_user
    msg = update.effective_message
    if not caller or not msg:
        return
    caller_role = get_user_role_db(caller.id)
    if caller_role not in ("GOD", "Owner", "Admin"):
        await msg.reply_text("⛔ Unauthorized. Only Administrators and GOD can manage roles.")
        return

    reply_msg = msg.reply_to_message
    if reply_msg and reply_msg.from_user and not context.args:
        target_id = reply_msg.from_user.id
        display = f"@{reply_msg.from_user.username}" if reply_msg.from_user.username else reply_msg.from_user.first_name
    else:
        if not context.args:
            cmd = (msg.text or "").split()[0]
            await msg.reply_text(f"⚠️ <b>Usage:</b> <code>{cmd} &lt;user_id|@username&gt;</code>", parse_mode="HTML")
            return
        target_id, display = await resolve_target_identifier(update, context, context.args[0])
        if not target_id:
            await msg.reply_text(f"⚠️ Could not resolve user: <code>{context.args[0]}</code>", parse_mode="HTML")
            return

    target_role = get_user_role_db(target_id)
    if target_role in ("GOD", "Owner"):
        await msg.reply_text("⛔ Cannot modify the role of GOD.")
        return
    if target_role == "Admin" and caller_role != "GOD":
        await msg.reply_text("⛔ Only GOD can modify an Administrator's role.")
        return

    set_user_role_db(target_id, new_role)
    if new_role == "Normal User":
        await msg.reply_text(f"✅ Demoted <b>{display}</b> (<code>{target_id}</code>) to <b>Normal User</b>.", parse_mode="HTML")
    else:
        await msg.reply_text(f"✅ Promoted <b>{display}</b> (<code>{target_id}</code>) to <b>{action_label}</b>.", parse_mode="HTML")


async def addmoderator_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin/GOD command to promote a user to Moderator."""
    await _process_role_change(update, context, "Moderator", "Moderator")


async def removemoderator_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin/GOD command to demote a Moderator to Normal User."""
    await _process_role_change(update, context, "Normal User", "Normal User")


async def addvolunteer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin/GOD command to promote a user to Volunteer."""
    await _process_role_change(update, context, "Volunteer", "Volunteer")


async def removevolunteer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin/GOD command to demote a Volunteer to Normal User."""
    await _process_role_change(update, context, "Normal User", "Normal User")


async def addpromoter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin/GOD command to promote a user to Promoter."""
    await _process_role_change(update, context, "Promoter", "Promoter")


async def removepromoter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin/GOD command to demote a Promoter to Normal User."""
    await _process_role_change(update, context, "Normal User", "Normal User")

async def enforce_ban_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Middleware to intercept messages and enforce user/chat bans."""
    if not update.effective_user or not update.effective_chat:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    if chat_type in ("group", "supergroup", "channel"):
        try:
            from modules.database.user_db import register_chat_db
            register_chat_db(chat_id, chat_type, update.effective_chat.title or "", getattr(update.effective_chat, "username", ""))
        except Exception:
            pass

    allowed, reason = check_user_access(user_id, chat_id, chat_type)
    if not allowed:
        if update.message:
            try:
                await update.message.reply_text(reason)
            except Exception:
                pass
        raise ApplicationHandlerStop()
