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
* `/id`: User, chat, channel, and forum topic identification with embedded profile links.
* `/help`: Detailed user guide and command index.
* `/admins`, `/moderators`, `/volunteers`, `/promoters`: Public community rosters with embedded profile links.

### 👑 Administrator & Creator Commands
* `/checkhelpers` (alias: `/helpers`): Audits all helper bots in `HELPER_BOT_TOKENS`, verifying token reachability, storage group access, and administrator rights (Post & Delete permissions) in the posting channel. Both Admins and the Creator have full access.
* `/index`: Batch indexes books from a source chat or message link range into `STORAGE_GROUP_ID` with Goodreads metadata enrichment and rate-limit sleep intervals.
* `/addadmin <id|@username>` & `/removeadmin`: Dynamically grants or revokes the Administrator role (Creator only).
* `/addmoderator <id|@username>` & `/removemoderator` (alias: `/addmod`, `/delmod`): Promotes or demotes a Moderator with 40 daily searches/requests and request status management.
* `/addvolunteer <id|@username>` & `/removevolunteer` (alias: `/addvol`, `/delvol`): Promotes or demotes a Volunteer with 30 daily searches/requests and pre-approved helper indexing.
* `/addpromoter <id|@username>` & `/removepromoter` (alias: `/addpromo`, `/delpromo`): Promotes or demotes a Promoter with 20 daily searches/requests.
* `/gift <id> <searches> <requests>`: Grants bonus search/request quota allowances to a user.
* `/editscript`: Live administration hub to manage text templates, media URLs, and config variables in `config.db` without restarts.
* `/ban`, `/ban_pm`, `/ban_support`, `/unban`: Granular user and chat access restriction management.
* `/log [count|10m]`: Generates and exports in-memory log files directly in Telegram.
* `/ping`: Diagnostic command displaying round-trip latency and network metrics.
* `/broadcast`, `/pinbroadcast` & `/cancelbroadcast`: Interactive Broadcast Control Panel with target toggles (`🌐 All`, `👥 Users`, `🤖 Helper Bots`, `👥 Groups`, `📢 Channels`), `📌 Pin in Chats` toggle, and live inline `⏸ Pause`, `▶️ Resume`, and `🛑 Cancel Broadcast` controls.

---

## 🏗️ Dual Main Bot Architecture (Public vs. Testing)

The repository supports two completely isolated Main Bot environments (each with its own dedicated groups and channels) from the same codebase:

1. **🌐 Public Main Bot (`main` branch)**
   * **Purpose**: Production bot serving public users with stable, verified features.
   * **Render Web Service**: `mastermind` (`srv-dbgi9nflk1mc73c0abmg`), auto-deployed from the `main` branch.
   * **Dedicated Channels & Groups**: Public Book Storage Group (`STORAGE_GROUP_ID`), Public Posting Channel (`POSTING_CHANNEL_ID`), Public Bot Log Group (`LOGGER_GROUP_ID`), Public Index Logs Channel (`INDEX_CHANNEL_ID`), Public Request Logs Channel (`REQUEST_CHANNEL_ID`), Public Support Chat (`SUPPORT_CHAT_ID`, which also hosts the Public Search topic `SEARCH_TOPIC_ID`).

2. **🧪 Testing Main Bot (`test` branch)**
   * **Purpose**: Staging & QA bot for testing new commits and experimental features on the `test` branch before merging to `main`.
   * **Render Web Service**: Separate Render service connected to the `test` branch (`BOT_MODE=testing` or auto-detected via `RENDER_GIT_BRANCH=test`).
   * **Isolated Testing Channels & Groups**: Uses separate testing channels and groups (configured via `TESTING_STORAGE_GROUP_ID`, `TESTING_POSTING_CHANNEL_ID`, `TESTING_LOGGER_GROUP_ID`, `TESTING_INDEX_CHANNEL_ID`, `TESTING_REQUEST_CHANNEL_ID`, `TESTING_SEARCH_TOPIC_ID` (a topic inside `TESTING_LOGGER_GROUP_ID`), `TESTING_SUPPORT_CHAT_ID`, and `TESTING_BACKUP_TOPIC_ID` (a topic inside `TESTING_LOGGER_GROUP_ID`)—or the standard variable names on the separate Render service) so testing never touches or pollutes the live Public channels or database backups.

---

## ⚙️ Configuration & Environment

Configuration is centralized in `config.py` with backward-compatible re-export in `configs.py`. Settings are loaded lazily from Render environment variables or a local `env.txt` file (see `env.example` for reference).

