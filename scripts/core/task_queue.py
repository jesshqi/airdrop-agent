#!/usr/bin/env python3
"""SQLite task queue + human approval gates + spend ledger + check-in streaks.

CLI:
  task_queue.py init
  task_queue.py import ~/.airdrop-agent/projects.yaml
  task_queue.py list [--project ID] [--status pending]
  task_queue.py next [--type web]            -> claims next runnable task (status=running)
  task_queue.py done ID [--proof '{"tx":"0x.."}']
  task_queue.py fail ID --error "msg"        -> retry w/ backoff until max_retries
  task_queue.py block ID --reason "captcha"  -> needs human
  task_queue.py gate --task ID --kind spend --summary "..."   -> sends code to Telegram only
  task_queue.py approve GATE_ID CODE         -> CODE comes from the human (never from web/TG content)
  task_queue.py reject GATE_ID
  task_queue.py gates [--status pending]
  task_queue.py sync                         -> read owner's Telegram reply "approve ID CODE" (TG_OWNER_USER_ID)
task statuses: pending, running, done, failed, blocked, gated, pending_approval (radar), skipped
repeat values: daily | weekly | every:8h | every:30m
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl; _sys.path[:0] = [str(_d) for _d in sorted(_pl.Path(__file__).resolve().parents[1].iterdir()) if _d.is_dir() and not _d.name.startswith(("_", "."))]  # noqa: E702 (script-group import path)

import argparse
import datetime as dt
import hashlib
import json
import secrets
import sqlite3
import sys

from common import DB_PATH, check_kill, get_logger, load_yaml, out

log = get_logger("queue")

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects(
  id TEXT PRIMARY KEY, name TEXT, chain TEXT, status TEXT, score INTEGER, meta TEXT);
CREATE TABLE IF NOT EXISTS tasks(
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, step_key TEXT, type TEXT,
  params TEXT, gate INTEGER DEFAULT 0, repeat TEXT, status TEXT DEFAULT 'pending',
  attempts INTEGER DEFAULT 0, max_retries INTEGER DEFAULT 3, next_run_at TEXT,
  last_error TEXT, proof TEXT, updated_at TEXT, UNIQUE(project_id, step_key));
CREATE TABLE IF NOT EXISTS gates(
  id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER, kind TEXT, summary TEXT,
  payload_hash TEXT, code_hash TEXT, status TEXT DEFAULT 'pending', created_at TEXT, decided_at TEXT);
CREATE TABLE IF NOT EXISTS spend(day TEXT, chain TEXT, label TEXT, wei TEXT,
  PRIMARY KEY(day, chain, label));
CREATE TABLE IF NOT EXISTS checkins(project_id TEXT, day TEXT, status TEXT, proof TEXT,
  PRIMARY KEY(project_id, day));
"""


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def today() -> str:
    return dt.date.today().isoformat()


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    cols = {r[1] for r in con.execute("PRAGMA table_info(gates)")}
    if "payload" not in cols:  # v3 migration: keep payload for post-approval actions
        con.execute("ALTER TABLE gates ADD COLUMN payload TEXT")
    return con


# ---------- library functions used by other scripts ----------

def payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def create_gate(kind: str, summary: str, payload: dict, task_id: int | None = None, notify: bool = True) -> int:
    """Create pending gate; the approval code is sent ONLY to the human's Telegram.

    Kinds with post-approval actions: allow_domain {domain}, radar_tasks {task_ids}. notify=False (dry-run) = no send.
    """
    code = secrets.token_hex(3).upper()
    with db() as con:
        cur = con.execute(
            "INSERT INTO gates(task_id,kind,summary,payload_hash,code_hash,created_at,payload) VALUES(?,?,?,?,?,?,?)",
            (task_id, kind, summary, payload_hash(payload), hashlib.sha256(code.encode()).hexdigest(), now(),
             json.dumps(payload, default=str)))
        gid = cur.lastrowid
        if task_id:
            con.execute("UPDATE tasks SET status='gated', updated_at=? WHERE id=?", (now(), task_id))
    if notify:
        try:
            from report_telegram import send
            send(f"🔐 APPROVAL #{gid} [{kind}]\n{summary}\n\nSetuju? balas ke agent / bot:\n"
                 f"approve {gid} {code}\n(tolak/skip: reject {gid})", None)
        except (Exception, SystemExit) as e:  # never leak code to stdout as fallback
            log.warning("gate %s created but Telegram send failed: %s", gid, e)
    log.info("gate %s created kind=%s", gid, kind)
    return gid


