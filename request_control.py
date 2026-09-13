"""Persisted pacing for Discover requests across pages, batches and process restarts."""
from contextlib import closing
from email.utils import parsedate_to_datetime
import math
from pathlib import Path
import random
import sqlite3
import time

GATE_PATH = Path(__file__).resolve().parent / ".collection" / "request_gate.sqlite3"


class CooldownActive(RuntimeError):
    def __init__(self, until, now, reason="server_retry_after"):
        kind = "challenge_cooldown_active" if reason == "cloudflare_challenge" else "retry_after_active"
        super().__init__(kind)
        self.details = {
            "kind": kind,
            "retry_at": until,
            "wait_seconds": math.ceil(until - now),
            "cooldown_reason": reason,
        }


def parse_retry_after(value, now=None):
    if not isinstance(value, str) or not value.strip():
        return None
    now = time.time() if now is None else now
    value = value.strip()
    try:
        seconds = int(value) if value.isdigit() else parsedate_to_datetime(value).timestamp() - now
        return max(0, float(seconds)) if math.isfinite(seconds) else None
    except (ValueError, TypeError, OverflowError):
        return None


class RequestGate:
    def __init__(self, delay_min, delay_max, progress=print, path=None):
        self.low, self.high = float(delay_min), float(delay_max)
        if not all(math.isfinite(x) for x in (self.low, self.high)) or self.low < 0 or self.high < self.low:
            raise ValueError("Invalid request interval")
        self.path = Path(path) if path is not None else GATE_PATH
        self.progress = progress

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("CREATE TABLE IF NOT EXISTS gate (id INTEGER PRIMARY KEY, last_start REAL NOT NULL, blocked_until REAL NOT NULL, blocked_reason TEXT NOT NULL DEFAULT '')")
        columns = {row[1] for row in db.execute("PRAGMA table_info(gate)")}
        if "blocked_reason" not in columns:
            db.execute("ALTER TABLE gate ADD COLUMN blocked_reason TEXT NOT NULL DEFAULT ''")
        db.execute("INSERT OR IGNORE INTO gate (id, last_start, blocked_until, blocked_reason) VALUES (1, 0, 0, '')")
        db.commit()
        return db

    def before_request(self):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            last, blocked, reason = db.execute("SELECT last_start, blocked_until, blocked_reason FROM gate WHERE id=1").fetchone()
            now = time.time()
            if blocked > now:
                raise CooldownActive(blocked, now, reason)
            ready = max(now, last + random.uniform(self.low, self.high))
            db.execute("UPDATE gate SET last_start=? WHERE id=1", (ready,))
        if ready > now:
            self.progress(f"REQUEST_WAIT seconds={math.ceil(ready-now)} 跨页、跨批次及重新点击运行均遵守请求间隔")
        while ready > time.time():
            time.sleep(max(0, min(30, ready - time.time())))
        # A different process may have received Retry-After while this request waited.
        with closing(self.connect()) as db:
            blocked, reason = db.execute("SELECT blocked_until, blocked_reason FROM gate WHERE id=1").fetchone()
        if blocked > time.time():
            raise CooldownActive(blocked, time.time(), reason)

    def defer(self, seconds, reason="server_retry_after"):
        until = time.time() + seconds
        with closing(self.connect()) as db, db:
            current = db.execute("SELECT blocked_until FROM gate WHERE id=1").fetchone()[0]
            if until >= current:
                db.execute("UPDATE gate SET blocked_until=?, blocked_reason=? WHERE id=1", (until, reason))
                return until
            return current
