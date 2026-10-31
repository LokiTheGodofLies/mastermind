"""Persistent storage for Render's ephemeral disk using Telegram.

  * BACKUP  - periodically (when any DB file changes) and on shutdown, a
              consistent SQLite snapshot of all three databases is zipped with an
              IST timestamp (`test_backup_YYYYMMDD-HHMM.zip` or `public_backup_YYYYMMDD-HHMM.zip`),
              uploaded/edited in the Backup Logs topic of the logger group, kept pinned,
              and its message_id is recorded in the Logger Group description tag
              `[MM_BACKUP:msg_id=<id>:file=<fname>]`.
  * RESTORE - on a fresh container (no local marker file) the latest backup is
              located (either from the latest pinned message OR from the Logger Group
              description tag `[MM_BACKUP:msg_id=<id>:file=<fname>]` so other pinned
              messages in the logger group never need to be unpinned), verified with
              `PRAGMA integrity_check`, and placed on disk. If the previous backup was
              deleted before deployment, the bot starts fresh with `backup_allowed=True`.
"""
import asyncio
import io
import json
import logging
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timedelta, timezone

import requests

from config import (
    bot_token,
    backup_chat_id,
    backup_topic_id,
    backup_interval_seconds,
    backup_filename,
    is_valid_backup_filename,
    db_dir,
    config_db_path,
    files_db_path,
    users_db_path,
    max_upload_bytes,
    max_download_bytes,
)

logger = logging.getLogger(__name__)

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

_BACKUP_TAG_RE = re.compile(r"\[MM_BACKUP:msg_id=(\d+)(?::file=([^\]]+))?\]")


def _db_files() -> dict:
    return {
        "config.db": os.path.abspath(config_db_path()),
        "files.db": os.path.abspath(files_db_path()),
        "mastermind_users.db": os.path.abspath(users_db_path()),
    }


def _marker_path() -> str:
    return os.path.abspath(os.path.join(db_dir(), ".seeded"))


_lock = threading.Lock()
_state = {
    "restore": "not_run",  # not_run | skipped | restored | no_backup | failed | disabled
    "restore_detail": "",
    "backup_allowed": True,
    "backup_msg_id": None,
    "backup_chat": None,
    "last_backup_ts": 0.0,
    "last_backup_detail": "never",
    "last_error": "",
    "pin_ok": True,
    "fingerprint": None,
}


def _token() -> str:
    return (bot_token() or "").strip()


def _backup_chat() -> str:
    cid = backup_chat_id()
    return str(cid) if cid is not None else ""


def _backup_topic() -> str:
    tid = backup_topic_id()
    return str(tid) if tid is not None else ""


def _api(method: str, **kw):
    url = f"https://api.telegram.org/bot{_token()}/{method}"
    timeout = kw.pop("timeout", 30)
    r = requests.post(url, timeout=timeout, **kw)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "description": f"HTTP {r.status_code}: {r.text[:120]}"}


_TOKEN_RE = re.compile(r"bot\d+:[A-Za-z0-9_-]+")


def _redact(text: str) -> str:
    """Strip bot tokens (e.g. from requests URLs inside exception text)."""
    return _TOKEN_RE.sub("bot<redacted>", text or "")


def _ist_now() -> str:
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).strftime("%d-%m-%Y %I:%M:%S %p IST")


def _count(path: str, table: str) -> int:
    if not path or not os.path.exists(path):
        return 0
    try:
        conn = sqlite3.connect(path, timeout=10)
        try:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        finally:
            conn.close()
    except Exception:
        return 0


def _stats_from_paths(paths: dict) -> dict:
    cfg_path = paths.get("config.db", "")
    cfg_count = _count(cfg_path, "config")
    if cfg_count == 0:
        cfg_count = _count(cfg_path, "templates")
    return {
        "files": _count(paths.get("files.db", ""), "indexed_files"),
        "users": _count(paths.get("mastermind_users.db", ""), "users"),
        "templates": cfg_count,
    }


def _stats_line(st: dict) -> str:
    return f"📚 files: {st['files']} | 👥 users: {st['users']} | 🧩 templates: {st['templates']}"


def _integrity_ok(path: str) -> bool:
    try:
        conn = sqlite3.connect(path, timeout=10)
        try:
            return conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            conn.close()
    except Exception:
        return False


