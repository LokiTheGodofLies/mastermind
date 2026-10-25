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
