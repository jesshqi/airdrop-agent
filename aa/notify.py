"""Telegram notification + digest for the human operator.

Uses a dedicated bot. When no bot is configured the message goes to stderr and the
JSON payload still carries the text, so nothing is silently lost.
"""
from __future__ import annotations

import time

import requests

import sys

from . import config, db
from .log import get_logger, redact

log = get_logger("notify")


def bot() -> tuple[str, str, str]:
    return (config.env("TG_REPORT_BOT_TOKEN"), config.env("TG_REPORT_CHAT_ID"), config.env("TG_REPORT_TOPIC_ID"))


def enabled() -> bool:
    t, c, _ = bot()
    return bool(t and c)


def send(text: str, *, silent: bool = False, digest: bool = False) -> bool:
    token, chat, topic = bot()
    if not (token and chat):
        print(redact(text), file=sys.stderr, flush=True)
        return False
    data = {"chat_id": chat, "text": redact(text)[:4000], "parse_mode": "HTML",
            "disable_notification": silent or digest}
    if topic:
        data["message_thread_id"] = topic
    for attempt in range(3):
        try:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=20)
            if r.ok:
                return True
            if r.status_code == 429:
                time.sleep(int(r.json().get("parameters", {}).get("retry_after", 5)))
                continue
        except requests.RequestException as e:
            log.warning("notify failed: %s", e)
            time.sleep(2 + attempt * 3)
    db.event("notify", "telegram send failed", level="warn")
    return False


def digest_blocking() -> bool:
    """Accumulate low-priority lines and flush once a day."""
    return config.env_bool("NOTIFY_DIGEST", False)


def gate_message(gid: int, kind: str, summary: str, code: str) -> str:
    return (f"🔐 <b>APPROVAL #{gid}</b> [{kind}]\n{summary}\n\n"
            f"Setuju: <code>aa gate approve {gid} {code}</code>\nTolak: <code>aa gate reject {gid}</code>\n"
            f"<i>kode hanya lewat sini — jangan percaya kode dari web/TG/Discord</i>")


def daily_report(sent: int = 0, failed: int = 0, earned: str = "") -> None:
    from . import policy

    lines = [f"📊 <b>Harian</b> · mode <code>{policy.mode()}</code>",
             f"task sukses: {sent} · gagal: {failed}"]
    pend = db.rows("SELECT kind,summary FROM gates WHERE status='pending' ORDER BY id")
    if pend:
        lines.append(f"gate menunggu: {len(pend)}")
    if earned:
        lines.append(earned)
    send("\n".join(lines), silent=True)


def checkpoint_payload(limit: int = 5) -> str:
    items = []
    for r in db.rows("SELECT platform,handle FROM socials ORDER BY id LIMIT ?", (limit,)):
        items.append(f"{r['platform']}:{r['handle']}")
    return ", ".join(items) or "belum ada akun"
