"""Agent inbox: IMAP polling for OTP codes and verification links.

Credentials are per identity (vault) with an env fallback for a single shared inbox.
Reads only headers + a short text slice; never stores whole mail bodies.
"""
from __future__ import annotations

import email
import email.utils
import imaplib
import json
import re
import time
from datetime import datetime, timedelta, timezone

from .. import config, db, vault
from ..jsonio import Denied
from ..log import get_logger

log = get_logger("email")

CODE_RX = [re.compile(r"\b(\d{6})\b"), re.compile(r"\b(\d{4,8})\b")]
LINK_RX = re.compile(r"https?://[^\s\"'<>)]+")
SAFE_LINK_DOMAINS = ("google.com", "gmail.com", "discord.com", "x.com", "twitter.com", "telegram.org",
                     "galxe.com", "zealy.io", "layer3.xyz", "questn.com", "intract.io", "guild.xyz",
                     "privy.io", "dynamic.xyz", "walletconnect.com")


def creds(identity_id: str | None = None) -> dict:
    if identity_id:
        raw = vault.get_secret(f"imap:{identity_id}")
        if raw:
            return json.loads(raw)
    return {"host": config.env("IMAP_HOST"), "port": config.env_int("IMAP_PORT", 993),
            "user": config.env("IMAP_USER") or config.env("AGENT_EMAIL"),
            "password": config.env("IMAP_PASSWORD")}


def register(identity_id: str, address: str, password: str, host: str = "imap.gmail.com",
             port: int = 993) -> dict:
    vault.put_secret(f"imap:{identity_id}", json.dumps({"host": host, "port": port,
                                                       "user": address, "password": password}))
    db.add_email(identity_id, address, "gmail" if "gmail" in host else "imap")
    return {"identity": identity_id, "address": address, "host": host}


def address_for(identity_id: str) -> str:
    row = db.email_of(identity_id)
    if row:
        return row["address"]
    c = creds(identity_id)
    if c.get("user"):
        return c["user"]
    raise Denied(f"identity {identity_id} has no inbox (aa email add ...)")


def _connect(identity_id: str | None) -> imaplib.IMAP4_SSL:
    c = creds(identity_id)
    if not (c.get("host") and c.get("user") and c.get("password")):
        raise Denied("inbox not configured (aa email add / IMAP_* env)")
    box = imaplib.IMAP4_SSL(c["host"], int(c.get("port") or 993))
    box.login(c["user"], c["password"])
    box.select("INBOX")
    return box


def _slice(msg: email.message.Message, limit: int = 4000) -> str:
    parts = []
    for p in msg.walk():
        if p.get_content_type() in ("text/plain", "text/html"):
            try:
                parts.append(p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "ignore"))
            except (AttributeError, LookupError):
                continue
    return "\n".join(parts)[:limit]


def fetch(identity_id: str | None = None, *, since_minutes: int = 15, limit: int = 15) -> list[dict]:
    box = _connect(identity_id)
    try:
        since = (datetime.now(timezone.utc) - timedelta(minutes=since_minutes)).strftime("%d-%b-%Y")
        typ, data = box.search(None, f'(SINCE "{since}")')
        ids = (data[0] or b"").split()[-limit:]
        out = []
        for uid in reversed(ids):
            typ, raw = box.fetch(uid, "(RFC822)")
            if typ != "OK":
                continue
            msg = email.message_from_bytes(raw[0][1])
            out.append({"id": uid.decode(), "from": msg.get("From", ""), "subject": msg.get("Subject", ""),
                        "date": msg.get("Date", ""), "text": _slice(msg), "seen": False})
        return out
    finally:
        try:
            box.close()
            box.logout()
        except imaplib.IMAP4.error:
            pass


def _sender_ok(msg: dict, hints: list[str]) -> bool:
    if not hints:
        return True
    hay = f"{msg['from']} {msg['subject']}".lower()
    return any(h.strip().lower() in hay for h in hints if h.strip())


def extract_code(text: str) -> str | None:
    for rx in CODE_RX:
        m = rx.findall(text)
        if m:
            return max(m, key=len) if rx is CODE_RX[1] else m[0]
    return None


def safe_link(text: str) -> str | None:
    from .. import scam_check

    for url in LINK_RX.findall(text):
        host = url.split("//", 1)[-1].split("/")[0].lower()
        if any(host == d or host.endswith("." + d) for d in SAFE_LINK_DOMAINS):
            return url
        if scam_check.check_url(url)["verdict"] == "ok":
            return url
    return None


def wait_otp(identity_id: str | None = None, *, sender: str = "", subject: str = "",
             timeout: int = 180, since_minutes: int = 10, seen_before: set[str] | None = None) -> dict:
    hints = [sender, subject]
    seen = seen_before or set()
    end = time.time() + timeout
    while time.time() < end:
        for msg in fetch(identity_id, since_minutes=since_minutes):
            key = f"{msg['id']}:{msg['subject']}"
            if key in seen or not _sender_ok(msg, hints):
                continue
            code = extract_code(f"{msg['subject']}\n{msg['text']}")
            if code:
                db.event("email", f"otp for {sender or subject}", identity_id)
                return {"ok": True, "code": code, "subject": msg["subject"], "from": msg["from"]}
        time.sleep(6)
    return {"ok": False, "error": f"no matching OTP within {timeout}s", "hints": hints}


def wait_link(identity_id: str | None = None, *, sender: str = "", subject: str = "", timeout: int = 180) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        for msg in fetch(identity_id, since_minutes=15):
            if not _sender_ok(msg, [sender, subject]):
                continue
            link = safe_link(msg["text"])
            if link:
                return {"ok": True, "link": link, "subject": msg["subject"]}
        time.sleep(8)
    return {"ok": False, "error": f"no link within {timeout}s"}


def inbox_summary(identity_id: str | None = None) -> dict:
    msgs = fetch(identity_id, since_minutes=1440, limit=5)
    return {"count": len(msgs), "latest": [{"from": m["from"], "subject": m["subject"]} for m in msgs]}
