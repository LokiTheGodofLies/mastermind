# 🤖 Mastermind Telegram Bot (Bot API 10.3 Rich UI Edition)

A high-performance, modular Telegram bot built using Python and `python-telegram-bot` (v21+), upgraded with **Telegram Bot API 10.3 Rich Messages (`sendRichMessage`) & Colorful In-Text Buttons (`<tg-button>`, `<tg-button-row>`, `primary` / `success` / `danger` / `disabled`)**, 3-Stage Self-Healing Indexing across 8 book & audiobook catalogs, dual Index Channel + Logger Group logging, and timestamped zero-unpin SQLite persistence.

---

## 🎨 Telegram Bot API 10.3 Rich Formatting & Colorful Buttons (`modules/utility/rich_ui.py`)

* **🔁 In-Text Button Revolution (`<tg-button>` & `<tg-button-row align="...">`)**:
  * Replaces raw text hyperlinks (`<a href="...">`) and legacy inline keyboards across interactive cards (search results, book requests, file delivery cards, rosters, `/id`, and help menus) with native Bot API 10.3 in-text buttons.
  * Supports `type="callback_data"`, `type="url"`, `type="copy_text"` (one-tap clipboard copy for user/chat IDs and referral links), and `type="disabled"` (`DisabledButton` for non-clickable page indicators like `📄 1/2`).
* **🎨 Semantic Button Color Palette**:
  * **🟢 Green (`style="success"`)**: Primary positive actions (`📥 Download #N`, `📨 Send All`, `🚀 Confirm Publish`, `✅ Approve`, `📤 Submit Request`, `📤 Refer & Earn`, active toggles ending in `✅`).
  * **🔵 Blue (`style="primary"`)**: Navigation, filters, pagination (`◀️ Prev`, `Next ▶️`, `« Back`), Goodreads/Storage inspection links, and help category cards.
  * **🔴 Red (`style="danger"`)**: Destructive or cancellation actions (`⛔ Cancel Indexing`, `🛑 Cancel Broadcast`, `❌ Reject`, `❌ Close Menu`).
* **💪 Rich HTML Typography**:
  * Uses `<mark>` highlighted pill badges, `<blockquote expandable>` collapsible logs/previews, and automatic fallback to standard `HTML` + styled `InlineKeyboardMarkup` (`api_kwargs={"style": ...}`) for 100% cross-client compatibility.

---

## 📋 Search Result Tables (`modules/search/handlers.py`, `modules/utility/rich_ui.py`)

* Each search result is a Bot API 10.3 rich `<table>` (`build_result_table_html()`): **No. / Title / Author / Series / Size / Format / Ext**, followed by its own `<tg-button-row>` (`📥 Download #N`, `⚡ Direct Link`). In-text buttons keep the translucent, colored look.
* **Fallback** (Telegram rejects the rich message): `tables_to_pre()` turns every table into a monospace block (plain letters), buttons move to the keyboard under the message, and long cells are shortened step by step so the message stays under 4096 characters.
* In-text button URLs are percent-encoded (`_safe_url()`), because a raw space or apostrophe in a link (e.g. the `/start` share link) can make Telegram reject the whole rich message and force the solid keyboard-button fallback.
* When a rich send/edit is rejected, the reason is now logged as a **WARNING** (`sendRichMessage rejected...` / `editMessageText(rich) rejected...`) so it shows in the Render logs.
* Tests: `python tests/test_search_table.py`.

## 🔠 Small Caps Text Engine (`modules/utility/small_caps.py`)

Every message, caption, button label and callback toast the bot sends is converted to small caps automatically, at the last step before it reaches Telegram. **Bot strings stay written in normal text in the source code**; no small-caps glyphs are typed anywhere.

