# 🤖 Mastermind Telegram Bot

A high-performance, modular Telegram bot built using Python and `python-telegram-bot` (v21+), engineered for community library search, book requests, multi-site metadata enrichment, granular role-based access control, dual file delivery, and automated SQLite persistence.

---

## 🚀 Features, Roles & Commands

### 👥 Community Roles & Permission Matrix

The system implements a strict 6-tier role hierarchy:

| Role | Daily Searches | Daily Requests | Key Permissions & Privileges |
| :--- | :---: | :---: | :--- |
| **👤 Normal User** | 10 | 10 | `/start`, `/search`, `/request`, `/quota`, `/refer`, `/support`, `/stats`, `/id`, Roster viewing, Dual delivery |
| **📣 Promoter** | 20 | 20 | Elevated daily allowances for community outreach and promotion |
| **🤝 Volunteer** | 30 | 30 | Pre-approved direct book & audiobook indexing via Helper Bot DMs |
| **🛡️ Moderator** | 40 | 40 | Pre-approved direct indexing + Request Channel status control (Pending, Processing, Completed, Rejected) |
| **⚔️ Administrator** | Unlimited | Unlimited | Batch range `/index`, `/broadcast`, `/checkhelpers`, `/ban`, `/gift`, `/editscript`, `/log`, `/ping`, Role management |
| **👑 Creator** | Unlimited | Unlimited | Supreme governance, `/addadmin`, SQLite database persistence, and system backups |

---

### 👤 Standard User Commands
* `/start`: Opens the interactive welcome menu, processes referral bonuses, and handles deep-link file delivery.
* `/search <query>`: Tokenized SQL search across filenames, titles, authors, series, and captions with dual-apostrophe matching and pagination.
* `/request <title and author>`: Interactive request assistant with standalone and series templates, routed to the Request Channel.
* `/quota`: Displays real-time search/request quota consumption, tier limits, and midnight IST reset countdown.
* `/refer` & `/myreferrals`: Personal referral dashboard to invite members and earn bonus search/request allowances (+10 per invite).
* `/support`: Verification quiz with single-use invite link generation to join the support community.
* `/stats`: Public bot metrics displaying total indexed files, ebook counts, audiobook counts, and uptime.
* `/id`: Identification inspector for users, chats, channels, and forum topics with embedded profile links.
* `/help`: Role-gated, paginated documentation hub displaying only the user's accessible commands and an open User Roles guide.
* `/admins`, `/moderators`, `/volunteers`, `/promoters`: Public team rosters with direct profile links.

---

### 🤝 Volunteer & 🛡️ Moderator Operations
* **Direct Helper Indexing**: Volunteers and Moderators can send or forward supported ebook (`.epub`, `.pdf`, `.mobi`, `.azw`, `.azw3`, `.cbr`, `.cbz`) and audiobook (`.mp3`, `.m4b`, `.flac`, `.wav`, `.aax`, `.aa`) files directly to any configured Helper Bot in private chat. The file is validated, enriched, and stored in the library without manual admin review.
* **Request Management (Moderators Only)**: Interactive inline buttons on forwarded user requests in the Request Channel:
  * ⏳ **Pending**: Request is queued for review.
  * 🔄 **Processing**: Request is actively being sourced.
  * ✅ **Completed**: Book was indexed into the library.
  * ❌ **Rejected**: Request cannot be fulfilled.

---

### ⚔️ Administrator & 👑 Creator Commands
* `/index`: Batch indexes books from a source chat or message link range (`/index <first_link> <last_link>`) into `STORAGE_GROUP_ID` with multi-site metadata enrichment and rate-limit sleep intervals.
* `/checkhelpers` (alias: `/helpers`): Audits all configured helper delivery bots, verifying token reachability, storage group access, and posting channel administrator rights (Post & Delete permissions) for 5-minute auto-delete.
* `/broadcast` & `/cancelbroadcast`: Interactive Broadcast Control Panel with target toggles (`🌐 All`, `👥 Users`, `🤖 Helper Bots`, `👥 Groups`, `📢 Channels`), auto-pinning in chats (`📌 Pin in Chats`), and live inline `⏸ Pause`, `▶️ Resume`, and `🛑 Cancel` controls.
* `/addadmin <id|@username>` & `/removeadmin`: Appoints or removes an Administrator (exclusive to Creator).
* `/addmoderator <id|@username>` & `/removemoderator` (alias: `/addmod`, `/delmod`): Promotes or demotes a Moderator.
* `/addvolunteer <id|@username>` & `/removevolunteer` (alias: `/addvol`, `/delvol`): Promotes or demotes a Volunteer.
* `/addpromoter <id|@username>` & `/removepromoter` (alias: `/addpromo`, `/delpromo`): Promotes or demotes a Promoter.
* `/gift <id> <searches> <requests>`: Grants bonus search/request quota allowances to any user.
* `/editscript`: Live administration hub to manage text templates, media URLs, and config variables in `config.db` without restarting.
* `/ban`, `/ban_pm`, `/ban_support`, `/unban`: Granular user and chat access restriction management.
* `/log [count|duration]`: Exports in-memory ring-buffer system logs as a downloadable document directly in Telegram.
* `/ping`: Diagnostic command displaying round-trip API latency and network statistics.

