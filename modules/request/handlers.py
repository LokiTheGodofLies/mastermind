from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import os

REQUEST_QUIZ_QUESTIONS = [
    ("1. Is casual chatting allowed in the request chat?", False),
    ("2. Should you check if a file already exists before requesting?", True),
    ("3. Can you post spam or external links here?", False),
]

async def request_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📥 **Mastermind Request Center**\n\n"
        "To keep requests orderly and spam-free, "
        "you must pass a quick verification quiz first."
    )
    keyboard = [[InlineKeyboardButton("🚀 Start Request Verification", callback_data="request_start_quiz")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=reply_markup)

async def request_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "request_start_quiz":
        context.user_data["request_quiz_step"] = 0
        await send_request_question(query, context, step=0)

    elif data.startswith("request_ans_"):
        user_step = context.user_data.get("request_quiz_step", 0)
        user_choice = True if data == "request_ans_yes" else False
        expected_ans = REQUEST_QUIZ_QUESTIONS[user_step][1]

        if user_choice == expected_ans:
            user_step += 1
            context.user_data["request_quiz_step"] = user_step

            if user_step < len(REQUEST_QUIZ_QUESTIONS):
                await send_request_question(query, context, step=user_step)
            else:
                await finalize_request_quiz_success(query, context)
        else:
            context.user_data["request_quiz_step"] = 0
            fail_text = (
                "❌ **Incorrect Answer!**\n\n"
                "Quiz reset from the beginning. Let's try again."
            )
            keyboard = [[InlineKeyboardButton("🔄 Restart Quiz", callback_data="request_start_quiz")]]
            await query.message.edit_text(fail_text, parse_mode="Markdown", reply_markup=reply_markup)

async def send_request_question(query, context, step: int):
    question_text, _ = REQUEST_QUIZ_QUESTIONS[step]
    text = f"📝 **Request Verification ({step + 1}/{len(REQUEST_QUIZ_QUESTIONS)})**\n\n{question_text}"
    keyboard = [
        [
            InlineKeyboardButton("✅ Yes", callback_data="request_ans_yes"),
            InlineKeyboardButton("❌ No", callback_data="request_ans_no")
        ]
    ]
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=reply_markup)

async def finalize_request_quiz_success(query, context):
    request_chat_id = os.getenv("REQUEST_CHAT_ID")
    if not request_chat_id:
        await query.message.edit_text(
            "✅ **Quiz Passed Successfully!**\n\n⚠️ Request chat ID is not configured on this bot instance.",
            parse_mode="Markdown"
        )
        return

    try:
        invite_link = await context.bot.create_chat_invite_link(
            chat_id=int(request_chat_id),
            member_limit=1,
            creates_join_request=False
        )
        success_text = (
            "🎉 **Congratulations! You passed the verification.**\n\n"
            "Here is your secure, single-use invite link to join the request group:"
        )
        keyboard = [[InlineKeyboardButton("🔗 Join Request Group", url=invite_link.invite_link)]]
        await query.message.edit_text(success_text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as e:
        await query.message.edit_text(f"✅ **Quiz Passed!**\n\nCould not generate link: {e}", parse_mode="Markdown")