* **Where it hooks in**: `install_rich_ui_patches()` in `rich_ui.py` (`send_message`, `edit_message_text`, `edit_message_reply_markup`, photo/video/animation/document/audio/voice captions, `edit_message_caption`, `answer_callback_query`, and the Bot API 10.3 `sendRichMessage` / `editMessageText` paths). New handlers get it for free.
* **What stays untouched**: HTML tags and attributes, entities, URLs, `@usernames`, `/commands`, `#hashtags`, button `callback_data` / URLs / `copy_text`, and Storage Group captions (they are machine-read and re-indexed).
* **Monospace safety**: `<code>` / `<pre>` text is always shown in plain letters (Telegram's monospace font has no small-cap glyphs and would draw empty boxes), including names that were already stored in small caps.
* **Input side**: `from_small_caps()` maps text copied from the bot back to plain letters, so `/search` and `/request` still match the database.
* **Device support**: the default glyph set renders on iOS and Android phones from 2010 onward using the system font fallback. `q` uses a lookalike glyph, and `s` / `x` stay plain letters because they have no widely supported small-cap form.
* **Switches (`.env`)**: `SMALL_CAPS=0` disables the feature; `SMALL_CAPS_EXTENDED=1` also uses the true small-cap `s` (newer fonts only).
* **Tests**: `python tests/test_small_caps.py`

---

## 🚀 Features, Roles & Commands

### 👥 Community Roles & Permission Matrix

The system implements a strict 6-tier role hierarchy:

| Role | Daily Searches | Daily Requests | Key Permissions & Privileges |
| :--- | :---: | :---: | :--- |
| **👤 Normal User** | 10 | 10 | `/start`, `/search`, `/request`, `/quota`, `/refer`, `/support`, `/stats`, `/id`, Roster viewing, Dual delivery |
| **📣 Promoter** | 20 | 20 | Elevated daily allowances for community outreach and promotion |
| **🤝 Volunteer** | 30 | 30 | Pre-approved direct book, audiobook & archive indexing via Helper Bot DMs |
| **🛡️ Moderator** | 40 | 40 | Pre-approved direct indexing + Request Channel status control (`⏳ In Progress`, `✅ Completed`, `❌ Rejected`) |
| **⚔️ Administrator** | Unlimited | Unlimited | Batch range `/index` (Main + Helper Bots), `/broadcast`, `/checkhelpers`, `/ban`, `/gift`, `/editscript`, `/log`, `/ping`, Role management |
| **👑 Creator** | Unlimited | Unlimited | Supreme governance, `/addadmin`, `/update`, `/publish`, `/sh`, and timestamped SQLite database persistence |

---

### 👤 Standard User Commands
* `/start`: Opens the interactive welcome menu with colorful buttons, processes referral bonuses, and handles deep-link file delivery.
* `/search <query>`: Tokenized SQL search across filenames, titles, authors, series, and captions with dual-apostrophe matching, pagination, and and one **table per result** (No., Title, Author, Series or Standalone, Size, Format = Ebook / Audiobook / Archive, Ext) with its in-text `📥 Download #N` + `⚡ Direct Link` buttons directly below it. The Download button is unchanged (`file_dl_<id>` callback and `?start=dl_<id>` deep link, same dual delivery).
* `/request <title and author>`: Interactive request assistant with Goodreads metadata lookup and colorful `📥 Select` / `📖 Goodreads` buttons, routed to the Request Channel.
* `/quota`: Displays real-time search/request quota consumption, tier badges, and midnight IST reset status.
* `/refer` & `/myreferrals`: Personal referral dashboard with one-tap `📋 Copy Invite Link` and `📤 Share Link` buttons (+10 searches & requests per invite).
* `/support`: 10-question verification quiz with colorful Yes/No buttons and single-use invite link generation to join the support community.
* `/stats`: Live bot metrics displaying total indexed files, ebook counts, audiobook counts, and server diagnostics.
* `/id`: Identification inspector for users, chats, channels, and forum topics with one-tap `📋 Copy ID` buttons (automatically omits `User Name` and `User ID` when run inside a channel where the sender is anonymous).
* `/help`: Role-gated, paginated documentation hub with colorful category and command buttons.
* `/admins`, `/moderators`, `/volunteers`, `/promoters`: Public team rosters with in-text profile and `📋 Copy ID` buttons.

---

### ⚔️ Administrator & 👑 Creator Commands
* `/index`: Batch indexes books, audiobooks, and archives (`.zip`, `.rar`, `.7z`) from a source channel/group or message link range (`/index <first_link> <last_link>`) into `STORAGE_GROUP_ID`:
  * **Works on Both Main Bot & Helper Bots**: Registered on all Helper Bots as well as the Main Bot (with automatic `(chat.id, msg.message_id)` deduplication) so `/index` works in any channel where either a Helper Bot or the Main Bot is Admin.
  * **Channel Auto-Clean**: Immediately deletes the `/index` command post in channels and auto-deletes the temporary progress card 15 seconds after completion.
  * **Dual Index Logging**: Posts the 3-Tick Index Log and Batch Summary to **both** `PUBLIC_/TESTING_INDEX_CHANNEL_ID` and `PUBLIC_/TESTING_LOGGER_GROUP_ID` (`INDEX_LOG_TOPIC_ID`) from whichever bot is indexing the files.
* `/checkhelpers` (alias: `/helpers`): Audits **both the Main Bot and all configured Helper Bots** across `STORAGE_GROUP_ID`, `POSTING_CHANNEL_ID` (Admin with Post & Delete rights), `INDEX_CHANNEL_ID` (Admin with Post Messages rights), and `LOGGER_GROUP_ID`.
* `/broadcast` & `/cancelbroadcast`: Interactive Broadcast Control Panel with colorful target toggles (`🌐 All`, `👥 Users`, `🤖 Helper Bots`, `👥 Groups`, `📢 Channels`), auto-pinning in chats (`📌 Pin in Chats`), expandable quote preview, and live `⏸ Pause`, `▶️ Resume`, and `🛑 Cancel` controls.
* `/publish`: Exclusive to Creator. Merges the verified `test` branch into `main` and pushes to `loki main` & `origin main`, triggering live Render deployment on Public Books Bot.
* `/update`: Exclusive to Creator. In-chat bot updater. Send or reply to a `.zip` archive to unpack, verify with `compileall`, commit, and auto-push to GitHub without Termux.
* `/sh <command>` (alias: `/term`): Exclusive to Creator. Executes bash shell commands directly inside Telegram.
* `/addadmin`, `/addmoderator`, `/addvolunteer`, `/addpromoter` (and `/remove...` counterparts): Role management commands.
* `/gift <id> <searches> <requests>`: Grants bonus search/request quota allowances to any user.
* `/editscript`: Live administration hub to manage text templates, media URLs, and config variables in `config.db` without restarting.
* `/ban`, `/ban_pm`, `/ban_support`, `/unban`: Granular user and chat access restriction management.
* `/log [count|duration]`: Exports in-memory ring-buffer system logs as a downloadable document directly in Telegram.
* `/ping`: Diagnostic command displaying round-trip API latency and network statistics.

---

## 💾 Timestamped SQLite Persistence & Zero-Unpin Restore (`modules/database/persistence.py`)

* **Timestamped Backup Archives (IST)**:
  * Generates `test_backup_YYYYMMDD-HHMM.zip` on Testing and `public_backup_YYYYMMDD-HHMM.zip` on Public (matching any `test_backup*.zip` / `public_backup*.zip` on restore).
* **Zero-Unpin Restore via Logger Group Description Pointer**:
  * Whenever `backup_now()` uploads or edits the backup in `BACKUP_TOPIC_ID` (`583` on Testing / `4` on Public), it also records `[MM_BACKUP:msg_id=<id>:file=<fname>]` in the Logger Group's description (`setChatDescription`).
  * On startup (`restore_if_fresh()`), if the latest pinned message in the Logger Group is not the backup zip (for example, if other announcements are pinned or the previous backup was deleted before deployment), the bot checks the `[MM_BACKUP:msg_id=<id>:file=<fname>]` pointer automatically—never requiring admins to unpin messages in the Logger Group and never pausing `backup_allowed`.

---

## 📚 Complete Indexing Architecture & 3-Stage Self-Healing Pipeline

```
[ Incoming Media (Helper DM or Channel/Range /index) ]
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
   └─ Post 3-Tick Log to Index Ch + Topic       └─ Post 3-Tick Log (✅, ✅, 🚧)
```

### 8-Website Book & Audiobook Lookup Waterfall (Zero Movies/Anime)
* **Audiobooks Sequence**:
  `1. Audible` (Catalog API `.in`/`.com`/`.co.uk`/`.au`/`.ca`) ➔ `2. Storytel` (`__NEXT_DATA__` + JSON-LD) ➔ `3. Apple Books (Audiobook)` ➔ `4. Goodreads` (`auto_complete` + `/book/show/` Apollo state) ➔ `5. Penguin Random House Audio` ➔ `6. Internet Archive Audio` ➔ `7. Google Books` ➔ `8. OpenLibrary`.
* **Ebooks Sequence**:
  `1. Goodreads` (`auto_complete` + `/book/show/` Apollo state) ➔ `2. Storytel` ➔ `3. Apple Books (Ebook)` ➔ `4. Audible` ➔ `5. Penguin Random House` ➔ `6. Crossref / Internet Archive Texts` ➔ `7. Google Books` ➔ `8. OpenLibrary`.

---

## 🏗️ Dual Main Bot Architecture (Public vs. Testing)

1. **🌐 Public Main Bot (`main` branch)**
   * **Identity**: H D Carlton (`@HDCarltonbot`, ID: `8580921678`)
   * **Helper**: `@RickRiordanBot` (ID: `8768612669`)
   * **Channels & Groups**:
     * Storage Group: `-1004351628501` (`PUBLIC_STORAGE_GROUP_ID`)
     * Posting Channel: `-1003917326986` (`PUBLIC_POSTING_CHANNEL_ID`)
     * Logger Group: `-1003983227434` (`PUBLIC_LOGGER_GROUP_ID`)
     * Index Logs Channel: `-1004413927111` (`PUBLIC_INDEX_CHANNEL_ID`)
     * Request Channel: `-1003904970804` (`PUBLIC_REQUEST_CHANNEL_ID`)
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
     * Index Logs Channel: `-1004343321416` (`TESTING_INDEX_CHANNEL_ID`)
     * Request Channel: `-1004372625503` (`TESTING_REQUEST_CHANNEL_ID`)
     * Support Chat: `-1003689459842` (`TESTING_SUPPORT_CHAT_ID`)
     * Search Topic ID: `579` (`TESTING_SEARCH_TOPIC_ID`)
     * Backup Topic ID: `583` (`TESTING_BACKUP_TOPIC_ID`)
