# 🤖 Mastermind Library & Audiobook Telegram Bot

A modular Telegram bot for book and audiobook indexing, search with dual delivery (channel + DM), Goodreads & Audible metadata enrichment, topic-filtered book groups, multi-helper bot rotation, and dynamic in-bot configuration.

---

## 🚀 1-Click Deploy to Render

[[https://render.com/images/deploy-to-render-button.svg]](https://render.com/deploy)

---

## ⚙️ Environment Variables Reference (`env.txt` / Render)

### 1. Primary Bot & Ownership
| Variable | Example Value | Description |
| :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ` | Main Bot token from @BotFather (Required) |
| `ADMIN_IDS` | `7261537212,123456789` | Comma-separated Telegram User IDs of Bot Owners/Admins |

### 2. Channels & Groups
| Variable | Example Value | Description |
| :--- | :--- | :--- |
| `STORAGE_CHANNEL_ID` | `-1003511375054` | Master storage channel/group where indexed files reside |
| `POSTING_CHANNEL_ID` | `-1003936877675` | Temporary channel where files are posted for 2-minute access |
| `LOGGER_GROUP_ID` | `-1003936877675` | Multi-topic log group where system logs are routed |
| `REQUEST_CHANNEL_ID` | `-1004447576324` | Dedicated channel where book requests are forwarded |
| `INDEX_CHANNEL_ID` | `-1001234567890` | (Optional) Dedicated channel for file indexing updates |
| `SUPPORT_CHAT_ID` | `-1004496093454` | Support group for appeals and user inquiries |
| `BACKUP_CHAT_ID` | `-1004343321416` | (Recommended) Private chat/channel where the bot keeps its pinned database backup. Falls back to `INDEX_CHANNEL_ID`, then `LOGGER_GROUP_ID`. Bot needs post + pin rights |
| `BACKUP_INTERVAL_SECONDS` | `300` | (Optional) Minimum seconds between automatic backups (only runs if data changed) |

### 3. Log Group Forum Topics
| Variable | Example Value | Description |
| :--- | :--- | :--- |
| `GENERAL_TOPIC_ID` | `1` | Topic ID 1 for general bot restart and status logs |
| `INDEX_LOG_TOPIC_ID` | `18` | Topic ID for file indexing and upload approvals |
| `GROUP_LOG_TOPIC_ID` | `5` | Topic ID for group membership and admin events |
| `CHANNEL_LOG_TOPIC_ID` | `8` | Topic ID for channel post events and deletion logs |
| `USER_LOG_TOPIC_ID` | `11` | Topic ID for user registrations and role changes |
| `REQUEST_LOG_TOPIC_ID` | `0` | (Optional) Topic ID for book request queue (if no channel) |
| `ERROR_LOG_TOPIC_ID` | `0` | Topic ID for startup configuration and runtime error alerts |

### 4. Multi-Helper Bot Pool & Delivery Settings
| Variable | Example Value | Description |
| :--- | :--- | :--- |
| `HELPER_BOT_TOKENS` | `token1:AAA,token2:BBB` | Comma-separated Helper Bot tokens (usernames auto-fetched via API) |
| `REQUIRE_HELPER_BOT_START` | `true` | Requires user to start a helper bot before receiving files |
| `FILE_DELETE_AFTER_SECONDS` | `120` | Auto-delete timer (in seconds) for temporary posting channel posts |
| `AUTO_DELETE_ENABLED` | `true` | Whether temporary posted files auto-delete after the timer |

### 5. Throttling, Quotas & Role Defaults
| Variable | Example Value | Description |
| :--- | :--- | :--- |
| `MAX_INDEX_BATCH` | `10` | Max files processed per indexing batch cycle |
| `INDEX_SLEEP_SECONDS` | `10` | Cooldown sleep time (seconds) after every 10-file batch |
| `SEARCH_QUOTA_DEFAULT` | `10` | Daily search quota for Normal Users |
| `REQUEST_QUOTA_DEFAULT` | `10` | Daily request quota for Normal Users |
| `PROMOTER_QUOTA_DEFAULT` | `20` | Daily quota for Promoters |
| `VOLUNTEER_QUOTA_DEFAULT` | `30` | Daily quota for Volunteers (direct indexing allowed) |
| `MODERATOR_QUOTA_DEFAULT` | `40` | Daily quota for Moderators (request management allowed) |
| `REFERRAL_BONUS_SEARCH` | `10` | Search quota bonus awarded to both inviter and invitee |
| `REFERRAL_BONUS_REQUEST` | `10` | Request quota bonus awarded to both inviter and invitee |
| `FSUB_ENABLED` | `false` | Global toggle for Force Subscribe (`true` or `false`) |
| `IS_BROADCAST_ENABLED` | `true` | Global toggle for admin broadcasting |

### 6. Web Server & Deployment
| Variable | Example Value | Description |
| :--- | :--- | :--- |
| `PORT` | `8080` | HTTP port for the Render health-check server |
| `PYTHON_VERSION` | `3.11.9` | Python runtime version for Render |

---

## 💾 Database persistence on Render (free plan)

Render's free plan wipes the local disk on every deploy. The bot therefore keeps **all** its SQLite databases
(`files.db` indexed books, `mastermind_users.db` users/roles/quotas/bans, `config.db` customize settings, topics and force-sub channels)
safe inside Telegram:

* **Backup** – a zipped, consistent snapshot is uploaded to the backup chat as `mastermind_backup.zip` (one pinned message, edited in place)
  every few minutes when something changed, on shutdown/redeploy, before `/restart` / `/redeploy`, and on demand with `/backup`.
* **Restore** – on a fresh container the pinned backup is downloaded and verified **before any module loads**.
* **Safety** – if a restore fails (e.g. Telegram unreachable) automatic backups pause so a good backup is never overwritten by an empty database.
  The startup log shows the database status line.
* Never delete or unpin the backup message. One extra message is kept per deploy as history.

## 📚 Re-indexing

`/index` now saves every file it finds into the search database (previously files were only copied to storage). To rebuild
after a data loss run `/index t.me/c/<storage id>/<first>-<last>` on the Storage group itself.

---

## ⏱️ 24/7 Keep-Alive with UptimeRobot (Free)

1. Create a free account at [UptimeRobot](https://uptimerobot.com).
2. Click **+ Add New Monitor**.
3. Choose **Monitor Type:** `HTTP(s)`.
4. Set **URL:** `https://your-service-name.onrender.com`.
5. Set **Monitoring Interval:** `5 minutes`.
6. Click **Create Monitor** — UptimeRobot will ping the built-in health check endpoint to prevent Render from sleeping!
