# mastermind

matermind/
│
├── main.py                     # The main file that starts your bot and brings all modules together (upcoming)
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
    └── message/                # Folder for handling regular chat messages (upcoming)
        └── message_handler.py  # Will contain the reply for normal text with a help button