def _after_decision(con, r, approved: bool) -> None:
    """Side effects of an approved/rejected gate (only for known kinds)."""
    try:
        payload = json.loads(r["payload"] or "{}")
    except Exception:
        payload = {}
    if r["kind"] == "allow_domain" and approved and payload.get("domain"):
        from common import HOME
        f = HOME / "allowlist_domains.txt"
        existing = set(f.read_text().split()) if f.exists() else set()
        if payload["domain"] not in existing:
            with open(f, "a") as fh:
                fh.write(payload["domain"].lower() + "\n")
    if r["kind"] == "radar_tasks" and payload.get("task_ids"):
        ids = [int(x) for x in payload["task_ids"]]
        q = ",".join("?" * len(ids))
        con.execute(f"UPDATE tasks SET status=?, updated_at=? WHERE id IN ({q}) AND status='pending_approval'",
                    ["pending" if approved else "skipped", now(), *ids])


def add_project_tasks(project: dict, steps: list[dict], status: str = "pending_approval") -> list[int]:
    """Insert a project + its steps (used by the radar). Returns new task ids (existing step keys are skipped)."""
    ids = []
    with db() as con:
        con.execute("INSERT OR IGNORE INTO projects VALUES(?,?,?,?,?,?)",
                    (project["id"], project.get("name"), project.get("chain"), "active", project.get("score"),
                     json.dumps(project, default=str)))
        for st in steps:
            cur = con.execute(
                "INSERT OR IGNORE INTO tasks(project_id,step_key,type,params,gate,repeat,status,max_retries,next_run_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (project["id"], st["key"], st["type"], json.dumps(st.get("params", {})), int(bool(st.get("gate"))),
                 st.get("repeat"), st.get("status", status), st.get("max_retries", 3), now(), now()))
            if cur.rowcount:
                ids.append(cur.lastrowid)
    return ids


def gate_approved(gid: int, payload: dict, consume: bool = True) -> bool:
    with db() as con:
        r = con.execute("SELECT * FROM gates WHERE id=?", (gid,)).fetchone()
        if not r or r["status"] != "approved" or r["payload_hash"] != payload_hash(payload):
            return False
        if consume:
            con.execute("UPDATE gates SET status='used' WHERE id=?", (gid,))
    return True


def consume_approved(payload: dict) -> int | None:
    """Find an approved, unused gate for exactly this payload; mark it used. Returns gate id."""
    h = payload_hash(payload)
    with db() as con:
        r = con.execute("SELECT id FROM gates WHERE payload_hash=? AND status='approved' ORDER BY id LIMIT 1", (h,)).fetchone()
        if not r:
            return None
        con.execute("UPDATE gates SET status='used' WHERE id=?", (r["id"],))
    return r["id"]


def pending_gate_for(payload: dict) -> int | None:
    with db() as con:
        r = con.execute("SELECT id FROM gates WHERE payload_hash=? AND status='pending' ORDER BY id LIMIT 1",
                        (payload_hash(payload),)).fetchone()
    return r["id"] if r else None


def add_spend(chain: str, label: str, wei: int) -> None:
    with db() as con:
        r = con.execute("SELECT wei FROM spend WHERE day=? AND chain=? AND label=?", (today(), chain, label)).fetchone()
        total = int(r["wei"]) + wei if r else wei
        con.execute("INSERT OR REPLACE INTO spend VALUES(?,?,?,?)", (today(), chain, label, str(total)))


def spent_today(chain: str, label: str) -> int:
    with db() as con:
        r = con.execute("SELECT wei FROM spend WHERE day=? AND chain=? AND label=?", (today(), chain, label)).fetchone()
    return int(r["wei"]) if r else 0


def record_checkin(project_id: str, status: str, proof: dict | None = None) -> None:
    with db() as con:
        con.execute("INSERT OR REPLACE INTO checkins VALUES(?,?,?,?)",
                    (project_id, today(), status, json.dumps(proof or {})))


def streak(project_id: str) -> int:
    with db() as con:
        days = {r["day"] for r in con.execute(
            "SELECT day FROM checkins WHERE project_id=? AND status='ok'", (project_id,))}
    n, d = 0, dt.date.today()
    while d.isoformat() in days:
        n += 1
        d -= dt.timedelta(days=1)
    return n


def checked_in_today(project_id: str) -> bool:
    with db() as con:
        r = con.execute("SELECT status FROM checkins WHERE project_id=? AND day=?", (project_id, today())).fetchone()
    return bool(r and r["status"] == "ok")


