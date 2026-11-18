#!/usr/bin/env python3
"""Daily check-in runner for every active project with a `checkin:` block in projects.yaml.

checkin types:
  web:      {type: web, steps: ~/.airdrop-agent/quests/<p>_checkin.yaml}
  telegram: {type: telegram, bot: "@Bot", click: "Check-in"}      # or start: true / send: "/daily"
  tx:       {type: tx, chain: sepolia, txs: 1}                      # testnet_daily
  faucet:   {type: faucet}                                          # faucet_claim for the project
  command:  {type: command, cmd: ["python", "my_custom.py"]}        # your own script

Random jitter before start and between projects (CHECKIN_JITTER_MIN, default 25).
Streaks stored in SQLite; summary sent to Telegram topic.

usage: checkin_runner.py [--project ID] [--no-jitter] [--dry-run]
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl; _sys.path[:0] = [str(_d) for _d in sorted(_pl.Path(__file__).resolve().parents[1].iterdir()) if _d.is_dir() and not _d.name.startswith(("_", "."))]  # noqa: E702 (script-group import path)

import argparse
import os
import random
import subprocess
import sys
import time
from pathlib import Path

from common import check_kill, get_logger, load_projects, out, script
import task_queue as tq

log = get_logger("checkin")
HERE = Path(__file__).parent
PY = sys.executable


def run(cmd: list[str], timeout: int = 1200) -> tuple[bool, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout or r.stderr)[-300:]
    except subprocess.TimeoutExpired:
        return False, "timeout"


def do_checkin(p: dict) -> tuple[bool, str]:
    c = p["checkin"]
    t = c.get("type")
    label = p.get("wallet_label", "main-burner")
    if t == "web":
        return run([PY, script("web_quest.py"), "run", "--steps", os.path.expanduser(c["steps"])])
    if t == "telegram":
        if c.get("start"):
            ok, msg = run([PY, script("tg_tasks.py"), "start", c["bot"]])
            if not ok:
                return ok, msg
        if c.get("send"):
            return run([PY, script("tg_tasks.py"), "send", c["bot"], c["send"]])
        if c.get("click"):
            ok, msg = run([PY, script("tg_tasks.py"), "click", c["bot"], c["click"]])
            return ok and '"clicked": null' not in msg, msg
        return True, "started"
    if t == "tx":
        return run([PY, script("testnet_daily.py"), "--chain", c.get("chain", p.get("chain")), "--label", label,
                    "--txs", str(c.get("txs", 1))])
    if t == "faucet":
        return run([PY, script("faucet_claim.py"), "--project", p["id"]])
    if t == "command":
        return run([os.path.expanduser(x) for x in c["cmd"]])
    return False, f"unknown checkin type {t}"


def main() -> None:
    check_kill()
    ap = argparse.ArgumentParser()
    ap.add_argument("--project"); ap.add_argument("--no-jitter", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    jitter = int(os.environ.get("CHECKIN_JITTER_MIN", "25")) * 60
    projects = [p for p in load_projects().get("projects", [])
                if p.get("status", "active") == "active" and p.get("checkin") and (not a.project or p["id"] == a.project)]
    random.shuffle(projects)
    if not a.no_jitter and not a.dry_run:
        time.sleep(random.uniform(0, jitter))
    lines, results = [], []
    for p in projects:
        check_kill()
        if tq.checked_in_today(p["id"]):
            results.append({"project": p["id"], "status": "already"}); continue
        if a.dry_run:
            results.append({"project": p["id"], "would_run": p["checkin"]}); continue
        ok, detail = do_checkin(p)
        tq.record_checkin(p["id"], "ok" if ok else "fail", {"detail": detail})
        s = tq.streak(p["id"])
        lines.append(f"{'✅' if ok else '❌'} {p.get('name', p['id'])} — streak {s} hari" + ("" if ok else f"\n   ↳ {detail[-120:]}"))
        results.append({"project": p["id"], "ok": ok, "streak": s})
        if not a.no_jitter:
            time.sleep(random.uniform(30, 180))
    if lines:
        try:
            from report_telegram import send
            send("🗓️ <b>Daily check-in</b> " + tq.today() + "\n" + "\n".join(lines))
        except Exception as e:
            log.warning("report failed: %s", e)
    out(results)


if __name__ == "__main__":
    main()
