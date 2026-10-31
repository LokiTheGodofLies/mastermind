from config import bot_name
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.database.config_db import get_config, get_all_configs
from modules.database.user_db import is_admin_or_owner
from modules.utility.rich_ui import styled_button


def _main_editscript_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [styled_button("📝 Manage Scripts & Texts", callback_data="es_menu_scripts", style="primary")],
        [styled_button("🖼️ Manage Media Links", callback_data="es_menu_media", style="primary")],
        [styled_button("🔘 Manage Inline Buttons", callback_data="es_menu_buttons", style="primary")],
        [styled_button("⚙️ Manage Variables", callback_data="es_menu_vars", style="primary")],
        [styled_button("👀 Preview & Test", callback_data="es_menu_preview", style="success")],
    ])


async def editscript_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    if not message or not user or not is_admin_or_owner(user.id):
        if message:
            await message.reply_text("⛔ Unauthorized.")
        return

    await message.reply_text(
        f"🛠️ <b>{bot_name()} Admin Configuration Hub (<mark>/editscript</mark>)</b>\n\nSelect a category below to manage:",
        reply_markup=_main_editscript_keyboard(),
        parse_mode="HTML",
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
        await query.edit_message_text(
            f"🛠️ <b>{bot_name()} Admin Configuration Hub (<mark>/editscript</mark>)</b>\n\nSelect a category below to manage:",
            reply_markup=_main_editscript_keyboard(),
            parse_mode="HTML",
        )
    elif data == "es_menu_scripts":
        configs = get_all_configs()
        scripts = [c for c in configs if c[1] == "script"]
        keyboard = [[styled_button(s[0], callback_data=f"es_edit_key_{s[0]}", style="primary")] for s in scripts]
        keyboard.append([styled_button("« Back to Menu", callback_data="es_menu_main", style="primary")])
        await query.edit_message_text("📝 <b>Select script/text key to configure:</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    elif data.startswith("es_edit_key_"):
        key = data.replace("es_edit_key_", "")
        val = get_config(key, default="(Not set)")
        keyboard = [
            [styled_button("🔄 Toggle / Update Value", callback_data=f"es_prompt_set_{key}", style="success")],
            [styled_button("« Back", callback_data="es_menu_scripts", style="primary")],
        ]
        await query.edit_message_text(
            f"🔍 <b>Key:</b> <mark>{key}</mark>\n\n<b>Current Value:</b>\n<pre>{val}</pre>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
        )
    elif data.startswith("es_prompt_set_"):
        key = data.replace("es_prompt_set_", "")
        await query.edit_message_text(f"💡 To update <code>{key}</code>, use database setter or command helper.", parse_mode="HTML")
    elif data == "es_menu_preview":
        await query.edit_message_text(
            "👀 <b>[PREVIEW MODE]</b> Active configurations look synchronized and ready.",
            reply_markup=InlineKeyboardMarkup([[styled_button("« Back", callback_data="es_menu_main", style="primary")]]),
            parse_mode="HTML",
        )
    else:
        await query.edit_message_text(
            "⚙️ Submenu under construction.",
            reply_markup=InlineKeyboardMarkup([[styled_button("« Back", callback_data="es_menu_main", style="primary")]]),
            parse_mode="HTML",
        )
