from telegram import Update
from telegram.ext import ContextTypes
from modules.database.user_db import get_user_role_db, set_user_ban_db, remove_user_ban_db

async def resolve_target_identifier(update: Update, context: ContextTypes.DEFAULT_TYPE, target_arg: str):
    """Resolves target ID whether it's a numeric ID or a @username / handle."""
    target_arg = target_arg.strip()
    
    if target_arg.lstrip('-').isdigit():
        return int(target_arg), target_arg
        
    if target_arg.startswith('@'):
        username = target_arg[1:]
        import sqlite3
        conn = sqlite3.connect("mastermind_users.db")
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
    """Internal helper to process the three ban types with role validation."""
    admin_id = update.effective_user.id
    admin_role = get_user_role_db(admin_id)
    
    if admin_role not in ['Admin', 'Owner']:
        await update.message.reply_text("⛔ You do not have permission to use this command.")
        return
        
    args = context.args
    target_id = None
    target_display = ""
    reason = ""
    
    reply_message = update.message.reply_to_message
    if reply_message and reply_message.from_user:
        # Replying mode: args contain only the reason
        target_id = reply_message.from_user.id
        target_display = f"@{reply_message.from_user.username}" if reply_message.from_user.username else reply_message.from_user.first_name
        reason = " ".join(args) if args else ""
    else:
        # Argument mode: args[0] is target, rest is reason
        if not args:
            await update.message.reply_text(
                f"⚠️ **Usage:**\n"
                f"• `/ban <id|@username> [reason]` (or `/ban_pm`, `/ban_support`)\n"
                f"• *Or reply to a user's message with the command and reason.*",
                parse_mode="Markdown"
            )
            return
            
        resolved_id, display_str = await resolve_target_identifier(update, context, args[0])
        if not resolved_id:
            await update.message.reply_text(f"⚠️ Could not resolve target identifier: `{args[0]}`.", parse_mode="Markdown")
            return
            
        target_id = resolved_id
        target_display = display_str
        reason = " ".join(args[1:]) if len(args) > 1 else ""

    # Check reason requirement for Admin vs Owner
    if admin_role != 'Owner' and not reason:
        await update.message.reply_text(
            "⚠️ **Reason Required:** As an Admin, you cannot ban a user without providing a reason.",
            parse_mode="Markdown"
        )
        return
        
    if not reason:
        reason = "No reason provided (Owner action)"
        
    # Save ban configuration in database
    set_user_ban_db(target_id, ban_type, reason)
    
    type_descriptions = {
        'all': 'Banned from everywhere',
        'pm': 'Banned from bot private message',
        'support': 'Banned everywhere except support chat'
    }
    
    await update.message.reply_text(
        f"✅ Successfully updated restriction for <b>{target_display}</b> (<code>{target_id}</code>).\n"
        f"🔒 <b>Type:</b> {type_descriptions.get(ban_type, ban_type.upper())}\n"
        f"📝 <b>Reason:</b> {reason}",
        parse_mode="HTML"
    )

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ban type 1: /ban id reason (Ban from everywhere)"""
    await _process_ban(update, context, 'all')

async def ban_pm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ban type 2: /ban_pm id reason (Ban only from bot private message)"""
    await _process_ban(update, context, 'pm')

async def ban_support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ban type 3: /ban_support id reason (Ban everywhere except support chat)"""
    await _process_ban(update, context, 'support')

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin/Owner command to unban a user: /unban <target_id or @username>"""
    admin_id = update.effective_user.id
    admin_role = get_user_role_db(admin_id)
    
    if admin_role not in ['Admin', 'Owner']:
        await update.message.reply_text("⛔ You do not have permission to use this command.")
        return
        
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ **Usage:** `/unban <target_id|@username>`", parse_mode="Markdown")
        return
        
    resolved_id, display_str = await resolve_target_identifier(update, context, args[0])
    if not resolved_id:
        await update.message.reply_text("⚠️ Could not resolve target ID.")
        return
        
    remove_user_ban_db(resolved_id)
    await update.message.reply_text(f"✅ Target <b>{display_str}</b> (<code>{resolved_id}</code>) has been fully unbanned.", parse_mode="HTML")
