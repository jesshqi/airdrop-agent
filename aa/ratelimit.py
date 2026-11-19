"""Per-identity rate limiting and humane pacing.

Windows are persisted in SQLite so a restart does not reset the budget. Every
platform call goes through `acquire()` which sleeps a jittered amount instead of
firing bursts.
"""
from __future__ import annotations

import datetime as dt
import random
import time

from . import config, db
from .jsonio import Denied

DEFAULT_WINDOWS = {"follow": (40, 3600), "chat": (60, 3600), "message": (60, 3600),
                   "join": (15, 3600), "tg_action": (30, 3600), "x_read": (200, 86400),
                   "quest": (12, 3600), "tx": (20, 3600), "login": (6, 3600)}
JITTER = {"telegram": (1.5, 5.0), "x": (2.0, 8.0), "discord": (1.0, 4.0), "web": (0.5, 2.0)}


def windows() -> dict:
    return {**DEFAULT_WINDOWS, **(config.load_yaml("autopilot.yaml").get("rate_windows") or {})}


def used(identity_id: str, action: str) -> int:
    return int(db.scalar("SELECT COUNT(*) FROM kv WHERE key LIKE ?", (f"rl:{identity_id}:{action}:%",), 0) or 0)


def _gc(identity_id: str, action: str, window: int) -> None:
    cutoff = time.time() - window
    db.execute("DELETE FROM kv WHERE key LIKE ? AND CAST(value AS REAL) < ?",
               (f"rl:{identity_id}:{action}:%", cutoff))


def acquire(identity_id: str, action: str, cost: int = 0) -> dict:
    """Reserve one slot. Raises Denied when the window is exhausted."""
    total, window = windows().get(action, (60, 3600))
    _gc(identity_id, action, window)
    n = used(identity_id, action)
    if n >= total:
        raise Denied(f"rate limit {action}: {n}/{total} per {window}s for {identity_id}")
    db.kv_set(f"rl:{identity_id}:{action}:{time.time_ns()}", time.time())
    if cost:
        db.add_spend("rate", identity_id, cost)
    return {"action": action, "used": n + 1, "limit": total}


def pause(platform: str, scale: float = 1.0) -> float:
    lo, hi = JITTER.get(platform, (1.0, 3.0))
    d = random.uniform(lo, hi) * scale
    time.sleep(d)
    return round(d, 2)


def in_window(identity_id: str | None = None) -> bool:
    """Respect configured active hours (local time, WIB by default)."""
    ap = config.load_yaml("autopilot.yaml")
    hours = ap.get("active_hours")
    if not hours:
        return True
    start, end = int(hours[0]), int(hours[1])
    h = dt.datetime.now().hour
    return start <= h < end if start <= end else (h >= start or h < end)


def until_window() -> int:
    """Seconds until the next active window starts."""
    ap = config.load_yaml("autopilot.yaml")
    hours = ap.get("active_hours")
    if not hours:
        return 0
    start = int(hours[0])
    now = dt.datetime.now()
    nxt = now.replace(hour=start, minute=random.randint(0, 25), second=0, microsecond=0)
    if nxt <= now:
        nxt += dt.timedelta(days=1)
    return int((nxt - now).total_seconds())
