# 📚 Mastermind Library Bot

A Telegram **library & file-management bot**: it indexes ebooks and audiobooks, enriches them with
Goodreads / Audible / Storytel metadata, lets users search and receive files, takes book requests,
converts ebooks between formats, and gives admins full control from inside Telegram.

* Python 3.11+, [python-telegram-bot](https://python-telegram-bot.org) ≥ 21, SQLite, aiohttp
* Designed for Render's free plan: all data is backed up to Telegram and restored automatically
* Every module has a `help.txt` next to its code explaining what it does

---

## Contents

1. [Features](#features) · 2. [Project layout](#project-layout) · 3. [Quick start](#quick-start)
4. [Configuration](#configuration) · 5. [Commands](#commands) · 6. [Inline buttons](#inline-buttons-callbacks)
7. [How it works](#how-it-works-logic) · 8. [Roles & quotas](#roles--quotas) · 9. [Ebook converter](#ebook-converter)
10. [Persistence](#database--persistence) · 11. [Deploy](#deployment) · 12. [Development](#development)

---

## Features

| Area | What it does |
| :-- | :-- |
| **Search** | `/search`, `/searchebook`, `/searchaudiobook`, or just type in DM; paginated, filterable, "Send All" |
| **Delivery** | Rotating helper bots copy the file to a temporary channel + your DM; channel copy auto-deletes |
| **Indexing** | Upload queue with admin approval, `/index` range scanner, multi-source metadata, progress card |
| **Requests** | Goodreads/Audible matching, manual wizard, moderator status buttons, user notifications |
| **Converter** | `/convert` + inline format buttons; 61 input / 31 output formats via Calibre, Pandoc, PyMuPDF and Anydoc; optional RTL and KFX |
| **Quotas & referrals** | Per-role daily quotas, gifts, invite bonuses |
| **Moderation** | 3 ban types (user or chat), force-subscribe, support quiz, topic-restricted groups |
| **Admin tools** | `/customize` dashboard, live config, template editor, broadcast, logs, Render redeploy |
| **Reliability** | Pinned Telegram backup + auto-restore, single-instance lock, health endpoint for UptimeRobot |

## Project layout

```
main.py                 entry point: env → restore backup → init DBs → register handlers → poll
server.py               tiny HTTP health-check server (PORT) for uptime monitors
config.py               helpers to read env values (env_str/env_int/env_bool/env_list)
lib/mediagoer.py        metadata library (IMDb, Goodreads, Audible, Storytel, ...)
modules/                one folder per feature, each with help.txt  (see modules/help.txt)
  allowance/ ban/ broadcast/ converter/ database/ editscript/ fsub/ help/ id/ indexing/
  log/ message/ request/ roles/ search/ start/ stats/ support/ utility/  bot_manager.py
scripts/push_sync.sh    optional git push helper
tests/                  pytest suite (converter engine + routing, config/secrets, filename parser)
examples/               convert_cli.py (engine without a bot) and a standalone Telethon converter bot
Dockerfile              optional image with Calibre + Pandoc + converter extras (needed by /convert)
requirements-converter.txt  optional converter packages (pymupdf, firecrawl-anydoc)
requirements-telethon.txt   only for modules/converter/telethon_adapter.py
env.example             every setting, documented
```

## Quick start

```bash
git clone <your-fork> && cd mastermind-library-bot
pip install -r requirements.txt
cp env.example env.txt        # fill in TELEGRAM_BOT_TOKEN and ADMIN_IDS at minimum
python main.py
```

1. Create the bot with @BotFather and put the token in `TELEGRAM_BOT_TOKEN`.
2. Put your numeric Telegram ID in `ADMIN_IDS` – that makes you **Owner**.
3. Create the chats (storage, posting, logs, requests, support, backup), add the bot as admin
   and fill the IDs. Send `/id` in a chat to read its ID. After start-up, `/customize` and
   `/setconfig` can change everything live.
4. Optional: add helper bots (`HELPER_BOT_TOKENS`), enable force-subscribe, set topics with `/settopic`.

> 🔐 `env.txt` and `.env` are git-ignored. Never commit tokens. If a token was ever pushed or
> shared, revoke it in @BotFather (and regenerate Render keys).

## Configuration

Value priority (highest first): **edited in Telegram** (`/setconfig`, `/customize`, `/settopic`) →
**environment variable / `env.txt`** → **stored default**. Secrets (anything with `token`,
`api_key`, `hook_url`) are always masked in Telegram.

### Required
| Variable | Description |
| :-- | :-- |
| `TELEGRAM_BOT_TOKEN` | Main bot token |
| `ADMIN_IDS` (or `OWNER_IDS`) | Comma-separated owner user IDs |

### Chats and groups
| Variable | Description |
| :-- | :-- |
| `STORAGE_CHANNEL_ID` | Permanent storage of indexed files |
| `POSTING_CHANNEL_ID` | Temporary delivery channel (files auto-delete) |
| `LOGGER_GROUP_ID` | Forum group that receives logs (aliases: `GENERAL_LOG_GROUP_ID`, `ADMIN_LOG_GROUP_ID`) |
| `REQUEST_CHANNEL_ID` | Where request cards are posted |
| `SUPPORT_CHAT_ID` | Support group (single-use invites) |
| `INDEX_CHANNEL_ID` | Optional index updates channel |
| `BACKUP_CHAT_ID` | Private chat for the pinned DB backup (falls back to `INDEX_CHANNEL_ID`, then `LOGGER_GROUP_ID`) |
| `BACKUP_INTERVAL_SECONDS` | Min seconds between automatic backups (default 300, min 60) |

### Log topics (forum group)
`GENERAL_TOPIC_ID`, `INDEX_LOG_TOPIC_ID`, `GROUP_LOG_TOPIC_ID`, `CHANNEL_LOG_TOPIC_ID`,
`USER_LOG_TOPIC_ID`, `REQUEST_LOG_TOPIC_ID`, `ERROR_LOG_TOPIC_ID`. Easier: run `/settopic index`,
`/settopic user`, … inside each topic.

### Delivery
| Variable | Default | Description |
| :-- | :-- | :-- |
| `HELPER_BOT_TOKENS` | – | Extra bots used round-robin for delivery (usernames auto-detected) |
| `REQUIRE_HELPER_BOT_START` | `true` | User must start a helper bot first |
| `FILE_DELETE_AFTER_SECONDS` | `120` | Lifetime of the posting-channel copy |
| `AUTO_DELETE_ENABLED` | `true` | Enable the auto-delete |

### Throttling, quotas, toggles
| Variable | Default |
| :-- | :-- |
| `MAX_INDEX_BATCH` / `INDEX_SLEEP_SECONDS` | `10` / `10` |
| `SEARCH_QUOTA_DEFAULT` / `REQUEST_QUOTA_DEFAULT` | `10` / `10` (Normal User) |
| `PROMOTER_QUOTA_DEFAULT` / `VOLUNTEER_QUOTA_DEFAULT` / `MODERATOR_QUOTA_DEFAULT` | `20` / `30` / `40` |
| `REFERRAL_BONUS_SEARCH` / `REFERRAL_BONUS_REQUEST` | `10` / `10` |
| `FSUB_ENABLED` | `false` |
| `IS_BROADCAST_ENABLED` | `true` |

### Ebook converter
| Variable | Default | Description |
| :-- | :-- | :-- |
| `CONVERT_ENABLED` | `true` | Master switch |
| `CONVERT_TIMEOUT_SECONDS` | `300` | Per-conversion time limit |
| `CONVERT_MAX_CONCURRENT` | `2` | Parallel conversions on the host |
| `CONVERT_MAX_INPUT_MB` | `20` | Input size cap (Bot API maximum is 20) |
| `CONVERT_KFX_ENABLED` | `false` | Offer KFX in/out (requires Calibre's KFX Input/Output plugins) |

### Optional integrations
`COMMUNITY_URL` (button on start menu / captions), `GITHUB_REPO` (`owner/name`, deploy target
commit), `RENDER_API_KEY`, `RENDER_SERVICE_ID`, `RENDER_DEPLOY_HOOK_URL`, `PORT` (default 8080).

## Commands

### Everyone
| Command | What it does |
| :-- | :-- |
| `/start` | Register, open the main menu. Deep links: `file_<id>` delivers a file, `ref_<id>` claims a referral, `helper_init` activates a helper bot |
| `/help` | Interactive user guide |
| `/search <text>` · `/searchebook <text>` · `/searchaudiobook <text>` | Search the library (all / ebooks / audiobooks). Also works as a reply to a text message |
| `/request <title> [author]` (`/req`) | Request a missing book or audiobook |
| `/convert` | Convert an ebook (reply to a file, or send the command then the file) |
| `/quota` | Your role and remaining daily searches/requests |
| `/refer` (`/ref`) | Your invite link, invite count and bonus earned |
| `/support` | Verification quiz → single-use invite to the support chat |
| `/id` | Your user ID / chat ID (reply to a message for that user's ID) |
| `/ping` | Latency and host network counters |
| `/settopic search` · `/settopic request` | **Group admins:** limit the bot to the current topic |

### Volunteer and above
| Command | What it does |
| :-- | :-- |
| `/index [links…]` | Index a message range of a source chat (wizard or arguments, see below) |

### Moderator (via buttons) · Admin · Owner
| Command | Role | What it does |
| :-- | :-- | :-- |
| *Show Options* buttons on request cards | Moderator+ | Set request status |
| `/adminhelp` (`/ownerhelp`) | Admin+ | Admin guide |
| `/stats` | all | Library statistics |
| `/backup` | Admin+ | Back up the databases now |
| `/log [n]` | Admin+ | Last *n* log lines as a file (default 20, max 1000) |
| `/gift <user_id> <search> [request]` | Admin+ | Add bonus quota |
| `/ban` · `/ban_pm` · `/ban_support` `<id\|@user> [reason]` | Admin+ | Ban everywhere / in PM / except support chat (users or chats; reason required for Admins) |
| `/unban <id\|@user>` | Admin+ | Remove a ban |
| `/addvol` · `/addprom` · `/addmod` `<user>` | Admin+ | Assign Volunteer / Promoter / Moderator |
| `/addadmin <user>` | Owner | Assign Admin |
| `/broadcast <target> <msg>` · `/broadcast_confirm <target> <msg>` | Admin+ | Message everyone or one role (preview + confirm / immediate) |
| `/customize` (`/editscript` `/config` `/showconfig`) | Admin+ | Settings & template dashboard |
| `/setconfig <key> <value>` · `/getconfig [key]` · `/reloadconfig` | Admin+ | Live configuration |
| `/listtemplates` · `/showtemplate <n>` · `/edittext <n> <text>` | Admin+ | Template text |
| `/setmedia <n> <file_id\|url>` · `/removemedia <n>` | Admin+ | Template picture |
| `/addbutton <n> <label> <url\|callback>` · `/removebutton <n> <i>` | Admin+ | Template buttons |
| `/restart` · `/redeploy` | Admin+ | Hot reload, hard restart, Render redeploy |

`/index` forms: `/index` (wizard) · `/index t.me/ch/100-300` · `/index t.me/ch/100 t.me/ch/300` ·
`/index t.me/ch skip 200` · `skip 200-250` · `limit=10` · `--from N --to N`.

## Inline buttons (callbacks)

| Prefix | Module | Purpose |
| :-- | :-- | :-- |
| `help_*`, `adm_sec_*`, `search_menu`, `stats_menu`, `start_menu`, `quota_menu`, `bot_owner` | start/help | Menu navigation |
| `spg\|`, `sendall\|`, `search_cancel`, `noop`, `dl_*`, `file_dl_*` | search | Pages, filters, Send All, download |
| `req_*` | request | Format, match pick, manual wizard, status management |
| `idx_*` | indexing | Progress card control, upload approval, `/index` wizard |
| `cv\|*` | converter | Open converter, choose format, cancel |
| `cust_*`, `es_*` | editscript | Dashboard (admins only) |
| `bcast_*` | broadcast | Confirm / cancel |
| `fsub_*` | fsub | Verify subscription |
| `support_*`, `quiz_ans_*` | support | Verification quiz |

## How it works (logic)

**Update pipeline** – middlewares run first: *ban check* (group -3) → *topic filter* (-2) →
*force-subscribe* (-1). Then commands, callbacks, uploads and text. A middleware stops the update
by raising `ApplicationHandlerStop`.

**Search** – every word must match one of title, author, series, file name, keywords, description
or caption. Max 100 hits, 8 per page, newest first. Mode filters use the extension (`.mp3/.m4b/.aax`)
or `category=audiobook`.

**Delivery** – requires quota (and a started helper bot when `REQUIRE_HELPER_BOT_START`). A
rotating helper bot copies the file from storage to the posting channel and to the user's DM.
Quota is deducted **only after** a successful copy. The channel copy is deleted after
`FILE_DELETE_AFTER_SECONDS` and the deletion is logged.

**Indexing** – accepted types: `.epub .pdf .mobi .azw3 .djvu .cbz .mp3 .m4b .aax`. Duplicates are
detected by Telegram's `file_unique_id`. Volunteers/Admins/Owners are indexed at once (priority
queue); other users' uploads wait for **Approve/Reject** in the index log topic. The queue handles
`MAX_INDEX_BATCH` files then sleeps `INDEX_SLEEP_SECONDS`. Metadata: filename parser → Goodreads /
Storytel / Audible → OceanofPDF, EbookHunter, Anna's Archive, Mobilism (ebooks) or AudioBookBay,
Mobilism (audiobooks); author/series from the file name are kept as fallback. `/index` forwards each
message id of the source range into storage, reads its file, deletes the temporary copy and re-posts
it with a caption + database row (works on the storage chat itself to rebuild a lost database).

**Requests** – format → Goodreads/Audible suggestions (or manual 4-step form) → card in the request
chat (1 request quota consumed only then) → moderators set *Added*, *Already available*, *Not
available*, *Not released*, *Request again* → requester is notified.

**Quotas** – reset daily; searching is free; delivered file = 1 search; posted request = 1 request.
Admin/Owner unlimited; banned = 0. Bonus quota from referrals/gifts survives role changes.

**Bans** – `all` (everywhere), `pm` (private chat), `support` (only the support chat). Chats can be
banned too (the bot leaves). Owner may omit the reason.

**Force-subscribe** – private chats only; normal channels need membership, join-request channels
accept a pending request; admins are exempt.

**Topics** – `/settopic search|request` in a group makes the bot answer only in those topics.

**Config** – see priority order above; `/setconfig` applies immediately.

## Roles & quotas

| Role | Daily search/request | Extra rights |
| :-- | :-- | :-- |
| Banned | 0 | none |
| Normal User | 10 / 10 | uploads need approval |
| Promoter | 20 / 20 | uploads need approval |
| Volunteer | 30 / 30 | direct indexing, `/index` |
| Moderator | 40 / 40 | manage request statuses |
| Admin | unlimited | roles (except Admin), ban, broadcast, config, logs |
| Owner | unlimited | everything, assigns Admin (from `ADMIN_IDS`) |

## Ebook converter

`/convert` → send/reply to a file → tap a format → receive the converted file.

* **Reads 61 formats**, e.g. epub, mobi, azw3, fb2, pdf, docx, doc, rtf, odt, htmlz, cbz, djvu, lit, lrf,
  md, rst, tex, org, typst, xlsx, pptx … (full list: `modules/converter/formats.py::INPUT_FORMATS`)
* **Writes 31 formats**: EPUB, MOBI, AZW3, PDF, DOCX, FB2, RTF, TXT, HTMLZ, TXTZ, MD, HTML, ODT, RST, TeX,
  Typst, AsciiDoc, Org, PPTX, KEPUB, LIT, LRF, PDB, … The buttons only offer what is possible for the input
  *and* installed on the host.
* **Backends**: Calibre `ebook-convert` (most ebook formats) · Pandoc (markup/office formats) ·
  PyMuPDF (PDF text → cleaner conversions, optional) · Anydoc (legacy `.doc/.xls/.ppt/.odp/.ods`, optional) ·
  Calibre KFX plugins (opt-in via `CONVERT_KFX_ENABLED`)
* **Force RTL** button for right-to-left books (EPUB page progression + CSS direction)
* Limits: 20 MB input, ~49 MB output, one conversion per user at a time, `CONVERT_MAX_CONCURRENT`
  globally, `CONVERT_TIMEOUT_SECONDS` per run (the whole process group is killed on timeout)
* Temporary files live in a private temp folder that is always deleted
* **Needs Calibre and/or Pandoc.** Use the provided `Dockerfile` (Render: *Docker* runtime), which installs
  both plus `requirements-converter.txt`. Without them the bot politely says the converter is unavailable
* Use the engine without Telegram: `python examples/convert_cli.py book.epub pdf`. A Telethon front-end
  (`modules/converter/telethon_adapter.py`, `requirements-telethon.txt`) is included for a separate MTProto bot

## Database & persistence

| File | Tables |
| :-- | :-- |
| `database/files.db` | `indexed_files`, `indexing_queue`, `requests_queue`, `delivery_logs` |
| `mastermind_users.db` | `users`, `quotas`, `referrals`, `bans` |
| `database/config.db` | `config`, `templates`, `fsub_channels`, `fsub_requests`, `group_topics` |

Render's free plan wipes the disk on each deploy, so the bot keeps a **zipped consistent snapshot**
(`mastermind_backup.zip`) in the backup chat as one pinned message (edited in place):
automatically every few minutes when data changed, on shutdown/redeploy, before `/restart` /
`/redeploy`, and on demand with `/backup`. On a fresh container the pinned backup is downloaded and
integrity-checked **before any module loads**. If a restore fails, backups pause so a good backup is
never overwritten by an empty database. Never delete or unpin the backup message. To rebuild only the
library after data loss run `/index t.me/c/<storage id>/<first>-<last>` on the storage chat.

## Deployment

**Render (free, Python runtime)** – connect the repo; `render.yaml` defines build/start commands.
Add the environment variables from `env.example`. Everything works except `/convert` (no Calibre/Pandoc there).
**Render with converter** – create the service with the *Docker* runtime (uses `Dockerfile`).
**Keep-alive** – point UptimeRobot (HTTP, 5 min) at `https://<service>.onrender.com`; the built-in
server answers `Mastermind Bot is alive and running!`.

## Development

```bash
pip install -r requirements-dev.txt
pytest
```

* Each feature lives in `modules/<name>/`; read its `help.txt` first.
* New command: add the handler function, register it in `main.py::register_handlers`, document it in the
  module's `help.txt` and in this README.
* Secrets belong in the environment only (`SECRET_KEY_HINTS` in `config_db.py` decides what is masked).
