import logging
from collections import deque
from datetime import datetime, timezone, timedelta

# In-memory buffer holding up to 3000 log records
LOG_BUFFER = deque(maxlen=3000)
IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_now() -> datetime:
    return datetime.now(IST)

def get_ist_str(fmt: str = "%Y-%m-%d %H:%M:%S IST") -> str:
    return get_ist_now().strftime(fmt)

def ist_converter(*args):
    return get_ist_now().timetuple()

logging.Formatter.converter = ist_converter

class InMemoryLogHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            timestamp = get_ist_str("%Y-%m-%d %H:%M:%S IST")
            LOG_BUFFER.append((get_ist_now(), f"[{timestamp}] {msg}\n"))
        except Exception:
            self.handleError(record)

def setup_in_memory_logger():
    root = logging.getLogger()
    if not any(isinstance(h, InMemoryLogHandler) for h in root.handlers):
        h = InMemoryLogHandler()
        fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s", datefmt="%Y-%m-%d %H:%M:%S IST")
        h.setFormatter(fmt)
        root.addHandler(h)

def get_logs_by_count(n: int = 50) -> str:
    if not LOG_BUFFER:
        return f"[{get_ist_str()}] No logs captured in memory."
    lines = [item[1] for item in LOG_BUFFER]
    return "".join(lines[-n:] if len(lines) >= n else lines)

def get_logs_by_time(minutes: int = 30) -> str:
    if not LOG_BUFFER:
        return f"[{get_ist_str()}] No logs captured in memory."
    cutoff = get_ist_now() - timedelta(minutes=minutes)
    lines = [item[1] for item in LOG_BUFFER if item[0] >= cutoff]
    return "".join(lines) if lines else f"[{get_ist_str()}] No logs within last {minutes}m."