---

## 📚 Complete Indexing Architecture & Caption Enrichment Pipeline

The indexing pipeline implements a 3-stage validation process with multi-site metadata extraction and live admin edit synchronization:

```
[ Incoming Media (Helper DM or /index) ]
                 │
                 ▼
  [ Stage 1: Extension Validation ] ──► (Reject unsupported formats)
                 │
                 ▼
  [ Stage 2: Storage & DB Presence ] ──► (Verify existence in files.db & Storage Group)
                 │
                 ▼
  [ Stage 3: Multi-Site Enrichment ]
                 │
   ┌─────────────┴──────────────────────────────┐
   ▼                                            ▼
[ Parameter Match >= 2 ]               [ Parameter Match < 2 ]
   │                                            │
   ├─ Clean Title T & Series S                  ├─ Empty T & A Placeholders
   ├─ Matched Book Info Page URL                ├─ Store in Storage & files.db
   ├─ Zero N/A Captions                         ├─ Log Error to ERROR_LOG_TOPIC_ID
   └─ Post Index Log (📝)                       └─ Post Index Log (🚧)
                                                        │
                                                        ▼
                                       [ Admin Edits Caption in Storage ]
                                                        │
                                                        ▼
                                       [ Bot Intercepts Update.edited_message ]
                                                        │
                                                        ▼
                                       [ Syncs files.db & Logs (✍️) ]
```

