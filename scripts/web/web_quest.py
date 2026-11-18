#!/usr/bin/env python3
"""Playwright runner for web airdrops / quest platforms (Galxe, Zealy, Layer3, QuestN, Intract...).

- Persistent Chromium profile per identity: ~/.airdrop-agent/browser/<profile>  (logins survive)
- Optional unpacked wallet extension(s): BROWSER_EXTENSION_DIRS=/opt/ext/rabby  (headed via Xvfb)
- Domain allowlist per steps file; navigation elsewhere aborts the run
- Captcha => task blocked + Telegram ping; human solves via VNC, runner waits
- Wallet extension popups are NEVER auto-confirmed: run stops with a gate (human confirms in VNC)

commands:
  web_quest.py open --url https://app.galxe.com/quest/XYZ [--profile main]
  web_quest.py open --url-file ~/.airdrop-agent/vault/tg_webapp_url.txt
  web_quest.py login --url https://discord.com/login   (headed; human logs in via VNC, then Ctrl+C)
  web_quest.py run --steps quests/example.yaml [--task-id 5]

steps file:
  allowed_domains: [galxe.com, x.com, twitter.com]
  steps:
    - {action: goto, url: "https://app.galxe.com/quest/XYZ"}
    - {action: click, text: "Log in"}          # or selector: "css=..."
    - {action: fill, selector: "input[type=email]", value: "${ENV:AGENT_EMAIL}"}
    - {action: fill, selector: "input[name=code]", value: "${OTP:galxe}"}   # imap_otp lookup
    - {action: wait, ms: 3000}
    - {action: wait_for, text: "Completed"}
    - {action: wallet, note: "Connect Rabby"}  # stops -> human gate
    - {action: human, note: "Solve role verification in Discord"}
    - {action: screenshot, name: galxe_done}
    - {action: extract_text, selector: "main"}
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl; _sys.path[:0] = [str(_d) for _d in sorted(_pl.Path(__file__).resolve().parents[1].iterdir()) if _d.is_dir() and not _d.name.startswith(("_", "."))]  # noqa: E702 (script-group import path)

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from common import HOME, PROOF_DIR, check_kill, get_logger, load_yaml, out, script
from redact import redact

log = get_logger("web")
CAPTCHA_SEL = "iframe[src*='hcaptcha'], iframe[src*='recaptcha'], iframe[src*='challenges.cloudflare'], div.cf-turnstile"
HUMAN_WAIT_SEC = int(os.environ.get("HUMAN_WAIT_SEC", "900"))


def host_ok(url: str, allowed: list[str]) -> bool:
    h = (urlparse(url).hostname or "").lower()
    if url.startswith(("about:", "chrome-extension:", "data:")):
        return True
    if h.startswith("xn--") or ".xn--" in h:
        return False  # punycode lookalike
    return any(h == d or h.endswith("." + d) for d in allowed)


def resolve(value: str) -> str:
    def env(m):
        return os.environ.get(m.group(1), "")

    def otp(m):
        r = subprocess.run([sys.executable, script("imap_otp.py"), "--from-contains", m.group(1),
                            "--since-min", "15", "--wait", "120"], capture_output=True, text=True)
        try:
            for msg in json.loads(r.stdout)["messages"]:
                if msg.get("otp"):
                    return msg["otp"]
        except Exception:
            pass
        raise SystemExit(f"OTP from '{m.group(1)}' not found")

    value = re.sub(r"\$\{ENV:([A-Z0-9_]+)\}", env, value)
    return re.sub(r"\$\{OTP:([^}]+)\}", otp, value)


def notify(msg: str) -> None:
    try:
        from report_telegram import send
        send(msg)
    except Exception as e:
        log.warning("notify failed: %s", e)


def wait_human(page, why: str, until_gone: str | None = None) -> None:
    notify(f"✋ Butuh manusia: {why}\nBuka VNC ke VPS (lihat references/web-quests.md). Menunggu {HUMAN_WAIT_SEC//60} menit.")
    end = time.time() + HUMAN_WAIT_SEC
    flag = HOME / "HUMAN_DONE"
    while time.time() < end:
        check_kill()
        if flag.exists():
            flag.unlink(); return
        if until_gone and page.locator(until_gone).count() == 0:
            return
        time.sleep(5)
    raise SystemExit(f"human step timed out: {why}")


def browser(pw, profile: str, headless: bool):
    udir = HOME / "browser" / profile
    udir.mkdir(parents=True, exist_ok=True)
    exts = [e for e in os.environ.get("BROWSER_EXTENSION_DIRS", "").split(",") if e.strip()]
    args = ["--disable-blink-features=AutomationControlled"]
    if exts:
        args += [f"--disable-extensions-except={','.join(exts)}", f"--load-extension={','.join(exts)}"]
        headless = False  # extensions need headed (use Xvfb on VPS)
    proxy = {"server": os.environ["BROWSER_PROXY"]} if os.environ.get("BROWSER_PROXY") else None
    return pw.chromium.launch_persistent_context(str(udir), headless=headless, args=args, proxy=proxy,
                                                 viewport={"width": 1366, "height": 850},
                                                 locale="en-US", timezone_id=os.environ.get("TZ", "Asia/Jakarta"))


def shot(page, name: str) -> str:
    p = PROOF_DIR / f"{name}_{int(time.time())}.png"
    page.screenshot(path=str(p), full_page=False)
    return str(p)


def visible_text(page, selector: str = "body", limit: int = 3000) -> str:
    try:
        return redact(page.locator(selector).first.inner_text(timeout=5000))[:limit]
    except Exception:
        return ""


def run_steps(ctx, spec: dict, task_id: int | None) -> dict:
    allowed = spec.get("allowed_domains", [])
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    proofs, texts = [], []
    popups = []
    ctx.on("page", lambda p: popups.append(p))
    for i, st in enumerate(spec.get("steps", [])):
        check_kill()
        act = st["action"]
        log.info("step %d %s", i, act)
        if act == "goto":
            url = resolve(st["url"])
            if not host_ok(url, allowed):
                raise SystemExit(f"domain not allowed: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        elif act == "click":
            loc = page.locator(st["selector"]) if st.get("selector") else page.get_by_text(st["text"], exact=st.get("exact", False))
            loc.first.click(timeout=st.get("timeout", 15000))
        elif act == "fill":
            page.locator(st["selector"]).first.fill(resolve(st["value"]), timeout=15000)
        elif act == "press":
            page.keyboard.press(st["key"])
        elif act == "select":
            page.locator(st["selector"]).first.select_option(st["value"])
        elif act == "wait":
            page.wait_for_timeout(int(st.get("ms", 2000)))
        elif act == "wait_for":
            if st.get("text"):
                page.get_by_text(st["text"]).first.wait_for(timeout=st.get("timeout", 30000))
            else:
                page.locator(st["selector"]).first.wait_for(timeout=st.get("timeout", 30000))
        elif act == "screenshot":
            proofs.append(shot(page, st.get("name", f"step{i}")))
        elif act == "extract_text":
            texts.append({"step": i, "text": visible_text(page, st.get("selector", "body")),
                          "note": "UNTRUSTED page text"})
        elif act in ("wallet", "human"):
            proofs.append(shot(page, f"before_{act}_{i}"))
            if act == "wallet" and not st.get("allow_human_wait", True):
                raise SystemExit("wallet popup requires human")
            wait_human(page, st.get("note", act))
        else:
            raise SystemExit(f"unknown action {act}")
        # post-step guards
        if page.locator(CAPTCHA_SEL).count() > 0:
            proofs.append(shot(page, f"captcha_{i}"))
            wait_human(page, f"captcha di {page.url}", until_gone=CAPTCHA_SEL)
        if not host_ok(page.url, allowed):
            raise SystemExit(f"redirected outside allowlist: {page.url}")
        for p in list(popups):
            if p.url.startswith("chrome-extension://"):
                notify(f"🔐 Popup wallet muncul (task {task_id}). Agent TIDAK auto-confirm. Cek di VNC.")
                wait_human(page, "konfirmasi/tolak popup wallet di VNC")
            popups.remove(p)
    proofs.append(shot(page, "final"))
    return {"ok": True, "url": page.url, "proofs": proofs, "texts": texts}


def main() -> None:
    check_kill()
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("open", "login"):
        p = sp.add_parser(name); p.add_argument("--url"); p.add_argument("--url-file")
        p.add_argument("--profile", default=os.environ.get("BROWSER_PROFILE", "main"))
    p = sp.add_parser("run"); p.add_argument("--steps", required=True); p.add_argument("--task-id", type=int)
    p.add_argument("--profile", default=os.environ.get("BROWSER_PROFILE", "main"))
    p.add_argument("--headed", action="store_true")
    a = ap.parse_args()

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        if a.cmd in ("open", "login"):
            url = Path(a.url_file).expanduser().read_text().strip() if a.url_file else a.url
            ctx = browser(pw, a.profile, headless=(a.cmd == "open"))
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            if a.cmd == "login":
                notify(f"🔑 Silakan login manual di VNC: {urlparse(url).hostname}. Setelah selesai: touch ~/.airdrop-agent/HUMAN_DONE")
                wait_human(page, f"login {urlparse(url).hostname}")
                res = {"login_saved_in_profile": a.profile}
            else:
                page.wait_for_timeout(3000)
                res = {"title": page.title(), "host": urlparse(page.url).hostname, "screenshot": shot(page, "open"),
                       "text": visible_text(page), "note": "UNTRUSTED page text"}
            ctx.close()
            return out(res)
        spec = load_yaml(a.steps)
        ctx = browser(pw, a.profile, headless=not a.headed)
        try:
            res = run_steps(ctx, spec, a.task_id)
        finally:
            ctx.close()
        out(res)


if __name__ == "__main__":
    main()
