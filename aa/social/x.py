"""X (Twitter): real login, follow, post, reply, like, repost, read timelines.

Login is a browser flow on a dedicated profile (password + email OTP or TOTP stored in
the vault). Actions then run through the same logged-in profile, rate limited per
identity. Public timeline reads use the no-auth syndication endpoint so monitoring
costs nothing.
"""
from __future__ import annotations

import asyncio
import json
import random
import re

import requests

from .. import config, db, ratelimit, scam_check, vault
from ..browser.engine import Browser
from ..email import imap
from ..jsonio import Denied
from ..log import get_logger
from . import totp

log = get_logger("x")
HOME = "https://x.com"
SYND = "https://syndication.twitter.com/srv/timeline-profile/screen-name/{h}"
BEARER = ("AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4"
          "FA33AGWWjCpTnA")


def handle(u: str) -> str:
    h = u.strip()
    m = re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})", h)
    if m:
        h = m.group(1)
    return h.lstrip("@")


def store_cookies(identity_id: str, cookies: list[dict]) -> None:
    keep = {c["name"]: c["value"] for c in cookies if c["name"] in ("auth_token", "ct0", "twid", "kdt", "guest_id")}
    if "auth_token" in keep:
        vault.put_secret(f"xcookies:{identity_id}", json.dumps(keep))


