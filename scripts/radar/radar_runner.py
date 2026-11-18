#!/usr/bin/env python3
"""Radar orchestrator.

  radar_runner.py run                  long-running: TG listener (child) + X poll every N min + daily TG join
                                       + executes approved simple radar tasks (telegram join/start, x follow)
  radar_runner.py once                 one X poll + one TG backfill (cron-friendly)
  radar_runner.py status               candidates, queue, budgets, RISK mode
  radar_runner.py dry-run --file F [--write] [--risk on|off]
                                       offline: no network, no Telegram. Default uses a throw-away sandbox
                                       (~/.airdrop-agent/radar-sandbox) seeded with your config; --write = real queue.
  radar_runner.py exec [--limit 5]     run pending simple radar tasks once

Env: RADAR_TG_SYNC=1 -> run also polls Telegram approvals (task_queue sync, includes /risk on|off). Leave 0 if the
report bot token is polled by another bot (getUpdates conflict) and run `task_queue.py sync` elsewhere.
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl; _sys.path[:0] = [str(_d) for _d in sorted(_pl.Path(__file__).resolve().parents[1].iterdir()) if _d.is_dir() and not _d.name.startswith(("_", "."))]  # noqa: E702 (script-group import path)

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from common import HOME, KILL_FILE, SKILL_DIR, check_kill, get_logger, load_yaml, out, script

log = get_logger("radar.runner")
CFG = os.environ.get("RADAR_SOURCES_FILE", str(HOME / "radar_sources.yaml"))


def load_cfg() -> dict:
    p = Path(CFG)
    if not p.exists():
        p = SKILL_DIR / "templates" / "radar_sources.yaml"
    return load_yaml(p)


def parse_sample(path: str, cfg: dict) -> list[dict]:
    trust = {("tg:" + s["target"]).lower(): s.get("trust", 0.5) for s in cfg.get("telegram", [])}
    trust.update({("x:@" + a["handle"]).lower(): a.get("trust", 0.5) for a in cfg.get("x_accounts", [])})
    posts, cur = [], None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        m = re.match(r"^=== source=(\S+) id=(\S+)", line)
        if m:
            cur = {"source": m.group(1), "post_id": m.group(2), "text": "", "url": f"sample://{m.group(1)}/{m.group(2)}",
                   "trust": float(trust.get(m.group(1).lower(), 0.5))}
            posts.append(cur)
        elif cur is not None:
            cur["text"] += line + "\n"
    return posts


def sandbox_reexec(a) -> None:
    """Re-run this command with AIRDROP_HOME pointing to a fresh sandbox (real queue untouched)."""
    sb = HOME / "radar-sandbox"
    shutil.rmtree(sb, ignore_errors=True)
    sb.mkdir(parents=True)
    for name in ("policy.yaml", "projects.yaml", "radar_sources.yaml", "allowlist_domains.txt"):
        src = HOME / name if (HOME / name).exists() else SKILL_DIR / "templates" / name
        if src.exists():
            shutil.copy(src, sb / name)
    env = {**os.environ, "AIRDROP_HOME": str(sb), "RADAR_SANDBOX": "1", "RADAR_DRY_RUN": "1",
           "RADAR_SOURCES_FILE": str(sb / "radar_sources.yaml")}
    env.pop("TG_REPORT_BOT_TOKEN", None)  # belt and braces: no Telegram from a dry-run
    os.execve(sys.executable, [sys.executable, __file__, *sys.argv[1:]], env)


def dry_run(a) -> None:
    os.environ["RADAR_DRY_RUN"] = "1"
    import risk_mode as RM
    if a.risk:
        RM.set_mode(a.risk, "dry-run", 1)
    import pipeline as P
    import task_queue as tq
    cfg = load_cfg()
    res = [P.process_post(p, cfg, live=False, offline=True) for p in parse_sample(a.file, cfg)]
    with tq.db() as con:
        tasks = [dict(r) for r in con.execute(
            "SELECT id, project_id, step_key, type, status, params FROM tasks WHERE project_id LIKE 'radar-%' ORDER BY id")]
        gates = [dict(r) for r in con.execute("SELECT id, kind, status, task_id, summary FROM gates ORDER BY id")]
    for g in gates:
        g["summary"] = g["summary"].splitlines()[0][:120]
    allow = (HOME / "allowlist_domains.txt")
    out({"home": str(HOME), "sandbox": bool(os.environ.get("RADAR_SANDBOX")), "risk_mode": RM.state(),
         "decisions": [{k: v for k, v in r.items() if k != "digest"} for r in res],
         "digests": [r["digest"] for r in res if r.get("digest")],
         "queue_tasks": tasks, "gates": gates,
         "allowlist_domains": allow.read_text().split() if allow.exists() else []})


def status() -> None:
    import extract as X
    import risk_mode as RM
    import task_queue as tq
    with X.db() as con:
        by = [dict(r) for r in con.execute("SELECT status, risk, COUNT(*) n FROM candidates GROUP BY status, risk")]
        last = [dict(r) for r in con.execute(
            "SELECT id, project, task_type, risk, score, status, primary_url FROM candidates ORDER BY id DESC LIMIT 10")]
        joined = con.execute("SELECT COUNT(*) FROM joined WHERE status='ok'").fetchone()[0]
        followed = con.execute("SELECT COUNT(*) FROM followed WHERE status='ok'").fetchone()[0]
    with tq.db() as con:
        q = [dict(r) for r in con.execute(
            "SELECT status, COUNT(*) n FROM tasks WHERE project_id LIKE 'radar-%' GROUP BY status")]
        gp = con.execute("SELECT COUNT(*) FROM gates WHERE status='pending'").fetchone()[0]
    out({"risk_mode": RM.state(), "candidates": by, "latest": last, "radar_tasks": q, "pending_gates": gp,
         "tg_joined": joined, "x_followed": followed,
         "budget_today": {k: X.budget_used(k) for k in ("tg_join", "x_reads", "x_follow")}})


def exec_simple(limit: int = 5) -> list[dict]:
    """Run approved ('pending') radar tasks that need no browser/wallet: telegram join/start, x follow."""
    import task_queue as tq
    import risk_mode as RM
    done = []
    with tq.db() as con:
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM tasks WHERE status='pending' AND project_id LIKE 'radar-%' AND type IN ('telegram','x') "
            "ORDER BY id LIMIT ?", (limit,))]
    for t in rows:
        check_kill()
        p = json.loads(t["params"] or "{}")
        if t["type"] == "telegram":
            cmd = [sys.executable, script("tg_tasks.py"), p.get("action", "join"), p.get("peer", "")]
            if p.get("action") == "start" and p.get("ref"):
                cmd += ["--ref", p["ref"]]
        else:
            cmd = [sys.executable, script("x_radar.py"), "follow", "--handle", p.get("handle", "")]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        ok = r.returncode == 0
        with tq.db() as con:
            con.execute("UPDATE tasks SET status=?, updated_at=? WHERE id=?", ("done" if ok else "failed", time.time(), t["id"]))
        done.append({"id": t["id"], "key": t["step_key"], "ok": ok})
        if RM.is_on():
            RM.report(f"task {t['step_key']} {'done' if ok else 'FAILED'}", t["project_id"], {"type": t["type"]})
        time.sleep(30)
    return done


def run() -> None:
    import x_radar
    import tg_radar  # noqa: F401  (import check)
    cfg = load_cfg()
    st = cfg.get("settings", {})
    x_every = int((st.get("poll_interval_min") or {}).get("x", 30)) * 60
    child = None
    if cfg.get("telegram") and os.environ.get("TG_API_ID"):
        child = subprocess.Popen([sys.executable, script("tg_radar.py"), "listen"])
    last_x = last_join = last_sync = 0.0
    try:
        while not KILL_FILE.exists():
            now = time.time()
            if child and child.poll() is not None:
                log.warning("tg listener exited (%s), restarting in 60s", child.returncode)
                time.sleep(60); child = subprocess.Popen([sys.executable, script("tg_radar.py"), "listen"])
            if now - last_join > 86400 and cfg.get("telegram") and os.environ.get("TG_API_ID"):
                subprocess.run([sys.executable, script("tg_radar.py"), "join"], timeout=7200); last_join = now
            if now - last_x > x_every and (cfg.get("x_accounts") or cfg.get("x_queries")) and os.environ.get("X_BEARER_TOKEN"):
                try:
                    r = x_radar.poll(cfg); log.info("x poll: %d items, %s", len(r["processed"]), r["errors"][:2])
                except Exception as e:
                    log.warning("x poll failed: %s", e)
                last_x = now
            if os.environ.get("RADAR_TG_SYNC") == "1" and now - last_sync > 60:
                try:
                    import task_queue as tq
                    tq.sync_telegram_approvals()
                except Exception as e:
                    log.warning("sync failed: %s", e)
                last_sync = now
            exec_simple()
            time.sleep(30)
    finally:
        if child and child.poll() is None:
            child.terminate()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("run"); sp.add_parser("once"); sp.add_parser("status")
    e = sp.add_parser("exec"); e.add_argument("--limit", type=int, default=5)
    d = sp.add_parser("dry-run"); d.add_argument("--file", default=str(SKILL_DIR / "templates" / "sample_radar_posts.txt"))
    d.add_argument("--write", action="store_true"); d.add_argument("--risk", choices=["on", "off"])
    a = ap.parse_args()
    if a.cmd == "dry-run":
        if not a.write and not os.environ.get("RADAR_SANDBOX"):
            sandbox_reexec(a)
        return dry_run(a)
    check_kill()
    if a.cmd == "status":
        return status()
    if a.cmd == "exec":
        return out(exec_simple(a.limit))
    if a.cmd == "once":
        import x_radar
        cfg = load_cfg()
        res = {"x": x_radar.poll(cfg) if os.environ.get("X_BEARER_TOKEN") else "skipped (no X_BEARER_TOKEN)"}
        if cfg.get("telegram") and os.environ.get("TG_API_ID"):
            r = subprocess.run([sys.executable, script("tg_radar.py"), "backfill", "--limit", "20"], capture_output=True, text=True)
            res["tg"] = r.stdout[-2000:] or r.stderr[-300:]
        return out(res)
    run()


if __name__ == "__main__":
    main()
