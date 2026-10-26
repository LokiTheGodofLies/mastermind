from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import os

SEARCH_QUIZ_QUESTIONS = [
    ("1. Is casual chatting allowed in the search chat?", False),
    ("2. Can you submit files in this search group?", False),
    ("3. Should you use search keywords properly?", True),
]

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🔍 **Mastermind Search Center**\n\n"
        "To keep our search group clean and focused on finding books and files, "
        "you must pass a quick verification quiz first."
    )
    keyboard = [[InlineKeyboardButton("🚀 Start Search Verification", callback_data="search_start_quiz")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=reply_markup)

async def search_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "search_start_quiz":
        context.user_data["search_quiz_step"] = 0
        await send_search_question(query, context, step=0)

    elif data.startswith("search_ans_"):
        user_step = context.user_data.get("search_quiz_step", 0)
        user_choice = True if data == "search_ans_yes" else False
        expected_ans = SEARCH_QUIZ_QUESTIONS[user_step][1]

        if user_choice == expected_ans:
            user_step += 1
            context.user_data["search_quiz_step"] = user_step

            if user_step < len(SEARCH_QUIZ_QUESTIONS):
                await send_search_question(query, context, step=user_step)
            else:
                await finalize_search_quiz_success(query, context)
        else:
            context.user_data["search_quiz_step"] = 0
            fail_text = (
                "❌ **Incorrect Answer!**\n\n"
                "Quiz reset from the beginning. Let's try again."
            )
            keyboard = [[InlineKeyboardButton("🔄 Restart Quiz", callback_data="search_start_quiz")]]
            await query.message.edit_text(fail_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def send_search_question(query, context, step: int):
    question_text, _ = SEARCH_QUIZ_QUESTIONS[step]
    text = f"📝 **Search Verification ({step + 1}/{len(SEARCH_QUIZ_QUESTIONS)})**\n\n{question_text}"
    keyboard = [
        [
            InlineKeyboardButton("✅ Yes", callback_data="search_ans_yes"),
            InlineKeyboardButton("❌ No", callback_data="search_ans_no")
        ]
    ]
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def finalize_search_quiz_success(query, context):
    search_chat_id = os.getenv("SEARCH_CHAT_ID")
    if not search_chat_id:
        await query.message.edit_text(
            "✅ **Quiz Passed Successfully!**\n\n⚠️ Search chat ID is not configured on this bot instance.",
            parse_mode="Markdown"
        )
        return

    try:
        invite_link = await context.bot.create_chat_invite_link(
            chat_id=int(search_chat_id),
            member_limit=1,
            creates_join_request=False
        )
        success_text = (
            "🎉 **Congratulations! You passed the verification.**\n\n"
            "Here is your secure, single-use invite link to join the search group:"
        )
        keyboard = [[InlineKeyboardButton("🔗 Join Search Group", url=invite_link.invite_link)]]
        await query.message.edit_text(success_text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as e:
        await query.message.edit_text(f"✅ **Quiz Passed!**\n\nCould not generate link: {e}", parse_mode="Markdown")