def api_headers(identity_id: str) -> dict | None:
    raw = vault.get_secret(f"xcookies:{identity_id}")
    if not raw:
        return None
    c = json.loads(raw)
    return {"authorization": f"Bearer {BEARER}", "x-csrf-token": c.get("ct0", ""),
            "x-twitter-auth-type": "OAuth2Session", "x-twitter-active-user": "yes",
            "cookie": "; ".join(f"{k}={v}" for k, v in c.items()),
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/131.0.0.0"}


def _is_login_url(url: str) -> bool:
    return any(s in url for s in ("/login", "/i/flow/login", "/account/access"))


async def login(identity_id: str, user: str, password: str, *, otp_sender: str = "x.com",
                totp_secret: str = "") -> dict:
    async with Browser(identity_id, profile="x", headless=config.env_bool("BROWSER_HEADLESS", True)) as b:
        await b.page.goto(f"{HOME}/i/flow/login", wait_until="domcontentloaded")
        await b.human_wait(1.5, 3)
        await b.fill(user, selector='input[autocomplete="username"], input[name="text"]')
        await b.press("Enter")
        await b.human_wait(1.5, 3)

        # unusual-activity checkpoint asking for email/phone
        if await b.page.locator('input[data-testid="ocfEnterTextTextInput"]').count():
            await b.fill(user, selector='input[data-testid="ocfEnterTextTextInput"]')
            await b.press("Enter")
            await b.human_wait(1.2, 2.4)

        await b.fill(password, selector='input[type="password"], input[name="password"]')
        await b.press("Enter")
        await b.human_wait(2.0, 4.0)

        for _ in range(3):
            if await b.page.locator('input[data-testid="ocfEnterTextTextInput"]').count():
                code = ""
                if totp_secret:
                    code = totp.code(totp_secret)
                if not code:
                    got = await asyncio.to_thread(imap.wait_otp, identity_id, sender=otp_sender, timeout=150)
                    code = got.get("code", "")
                if not code:
                    return {"logged_in": False, "needs": "otp", "url": b.page.url}
                await b.fill(code, selector='input[data-testid="ocfEnterTextTextInput"]')
                await b.press("Enter")
                await b.human_wait(2.0, 3.5)
            else:
                break

        ok = not _is_login_url(b.page.url)
        cookies = await b._ctx.cookies()
        store_cookies(identity_id, cookies)
        me = await whoami(b)
        if ok and me:
            db.add_social(identity_id, "x", me)
            db.event("x", "logged in", identity_id)
        return {"logged_in": ok, "handle": me, "url": b.page.url}


async def whoami(b: Browser) -> str | None:
    try:
        await b.page.goto(f"{HOME}/home", wait_until="domcontentloaded")
        await b.human_wait(2, 3.5)
        if _is_login_url(b.page.url):
            return None
        m = await b.page.evaluate("""() => {
            const el = document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
            return el ? el.innerText : null; }""")
        if m:
            mm = re.search(r"@(\w+)", m)
            return mm.group(1) if mm else None
        ck = {c["name"]: c["value"] for c in await b._ctx.cookies()}
        twid = ck.get("twid", "")
        return None if not twid else None
    except Exception:  # noqa: BLE001
        return None


async def status(identity_id: str) -> dict:
    async with Browser(identity_id, profile="x") as b:
        h = await whoami(b)
        return {"logged_in": bool(h), "handle": h}


async def _open_profile(b: Browser, h: str) -> None:
    await b.page.goto(f"{HOME}/{h}", wait_until="domcontentloaded")
    await b.human_wait(2.0, 4.0)


async def follow(identity_id: str, targets: list[str], *, limit: int | None = None) -> list[dict]:
    out = []
    targets = [handle(t) for t in targets if handle(t)]
    if limit:
        targets = targets[:limit]
    async with Browser(identity_id, profile="x") as b:
        if not await whoami(b):
            raise Denied("not logged in to X (aa x login ...)")
        for h in targets:
            if db.one("SELECT 1 FROM follows WHERE identity_id=? AND platform='x' AND target=? AND status='following'",
                      (identity_id, h)):
                out.append({"handle": h, "status": "already-tracked"})
                continue
            try:
                ratelimit.acquire(identity_id, "follow")
                await _open_profile(b, h)
                btn = b.page.locator('[data-testid$="-follow"]').first
                if not await btn.count():
                    out.append({"handle": h, "status": "no-follow-button"})
                    continue
                label = (await btn.get_attribute("data-testid")) or ""
                if "unfollow" in label:
                    out.append({"handle": h, "status": "already"})
                    db.execute("INSERT OR REPLACE INTO follows VALUES(?,?,?,?,?)", (identity_id, "x", h, "following", db.now()))
                    continue
                await btn.click()
                await b.human_wait(1.5, 3.5)
                ok = await b.page.locator('[data-testid$="-unfollow"]').count() > 0
                db.execute("INSERT OR REPLACE INTO follows VALUES(?,?,?,?,?)",
                           (identity_id, "x", h, "following" if ok else "failed", db.now()))
                db.event("follow", f"x {h} {'ok' if ok else 'failed'}", identity_id)
                out.append({"handle": h, "status": "following" if ok else "failed"})
                await asyncio.sleep(random.uniform(6, 18))
            except Denied as e:
                out.append({"handle": h, "status": "rate-limited", "error": str(e)})
                await asyncio.sleep(random.uniform(30, 60))
            except Exception as e:  # noqa: BLE001
                out.append({"handle": h, "status": "error", "error": str(e)[:160]})
    return out


async def unfollow(identity_id: str, h: str) -> dict:
    h = handle(h)
    async with Browser(identity_id, profile="x") as b:
        await _open_profile(b, h)
        btn = b.page.locator('[data-testid$="-unfollow"]').first
        if not await btn.count():
            return {"handle": h, "status": "not-following"}
        await btn.click()
        await b.human_wait(0.8, 1.6)
        conf = b.page.get_by_test_id("confirmationSheetConfirm")
        if await conf.count():
            await conf.click()
        db.execute("INSERT OR REPLACE INTO follows VALUES(?,?,?,?,?)", (identity_id, "x", h, "unfollowed", db.now()))
        return {"handle": h, "status": "unfollowed"}


async def post(identity_id: str, text: str, *, reply_to: str = "") -> dict:
    ratelimit.acquire(identity_id, "message")
    async with Browser(identity_id, profile="x") as b:
        if reply_to:
            await b.page.goto(reply_to if reply_to.startswith("http") else f"{HOME}/status/{reply_to}",
                              wait_until="domcontentloaded")
            await b.human_wait(2, 3)
            box = b.page.locator('[data-testid="tweetTextarea_0"]').first
        else:
            await b.page.goto(f"{HOME}/compose/post", wait_until="domcontentloaded")
            await b.human_wait(1.5, 2.5)
            box = b.page.locator('[data-testid="tweetTextarea_0"]').first
        await box.click()
        await box.type(text, delay=random.randint(25, 90))
        await b.human_wait(0.8, 2.0)
        send = b.page.locator('[data-testid="tweetButton"], [data-testid="tweetButtonInline"]').first
        await send.click()
        await b.human_wait(2, 3.5)
        db.event("x", f"posted {len(text)} chars", identity_id)
        return {"posted": True, "chars": len(text), "reply_to": reply_to or None}


async def like(identity_id: str, url: str) -> dict:
    async with Browser(identity_id, profile="x") as b:
        await b.page.goto(url if url.startswith("http") else f"{HOME}/status/{url}", wait_until="domcontentloaded")
        await b.human_wait(1.5, 3)
        btn = b.page.locator('[data-testid="like"]').first
        if not await btn.count():
            return {"liked": False, "reason": "already liked or no button"}
        await btn.click()
        return {"liked": True}


async def repost(identity_id: str, url: str) -> dict:
    async with Browser(identity_id, profile="x") as b:
        await b.page.goto(url if url.startswith("http") else f"{HOME}/status/{url}", wait_until="domcontentloaded")
        await b.human_wait(1.5, 3)
        btn = b.page.locator('[data-testid="retweet"]').first
        await btn.click()
        await b.human_wait(0.6, 1.4)
        item = b.page.get_by_test_id("retweetConfirm")
        if await item.count():
            await item.click()
        return {"reposted": True}


# ---------- reads (no auth, no cost) ----------
def timeline(h: str, limit: int = 10) -> list[dict]:
    h = handle(h)
    try:
        r = requests.get(SYND.format(h=h), timeout=20,
                         headers={"user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
        if not r.ok:
            return []
        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', r.text, re.S)
        if not m:
            return []
        data = json.loads(m.group(1))
        entries = (((data.get("props") or {}).get("pageProps") or {}).get("timeline") or {}).get("entries") or []
        out = []
        for e in entries[:limit]:
            tw = ((e.get("content") or {}).get("tweet") or {})
            if not tw:
                continue
            out.append({"id": tw.get("id_str") or e.get("entry_id"),
                        "handle": ((tw.get("user") or {}).get("screen_name") or h),
                        "text": (tw.get("full_text") or tw.get("text") or "")[:1200],
                        "created": tw.get("created_at"),
                        "url": f"{HOME}/{((tw.get('user') or {}).get('screen_name') or h)}/status/{tw.get('id_str')}",
                        "likes": tw.get("favorite_count", 0), "replies": tw.get("reply_count", 0)})
        return out
    except (requests.RequestException, ValueError, KeyError):
        return []


async def search(identity_id: str, query: str, limit: int = 15) -> list[dict]:
    """Browser search on the logged-in profile; returns parsed posts."""
    async with Browser(identity_id, profile="x") as b:
        from urllib.parse import quote

        await b.page.goto(f"{HOME}/search?q={quote(query)}&f=live", wait_until="domcontentloaded")
        await b.human_wait(3, 5)
        html = await b.page.content()
        out = []
        for m in re.finditer(r'href="(/[A-Za-z0-9_]{1,15}/status/(\d+))"', html):
            url = HOME + m.group(1)
            if any(o["url"] == url for o in out):
                continue
            out.append({"url": url, "id": m.group(2)})
            if len(out) >= limit:
                break
        for item in out:
            item["verdict"] = scam_check.check_url(item["url"])["verdict"]
        return out
