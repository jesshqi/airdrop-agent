"""TOTP (RFC 6238) for 2FA logins, stdlib only."""
from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time


def code(secret: str, digits: int = 6, step: int = 30) -> str:
    s = secret.strip().replace(" ", "").upper()
    s += "=" * (-len(s) % 8)
    key = base64.b32decode(s)
    counter = int(time.time() // step)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    num = struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF
    return str(num % (10 ** digits)).zfill(digits)


def remaining(step: int = 30) -> int:
    return step - int(time.time()) % step


def otpauth_url(secret: str, label: str, issuer: str = "airdrop-agent") -> str:
    return f"otpauth://totp/{issuer}:{label}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"


def parse_url(url: str) -> str:
    from urllib.parse import parse_qs, urlparse

    q = parse_qs(urlparse(url).query)
    if "secret" not in q:
        raise ValueError("no secret in otpauth url")
    return q["secret"][0]
