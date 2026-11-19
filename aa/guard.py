"""KILL switch + mode helpers."""
from __future__ import annotations

import time

from . import config, db, policy
from .jsonio import Kill
from .log import get_logger

log = get_logger("guard")


def check_kill() -> None:
    if config.KILL_FILE.exists():
        raise Kill(f"KILL switch active ({config.KILL_FILE}) — remove with 'aa unkill'")


def kill(reason: str = "") -> dict:
    config.KILL_FILE.write_text(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {reason}\n")
    db.event("kill", f"KILL on: {reason}", level="warn")
    return {"kill": True, "reason": reason}


def unkill() -> dict:
    config.KILL_FILE.unlink(missing_ok=True)
    db.event("kill", "KILL off")
    return {"kill": False}


def status() -> dict:
    return {"kill": config.KILL_FILE.exists(), "mode": policy.mode(),
            "passphrase": bool(config.env("VAULT_PASSWORD") or config.env("VAULT_PASSWORD_FILE"))}
