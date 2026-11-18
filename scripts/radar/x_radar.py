#!/usr/bin/env python3
"""X (Twitter) radar: poll followed accounts' timelines + keyword searches, feed posts to the radar pipeline.

Reads use the OFFICIAL X API v2 with an app bearer token (X_BEARER_TOKEN). Pay-per-use billing (2026: ~$0.005 per
post read, ~$0.010 per user lookup); a daily read budget (settings.x_max_reads_per_day) is enforced locally and
since_id is stored so the same post is never paid twice.

Follow:
  * API follow (POST /2/users/:id/following) needs USER-context OAuth and, since Apr 2026, is not available on
    self-serve tiers (Enterprise only). Used only if X_API_FOLLOW_MODE=enterprise + X_USER_ACCESS_TOKEN + X_USER_ID.
  * Browser follow (Playwright, logged-in persistent profile made by a HUMAN via web_quest/browser_session login)
    is OPT-IN only: X_BROWSER_FOLLOW_OPTIN=I_ACCEPT_X_TOS_RISK. Automation may break X ToS -> account limits/ban.
    Capped by settings.x_follow_cap_per_day with random delays. No credential/cookie scraping ever.
  * Otherwise: a manual follow list is sent to Telegram.

  x_radar.py poll [--dry-run]           one polling round (timelines + searches)
  x_radar.py follow [--handle h ...]    follow targets (x_accounts with follow: true, or given handles)
  x_radar.py budget                     reads used today
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl; _sys.path[:0] = [str(_d) for _d in sorted(_pl.Path(__file__).resolve().parents[1].iterdir()) if _d.is_dir() and not _d.name.startswith(("_", "."))]  # noqa: E702 (script-group import path)

import argparse
import os
import random
import re
import time

import requests

from common import HOME, check_kill, get_logger, load_yaml, out
import extract as X
import pipeline as P

log = get_logger("radar.x")
API = "https://api.x.com/2"
CFG = os.environ.get("RADAR_SOURCES_FILE", str(HOME / "radar_sources.yaml"))
OPTIN = "I_ACCEPT_X_TOS_RISK"


def _state(key: str, val: str | None = None) -> str | None:
    with X.db() as con:
        if val is None:
            r = con.execute("SELECT value FROM x_state WHERE key=?", (key,)).fetchone()
            return r["value"] if r else None
        con.execute("INSERT OR REPLACE INTO x_state VALUES(?,?)", (key, val))
    return val


def _get(path: str, params: dict) -> dict:
    tok = os.environ.get("X_BEARER_TOKEN")
    if not tok:
        raise SystemExit("X_BEARER_TOKEN missing (reads need the official API)")
    r = requests.get(API + path, params=params, headers={"Authorization": f"Bearer {tok}"}, timeout=30)
    if r.status_code == 429:
        reset = int(r.headers.get("x-rate-limit-reset", time.time() + 900))
        raise RuntimeError(f"rate limited until {time.strftime('%H:%M', time.localtime(reset))}")
    if r.status_code in (402, 403):
        raise RuntimeError(f"X API {r.status_code}: plan/credits do not allow this call")
    r.raise_for_status()
    return r.json()


def _text_with_urls(tw: dict) -> str:
    text = tw.get("text", "")
    for u in (tw.get("entities") or {}).get("urls", []) or []:
        exp = u.get("unwound_url") or u.get("expanded_url")
        if exp and u.get("url"):
            text = text.replace(u["url"], exp)
    return text


def user_id(handle: str) -> str | None:
    key = f"uid:{handle.lower()}"
    if (v := _state(key)):
        return v
    d = _get(f"/users/by/username/{handle}", {})
    uid = (d.get("data") or {}).get("id")
    if uid:
        _state(key, uid)
    return uid


def _budget_ok(cfg: dict, n: int) -> bool:
    return X.budget_take("x_reads", n, int(cfg.get("settings", {}).get("x_max_reads_per_day", 300)))


def poll(cfg: dict, dry: bool = False) -> dict:
    st = cfg.get("settings", {})
    mx = max(5, min(100, int(st.get("x_max_results_per_call", 10))))
    fields = {"tweet.fields": "created_at,entities,author_id", "max_results": mx}
    res, errs = [], []
    jobs = [("user", a) for a in cfg.get("x_accounts", [])] + [("q", {"query": q, "trust": 0.4}) for q in cfg.get("x_queries", [])]
    for kind, j in jobs:
        check_kill()
        label = j.get("handle") if kind == "user" else j["query"][:40]
        if dry:
            res.append({"would_poll": kind, "target": label}); continue
        if not _budget_ok(cfg, mx):
            errs.append({"target": label, "error": "daily X read budget reached"}); break
        try:
            if kind == "user":
                uid = user_id(j["handle"])
                if not uid:
                    continue
                skey = f"since:u:{uid}"
                params = {**fields, "exclude": "replies"}
                if (sid := _state(skey)):
                    params["since_id"] = sid
                d = _get(f"/users/{uid}/tweets", params)
            else:
                skey = f"since:q:{X.project_key(j['query'])[:60]}"
                params = {**fields, "query": j["query"]}
                if (sid := _state(skey)):
                    params["since_id"] = sid
                d = _get("/tweets/search/recent", params)
        except Exception as e:
            errs.append({"target": label, "error": str(e)[:160]}); continue
        tweets = d.get("data") or []
        if tweets:
            _state(skey, max(tweets, key=lambda t: int(t["id"]))["id"])
        for tw in tweets:
            who = j.get("handle") or tw.get("author_id")
            post = {"source": f"x:@{who}", "post_id": tw["id"], "text": _text_with_urls(tw),
                    "url": f"https://x.com/{who}/status/{tw['id']}", "trust": float(j.get("trust", 0.5))}
            r = P.process_post(post, cfg)
            if r["decision"] not in ("seen", "not_airdrop"):
                res.append(r)
        time.sleep(random.uniform(1, 3))
    return {"processed": res, "errors": errs, "reads_today": X.budget_used("x_reads")}


def _mark_followed(h: str, via: str, status: str) -> None:
    with X.db() as con:
        con.execute("INSERT OR REPLACE INTO followed VALUES(?,?,?,?)", (h.lower(), time.time(), via, status))


def _already(h: str) -> bool:
    with X.db() as con:
        r = con.execute("SELECT status FROM followed WHERE handle=?", (h.lower(),)).fetchone()
    return bool(r and r["status"] == "ok")


def follow_api(handles: list[str]) -> list[dict]:
    tok, me = os.environ.get("X_USER_ACCESS_TOKEN"), os.environ.get("X_USER_ID")
    if not (tok and me):
        raise SystemExit("API follow needs X_USER_ACCESS_TOKEN (OAuth2 user context, follows.write) + X_USER_ID")
    res = []
    for h in handles:
        uid = user_id(h)
        r = requests.post(f"{API}/users/{me}/following", json={"target_user_id": uid},
                          headers={"Authorization": f"Bearer {tok}"}, timeout=30)
        ok = r.status_code == 200
        _mark_followed(h, "api", "ok" if ok else f"http{r.status_code}")
        res.append({"handle": h, "ok": ok, "status": r.status_code})
        if r.status_code in (402, 403, 429):
            break
        time.sleep(random.uniform(20, 60))
    return res


def follow_browser(handles: list[str], cfg: dict) -> list[dict]:
    from playwright.sync_api import sync_playwright
    st = cfg.get("settings", {})
    cap = int(st.get("x_follow_cap_per_day", 10))
    prof = HOME / "browser" / os.environ.get("X_BROWSER_PROFILE", os.environ.get("BROWSER_PROFILE", "main"))
    if not prof.exists():
        raise SystemExit(f"no logged-in browser profile at {prof}: human runs browser_session.py login --url https://x.com/login")
    res = []
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(str(prof), headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for h in handles:
            check_kill()
            if not X.budget_take("x_follow", 1, cap):
                res.append({"handle": h, "ok": False, "reason": f"daily cap {cap}"}); break
            page.goto(f"https://x.com/{h}", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(random.randint(2500, 5000))
            if "login" in page.url:
                res.append({"handle": h, "ok": False, "reason": "not logged in"}); break
            btn = page.locator('[data-testid$="-follow"]').first
            if btn.count() == 0:
                state = "already/unknown" if page.locator('[data-testid$="-unfollow"]').count() else "button not found"
                _mark_followed(h, "browser", "ok" if state.startswith("already") else state)
                res.append({"handle": h, "ok": state.startswith("already"), "reason": state})
            else:
                btn.click(); page.wait_for_timeout(random.randint(1500, 3000))
                _mark_followed(h, "browser", "ok"); res.append({"handle": h, "ok": True})
            time.sleep(random.uniform(40, 120))
        ctx.close()
    return res


def follow(cfg: dict, handles: list[str] | None) -> dict:
    hs = handles or [a["handle"] for a in cfg.get("x_accounts", []) if a.get("follow")]
    hs = [re.sub(r"[^A-Za-z0-9_]", "", h) for h in hs]
    hs = [h for h in hs if h and not _already(h)]
    if not hs:
        return {"follow": "nothing to do"}
    if os.environ.get("X_API_FOLLOW_MODE", "").lower() == "enterprise":
        return {"mode": "api", "result": follow_api(hs)}
    if os.environ.get("X_BROWSER_FOLLOW_OPTIN") == OPTIN:
        return {"mode": "browser", "result": follow_browser(hs, cfg)}
    P._notify("👤 Follow manual di X (API follow = Enterprise only; browser follow belum opt-in):\n"
              + "\n".join(f"https://x.com/{h}" for h in hs))
    return {"mode": "manual", "sent_to_telegram": hs}


def main() -> None:
    check_kill()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("poll"); p.add_argument("--dry-run", action="store_true")
    f = sp.add_parser("follow"); f.add_argument("--handle", nargs="*")
    sp.add_parser("budget")
    a = ap.parse_args()
    cfg = load_yaml(CFG)
    if a.cmd == "poll":
        out(poll(cfg, a.dry_run))
    elif a.cmd == "follow":
        out(follow(cfg, a.handle))
    else:
        out({"x_reads_today": X.budget_used("x_reads"), "x_follow_today": X.budget_used("x_follow"),
             "cap_reads": cfg.get("settings", {}).get("x_max_reads_per_day", 300)})


if __name__ == "__main__":
    main()
