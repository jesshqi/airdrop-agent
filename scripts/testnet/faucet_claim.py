#!/usr/bin/env python3
"""Testnet faucet claimer (template). Faucets are declared per project in projects.yaml:

  faucets:
    - name: example-http
      type: http                      # http | web | telegram | manual
      url: https://faucet.example.org/api/claim
      method: POST
      json: {address: "${ADDRESS}", network: "sepolia"}
      cooldown_hours: 24
    - name: example-web
      type: web
      steps: ~/.airdrop-agent/quests/example_faucet.yaml   # ${ENV:FAUCET_ADDRESS} available
      cooldown_hours: 24
    - name: example-tg
      type: telegram
      bot: "@ExampleFaucetBot"
      text: "/faucet ${ADDRESS}"
      cooldown_hours: 24
    - name: needs-github-and-captcha
      type: manual                    # sends a Telegram hand-off with the link
      url: https://faucet.example.org
      cooldown_hours: 24

Captcha: NOT bypassed. web type waits for a human via VNC; http type marks blocked.
Optional legit solver (opt-in): set CAPTCHA_SOLVER=... and implement solve() yourself — check the faucet ToS first.

usage: faucet_claim.py --project example-testnet [--label main-burner] [--force]
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl; _sys.path[:0] = [str(_d) for _d in sorted(_pl.Path(__file__).resolve().parents[1].iterdir()) if _d.is_dir() and not _d.name.startswith(("_", "."))]  # noqa: E702 (script-group import path)

import argparse
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

import requests

from common import check_kill, get_logger, load_projects, out, script
import task_queue as tq
import vault

log = get_logger("faucet")
HERE = Path(__file__).parent


def _db():
    con = tq.db()
    con.execute("CREATE TABLE IF NOT EXISTS faucet_claims(project TEXT, faucet TEXT, at TEXT, status TEXT, detail TEXT)")
    return con


def last_ok(project: str, faucet: str):
    with _db() as con:
        r = con.execute("SELECT at FROM faucet_claims WHERE project=? AND faucet=? AND status='ok' ORDER BY at DESC LIMIT 1",
                        (project, faucet)).fetchone()
    return dt.datetime.fromisoformat(r["at"]) if r else None


def record(project, faucet, status, detail=""):
    with _db() as con:
        con.execute("INSERT INTO faucet_claims VALUES(?,?,?,?,?)", (project, faucet, tq.now(), status, str(detail)[:500]))


def sub(obj, addr):
    if isinstance(obj, str):
        return obj.replace("${ADDRESS}", addr)
    if isinstance(obj, dict):
        return {k: sub(v, addr) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sub(v, addr) for v in obj]
    return obj


def claim(project: dict, f: dict, addr: str) -> tuple[str, str]:
    t = f.get("type", "manual")
    if t == "http":
        r = requests.request(f.get("method", "POST"), f["url"], json=sub(f.get("json"), addr),
                             headers=f.get("headers"), timeout=60)
        body = r.text[:300]
        if "captcha" in body.lower():
            return "blocked", "faucet requires captcha -> manual"
        return ("ok" if r.ok else "fail"), f"HTTP {r.status_code} {body}"
    if t == "web":
        env = dict(os.environ, FAUCET_ADDRESS=addr)
        r = subprocess.run([sys.executable, script("web_quest.py"), "run", "--steps", os.path.expanduser(f["steps"])],
                           env=env, capture_output=True, text=True)
        return ("ok" if r.returncode == 0 else "fail"), (r.stdout or r.stderr)[-400:]
    if t == "telegram":
        r = subprocess.run([sys.executable, script("tg_tasks.py"), "send", f["bot"], sub(f["text"], addr)],
                           capture_output=True, text=True)
        return ("ok" if r.returncode == 0 else "fail"), (r.stdout or r.stderr)[-400:]
    from report_telegram import send
    send(f"🚰 Faucet manual: <b>{project['id']}</b> / {f['name']}\n{f.get('url','')}\nAlamat: <code>{addr}</code>\n"
         f"Syarat: {', '.join(f.get('requires', [])) or '-'}")
    return "blocked", "manual hand-off sent"


def main() -> None:
    check_kill()
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--label")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    proj = next((p for p in load_projects().get("projects", []) if p["id"] == a.project), None)
    if not proj:
        raise SystemExit("project not found")
    addr = vault.address(a.label or proj.get("wallet_label", "main-burner"))
    results = []
    for f in proj.get("faucets", []):
        check_kill()
        last = last_ok(proj["id"], f["name"])
        cd = dt.timedelta(hours=f.get("cooldown_hours", 24))
        if last and not a.force and dt.datetime.fromisoformat(tq.now()) - last < cd:
            results.append({"faucet": f["name"], "status": "cooldown", "next": str(last + cd)}); continue
        try:
            status, detail = claim(proj, f, addr)
        except Exception as e:
            status, detail = "fail", str(e)
        record(proj["id"], f["name"], status, detail)
        results.append({"faucet": f["name"], "status": status, "detail": detail[:200]})
    out({"project": proj["id"], "address": addr, "results": results})


if __name__ == "__main__":
    main()
