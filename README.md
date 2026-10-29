# 🤖 Mastermind Telegram Bot

A modular Telegram bot built using Python and `python-telegram-bot`, designed for library search, requests, metadata enrichment, quota allowances, and dual file delivery via helper bots.

---

## 🚀 Features,  & Commands

### 👤 Standard User Commands
* `/start`: Opens the interactive welcome menu, processes referral bonuses, and handles file deep-links.
* `/search <query>`: Searches indexed ebooks and audiobooks with tokenized SQL matching, pagination, and file download cards.
* `/request`: Interactive request assistant with standalone and series templates; prompts with a library search button if matches already exist in the database.
* `/quota`: Displays remaining daily search and request allowances.
* `/refer`,  & `/myreferrals`: Personal referral dashboard to invite friends and earn bonus search/request allowances.
* `/support`: Verification quiz with single-use invite link generation to join the support community.
* `/stats`: Public bot operation statistics and media banners.
* `/help`: Detailed user guide and command index.
* `/admins`, `/moderators`, `/volunteers`, `/promoters`: Public community rosters with embedded profile links.

### 👑 Administrator & GOD Commands
* `/checkhelpers` (alias: `/helpers`): Audits all helper bots in `HELPER_BOT_TOKENS`, verifying token reachability, storage group access, and administrator rights (Post & Delete permissions) in the posting channel. Both Admins and GOD have full access.
* `/index`: Batch indexes books from a source chat or message link range into `STORAGE_GROUP_ID` with Goodreads metadata enrichment and rate-limit sleep intervals.
* `/addadmin <id|@username>` & `/removeadmin`: Dynamically grants or revokes the Administrator role (GOD only).
* `/addmoderator <id|@username>` & `/removemoderator` (alias: `/addmod`, `/delmod`): Promotes or demotes a Moderator with 40 daily searches/requests and request status management.
* `/addvolunteer <id|@username>` & `/removevolunteer` (alias: `/addvol`, `/delvol`): Promotes or demotes a Volunteer with 30 daily searches/requests and pre-approved helper indexing.
* `/addpromoter <id|@username>` & `/removepromoter` (alias: `/addpromo`, `/delpromo`): Promotes or demotes a Promoter with 20 daily searches/requests.
* `/gift <id> <searches> <requests>`: Grants bonus search/request quota allowances to a user.
* `/editscript`: Live administration hub to manage text templates, media URLs, and config variables in `config.db` without restarts.
* `/ban`, `/ban_pm`, `/ban_support`, `/unban`: Granular user and chat access restriction management.
* `/log [count|10m]`: Generates and exports in-memory log files directly in Telegram.
* `/ping`: Diagnostic command displaying round-trip latency and network metrics.
* `/broadcast`, `/pinbroadcast` & `/cancelbroadcast`: Multi-bot broadcast engine with real-time segmented progress cards, auto-pinning, and granular category cancellation.

---

## ⚙️ Configuration & Environment

Configuration is centralized in `config.py` with backward-compatible re-export in `configs.py`. Settings are loaded lazily from Render environment variables or a local `env.txt` file (see `env.example` for reference).

Key environment variables:
* `TELEGRAM_BOT_TOKEN`: Main Telegram bot token from @BotFather.
* `HELPER_BOT_TOKENS`: Comma-separated helper bot tokens for dual file delivery.
* `STORAGE_GROUP_ID`: Telegram group/channel where indexed files are stored.
* `POSTING_CHANNEL_ID`: Channel where helper bots post files with automatic deletion.
* `AUTO_DELETE_SECONDS`: Auto-deletion interval in the posting channel (default `300` seconds / 5 minutes).
* `SEARCH_GROUP_ID`: Chat ID where search group invite links are generated.
* `LOGGER_GROUP_ID`: Forum supergroup where operational logs and errors are routed.
* `OWNER_ID`,  & `ADMIN_IDS`: Telegram IDs authorized to administer the bot.

---

## 📂 Project Structure

```text
mastermind/
├── main.py                     # Application entry point, polling manager, and handler registration
├── config.py                   # Centralized configuration and lazy environment getters
├── configs.py                  # Backward-compatible re-export of config.py
├── env.example                 # Sample environment template with placeholder values
├── Dockerfile                  # Container definition for Render deployment
├── requirements.txt            # Python dependencies
│
└── modules/                    # Feature modules
    ├── allowance/              # Daily quota tracking, gifts, and referral bonuses
    ├── ban/                    # Ban middleware, restrictions, and admin promotion
    ├── database/               # SQLite persistence, files, users, and config schemas
    ├── editscript/             # Admin live configuration hub
    ├── help/                   # Help documentation and role-based guides
    ├── id/                     # User, chat, and channel ID lookup
    ├── indexing/               # Goodreads metadata scraping and batch indexing
    ├── log/                    # In-memory logging, member auditing, and error routing
    ├── message/                # Fallback conversational notices
    ├── request/                # Book request flows and Goodreads auto-complete
    ├── search/                 # Search engine and helper-bot dual delivery
    ├── start/                  # Welcome menu and deep-link routers
    ├── stats/                  # Public and admin metrics
    ├── support/                # Screening quiz and single-use support invites
    └── utility/                # Ping latency and helper bot permission auditing
```
