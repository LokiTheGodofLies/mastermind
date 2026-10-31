# 🤖 Mastermind Telegram Bot

A high-performance, modular Telegram bot built using Python and `python-telegram-bot` (v21+), engineered for community library search, book requests, 8-site book & audiobook metadata enrichment, granular role-based access control, dual file delivery, and automated SQLite persistence.

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
* **Direct Helper Indexing**: Volunteers and Moderators can send or forward supported ebook (`.epub`, `.pdf`, `.mobi`, `.azw`, `.azw3`, `.cbr`, `.cbz`, `.djvu`, `.fb2`, `.txt`, `.rtf`), audiobook (`.mp3`, `.m4b`, `.m4a`, `.flac`, `.wav`, `.aax`, `.aa`, `.ogg`, `.opus`), and archive (`.zip`, `.rar`, `.7z`) files directly to any configured Helper Bot in private chat. The file is validated, enriched, and stored in the library without manual admin review.
* **Request Management (Moderators Only)**: Interactive inline buttons on forwarded user requests in the Request Channel:
  * ⏳ **Pending**: Request is queued for review.
  * 🔄 **Processing**: Request is actively being sourced.
  * ✅ **Completed**: Book was indexed into the library.
  * ❌ **Rejected**: Request cannot be fulfilled.

---

### ⚔️ Administrator & 👑 Creator Commands
* `/index`: Batch indexes books and audiobooks from a source chat or message link range (`/index <first_link> <last_link>`) into `STORAGE_GROUP_ID` with 3-stage self-healing, 8-site metadata enrichment, and rate-limit sleep intervals.
* `/checkhelpers` (alias: `/helpers`): Audits all configured helper delivery bots, verifying token reachability, storage group access, and posting channel administrator rights (Post & Delete permissions) for 5-minute auto-delete.
* `/broadcast` & `/cancelbroadcast`: Interactive Broadcast Control Panel with target toggles (`🌐 All`, `👥 Users`, `🤖 Helper Bots`, `👥 Groups`, `📢 Channels`), auto-pinning in chats (`📌 Pin in Chats`), and live inline `⏸ Pause`, `▶️ Resume`, and `🛑 Cancel` controls.
* `/publish`: Exclusive to Creator. Merges the verified `test` branch into `main` and pushes to `loki main` & `origin main`, triggering live Render deployment on Public Books Bot.
* `/update`: Exclusive to Creator. In-chat bot updater. Send or reply to a `.zip` archive to unpack, verify with `compileall`, commit, and auto-push to GitHub without Termux.
* `/sh <command>` (alias: `/term`): Exclusive to Creator. Executes bash shell commands directly inside Telegram.
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

## 📚 Complete Indexing Architecture & 3-Stage Self-Healing Pipeline

The indexing pipeline implements a strict 3-stage ordered verification and self-healing process with 8-site metadata extraction and live admin edit synchronization:

```
[ Incoming Media (Helper DM or /index) ]
                 │
                 ▼
  [ Format & Archive Inspection ] ──► (Inspects .zip <= 20MB; strips promo/spam captions)
                 │
                 ▼
  [ Stage 1: Database Presence ] ───► (Checks files.db by file_unique_id; preserves row ID)
                 │
                 ▼
  [ Stage 2: Storage Group Presence ] ► (Verifies/restores message in STORAGE_GROUP_ID)
                 │
                 ▼
  [ Stage 3: 8-Site Caption Enrichment ]
                 │
   ┌─────────────┴──────────────────────────────┐
   ▼                                            ▼
[ Parameter Match >= 2 ]               [ Parameter Match < 2 ]
   │                                            │
   ├─ Clean Title T & Option B Series S         ├─ Empty T & A Placeholders
   ├─ Matched Book Info Page URL                ├─ Store in Storage & files.db
   ├─ Zero N/A Captions                         ├─ Log Error to ERROR_LOG_TOPIC_ID
   └─ Post 3-Tick Index Log (✅, ✅, ✅)        └─ Post Index Log (✅, ✅, 🚧)
```

### 1. Spam / Promo Stripping & Filename Tokenization
* **Promo Caption Stripping**: Automatically strips promotional/spam captions (including stylized small-caps like `ᴊᴏɪɴ @heyucutie ꜰᴏʀ ᴍᴏʀᴇ`, `@channel`, `t.me/...`) before parsing.
* **Watermark Stripping**: Strips shadow-library tags (`z-lib.org`, `z-library`, `annas-archive`, `libgen`, `oceanofpdf`, `audiobookbay`, `mobilism`, `pdfdrive`) and format extensions.
* **Apostrophe & Hyphen Handling**: Normalizes smart quotes (`’`, `‘`) to `'`, preserves compound titles (`Fifty-Fifty`), and dual-matches tokens (`Ender's` ↔ `Enders`).

### 2. Option B Title & Series Separation
* Always separates `📖 Title:` and `📚 Series:` onto distinct lines—never leaving `(Series #N)` inside `Title:`:
  * `📖 Title: Fifty-Fifty` (hyperlinked to matched catalog URL)
  * `📚 Series: Eddie Flynn (Book #5)` (or `Standalone` when standalone)

### 3. 8-Website Book & Audiobook Lookup Waterfall (Zero Movies/Anime)
* **Audiobooks Sequence**:
  `1. Audible` (Catalog API `.in`/`.com`/`.co.uk`/`.au`/`.ca`) ➔ `2. Storytel` (`__NEXT_DATA__` + JSON-LD) ➔ `3. Apple Books (Audiobook)` ➔ `4. Goodreads` (`auto_complete` + `/book/show/` Apollo state) ➔ `5. Penguin Random House Audio` ➔ `6. Internet Archive Audio` ➔ `7. Google Books` ➔ `8. OpenLibrary`.
* **Ebooks Sequence**:
  `1. Goodreads` (`auto_complete` + `/book/show/` Apollo state) ➔ `2. Storytel` ➔ `3. Apple Books (Ebook)` ➔ `4. Audible` ➔ `5. Penguin Random House` ➔ `6. Crossref / Internet Archive Texts` ➔ `7. Google Books` ➔ `8. OpenLibrary`.

### 4. Standardized 3-Tick Index Log Format
Every indexed or healed file generates a 3-stage verification log card in `INDEX_LOG_TOPIC_ID`:
```text
📥 File Index Log

📁 File Name: Fifty-Fifty.zip
📦 File Size: 303.95 MB
🔑 Unique ID: AQADfAsAAonW6FZy
🔗 Storage Link: https://t.me/c/3511375054/34
👤 Sent By: Loki (tg://user?id=8853305382)

3-Stage Verification Status:
1. 🗄 Database Presence: ✅ Present & Self-Healed in files.db
2. 📦 Storage Group Presence: ✅ Present in Storage Group (Caption Updated at Msg #34)
3. 📝 Caption Enrichment: ✅ Enriched via Goodreads (Eddie Flynn (Book #5))
⏰ Timestamp: 31 Oct 2026, 14:42 IST
```

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
