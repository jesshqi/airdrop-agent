"""Phishing / drainer heuristics for any URL the agent is about to touch.

Static checks run offline and always. RDAP (domain age) is optional and cached.

verdict: ok | warn | bad
  bad   -> never auto-connect/sign, always gate
  warn  -> connect only with a gate
  ok    -> auto-connect allowed (still subject to the domain allowlist)
"""
from __future__ import annotations

import re
import time
from urllib.parse import urlparse

import requests

from . import config, db
from .config import mask
from .log import get_logger

log = get_logger("scam")

BRANDS = ["uniswap", "galxe", "zealy", "layer3", "questn", "intract", "guild", "opensea",
          "metamask", "rabby", "phantom", "discord", "telegram", "coinbase", "binance",
          "arbitrum", "optimism", "solana", "base", "linea", "scroll", "zksync"]
SUSPICIOUS_TLD = {"xyz", "top", "click", "site", "online", "live", "app", "fun", "icu", "buzz", "gq", "tk"}
DRAIN_WORDS = ["seed phrase", "recovery phrase", "validate wallet", "sync wallet", "claim reward",
               "airdrop claim", "connect to claim", "migrate wallet", "upgrade wallet"]
BAD_DOMAINS = set()


def _lev(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 2:
        return 9
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _registrable(host: str) -> str:
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def check_url(url: str, deep: bool = False) -> dict:
    reasons: list[str] = []
    try:
        u = urlparse(url if "://" in url else "https://" + url)
    except ValueError:
        return {"verdict": "bad", "reasons": ["unparseable URL"], "host": ""}
    host = (u.hostname or "").lower()
    tld = host.rsplit(".", 1)[-1] if "." in host else ""
    verdict = "ok"
    if not host:
        return {"verdict": "bad", "reasons": ["no host"], "host": ""}
    if u.scheme != "https":
        reasons.append("not https")
        verdict = "warn"
    if re.fullmatch(r"[\d.]+", host):
        reasons.append("IP address, not a domain")
        verdict = "warn"
    if host.startswith("xn--") or ".xn--" in host:
        reasons.append("punycode domain (IDN homograph risk)")
        verdict = "bad"
    if tld in SUSPICIOUS_TLD:
        reasons.append(f"TLD .{tld} is over-used by drainers")
        verdict = "warn" if verdict == "ok" else verdict
    if host.count("-") >= 3:
        reasons.append("many hyphens")
        verdict = "warn" if verdict == "ok" else verdict
    if host in BAD_DOMAINS:
        reasons.append("known bad domain")
        verdict = "bad"

    reg = _registrable(host)
    name = reg.split(".")[0]
    for b in BRANDS:
        if name == b:
            break
        if b in name and name != b:
            # the brand's own domain is name == b; anything embedding it is a different
            # registrable domain (app-uniswap.org) and deserves a gate
            reasons.append(f"brand '{b}' embedded in '{name}'")
            verdict = "warn" if verdict == "ok" else verdict
        elif _lev(name, b) == 1 and name != b:
            reasons.append(f"lookalike of '{b}'")
            verdict = "bad"
            break
    if "login" in host or "verify" in host or "wallet" in name:
        reasons.append("login/verify keyword")

    if deep:
        age = domain_age(reg)
        if age is not None:
            if age < 30:
                reasons.append(f"domain only {age}d old")
                verdict = "bad"
            elif age < 120:
                reasons.append(f"domain {age}d old")
                verdict = "warn" if verdict == "ok" else verdict
    return {"verdict": verdict, "reasons": reasons, "host": host}


def domain_age(domain: str) -> int | None:
    key = f"rdap:{domain}"
    raw = db.kv_get(key)
    if raw:
        return raw.get("days") if isinstance(raw, dict) else raw
    try:
        r = requests.get(f"https://rdap.org/domain/{domain}", timeout=8)
        if not r.ok:
            return None
        for ev in r.json().get("events", []):
            if ev.get("eventAction") == "registration":
                t = time.mktime(time.strptime(ev["eventDate"][:10], "%Y-%m-%d"))
                days = int((time.time() - t) / 86400)
                db.kv_set(key, {"days": days, "at": int(time.time())})
                return days
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None
    return None


def check_page_text(text: str) -> dict:
    low = (text or "").lower()
    hits = [w for w in DRAIN_WORDS if w in low]
    if "requesting" in low and "signature" in low and "seed" in low:
        hits.append("asks for seed phrase")
    if "approve all" in low or "set approval for all" in low:
        hits.append("asks for unlimited approval")
    verdict = "bad" if "seed phrase" in hits else ("warn" if len(hits) >= 2 else "ok")
    return {"verdict": verdict, "reasons": hits, "hits": hits}


def is_ok(verdict: str) -> bool:
    return verdict == "ok"


def new_domain_auto_allowed(host: str) -> bool:
    if not (config.policy().get("auto_allowlist_domains", True)):
        return False
    return check_url("https://" + host)["verdict"] == "ok"


def describe(url: str) -> str:
    v = check_url(url, deep=True)
    return f"{v['verdict']}: {', '.join(v['reasons']) or 'no findings'} ({mask(url, 8)})"