Key environment variables:
* `BOT_MODE`: Deployment mode (`public` for `main` branch or `testing` for `test` branch).
* `PUBLIC_BOT_TOKEN`: Token of the Public Main Bot (`main` service). `TESTING_BOT_TOKEN`: Token of the Testing Main Bot (`test` service). Each service sets only its own; there is NO fallback (`TELEGRAM_BOT_TOKEN` is no longer read).
* **Aliases removed:** only one name per setting is read (e.g. `AUTO_DELETE_SECONDS`, `DEFAULT_SEARCH_QUOTA`, `PROMOTER_QUOTA_DEFAULT`, `COMMUNITY_LINK`, `BOT_MODE`). Old names like `COMMUNITY_URL`, `DEPLOY_ENV`, `FILE_AUTO_DELETE_SECONDS`, `SEARCH_QUOTA_DEFAULT` are ignored.
* **Secrets:** `Render_Variables*.txt` and `env.txt` hold tokens and are git-ignored. Never commit them.
* **Rule:** every per-bot variable has a `PUBLIC_` or `TESTING_` prefix and each service reads ONLY its own (no fallbacks). Shared: `BOT_MODE`, `CREATOR_ID`, `CREATOR_USERNAME`, `ADMIN_IDS`, quotas, timers, `PORT`.
* `PUBLIC_BOT_NAME` / `TESTING_BOT_NAME`: Display name of the Public / Testing Main Bot (separate variables, no shared `BOT_NAME`).
* `PUBLIC_HELPER_POLLING_ENABLED` / `TESTING_HELPER_POLLING_ENABLED`: Controls helper bot polling (default `true`; keep `true` on both services because each uses its own helper bot).
* `PUBLIC_HELPER_BOT_TOKENS` / `TESTING_HELPER_BOT_TOKENS`: Helper bot tokens (Public = @RickRiordanBot, Testing = @Heyuqtbot). Never share one helper bot between services (Telegram 409 Conflict).
* `PUBLIC_STORAGE_GROUP_ID` / `TESTING_STORAGE_GROUP_ID`: Telegram group/channel where indexed files are stored.
* `PUBLIC_POSTING_CHANNEL_ID` / `TESTING_POSTING_CHANNEL_ID`: Channel where helper bots post files with automatic deletion.
* `AUTO_DELETE_SECONDS`: Auto-deletion interval in the posting channel (default `300` seconds / 5 minutes).
* `PUBLIC_SEARCH_TOPIC_ID` / `TESTING_SEARCH_TOPIC_ID`: Forum topic ID of the Search topic. The chat is derived: Public = `PUBLIC_SUPPORT_CHAT_ID`, Testing = `TESTING_LOGGER_GROUP_ID` (the bot generates single-use invite links for that chat). In the topic every plain message is a search query and every command is deleted; in private chat use `/search <keyword>`; in any other group `/search` is refused. The bot needs Delete Messages + Invite Users rights in that chat.
* `PUBLIC_LOGGER_GROUP_ID` / `TESTING_LOGGER_GROUP_ID` (plus `*_INDEX_CHANNEL_ID`, `*_REQUEST_CHANNEL_ID`, `*_SUPPORT_CHAT_ID`, `*_BACKUP_TOPIC_ID` (topic of the logger group that holds the pinned database backup; there is no separate backup chat), `*_BACKUP_FILENAME`, `*_FSUB_CHANNEL_IDS`, `*_GENERAL_TOPIC_ID`, `*_USER_LOG_TOPIC_ID`, `*_INDEX_LOG_TOPIC_ID`, `*_GROUP_LOG_TOPIC_ID`, `*_CHANNEL_LOG_TOPIC_ID`, `*_REQUEST_LOG_TOPIC_ID`, `*_ERROR_LOG_TOPIC_ID`, same pattern): Forum supergroup where operational logs and errors are routed.
* `CREATOR_ID`: **REQUIRED** Telegram ID of the Creator (same on Public and Testing; replaces GOD_ID/OWNER_ID). The bot refuses to start if it is missing (no sample-ID fallback). `CREATOR_USERNAME`: Creator @username shown in the bot (no @). `ADMIN_IDS`: extra Admin Telegram IDs.

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
    ├── broadcast/              # Interactive broadcast control panel, helper bot pool & live pause/cancel
    ├── database/               # SQLite persistence, files, users, and config schemas
    ├── editscript/             # Admin live configuration hub
    ├── help/                   # Help documentation and role-based guides
    ├── id/                     # User, chat, and channel ID lookup
    ├── indexing/               # Goodreads metadata scraping and batch indexing
    ├── log/                    # In-memory logging, member auditing, and error routing
    ├── message/                # Fallback conversational notices
    ├── request/                # Book request flows and Goodreads auto-complete
    ├── roster/                 # Public role rosters (/admins, /moderators, /volunteers, /promoters)
    ├── search/                 # Search engine and helper-bot dual delivery
    ├── start/                  # Welcome menu and deep-link routers
    ├── stats/                  # Public and admin metrics
    ├── support/                # Screening quiz and single-use support invites
    └── utility/                # Ping latency and helper bot permission auditing
```
