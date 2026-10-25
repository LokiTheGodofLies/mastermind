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
