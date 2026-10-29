# 🤖 Mastermind Telegram Bot

A modular Telegram bot built using Python and python-telegram-bot, designed for library search, requests, metadata enrichment, quota allowances, and dual file delivery via helper bots.

---

## 🚀 Features & Commands

### 👤 Standard User Commands
* /start: Opens the interactive welcome menu, processes referral bonuses, and handles file deep-links.
* /search <query>: Searches indexed ebooks and audiobooks with tokenized SQL matching, pagination, and file download cards.
* /request: Interactive request assistant with standalone and series templates; prompts with a library search button if matches already exist in the database.
* /quota: Displays remaining daily search and request allowances.
* /refer & /myreferrals: Personal referral dashboard to invite friends and earn bonus search/request allowances.
* /support: Verification quiz with single-use invite link generation to join the support community.
* /stats: Public bot operation statistics and media banners.
* /help: Detailed user guide and command index.

### 👑 Administrator & Owner Commands
* /checkhelpers (alias: /helpers): Audits all helper bots in HELPER_BOT_TOKENS, verifying token reachability, storage group access, and administrator rights (Post & Delete permissions) in the posting channel. Both Admins and the Bot Owner have full access.
* /index: Batch indexes books from a source chat or message link range into STORAGE_GROUP_ID with Goodreads metadata enrichment and rate-limit sleep intervals.
* /addadmin <id|@username> & /removeadmin: Dynamically grants or revokes the Administrator role (Owner only).
* /gift <id> <searches> <requests>: Grants bonus search/request quota allowances to a user.
* /editscript: Live administration hub to manage text templates, media URLs, and config variables in config.db without restarts.
* /ban, /ban_pm, /ban_support, /unban: Granular user and chat access restriction management.
* /log [count|10m]: Generates and exports in-memory log files directly in Telegram.
* /ping: Diagnostic command displaying round-trip latency and network metrics.
