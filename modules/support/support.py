from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from modules.ban.ban import get_support_chat_id

# The 10 questions and their correct answers (True = Yes, False = No)
QUIZ_QUESTIONS = [
    ("1. Is casual chatting allowed in the support chat?", False),
    ("2. Can you submit files in this group?", False),
    ("3. Can you request files in this group?", False),
    ("4. Can you search for files in this group?", False),
    ("5. Can you appeal for an unban or check restrictions here?", True),
    ("6. Can you report errors encountered while using the bot?", True),
    ("7. Can you ask for help on how to use the bot?", True),
    ("8. Can you report wrong files here?", True),
    ("9. Can you leave feedback for the bot or owners?", True),
    ("10. Can you submit complaints here?", True),
]


def get_quiz_question(step: int):
    """Retrieves the question tuple (text, expected_answer) for the given step."""
    if 0 <= step < len(QUIZ_QUESTIONS):
        return QUIZ_QUESTIONS[step]
    return None


def verify_answer(step: int, user_choice: bool) -> bool:
    """Validates user choice against the expected correct answer."""
    if 0 <= step < len(QUIZ_QUESTIONS):
        return QUIZ_QUESTIONS[step][1] == user_choice
    return False


def get_total_questions() -> int:
    """Returns the total number of quiz questions."""
    return len(QUIZ_QUESTIONS)


async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the support center intro and start the verification quiz."""
    text = (
        "🛡️ **Mastermind Support Center**\n\n"
        "If you need help, you can join our support chat. However, to keep our "
        "support chat safe and protected from unnecessary/irrelevant questions, "
        "spam, chats, and attacks, you must pass a quick verification quiz first."
    )

    keyboard = [[InlineKeyboardButton("🚀 Start Verification Quiz", callback_data="support_start_quiz")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=reply_markup)


async def support_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quiz start and answer callbacks for the support flow."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "support_start_quiz":
        context.user_data["quiz_step"] = 0
        await send_quiz_question(query, context, step=0)
        return

    if data.startswith("quiz_ans_"):
        user_step = context.user_data.get("quiz_step", 0)
        user_choice = data == "quiz_ans_yes"

        if verify_answer(user_step, user_choice):
            user_step += 1
            context.user_data["quiz_step"] = user_step

            if user_step < get_total_questions():
                await send_quiz_question(query, context, step=user_step)
                return

            invite_link = await generate_support_invite(context)
            if invite_link:
                success_text = (
                    "🎉 **Congratulations! You passed the verification quiz.**\n\n"
                    "Here is your secure, single-use invite link to join the support chat. "
                    "Note that this link can only be used once."
                )
                keyboard = [[InlineKeyboardButton("🔗 Join Support Chat", url=invite_link)]]
                await query.message.edit_text(
                    success_text,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                return

            await query.message.edit_text(
                "✅ **Quiz Passed Successfully!**\n\n"
                "⚠️ Support chat ID is not configured on this bot instance. Please contact the owner.",
                parse_mode="Markdown",
            )
            return

        context.user_data["quiz_step"] = 0
        fail_text = (
            "❌ **Incorrect Answer!**\n\n"
            "You failed one of the screening questions. To protect the support chat, "
            "the quiz has been reset from the beginning.\n\n"
            "Let's try again."
        )
        keyboard = [[InlineKeyboardButton("🔄 Restart Quiz", callback_data="support_start_quiz")]]
        await query.message.edit_text(fail_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def send_quiz_question(query, context, step: int):
    """Display the current support quiz question with yes/no options."""
    question_text, _ = get_quiz_question(step)
    text = (
        f"📝 **Support Verification Quiz ({step + 1}/10)**\n\n"
        f"{question_text}"
    )
    keyboard = [
        [
            InlineKeyboardButton("✅ Yes", callback_data="quiz_ans_yes"),
            InlineKeyboardButton("❌ No", callback_data="quiz_ans_no"),
        ]
    ]
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def generate_support_invite(context):
    """Generate a single-use support invite link if the support chat is configured."""
    support_chat_id = get_support_chat_id()
    if not support_chat_id:
        return None

    invite_link = await context.bot.create_chat_invite_link(
        chat_id=support_chat_id,
        member_limit=1,
        creates_join_request=False,
    )
    return invite_link.invite_link