def _fingerprint():
    parts = []
    for p in _db_files().values():
        for suffix in ("", "-wal"):
            try:
                s = os.stat(p + suffix)
                parts.append((p + suffix, s.st_mtime_ns, s.st_size))
            except OSError:
                parts.append((p + suffix, 0, 0))
    return tuple(parts)


def _save_backup_pointer_in_chat_description(chat: str, msg_id: int, fname: str) -> None:
    """Stores `[MM_BACKUP:msg_id=<id>:file=<fname>]` in the Logger Group description so
    future deploys can locate the latest timestamped backup even if other messages are pinned."""
    try:
        info = _api("getChat", data={"chat_id": chat}, timeout=15)
        old_desc = ((info.get("result") or {}).get("description") or "").strip()
        cleaned_desc = _BACKUP_TAG_RE.sub("", old_desc).strip()
        tag = f"[MM_BACKUP:msg_id={msg_id}:file={fname}]"
        new_desc = f"{cleaned_desc}\n{tag}".strip() if cleaned_desc else tag
        if len(new_desc) > 255:
            new_desc = tag[:255]
        _api("setChatDescription", data={"chat_id": chat, "description": new_desc}, timeout=15)
    except Exception as exc:
        logger.debug("Could not update logger group backup pointer tag: %s", _redact(str(exc)))


def _probe_backup_message_by_id(chat: str, msg_id: int) -> dict | None:
    """Probes `msg_id` in `chat` by forwarding it silently into the backup topic and immediately
    deleting the temporary forward, returning `(doc_dict, msg_id)` if `msg_id` exists and is a valid backup."""
    try:
        fwd_data = {
            "chat_id": chat,
            "from_chat_id": chat,
            "message_id": int(msg_id),
            "disable_notification": "true",
        }
        topic = _backup_topic()
        if topic:
            fwd_data["message_thread_id"] = topic
        res = _api("forwardMessage", data=fwd_data, timeout=20)
        if not res.get("ok"):
            return None
        msg_obj = res.get("result") or {}
        temp_mid = msg_obj.get("message_id")
        if temp_mid:
            _api("deleteMessage", data={"chat_id": chat, "message_id": temp_mid}, timeout=10)
        doc = msg_obj.get("document") or {}
        if doc and is_valid_backup_filename(doc.get("file_name")):
            return doc
    except Exception as exc:
        logger.debug("Probe of backup message %s failed: %s", msg_id, _redact(str(exc)))
    return None


def sync_startup_log():
    """Updates modules.log.startup_log.DB_STATUS and DB_STATUS_OK from _state."""
    try:
        from modules.log import startup_log
        r = _state["restore"]
        d = _state["restore_detail"]
        if r == "restored":
            startup_log.DB_STATUS = f"restored from Telegram backup ({d})" if d else "restored from Telegram backup"
            startup_log.DB_STATUS_OK = True
        elif r == "skipped":
            startup_log.DB_STATUS = "local databases in use"
            startup_log.DB_STATUS_OK = True
        elif r == "no_backup":
            startup_log.DB_STATUS = "initialized (no backup found — auto-backup active)"
            startup_log.DB_STATUS_OK = True
        elif r == "failed":
            startup_log.DB_STATUS = f"restore FAILED: {d}"
            startup_log.DB_STATUS_OK = False
        elif r == "disabled":
            startup_log.DB_STATUS = f"backup disabled ({d})"
            startup_log.DB_STATUS_OK = False
    except Exception as exc:
        logger.debug("Could not sync startup_log status: %s", exc)


