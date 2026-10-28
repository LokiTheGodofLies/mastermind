"""Live progress reporter: turns converter output into a throttled, self-updating Telegram message."""
from __future__ import annotations

import asyncio
from collections import deque
from contextlib import suppress
import html
import re
import time

from telegram.error import BadRequest, RetryAfter, TelegramError

from modules.converter.engine import ProgressSink

PERCENT_RE = re.compile(r"^\s*(\d{1,3})%\s+(.*)$")
VISIBLE_LINES = 8          # log lines shown in the message
MAX_LINE_CHARS = 90        # keep lines phone-width
UPDATE_INTERVAL = 3.0      # seconds between edits (Telegram flood-limit friendly)
QUIET_AFTER = 20           # seconds of silence before showing a "still working" hint


def _mb(value: int | None) -> str:
    return "?" if value is None else f"{value / 1048576:.0f} MB"


def _bar(percent: int | None, width: int = 10) -> str:
    if percent is None:
        return "▱" * width
    filled = max(0, min(width, round(percent / 100 * width)))
    return "▰" * filled + "▱" * (width - filled)


class TelegramProgress(ProgressSink):
    """Collects engine events and edits ``message`` every few seconds while ``async with`` is active."""

    def __init__(self, message, *, title: str, file_name: str) -> None:
        self.message = message
        self.title = title
        self.file_name = file_name
        self.started_at = time.monotonic()
        self.last_event = self.started_at
        self.percent: int | None = None
        self.stage_text = "Starting…"
        self.tool = ""
        self.recent: deque[str] = deque(maxlen=VISIBLE_LINES)
        self.mem: tuple[int | None, int | None, int | None] = (None, None, None)
        self.peak_rss = 0
        self._last_text = ""
        self._task: asyncio.Task | None = None
        self._backoff_until = 0.0

    # ---- ProgressSink events (called from the engine, must be cheap)
    def stage(self, text: str) -> None:
        self.stage_text = text
        self.last_event = time.monotonic()

    def started(self, pid: int, tool: str) -> None:
        self.tool = tool
        self.last_event = time.monotonic()

    def line(self, text: str) -> None:
        self.last_event = time.monotonic()
        if match := PERCENT_RE.match(text):
            self.percent = min(100, int(match.group(1)))
            text = match.group(2)
            self.stage_text = text
        self.recent.append(text if len(text) <= MAX_LINE_CHARS else text[: MAX_LINE_CHARS - 1] + "…")

    def stats(self, proc_rss: int | None, cg_used: int | None, cg_limit: int | None) -> None:
        self.mem = (proc_rss, cg_used, cg_limit)
        if proc_rss:
            self.peak_rss = max(self.peak_rss, proc_rss)

    # ---- rendering
    def render(self) -> str:
        now = time.monotonic()
        elapsed = int(now - self.started_at)
        head = (
            f"⏳ <b>{html.escape(self.title)}</b>\n"
            f"📘 <code>{html.escape(self.file_name)}</code>\n\n"
            f"{_bar(self.percent)} {'' if self.percent is None else f'{self.percent}%'}\n"
            f"🔧 {html.escape(self.stage_text)}\n"
            f"⏱ {elapsed // 60}:{elapsed % 60:02d}"
        )
        rss, used, limit = self.mem
        if rss is not None or used is not None:
            head += f" · 🧠 {_mb(rss)}"
            if used is not None and limit:
                head += f" · container {_mb(used)}/{_mb(limit)}"
        idle = int(now - self.last_event)
        if idle >= QUIET_AFTER:
            head += f"\n💤 No output for {idle}s — {html.escape(self.tool or 'converter')} is still working (PDF rendering is quiet)."
        if self.recent:
            log = "\n".join(self.recent)
            head += f"\n\n<pre>{html.escape(log)}</pre>"
        return head

    async def _push(self, force: bool = False) -> None:
        text = self.render()
        if text == self._last_text or time.monotonic() < self._backoff_until:
            return
        try:
            await self.message.edit_text(text, parse_mode="HTML")
            self._last_text = text
        except RetryAfter as exc:  # flood control: back off instead of hammering
            self._backoff_until = time.monotonic() + float(exc.retry_after) + 1
        except BadRequest:
            pass  # "message is not modified" etc.
        except TelegramError:
            pass  # a failed progress edit must never break the conversion

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(UPDATE_INTERVAL)
            await self._push()

    async def __aenter__(self) -> "TelegramProgress":
        self._task = asyncio.create_task(self._loop())
        return self

    async def __aexit__(self, *exc) -> None:
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    def failure_log(self) -> str:
        return "\n".join(self.recent)