### 1. Filename Tokenization & Normalization
* **Watermark Stripping**: Strips known shadow-library tags (`z-lib.org`, `z-library`, `annas-archive`, `libgen`, `oceanofpdf`, `audiobookbay`, `mobilism`) and format extensions.
* **Apostrophe Handling**:
  * **Suggestion A**: Normalizes smart/curly quotes (`’`, `‘`, `` ` ``) to straight `'`.
  * **Suggestion B**: Preserves mid-word and ending apostrophes (`Ender's`, `O'Connor`, `witches'`), while stripping wrapping single quotes (`'The Hobbit'` → `The Hobbit`).
  * **Suggestion C**: Dual-matches tokens (matching both `Ender's` and `Enders`) during catalog lookups.

### 2. Regex Title & Series Separation
* Extracts embedded series tags like `(Sweet Omegaverse #8)`, `(Twisted, Book 2)`, or `(The Stormlight Archive, #1)` from raw titles and filenames:
  * `T` (Title): Clean title without series clutter (`Rescued Beta` or `Twisted Games`).
  * `S` (Series): Series name with book sequence (`Sweet Omegaverse (#8)` or `Twisted, Book 2`).

### 3. Multi-Site Scraping Waterfall (Zero Movies/Anime)
The bot queries 6 official and reliable public book catalogs in strict sequence:
* **Ebooks Waterfall**: Goodreads (`auto_complete` + page state) → Google Books API → OpenLibrary API → Apple Books API → Storytel → Audible.
* **Audiobooks Waterfall**: Audible Catalog API → Storytel → Apple Audiobooks API → Goodreads → Google Books API → OpenLibrary API.

### 4. Anti-False-Positive Filtering (SuperSummary Fix)
* **Strict Author Verification**: The author returned by the provider must match the author in the filename (`SuperSummary != Ana Huang` is immediately rejected).
* **Derivative Work Blacklist**: Filters out companion guides (`Study Guide:`, `Summary of`, `Analysis of`, `Book Analysis`) unless explicitly present in the original filename.
* **Multi-Parameter Threshold**: Requires at least 2 parameters (`T`, `S`, `A`) to match before accepting metadata.
* **Cross-Site Verification**: Once matched, the bot queries subsequent providers to confirm whether the book belongs to a series or is `Standalone`, and backfills missing optional fields.
* **Zero `N/A` Rule**: Missing optional fields (Pages, Release Date, Rating, Genres, Narrator, Duration) are completely omitted—never written as `N/A`.
* **Clickable Book Info URL**: The book title (`<a href="URL">Title</a>`) hyperlinks directly to the book info page of the site that matched parameters.

### 5. Storage Group Live Caption Edit Synchronization
When an Admin edits a file's caption directly in the Storage Group:
1. The bot intercepts the `Update.edited_message` event in real time.
2. Updates the file record in `files.db` with the new caption and sets `is_enriched = 1`.
3. Dispatches an updated Index Log to `INDEX_LOG_TOPIC_ID` with the badge: `✍️ caption enriched by admin (<a href="tg://user?id={admin_id}">{admin_name}</a>)`.

### 6. Standardized Index Log Format
Every indexed or updated file generates a structured log card in `INDEX_LOG_TOPIC_ID`:
```text
📥 File Index Log

📁 File Name: Twisted Games (Twisted, Book 2) - Ana Huang.epub
📦 File Size: 459.25 KB
🔑 Unique ID: AQAD...
🔗 Storage Link: https://t.me/c/3511375054/1042
👤 Sent By: Ana Huang (tg://user?id=123456789)
🌐 Source: Testing Dump Channel (https://t.me/testing_dump) [if via /index]

🗄 Database Check: ✅ updated / 📜 already present in database
📦 Storage Check: ✅ present / 🗃️ added to storage group
📝 Caption Check: 
   • 🚧 info not found reported to error logs
   • 📜 already enriched
   • 📝 caption enriched
   • ✍️ caption enriched by admin (Admin Name)
⏰ Timestamp: 31 Oct 2026, 01:30 IST
```

---

## 🔍 Enhanced Search Engine

* **Dual Filename & Caption Matching**: Searches across `file_name`, `caption`, `title`, `author`, and `series` simultaneously.
* **Dual Apostrophe Tolerance**: Searching `Enders Game` automatically matches `Ender's Game` and vice-versa.
* **Series Sequence Matching**: Querying `Sweet Omegaverse 8` matches `Sweet Omegaverse (#8)` and `Sweet Omegaverse, Book 8`.
* **Dual Delivery**:
  * 🤖 **Direct DM Delivery**: Helper bots dispatch the file directly to the user's private messages.
  * 📢 **Posting Channel**: Helper bots post the file to the Posting Channel with a 5-minute auto-delete countdown timer.

---

## 📖 Role-Gated Help Menu System

* **Strict Role Visibility**:
  * Normal Users only see User Functions and the open User Roles overview.
  * Higher-tier menus (Volunteer, Moderator, Administrator, Creator) are strictly hidden from users below those tiers.
  * Unauthorized button clicks are blocked with a `⛔ Access restricted to <Role>` alert.
* **Clean Command Titles**: Button labels display only the command name (e.g., `start`, `search`, `request`, `quota`, `index`, `broadcast`, `ban`, `ping`), omitting slashes and examples.
* **Submenu Pagination**: Category menus with more than 6 commands are cleanly split into paginated views (`◀️ Prev`, `Page X/Y`, `Next ▶️`) with a maximum of 6 buttons per page.

---

## 🏗️ Dual Main Bot Architecture (Public vs. Testing)

1. **🌐 Public Main Bot (`main` branch)**
   * **Identity**: H D Carlton (`@HDCarltonbot`, ID: `8580921678`)
   * **Helper**: `@RickRiordanBot` (ID: `8768612669`)
   * **Channels & Groups**:
     * Storage Group: `-1004351628501` (`PUBLIC_STORAGE_GROUP_ID`)
     * Posting Channel: `-1003917326986` (`PUBLIC_POSTING_CHANNEL_ID`)
     * Logger Group: `-1003983227434` (`PUBLIC_LOGGER_GROUP_ID`)
     * Support Chat: `-1003689459842` (`PUBLIC_SUPPORT_CHAT_ID`)
     * Search Topic ID: `4488` (`PUBLIC_SEARCH_TOPIC_ID`)
     * Backup Topic ID: `4` (`PUBLIC_BACKUP_TOPIC_ID`)

2. **🧪 Testing Main Bot (`test` branch)**
   * **Identity**: George Orwell (`@GeorgeOrwellAi`, ID: `9185254121`)
   * **Helper**: `@Heyuqtbot` (ID: `8752800863`)
   * **Channels & Groups**:
     * Storage Group: `-1003511375054` (`TESTING_STORAGE_GROUP_ID`)
     * Posting Channel: `-1004290994265` (`TESTING_POSTING_CHANNEL_ID`)
     * Logger Group: `-1004293995714` (`TESTING_LOGGER_GROUP_ID`)
     * Support Chat: `-1003689459842` (`TESTING_SUPPORT_CHAT_ID`)
     * Search Topic ID: `579` (`TESTING_SEARCH_TOPIC_ID`)
     * Backup Topic ID: `583` (`TESTING_BACKUP_TOPIC_ID`)

---

## 💾 SQLite Database Persistence & Telegram Backups

All state is preserved in persistent SQLite databases:
* `files.db`: Indexed media files, unique IDs, storage message IDs, file sizes, categories, and enriched captions.
* `mastermind_users.db`: User profiles, role assignments, referral metrics, and daily quota tracking.
* `config.db`: Dynamic runtime configurations, UI banners, and customizable templates.

Automated backups are compiled every 5 minutes and posted directly to the configured Backup Topic (`PUBLIC_BACKUP_TOPIC_ID=4` / `TESTING_BACKUP_TOPIC_ID=583`).