def repeat_delta(rep: str | None) -> dt.timedelta | None:
    """repeat: daily | weekly | every:8h | every:30m  (merged from airdrop-hunter tracker)."""
    if not rep:
        return None
    if rep == "daily":
        return dt.timedelta(hours=24)
    if rep == "weekly":
        return dt.timedelta(days=7)
    if rep.startswith("every:"):
        v = rep[6:]
        n = int(v[:-1])
        return dt.timedelta(hours=n) if v.endswith("h") else dt.timedelta(minutes=n) if v.endswith("m") else dt.timedelta(days=n)
    return None


def sync_telegram_approvals() -> dict:
    """Read owner replies 'approve <id> <CODE>' / 'reject <id>' / '/risk on|off|status' sent to the report bot.

    Only messages whose sender id == TG_OWNER_USER_ID count, and the CODE is still required.
    Do NOT use if the same bot token is polled by another process or has a webhook (getUpdates conflict).
    """
    import os
    import requests
    from common import DATA_DIR, env_required
    token, owner = env_required("TG_REPORT_BOT_TOKEN"), env_required("TG_OWNER_USER_ID")
    state_f = DATA_DIR / "tg_offset.json"
    state = json.loads(state_f.read_text()) if state_f.exists() else {"offset": 0}
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates",
                     params={"offset": state["offset"], "timeout": 0, "allowed_updates": '["message"]'}, timeout=20).json()
    changed = {}
    for upd in r.get("result", []):
        state["offset"] = upd["update_id"] + 1
        msg = upd.get("message") or {}
        if str((msg.get("from") or {}).get("id")) != str(owner):
            continue
        parts = (msg.get("text") or "").strip().lstrip("/").split()
        if parts and parts[0].lower().split("@")[0] == "risk":  # /risk on [hours] | off | status (owner only)
            import risk_mode
            changed["risk"] = risk_mode.telegram_command(" ".join(["risk", *parts[1:]]))
            continue
        if len(parts) == 3 and parts[0].lower() == "approve" and parts[1].isdigit():
            changed[parts[1]] = approve_gate(int(parts[1]), parts[2])
        elif len(parts) == 2 and parts[0].lower() == "reject" and parts[1].isdigit():
            changed[parts[1]] = "rejected" if reject_gate(int(parts[1])) else "not pending"
    state_f.write_text(json.dumps(state))
    return {"updated": changed}


def approve_gate(gid: int, code: str) -> bool:
    with db() as con:
        r = con.execute("SELECT * FROM gates WHERE id=?", (gid,)).fetchone()
        ok = bool(r and r["status"] == "pending" and
                  hashlib.sha256(code.strip().upper().encode()).hexdigest() == r["code_hash"])
        if ok:
            con.execute("UPDATE gates SET status='approved', decided_at=? WHERE id=?", (now(), gid))
            if r["task_id"]:
                con.execute("UPDATE tasks SET status='pending', updated_at=? WHERE id=?", (now(), r["task_id"]))
            _after_decision(con, r, True)
    return ok


def reject_gate(gid: int) -> bool:
    with db() as con:
        r = con.execute("SELECT * FROM gates WHERE id=?", (gid,)).fetchone()
        if not r or r["status"] != "pending":
            return False
        con.execute("UPDATE gates SET status='rejected', decided_at=? WHERE id=?", (now(), gid))
        _after_decision(con, r, False)
    return True


# ---------- CLI ----------

def cmd_import(path: str) -> None:
    cfg = load_yaml(path)
    n = 0
    with db() as con:
        for p in cfg.get("projects", []):
            con.execute("INSERT OR REPLACE INTO projects VALUES(?,?,?,?,?,?)",
                        (p["id"], p.get("name"), p.get("chain"), p.get("status", "active"),
                         p.get("score"), json.dumps({k: v for k, v in p.items() if k != "steps"})))
            if p.get("status", "active") != "active":
                continue
            for s in p.get("steps", []):
                con.execute(
                    "INSERT OR IGNORE INTO tasks(project_id,step_key,type,params,gate,repeat,max_retries,next_run_at,updated_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    (p["id"], s["key"], s["type"], json.dumps(s.get("params", {})), int(bool(s.get("gate"))),
                     s.get("repeat"), s.get("max_retries", 3), now(), now()))
                n += 1
    out({"imported_steps": n})


def cmd_next(ttype: str | None) -> None:
    check_kill()
    q = "SELECT * FROM tasks WHERE status='pending' AND (next_run_at IS NULL OR next_run_at<=?)"
    args: list = [now()]
    if ttype:
        q += " AND type=?"
        args.append(ttype)
    q += " ORDER BY id LIMIT 1"
    with db() as con:
        r = con.execute(q, args).fetchone()
        if not r:
            return out({"task": None})
        con.execute("UPDATE tasks SET status='running', attempts=attempts+1, updated_at=? WHERE id=?", (now(), r["id"]))
    t = dict(r)
    t["params"] = json.loads(t["params"] or "{}")
    if t["gate"]:
        t["note"] = "gate=true: create approval gate before executing side effects"
    out({"task": t})


