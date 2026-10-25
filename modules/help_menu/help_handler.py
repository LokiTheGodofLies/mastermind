from telegram import Update
from telegram.ext import ContextTypes

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "<b>🤖 Bot Help Menu</b>\n\n"
        "Here are my modules and functions I can perform:\n"
        "• <b>/start</b> - Greets you with a simple welcome message and quick buttons.\n"
        "• <b>/help</b> - Shows this list of all available modules and functions.\n"
        "• <b>Normal Text</b> - Reminds you that I can't chat and gives you a quick help button."
    )
    await update.message.reply_text(help_text, parse_mode='HTML')

async def help_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'help_button':
        help_text = (
            "<b>🤖 Bot Help Menu</b>\n\n"
            "Here are my modules and functions I can perform:\n"
            "• <b>/start</b> - Greets you with a simple welcome message and quick buttons.\n"
            "• <b>/help</b> - Shows this list of all available modules and functions.\n"
            "• <b>Normal Text</b> - Reminds you that I can't chat and gives you a quick help button."
        )
        await query.message.reply_text(help_text, parse_mode='HTML')