def restore_if_fresh() -> dict:
    """Restores databases from the latest timestamped backup in the logger group on a fresh container.
    Never requires unpinning other messages in the logger group."""
    with _lock:
        os.makedirs(db_dir(), exist_ok=True)
        marker = _marker_path()

        if os.path.exists(marker):
            _state.update(restore="skipped", restore_detail="local databases already present")
            sync_startup_log()
            return dict(_state)

        token, chat = _token(), _backup_chat()
        if not token or not chat or not _backup_topic():
            _state.update(
                restore="disabled",
                restore_detail="no bot token, PUBLIC_/TESTING_LOGGER_GROUP_ID or PUBLIC_/TESTING_BACKUP_TOPIC_ID configured",
                backup_allowed=False,
            )
            sync_startup_log()
            return dict(_state)
        _state["backup_chat"] = chat

        try:
            info = _api("getChat", data={"chat_id": chat}, timeout=20)
            if not info.get("ok"):
                raise RuntimeError(f"getChat failed: {info.get('description')}")

            chat_res = info.get("result") or {}
            pinned = chat_res.get("pinned_message") or {}
            doc = pinned.get("document") or {}
            resolved_msg_id = pinned.get("message_id")

            # 1. Check if the latest pinned message is a valid backup zip (timestamped or legacy)
            if not (doc and is_valid_backup_filename(doc.get("file_name"))):
                doc = {}
                resolved_msg_id = None

                # 2. Check the Logger Group description for `[MM_BACKUP:msg_id=<id>:file=<fname>]`
                desc = chat_res.get("description") or ""
                m_tag = _BACKUP_TAG_RE.search(desc)
                if m_tag:
                    tagged_mid = int(m_tag.group(1))
                    probed_doc = _probe_backup_message_by_id(chat, tagged_mid)
                    if probed_doc:
                        doc = probed_doc
                        resolved_msg_id = tagged_mid

            # 3. If no valid backup exists (e.g. previous backup was deleted or another message is pinned),
            # start fresh with auto-backup ACTIVE (never require unpinning other messages in the logger group).
            if not doc:
                _state.update(
                    restore="no_backup",
                    restore_detail="no active backup found in logger group - starting with fresh databases (auto-backup active)",
                    backup_allowed=True,
                )
                with open(marker, "w", encoding="utf-8") as mf:
                    mf.write(str(time.time()))
                sync_startup_log()
                return dict(_state)

            fi = _api("getFile", data={"file_id": doc["file_id"]}, timeout=20)
            if not fi.get("ok"):
                raise RuntimeError(f"getFile failed: {fi.get('description')}")
            fpath = fi["result"]["file_path"]
            r = requests.get(f"https://api.telegram.org/file/bot{token}/{fpath}", timeout=120)
            r.raise_for_status()
            blob = r.content
            if len(blob) > max_download_bytes() + 1024:
                raise RuntimeError("backup is larger than the bot download limit")

            db_map = _db_files()
            tmp = tempfile.mkdtemp(prefix="mm_restore_")
            try:
                with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                    names = set(zf.namelist())
                    extracted = {}
                    for name in db_map:
                        if name in names:
                            zf.extract(name, tmp)
                            extracted[name] = os.path.join(tmp, name)
                if not extracted:
                    raise RuntimeError("backup archive contains no database files")
                for name, p in extracted.items():
                    if not _integrity_ok(p):
                        raise RuntimeError(f"{name} in backup failed integrity check")

                for name, src in extracted.items():
                    dst = db_map[name]
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    for suffix in ("", "-wal", "-shm", "-journal"):
                        try:
                            os.remove(dst + suffix)
                        except OSError:
                            pass
                    shutil.move(src, dst)
                st = _stats_from_paths(db_map)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

            with open(marker, "w", encoding="utf-8") as mf:
                mf.write(str(time.time()))
            restored_fname = doc.get("file_name") or "backup.zip"
            _state.update(
                restore="restored",
                restore_detail=f"{restored_fname} — {_stats_line(st)}",
                backup_msg_id=resolved_msg_id,
                backup_allowed=True,
                fingerprint=_fingerprint(),
            )
            logger.info("Databases restored from Telegram backup (%s): %s", restored_fname, _stats_line(st))
        except Exception as exc:
            _state.update(
                restore="failed",
                restore_detail=_redact(str(exc))[:200],
                backup_allowed=True,
                last_error=_redact(str(exc))[:200],
            )
            logger.error("Database restore FAILED: %s", _redact(str(exc)))

        sync_startup_log()
        return dict(_state)


