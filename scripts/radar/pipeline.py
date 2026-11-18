#!/usr/bin/env python3
"""Radar pipeline: post -> extract -> dedupe -> scam_check (+research_score) -> score/risk -> tasks + approval gate.

Risk policy (hard rules, config can't loosen them):
  injection attempt / scam_check block      -> no tasks, warning only
  claim / "connect wallet to claim" / unknown-domain + high-risk words -> HIGH: never auto, manual review gate
  every link on known platform or allowlisted domain -> LOW: tasks from templates (pending_approval;
      auto 'pending' only if settings.auto_approve_low_risk AND the task needs no wallet/signature)
  otherwise (new domain) -> MEDIUM: tasks pending_approval + one allow_domain gate per new domain
Approval/skip = task_queue gate codes (Telegram reply "approve ID CODE" / "reject ID", or CLI).
RISK=ON (risk_mode.py): LOW/MEDIUM finds -> all tasks 'pending' (wallet ones too), new domains auto-allowlisted when
  every scam_check == ok, each auto action reported to Telegram. HIGH (drainer heuristic / scam_check != ok /
  injection) is still never automatic.
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl; _sys.path[:0] = [str(_d) for _d in sorted(_pl.Path(__file__).resolve().parents[1].iterdir()) if _d.is_dir() and not _d.name.startswith(("_", "."))]  # noqa: E702 (script-group import path)

import json
import re
import subprocess
import sys
import time

from common import HOME, get_logger, load_policy, script
from redact import redact
import extract as X
import scam_check as S
import task_queue as tq
import risk_mode as RM
import sign_guard as G

log = get_logger("radar.pipeline")
SOCIAL = {"x", "telegram", "discord"}
_digest_times: list[float] = []


def allowlisted(host: str) -> bool:
    allow = [d.lower() for d in load_policy().get("siwe_domain_allowlist", [])]
    f = HOME / "allowlist_domains.txt"
    if f.exists():
        allow += f.read_text().split()
    return any(host == d or host.endswith("." + d) for d in allow)


def known_platform(host: str, platforms: dict) -> bool:
    return any(host == d or host.endswith("." + d) for d in platforms)


def fill(obj, ctx: dict):
    if isinstance(obj, str):
        for k, v in ctx.items():
            obj = obj.replace("{" + k + "}", str(v or ""))
        return obj
    if isinstance(obj, dict):
        return {k: fill(v, ctx) for k, v in obj.items()}
    if isinstance(obj, list):
        return [fill(v, ctx) for v in obj]
    return obj


def research(url: str) -> dict | None:
    try:
        r = subprocess.run([sys.executable, script("research_score.py"), "--url", url], capture_output=True, text=True, timeout=60)
        return json.loads(r.stdout)
    except Exception:
        return None


def build_tasks(cand: dict, cfg: dict, risk: str, risk_on: bool = False) -> list[dict]:
    tpl = cfg.get("task_templates", {})
    st = cfg.get("settings", {})
    auto = bool(st.get("auto_approve_low_risk", False)) and risk == "low"
    tasks, used = [], set()

    def add(typ: str, ctx: dict):
        for t in tpl.get(typ, []):
            t = fill(t, ctx)
            key = re.sub(r"[^a-zA-Z0-9_-]", "", t["key"])[:40] or typ
            if key in used:
                continue
            used.add(key)
            status = "pending" if (risk_on or (auto and not t.get("wallet"))) else "pending_approval"
            tasks.append({"key": key, "type": t["type"], "params": t.get("params", {}), "wallet": bool(t.get("wallet")),
                          "status": status})

    if risk == "high":
        primary = cand["links"][0]["url"] if cand["links"] else ""
        tasks.append({"key": "manual-review", "type": "manual", "wallet": False, "status": "pending_approval",
                      "params": {"note": "HIGH RISK (claim/drainer pattern). Verify on OFFICIAL site/X yourself. "
                                         "Agent must NOT open or connect.", "url": primary}})
        return tasks
    main = cand.get("task_type")
    for l in cand["links"]:
        typ = l["type"] or (main if main in ("faucet", "testnet", "waitlist") else None)
        if not typ or typ == "claim":
            continue
        path = l["url"].split("/", 3)[-1] if l["url"].count("/") >= 3 else ""
        peer = "@" + path.split("/")[0].split("?")[0] if typ in ("telegram", "tg-miniapp") and path else ""
        if typ == "telegram" and (not peer or peer.startswith("@+") or peer == "@joinchat"):
            peer = l["url"]  # invite link
        handle = path.split("/")[0] if typ == "x" else ""
        add(typ, {"url": l["url"], "peer": peer, "ref": l.get("ref", ""), "handle": handle})
    for h in cand.get("handles", [])[:2]:
        add("x", {"handle": h, "url": f"https://x.com/{h}"})
    if "testnet" in (cand.get("all_types") or [main]) and not any(t["type"] == "research" for t in tasks):
        docs = next((l["url"] for l in cand["links"] if l["type"] is None), "")
        if docs:
            add("testnet", {"url": docs})
    return tasks


def digest_text(c: dict, tasks: list[dict], src_url: str, reasons: list[str]) -> str:
    emo = {"low": "🟢", "medium": "🟡", "high": "🔴"}[c["risk"]]
    lines = [f"🛰️ RADAR {emo} {c['risk'].upper()} · skor {c['score']} · {c.get('task_type') or '-'}",
             f"Project: {c.get('project') or '?'}" + (f" · chain {c['chain']}" if c.get("chain") else "")
             + (f" · deadline {c['deadline']}" if c.get("deadline") else ""),
             f"Sumber: {src_url}"]
    for l in c["links"][:4]:
        lines.append(f"• {l['url']}" + (f" ({l['type']})" if l["type"] else ""))
    if tasks:
        lines.append("Task: " + ", ".join(f"{t['key']}[{'wallet' if t['wallet'] else 'no-wallet'}|{t['status']}]" for t in tasks))
    if reasons:
        lines.append("Catatan: " + "; ".join(reasons[:4]))
    if c["risk"] == "high":
        lines.append("⚠️ Pola claim/drainer — JANGAN connect wallet dari link ini. Approve = kamu cek manual saja.")
    return "\n".join(lines)


def can_digest(cfg: dict) -> bool:
    cap = int(cfg.get("settings", {}).get("digest_max_per_hour", 12))
    now = time.time()
    _digest_times[:] = [t for t in _digest_times if now - t < 3600]
    if len(_digest_times) >= cap:
        return False
    _digest_times.append(now)
    return True


def process_post(post: dict, cfg: dict, live: bool = True, offline: bool = False) -> dict:
    """post: {source, post_id, text, url, trust}. live=False -> no Telegram sends (dry-run)."""
    st = cfg.get("settings", {})
    text = post.get("text", "")
    src = f"{post.get('source')}#{post.get('post_id')}"
    if X.seen_post(post.get("source", ""), str(post.get("post_id", "")), text):
        return {"post": src, "decision": "seen"}
    c = X.extract(text, cfg)
    reasons: list[str] = []
    # --- hard stops
    if c["injection"]:
        _store(c, "flagged_injection", "high", 0, ["prompt-injection / fund-request text"], src, None, [])
        if live:
            _notify(f"🛑 RADAR: post berisi instruksi mencurigakan (injection/minta dana/seed) diabaikan.\nSumber: {post.get('url') or src}")
        return {"post": src, "decision": "flagged_injection", "project": c["project"], "tasks": []}
    if c["exclude_hits"] and not c["links"]:
        return {"post": src, "decision": "excluded", "hits": c["exclude_hits"]}
    if not c["include_hits"] and not any(l["type"] for l in c["links"]):
        return {"post": src, "decision": "not_airdrop"}
    if st.get("llm_classifier") and not offline:
        llm = X.llm_classify(text)
        if llm:
            if not c["project"] and llm["project"]:
                c["project"], c["project_key"] = llm["project"], X.project_key(llm["project"])
            if not c["task_type"] and llm["task_type"] != "none":
                c["task_type"] = llm["task_type"]
            if llm["risk_hint"] == "high":
                reasons.append("LLM: high risk")
                c["high_risk_hits"].append("llm")
    verdicts = []
    for l in c["links"]:
        if l["type"] in SOCIAL:
            continue
        v = S.check_url(l["url"])
        verdicts.append((l, v))
        if v["verdict"] == "block":
            _store(c, "scam", "high", 0, v["reasons"], src, None, [])
            if live:
                _notify(f"☠️ RADAR: link scam terdeteksi ({l['host']}): {'; '.join(v['reasons'])}\nSumber: {post.get('url') or src}")
            return {"post": src, "decision": "scam", "host": l["host"], "reasons": v["reasons"]}

    # --- dedupe
    dup = X.find_duplicate(c, int(st.get("dedupe_days", 14)))
    if dup:
        with X.db() as con:
            r = con.execute("SELECT sources, score FROM candidates WHERE id=?", (dup,)).fetchone()
            srcs = json.loads(r["sources"] or "[]")
            if src not in srcs:
                srcs.append(src)
            con.execute("UPDATE candidates SET sources=?, score=?, last_seen=? WHERE id=?",
                        (json.dumps(srcs), min(100, (r["score"] or 0) + 5), time.time(), dup))
        return {"post": src, "decision": "duplicate", "candidate": dup}

    # --- score
    platforms = cfg.get("platforms", {})
    score = 40 * float(post.get("trust", 0.5))
    score += min(15, 3 * len(c["include_hits"]))
    plat_links = [l for l in c["links"] if l["type"] and l["type"] not in SOCIAL | {"claim", "faucet"}]
    score += 15 if plat_links else 0
    score += 3 if c["deadline"] else 0
    score += 5 if c["project"] else 0
    for l, v in verdicts:
        score += 5 if v["verdict"] == "ok" else -15
        if v["verdict"] == "warn":
            reasons.append(f"{l['host']}: {'; '.join(v['reasons'][:2])}")
    nonsocial = [l for l in c["links"] if l["type"] not in SOCIAL]
    new_domains = sorted({X.root_domain(l["host"]) for l in nonsocial
                          if not known_platform(l["host"], platforms) and not allowlisted(l["host"])})
    hi = bool(c["high_risk_hits"])
    if hi:
        score -= 10
    # --- risk. Drainer heuristic (HARD, also in RISK=ON): claim / connect-wallet pattern on a site that is new
    # (not platform/allowlisted) or whose scam_check != ok -> never automatic.
    claimish = c["task_type"] == "claim" or any(l["type"] == "claim" for l in c["links"]) or hi
    not_ok = any(v["verdict"] != "ok" for _, v in verdicts)
    if (claimish and (new_domains or not_ok)) \
            or any(v["verdict"] == "warn" and X.root_domain(l["host"]) in new_domains for l, v in verdicts):
        risk = "high"
        reasons.append("claim/connect-wallet pattern (drainer heuristic)" if claimish else "suspicious new domain")
    elif not new_domains:
        risk = "low"
    else:
        risk = "medium"
        reasons.append("domain baru: " + ", ".join(new_domains))
    if st.get("online_research", True) and not offline and nonsocial and risk != "high":
        rs = research(nonsocial[0]["url"])
        if rs and isinstance(rs.get("score"), int):
            score = 0.6 * score + 0.4 * rs["score"]
            if rs.get("critical"):
                risk = "high"
                reasons.append("research_score: " + "; ".join(rs["critical"][:2]))
    score = int(max(0, min(100, round(score))))
    c.update(score=score, risk=risk)
    if score < int(st.get("min_score", 55)) and risk != "high":
        _store(c, "low_score", risk, score, reasons, src, None, [])
        return {"post": src, "decision": "low_score", "score": score, "project": c["project"]}

    # --- RISK=ON: low/medium go straight to the queue as 'pending' (no codes); high stays gated (hard rule)
    risk_on = RM.is_on() and risk in ("low", "medium") and not not_ok
    auto_domains = []
    if risk_on and risk == "medium":
        if RM.cfg().get("auto_allowlist_domains", True):
            for d in new_domains:
                if G.add_allowlist(d):
                    auto_domains.append(d)
        else:
            risk_on = False

    # --- tasks + gates
    tasks = build_tasks(c, cfg, risk, risk_on)
    base_id = c["project_key"] or (X.root_domain(nonsocial[0]["host"]).split(".")[0] if nonsocial else "unknown")
    pid = f"radar-{base_id}"[:60]
    pid = re.sub(r"[^a-z0-9.-]", "", pid.lower())
    project = {"id": pid, "name": c["project"] or pid, "chain": c["chain"], "score": score,
               "links": {f"l{i}": l["url"] for i, l in enumerate(c["links"])}, "source": post.get("url") or src}
    ids = tq.add_project_tasks(project, [{**t, "params": t["params"]} for t in tasks]) if tasks else []
    notify = live and st.get("digest", True) and can_digest(cfg)
    text_d = digest_text(c, tasks, post.get("url") or src, reasons)
    gid = None
    pending_ids = []
    with tq.db() as con:
        for tid in ids:
            r = con.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()
            if r and r["status"] == "pending_approval":
                pending_ids.append(tid)
    if risk_on:
        RM.report("radar find auto-queued (no approval)", post.get("url") or src,
                  {"project": c["project"] or pid, "risk": risk, "score": score, "type": c["task_type"],
                   "tasks": ", ".join(f"#{i} {t['key']}" for i, t in zip(ids, tasks)) or "-",
                   "auto_allowlisted": ", ".join(auto_domains) or "-"}, notify=live)
    elif pending_ids or risk == "high":
        gid = tq.create_gate("radar_tasks", text_d, {"task_ids": pending_ids, "project": pid}, notify=notify)
    elif notify:
        _notify(text_d + "\n(auto-approved: task tanpa wallet)")
    for d in new_domains if (risk == "medium" and not risk_on) else []:
        if not tq.pending_gate_for({"domain": d}):
            tq.create_gate("allow_domain", f"Izinkan domain baru {d} (dari radar: {c['project'] or pid})? "
                           f"Setelah approve, agent boleh connect/SIWE di domain ini.", {"domain": d}, notify=notify)
    cid = _store(c, "queued", risk, score, reasons, src, gid, ids)
    return {"post": src, "decision": "queued", "candidate": cid, "project": c["project"], "risk": risk, "score": score,
            "task_type": c["task_type"], "gate": gid, "tasks": [{"id": i, **t} for i, t in zip(ids, tasks)] if ids else tasks,
            "new_domains": new_domains, "risk_mode": "ON" if RM.is_on() else "OFF", "auto_allowlisted": auto_domains,
            "digest": redact(text_d) if not live else None}


def _store(c, status, risk, score, reasons, src, gid, ids) -> int:
    with X.db() as con:
        cur = con.execute(
            "INSERT INTO candidates(project_key,project,links,primary_url,chain,task_type,deadline,risk,score,status,reasons,"
            "sources,gate_id,task_ids,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (c.get("project_key"), c.get("project"), json.dumps(c["links"]), c["links"][0]["url"] if c["links"] else None,
             c.get("chain"), c.get("task_type"), c.get("deadline"), risk, score, status, json.dumps(reasons),
             json.dumps([src]), gid, json.dumps(ids), time.time(), time.time()))
        cid = cur.lastrowid
        if status == "queued":
            for l in c["links"]:
                if l["type"] not in SOCIAL:
                    con.execute("INSERT OR IGNORE INTO url_index VALUES(?,?)", (l["url"], cid))
    return cid


def _notify(text: str) -> None:
    try:
        from report_telegram import send
        send(text, None)
    except (Exception, SystemExit) as e:
        log.warning("notify failed: %s", e)
