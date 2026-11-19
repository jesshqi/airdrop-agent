"""Radar sources: Telegram channels, X accounts/queries, RSS-ish web pages.

Telegram reads use the radar identity's own session. X timelines use the free
syndication endpoint; keyword search uses the logged-in browser profile only when
enabled (it is slower but costs nothing).
"""
from __future__ import annotations

import asyncio

import requests

from .. import config, db
from ..jsonio import Denied
from ..log import get_logger
from . import extract

log = get_logger("radar.sources")


def conf() -> dict:
    return config.load_yaml("radar_sources.yaml")


def save(c: dict) -> None:
    config.save_yaml("radar_sources.yaml", c)


def _capped() -> bool:
    caps = conf().get("caps") or {}
    reads = int(db.kv_get(f"radar:reads:{db.today()}", 0) or 0)
    return reads >= int(caps.get("x_reads_per_day", 400))


def _count_read(n: int = 1) -> None:
    k = f"radar:reads:{db.today()}"
    db.kv_set(k, int(db.kv_get(k, 0) or 0) + n)


# ---------- telegram ----------
async def scan_telegram(identity_id: str, limit_per_channel: int = 15) -> list[dict]:
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    from .. import vault

    sess = vault.get_secret(f"tg:{identity_id}")
    if not sess:
        raise Denied("radar identity not logged in to Telegram")
    c = TelegramClient(StringSession(sess), int(config.env_required("TG_API_ID")), config.env_required("TG_API_HASH"))
    await c.connect()
    out: list[dict] = []
    try:
        for src in conf().get("tg_channels") or []:
            if not src.get("enabled", True):
                continue
            target = src["target"]
            last_key = f"radar:last:tg:{target}"
            last = int(db.kv_get(last_key, 0) or 0)
            try:
                ent = await c.get_entity(target)
                msgs = await c.get_messages(ent, limit=limit_per_channel, min_id=last)
            except Exception as e:  # noqa: BLE001
                log.warning("read %s failed: %s", target, e)
                continue
            for m in msgs:
                if m.id <= last or not (m.message or "").strip():
                    continue
                n = extract.normalize(m.message, target)
                if n["kind"] == "unknown" and n["noise"]:
                    continue
                out.append({"source": f"tg:{target}", "trust": int(src.get("trust", 1)),
                            "url": f"https://t.me/{str(target).lstrip('@')}/{m.id}",
                            "text": n["text"], "kind": n["kind"], "links": n["links"],
                            "hints": n["hints"], "project": n["project"], "noise": n["noise"],
                            "posted": str(m.date)})
            if msgs:
                db.kv_set(last_key, max(m.id for m in msgs))
    finally:
        await c.disconnect()
    return out


# ---------- x ----------
def scan_x_accounts(limit_per: int = 8) -> list[dict]:
    from ..social import x as X

    if _capped():
        return []
    out = []
    for src in conf().get("x_accounts") or []:
        if not src.get("enabled", True):
            continue
        posts = X.timeline(src["handle"], limit_per)
        _count_read(len(posts))
        for p in posts:
            n = extract.normalize(p["text"], src["handle"])
            if n["kind"] == "unknown" and n["noise"]:
                continue
            out.append({"source": f"x@{src['handle']}", "trust": int(src.get("trust", 1)),
                        "url": p["url"], "text": n["text"], "kind": n["kind"], "links": n["links"],
                        "hints": n["hints"], "project": n["project"], "noise": n["noise"],
                        "likes": p.get("likes"), "replies": p.get("replies"), "posted": p.get("created")})
    return out


async def scan_x_queries(identity_id: str, per_query: int = 10) -> list[dict]:
    from ..social import x as X

    if not conf().get("x_search_enabled", False) or _capped():
        return []
    out = []
    for q in conf().get("x_queries") or []:
        try:
            hits = await X.search(identity_id, q, per_query)
        except Exception as e:  # noqa: BLE001
            log.warning("x search %s failed: %s", q, e)
            continue
        _count_read(len(hits))
        for h in hits:
            out.append({"source": f"xq:{q}", "trust": 1, "url": h["url"], "text": "", "kind": "unknown",
                        "links": [{"url": h["url"], "type": "x"}], "hints": {}, "project": q})
        await asyncio.sleep(4)
    return out


# ---------- web ----------
def scan_web(urls: list[str]) -> list[dict]:
    out = []
    for u in urls:
        try:
            r = requests.get(u, timeout=20, headers={"user-agent": "Mozilla/5.0"})
            text = extract.clean(r.text)[:6000]
        except requests.RequestException as e:
            log.warning("fetch %s: %s", u, e)
            continue
        n = extract.normalize(text, u)
        out.append({"source": f"web:{u}", "trust": 1, "url": u, "text": n["text"], "kind": n["kind"],
                    "links": n["links"], "hints": n["hints"], "project": n["project"]})
    return out


# ---------- management ----------
def add(kind: str, target: str, trust: int = 1) -> dict:
    c = conf()
    key = {"tg": "tg_channels", "x": "x_accounts", "query": "x_queries"}.get(kind)
    if not key:
        raise Denied("kind must be tg, x or query")
    if kind == "query":
        c.setdefault(key, [])
        if target in c[key]:
            return {"added": False, "target": target}
        c[key].append(target)
    else:
        c.setdefault(key, [])
        if any(s["target"] if kind == "tg" else s["handle"] for s in c[key]
               if (s.get("target") == target or s.get("handle") == target)):
            return {"added": False, "target": target}
        c[key].append({"target": target} if kind == "tg" else {"handle": target.lstrip("@")})
    save(c)
    return {"added": True, "kind": kind, "target": target}


def remove(kind: str, target: str) -> dict:
    c = conf()
    key = {"tg": "tg_channels", "x": "x_accounts", "query": "x_queries"}.get(kind)
    if not key:
        raise Denied("kind must be tg, x or query")
    before = len(c.get(key) or [])
    if kind == "query":
        c[key] = [q for q in (c.get(key) or []) if q != target]
    else:
        c[key] = [s for s in (c.get(key) or [])
                  if (s.get("target") != target and s.get("handle") != target)]
    save(c)
    return {"removed": before - len(c[key])}


def listing() -> dict:
    c = conf()
    return {"tg": [s.get("target") for s in (c.get("tg_channels") or [])],
            "x": [s.get("handle") for s in (c.get("x_accounts") or [])],
            "queries": c.get("x_queries") or [], "min_score": c.get("min_score"),
            "reads_today": int(db.kv_get(f"radar:reads:{db.today()}", 0) or 0),
            "cap": (c.get("caps") or {}).get("x_reads_per_day")}


def reset_reads() -> dict:
    db.kv_set(f"radar:reads:{db.today()}", 0)
    return {"reads": 0}
