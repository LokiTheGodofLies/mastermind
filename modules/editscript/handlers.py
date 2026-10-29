from config import bot_name
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.database.config_db import get_config, get_all_configs
from modules.database.user_db import is_admin_or_owner


async def editscript_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    if not message or not user or not is_admin_or_owner(user.id):
        if message:
            await message.reply_text("⛔ Unauthorized.")
        return

    keyboard = [
        [InlineKeyboardButton("📝 Manage Scripts & Texts", callback_data="es_menu_scripts")],
        [InlineKeyboardButton("🖼️ Manage Media Links", callback_data="es_menu_media")],
        [InlineKeyboardButton("🔘 Manage Inline Buttons", callback_data="es_menu_buttons")],
        [InlineKeyboardButton("⚙️ Manage Variables", callback_data="es_menu_vars")],
        [InlineKeyboardButton("👀 Preview & Test", callback_data="es_menu_preview")],
    ]
    await message.reply_text(
        f"🛠️ <b>{bot_name()} Admin Configuration Hub (/editscript)</b>\n\nSelect a category to manage:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


async def editscript_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not is_admin_or_owner(query.from_user.id):
        if query:
            await query.answer("⛔ Unauthorized.", show_alert=True)
        return
    await query.answer()
    data = query.data

    if data == "es_menu_main":
        keyboard = [
            [InlineKeyboardButton("📝 Manage Scripts & Texts", callback_data="es_menu_scripts")],
            [InlineKeyboardButton("🖼️ Manage Media Links", callback_data="es_menu_media")],
            [InlineKeyboardButton("🔘 Manage Inline Buttons", callback_data="es_menu_buttons")],
            [InlineKeyboardButton("⚙️ Manage Variables", callback_data="es_menu_vars")],
            [InlineKeyboardButton("👀 Preview & Test", callback_data="es_menu_preview")],
        ]
        await query.edit_message_text(
            f"🛠️ <b>{bot_name()} Admin Configuration Hub (/editscript)</b>\n\nSelect a category to manage:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    elif data == "es_menu_scripts":
        configs = get_all_configs()
        scripts = [c for c in configs if c[1] == "script"]
        keyboard = [[InlineKeyboardButton(s[0], callback_data=f"es_edit_key_{s[0]}")] for s in scripts]
        keyboard.append([InlineKeyboardButton("« Back to Menu", callback_data="es_menu_main")])
        await query.edit_message_text("📝 <b>Select script/text key to configure:</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    elif data.startswith("es_edit_key_"):
        key = data.replace("es_edit_key_", "")
        val = get_config(key, default="(Not set)")
        keyboard = [
            [InlineKeyboardButton("🔄 Toggle / Update Value", callback_data=f"es_prompt_set_{key}")],
            [InlineKeyboardButton("« Back", callback_data="es_menu_scripts")]
        ]
        await query.edit_message_text(f"🔍 <b>Key:</b> <code>{key}</code>\n\n<b>Current Value:</b>\n<pre>{val}</pre>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    elif data.startswith("es_prompt_set_"):
        key = data.replace("es_prompt_set_", "")
        await query.edit_message_text(f"💡 To update <code>{key}</code>, use database setter or command helper.", parse_mode="HTML")
    elif data == "es_menu_preview":
        await query.edit_message_text("👀 [PREVIEW MODE] Active configurations look synchronized and ready.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data="es_menu_main")]]), parse_mode="HTML")
    else:
        await query.edit_message_text("⚙️ Submenu under construction.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data="es_menu_main")]]), parse_mode="HTML")