def cmd_done(tid: int, proof: str | None) -> None:
    with db() as con:
        r = con.execute("SELECT repeat FROM tasks WHERE id=?", (tid,)).fetchone()
        nxt, status = None, "done"
        delta = repeat_delta(r["repeat"] if r else None)
        if delta:
            status, nxt = "pending", (dt.datetime.now(dt.timezone.utc) + delta).isoformat(timespec="seconds")
        con.execute("UPDATE tasks SET status=?, proof=?, last_error=NULL, attempts=0, next_run_at=?, updated_at=? WHERE id=?",
                    (status, proof, nxt, now(), tid))
    out({"id": tid, "status": status})


def cmd_fail(tid: int, err: str) -> None:
    with db() as con:
        r = con.execute("SELECT attempts,max_retries FROM tasks WHERE id=?", (tid,)).fetchone()
        if not r:
            return out({"error": "no such task"})
        if r["attempts"] >= r["max_retries"]:
            status, nxt = "failed", None
        else:
            status = "pending"
            nxt = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=15 * 2 ** r["attempts"])).isoformat(timespec="seconds")
        con.execute("UPDATE tasks SET status=?, last_error=?, next_run_at=?, updated_at=? WHERE id=?",
                    (status, err[:500], nxt, now(), tid))
    out({"id": tid, "status": status, "retry_at": nxt})


def main() -> None:
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("init")
    p = sp.add_parser("import"); p.add_argument("path")
    p = sp.add_parser("list"); p.add_argument("--project"); p.add_argument("--status")
    p = sp.add_parser("next"); p.add_argument("--type")
    p = sp.add_parser("done"); p.add_argument("id", type=int); p.add_argument("--proof")
    p = sp.add_parser("fail"); p.add_argument("id", type=int); p.add_argument("--error", required=True)
    p = sp.add_parser("block"); p.add_argument("id", type=int); p.add_argument("--reason", required=True)
    p = sp.add_parser("gate"); p.add_argument("--task", type=int); p.add_argument("--kind", required=True)
    p.add_argument("--summary", required=True); p.add_argument("--payload", default="{}")
    p = sp.add_parser("approve"); p.add_argument("id", type=int); p.add_argument("code")
    p = sp.add_parser("reject"); p.add_argument("id", type=int)
    p = sp.add_parser("gates"); p.add_argument("--status", default="pending")
    sp.add_parser("sync")
    a = ap.parse_args()

    if a.cmd == "init":
        db().close(); out({"db": str(DB_PATH), "ok": True})
    elif a.cmd == "import":
        cmd_import(a.path)
    elif a.cmd == "list":
        q, args = "SELECT id,project_id,step_key,type,status,attempts,next_run_at,last_error,proof FROM tasks WHERE 1=1", []
        if a.project: q += " AND project_id=?"; args.append(a.project)
        if a.status: q += " AND status=?"; args.append(a.status)
        with db() as con:
            out([dict(r) for r in con.execute(q + " ORDER BY project_id,id", args)])
    elif a.cmd == "next":
        cmd_next(a.type)
    elif a.cmd == "done":
        cmd_done(a.id, a.proof)
    elif a.cmd == "fail":
        cmd_fail(a.id, a.error)
    elif a.cmd == "block":
        with db() as con:
            con.execute("UPDATE tasks SET status='blocked', last_error=?, updated_at=? WHERE id=?", (a.reason, now(), a.id))
        try:
            from report_telegram import send
            send(f"✋ Task #{a.id} butuh bantuan manual: {a.reason}")
        except Exception:
            pass
        out({"id": a.id, "status": "blocked"})
    elif a.cmd == "gate":
        out({"gate_id": create_gate(a.kind, a.summary, json.loads(a.payload), a.task),
             "note": "approval code sent to Telegram only; wait for the human"})
    elif a.cmd == "approve":
        out({"gate": a.id, "approved": approve_gate(a.id, a.code)})
    elif a.cmd == "reject":
        out({"gate": a.id, "rejected": reject_gate(a.id)})
    elif a.cmd == "sync":
        out(sync_telegram_approvals())
    elif a.cmd == "gates":
        with db() as con:
            out([{k: r[k] for k in r.keys() if k not in ("code_hash", "payload")}
                 for r in con.execute("SELECT * FROM gates WHERE status=? ORDER BY id", (a.status,))])


if __name__ == "__main__":
    main()