def _build_archive() -> tuple:
    """Consistent snapshot of every DB (sqlite online-backup API) -> (zip bytes, stats)."""
    tmp = tempfile.mkdtemp(prefix="mm_backup_")
    try:
        snap = {}
        for name, path in _db_files().items():
            if not os.path.exists(path):
                continue
            out = os.path.join(tmp, name)
            src = sqlite3.connect(path, timeout=30)
            dst = sqlite3.connect(out)
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
            snap[name] = out
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for name, p in snap.items():
                zf.write(p, name)
        return buf.getvalue(), _stats_from_paths(snap)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def backup_now(reason: str = "periodic") -> tuple:
    """Upload a fresh timestamped backup. Blocking - call with asyncio.to_thread() from async code."""
    with _lock:
        if not _state["backup_allowed"]:
            return False, f"backups are paused ({_state['restore_detail'] or 'restore did not complete'})"
        token = _token()
        chat = _state["backup_chat"] or _backup_chat()
        if not token or not chat or not _backup_topic():
            return False, "no backup topic configured (set PUBLIC_/TESTING_LOGGER_GROUP_ID and PUBLIC_/TESTING_BACKUP_TOPIC_ID)"
        _state["backup_chat"] = chat

        try:
            blob, st = _build_archive()
            if len(blob) > min(max_upload_bytes(), max_download_bytes()):
                raise RuntimeError(f"backup is {len(blob)/1048576:.1f} MB (exceeds upload limit)")
            fname = backup_filename(with_timestamp=True)
            caption = (
                "💾 Mastermind database backup\n"
                f"📦 {fname}\n"
                f"🕒 {_ist_now()} ({reason})\n"
                f"{_stats_line(st)}\n"
                "⚠️ Latest timestamped backup — used automatically on redeploy."
            )

            if _state["backup_msg_id"]:
                media = json.dumps({"type": "document", "media": "attach://backup", "caption": caption})
                res = _api(
                    "editMessageMedia",
                    data={"chat_id": chat, "message_id": _state["backup_msg_id"], "media": media},
                    files={"backup": (fname, blob, "application/zip")},
                    timeout=90,
                )
                if res.get("ok") or "not modified" in str(res.get("description", "")).lower():
                    _save_backup_pointer_in_chat_description(chat, int(_state["backup_msg_id"]), fname)
                    _state.update(
                        last_backup_ts=time.time(),
                        last_backup_detail=f"{fname} | {_stats_line(st)} ({len(blob)/1024:.0f} KB)",
                        fingerprint=_fingerprint(),
                    )
                    return True, _state["last_backup_detail"]
                logger.warning("editMessageMedia failed (%s) - posting a new backup message", res.get("description"))
                _state["backup_msg_id"] = None

            res = _api(
                "sendDocument",
                data={"chat_id": chat, "message_thread_id": _backup_topic(), "caption": caption, "disable_notification": "true"},
                files={"document": (fname, blob, "application/zip")},
                timeout=90,
            )
            if not res.get("ok"):
                raise RuntimeError(f"sendDocument failed: {res.get('description')}")
            mid = res["result"]["message_id"]
            _state["backup_msg_id"] = mid
            _save_backup_pointer_in_chat_description(chat, int(mid), fname)

            pin = _api("pinChatMessage", data={"chat_id": chat, "message_id": mid, "disable_notification": "true"}, timeout=20)
            _state["pin_ok"] = bool(pin.get("ok"))
            if not pin.get("ok"):
                _state["last_error"] = f"pin failed: {pin.get('description')}"
                logger.error("Could not pin backup message: %s", pin.get("description"))

            _state.update(
                last_backup_ts=time.time(),
                last_backup_detail=f"{fname} | {_stats_line(st)} ({len(blob)/1024:.0f} KB)",
                fingerprint=_fingerprint(),
            )
            if not _state["pin_ok"]:
                return True, _state["last_backup_detail"] + " - ⚠️ pin failed, give the bot 'Pin messages' rights in the logger group"
            return True, _state["last_backup_detail"]
        except Exception as exc:
            _state["last_error"] = _redact(str(exc))[:200]
            logger.error("Backup failed: %s", _redact(str(exc)))
            return False, _redact(str(exc))[:200]


def has_changed() -> bool:
    return _fingerprint() != _state.get("fingerprint")


async def backup_loop():
    """Background task: back up whenever data changed, at most once per interval."""
    interval = backup_interval_seconds()
    await asyncio.sleep(20)
    while True:
        try:
            if _state["backup_allowed"] and (_state["last_backup_ts"] == 0 or has_changed()):
                await asyncio.to_thread(backup_now, "auto")
        except Exception as exc:
            logger.error("backup_loop error: %s", _redact(str(exc)))
        await asyncio.sleep(interval)


def final_backup():
    """Blocking final snapshot for the shutdown hook."""
    if _state["backup_allowed"] and has_changed():
        return backup_now("shutdown")
    return True, "no changes since last backup"


def get_status() -> dict:
    return dict(_state)
