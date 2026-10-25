# 🤖 Mastermind Telegram Bot

A modular Telegram bot built using Python and the `python-telegram-bot` library, featuring a clean directory layout separating each command and feature into dedicated modules.

---

## 📂 Project Structure

<details>
<summary><b>Click to expand directory structure</b></summary>

```text
mastermind/
│
├── main.py                     # The main file that starts your bot and brings all modules together
├── env.txt                     # Secret file storing your sensitive environment variables (like your bot token)
├── .gitignore                  # Git configuration file to keep secret files out of GitHub
│
└── modules/                    # Folder holding all your bot's feature modules
    │
    ├── help_menu/              # Folder for the /help command and help button clicks
    │   └── help_handler.py     # Contains the logic to display the help menu text
    │
    ├── start/                  # Folder for the /start command and welcome buttons
    │   └── start_handler.py    # Contains the welcome message, help button, and bot owner button
    │
    └── message/                # Folder for handling regular chat messages
        └── message_handler.py  # Contains the reply for normal text with an expandable section and help button

🚀 Features
/start Command: Greets the user with a customized welcome message, an interactive Help Menu button, and a direct Bot Owner link button.

/help Command: Displays a clean, HTML-formatted list of all available modules and functions.

Normal Text Handler: Gently responds to casual chat with an expandable blockquote notice and a quick shortcut button back to the help menu.

Modular Architecture: Every feature lives inside its own independent folder and file for maximum maintainability.

⚙️ Installation & Setup
Clone or download this repository into your workspace (or Termux on your Android tablet).

Install the required dependency:

Bash


pip install python-telegram-bot
Create your env.txt file in the root folder with your bot token:

Plaintext


TELEGRAM_BOT_TOKEN=your_bot_token_here
Run main.py to start Mastermind!
