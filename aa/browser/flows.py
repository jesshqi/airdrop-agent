"""Generic form filling, modal dismissal and OTP-driven flows.

Field matching is rule-based first (never guesses blindly): type, name, id,
placeholder and label are scored against a synonym table. Unknown required fields are
reported back so the caller can block instead of submitting garbage.
"""
from __future__ import annotations

import random
import re

from .. import config, db, vault
from ..log import get_logger

log = get_logger("forms")

RULES = [
    ("email", ["email", "e-mail", "mail", "surel"], "email"),
    ("password", ["password", "passwd", "pass", "sandi"], "password"),
    ("password2", ["confirm", "repeat", "ulangi", "konfirmasi"], "password"),
    ("username", ["username", "user name", "handle", "nickname", "display name", "name"], "handle"),
    ("first", ["first name", "given name", "nama depan"], "first"),
    ("last", ["last name", "surname", "family name", "nama belakang"], "last"),
    ("wallet", ["wallet", "address", "evm", "0x", "dompet"], "wallet"),
    ("solwallet", ["solana", "phantom"], "solwallet"),
    ("code", ["code", "otp", "verification", "kode", "2fa", "token"], "code"),
    ("phone", ["phone", "mobile", "whatsapp", "telepon", "hp"], "phone"),
    ("twitter", ["twitter", "x.com", "@", "x username"], "twitter"),
    ("discord", ["discord"], "discord"),
    ("telegram", ["telegram"], "telegram"),
    ("url", ["website", "url", "portfolio"], "url"),
    ("bio", ["bio", "about", "description", "message", "komentar", "reason"], "bio"),
]


def _score(field: dict, words: list[str]) -> int:
    hay = " ".join([field.get("label", ""), field.get("name", ""), field.get("id", ""),
                    field.get("placeholder", "")]).lower()
    return sum(3 if w in (field.get("name", "") + field.get("id", "")).lower() else 2 for w in words if w in hay)


def classify(fields: list[dict]) -> dict[int, str]:
    out = {}
    for f in fields:
        if f.get("type") in ("hidden", "submit", "button", "file"):
            continue
        best, kind = 0, ""
        for name, words, target in RULES:
            s = _score(f, words)
            if s > best:
                best, kind = s, target
        if kind == "password" and any(k == "password" for k in out.values()):
            kind = "password2"
        if best:
            out[f["i"]] = kind
    return out


def _gen_password() -> str:
    import secrets
    import string

    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(16))


def identity_values(identity_id: str) -> dict:
    from .. import humanize

    row = db.identity(identity_id)
    p = humanize.persona(row.get("persona"))
    handle = f"{config.slug(row['label']).replace('-', '')}{random.randint(10, 99)}"[:20]
    ws_evm = db.wallets(identity_id, "evm")
    ws_sol = db.wallets(identity_id, "sol")
    return {
        "email": db.email_of(identity_id)["address"] if db.email_of(identity_id) else config.env("AGENT_EMAIL"),
        "handle": handle,
        "first": handle[:8].capitalize(),
        "last": random.choice(["K", "W", "P", "S"]),
        "wallet": ws_evm[0]["address"] if ws_evm else "",
        "solwallet": ws_sol[0]["address"] if ws_sol else "",
        "password": vault.get_secret(f"pw:{identity_id}") or "",
        "phone": config.env("AGENT_PHONE"),
        "bio": random.choice(["here for the tech", "testing things early", "builder", "just exploring"]) or
        p.get("tone", ""),
        "url": "",
        "twitter": "@" + (db.social(identity_id, "x") or {}).get("handle", ""),
        "discord": (db.social(identity_id, "discord") or {}).get("handle", ""),
        "telegram": (db.social(identity_id, "telegram") or {}).get("handle", ""),
    }


async def dismiss(b) -> int:
    """Close cookie banners / newsletter modals. Returns how many were clicked."""
    clicked = 0
    for txt in ("Accept all", "Accept", "Terima semua", "Setuju", "Got it", "Mengerti", "OK", "Close", "Tutup"):
        try:
            loc = b.page.get_by_role("button", name=re.compile(f"^{re.escape(txt)}$", re.I)).first
            if await loc.count() and await loc.is_visible():
                await loc.click(timeout=2500)
                clicked += 1
                await b.human_wait(0.2, 0.6)
        except Exception:  # noqa: BLE001
            continue
    return clicked


async def fill_form(b, identity_id: str, *, overrides: dict | None = None, otp_sender: str = "",
                    otp_subject: str = "", timeout_otp: int = 180) -> dict:
    snap = await b.snapshot()
    fields = snap.get("fields", [])
    mapping = classify(fields)
    vals = identity_values(identity_id)
    vals.update(overrides or {})
    filled, missing = [], []
    for f in fields:
        kind = mapping.get(f["i"])
        if not kind:
            if f.get("required") and f.get("type") not in ("checkbox", "radio"):
                missing.append(f.get("label") or f.get("name"))
            continue
        if f.get("type") == "checkbox":
            try:
                await b.check(f'[data-aa-idx="{f["i"]}"]')
                filled.append("checkbox")
            except Exception:  # noqa: BLE001
                pass
            continue
        value = vals.get(kind, "")
        if kind == "password" and not value:
            value = _gen_password()
            vault.put_secret(f"pw:{identity_id}", value)
            vals["password"] = value
        if kind == "password2":
            value = vals.get("password", "")
        if kind == "code" and not value and otp_sender or kind == "code" and not value and otp_subject:
            from ..email import imap

            r = imap.wait_otp(identity_id, sender=otp_sender, subject=otp_subject, timeout=timeout_otp)
            if not r.get("ok"):
                missing.append("otp")
                continue
            value = r["code"]
        if not value:
            if f.get("required"):
                missing.append(f.get("label") or f.get("name"))
            continue
        try:
            await b.fill(value, index=f["i"])
            filled.append(kind)
        except Exception as e:  # noqa: BLE001
            log.warning("fill %s failed: %s", kind, e)
    return {"filled": filled, "missing": missing, "snapshot_url": snap.get("url")}


async def submit(b) -> dict:
    for txt in ("Submit", "Kirim", "Sign up", "Register", "Daftar", "Simpan", "Selesai", "Continue", "Next", "Claim"):
        try:
            loc = b.page.get_by_role("button", name=re.compile(f"^{re.escape(txt)}$", re.I)).first
            if await loc.count() and await loc.is_visible():
                await loc.click()
                await b.human_wait(1.0, 2.4)
                return {"submitted": txt}
        except Exception:  # noqa: BLE001
            continue
    try:
        await b.page.keyboard.press("Enter")
        return {"submitted": "enter"}
    except Exception:  # noqa: BLE001
        return {"submitted": None}


async def read_form_errors(b) -> list[str]:
    txt = await b.text()
    errs = []
    for line in txt.splitlines():
        low = line.lower()
        if any(w in low for w in ("invalid", "required", "sudah dipakai", "already used", "salah", "error")) and len(line) < 160:
            errs.append(line.strip())
    return errs[:8]


async def wait_for_success(b, markers: list[str], timeout: int = 60) -> bool:
    import asyncio

    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        txt = (await b.text()).lower()
        if any(m.lower() in txt for m in markers):
            return True
        await asyncio.sleep(2)
    return False
