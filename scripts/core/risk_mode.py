#!/usr/bin/env python3
"""Global RISK mode switch.

RISK=OFF (default): every risky step needs an approval code (normal behaviour).
RISK=ON : radar finds are queued AND executed without approval codes; new domains are auto-allowlisted when
          scam_check == ok; wallet connect / SIWE / tx on testnet AND mainnet run without codes, but only
          inside the separate `risk_on` caps in policy.yaml and only with burner labels in risk_on.wallet_labels.

NEVER bypassable, even in RISK=ON (enforced in the calling scripts, not here):
  KILL file · eth_sign / blind 32-byte hash / non-UTF8 signing · unlimited approvals (approve/increaseAllowance
  >= 2^255, typed data with max amounts) · Permit/Permit2/Seaport/meta-tx typed data on mainnet · claim-pattern
  or any site whose scam_check != ok · SIWE domain != page origin · blocklisted addresses · risk_on per-tx /
  daily / gas caps (a chain without risk_on caps = no auto, gate as usual) · labels outside wallet_labels
  (main wallet is never in the vault) · keys/seed never printed or sent.
Every automatic action is logged to logs/risk_auto.jsonl and reported to Telegram immediately; without Telegram
reporting configured RISK=ON is ignored (treated as OFF).

State: ~/.airdrop-agent/risk_mode.json (set by CLI or Telegram "/risk on|off|status" from TG_OWNER_USER_ID)
       overrides env RISK_MODE=on|off. risk_on.max_hours (default 24, 0 = no expiry) auto-reverts to OFF.

  risk_mode.py status | on [--hours N] | off
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

from common import HOME, KILL_FILE, LOG_DIR, get_logger, load_policy, out

log = get_logger("risk_mode")
STATE = HOME / "risk_mode.json"
AUDIT = LOG_DIR / "risk_auto.jsonl"
FORBIDDEN_LABEL = re.compile(r"(?i)^(main|primary|cold|hodl|savings?|treasury|personal)$")


def cfg() -> dict:
    return load_policy().get("risk_on", {}) or {}


def state() -> dict:
    """Effective mode: {'on': bool, 'source': ..., 'expires': ts|None}."""
    if KILL_FILE.exists():
        return {"on": False, "source": "KILL"}
    if STATE.exists():
        try:
            s = json.loads(STATE.read_text())
        except Exception:
            s = {}
        exp = s.get("expires")
        if s.get("mode") == "on" and exp and time.time() > exp:
            set_mode("off", "expired")
            report("RISK mode expired -> OFF", "risk_mode", {})
            return {"on": False, "source": "expired"}
        return {"on": s.get("mode") == "on", "source": s.get("by", "file"), "expires": exp, "since": s.get("since")}
    return {"on": os.environ.get("RISK_MODE", "off").strip().lower() in ("on", "1", "true"), "source": "env",
            "expires": None}


def reporting_ready() -> bool:
    """RISK=ON is only honoured when auto actions can be reported (Telegram configured) — or in a dry-run."""
    return os.environ.get("RADAR_DRY_RUN") == "1" or bool(
        os.environ.get("TG_REPORT_BOT_TOKEN") and os.environ.get("TG_REPORT_CHAT_ID"))


def is_on() -> bool:
    if not state()["on"]:
        return False
    if not reporting_ready():
        log.warning("RISK mode requested but Telegram reporting is not configured -> treated as OFF")
        return False
    return True


def set_mode(mode: str, by: str, hours: float | None = None) -> dict:
    mode = "on" if mode == "on" else "off"
    hrs = float(cfg().get("max_hours", 24) if hours is None else hours)
    s = {"mode": mode, "by": by, "since": time.time(),
         "expires": (time.time() + hrs * 3600) if (mode == "on" and hrs > 0) else None}
    STATE.write_text(json.dumps(s))
    os.chmod(STATE, 0o600)
    log.warning("RISK mode -> %s (by %s)", mode.upper(), by)
    return s


def label_ok(label: str) -> bool:
    labels = cfg().get("wallet_labels", [])
    return bool(label) and label in labels and not FORBIDDEN_LABEL.match(label)


def caps(chain: str) -> dict | None:
    """risk_on caps for a chain, or None (= no auto on this chain)."""
    c = (cfg().get("chains") or {}).get(chain)
    if not c or not all(k in c for k in ("max_tx_native", "max_daily_native", "max_gas_native")):
        return None
    return c


def report(what: str, where: str, detail: dict | None = None, notify: bool = True) -> None:
    """Audit + immediate Telegram report of an automatic action (no secrets in detail!)."""
    from redact import redact
    rec = {"ts": time.time(), "what": what, "where": where, **(detail or {})}
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT, "a") as fh:
        fh.write(redact(json.dumps(rec, default=str)) + "\n")
    if not notify or os.environ.get("RADAR_DRY_RUN") == "1":
        return
    try:
        from report_telegram import send
        lines = [f"⚡ RISK-ON AUTO: {what}", f"Di: {where}"]
        for k, v in (detail or {}).items():
            lines.append(f"{k}: {v}")
        send(redact("\n".join(lines)), None)
    except (Exception, SystemExit) as e:
        log.warning("risk report send failed: %s", e)


def telegram_command(text: str) -> str | None:
    """Handle '/risk on [hours]|off|status' (caller must already have checked sender == TG_OWNER_USER_ID)."""
    p = text.strip().lstrip("/").split()
    if not p or p[0].lower() != "risk":
        return None
    sub = p[1].lower() if len(p) > 1 else "status"
    if sub == "on":
        hrs = float(p[2]) if len(p) > 2 and re.fullmatch(r"\d+(\.\d+)?", p[2]) else None
        s = set_mode("on", "telegram", hrs)
        exp = time.strftime("%Y-%m-%d %H:%M", time.localtime(s["expires"])) if s["expires"] else "tidak ada"
        msg = (f"⚠️ RISK MODE: ON (expire {exp}). Radar & task jalan TANPA approval, dalam cap risk_on policy.yaml. "
               f"Hard-block tetap aktif. Matikan: /risk off · darurat: touch ~/.airdrop-agent/KILL")
    elif sub == "off":
        set_mode("off", "telegram"); msg = "✅ RISK MODE: OFF — semua langkah berisiko kembali butuh approval."
    else:
        st = state(); msg = f"RISK MODE: {'ON' if st['on'] else 'OFF'} (source {st.get('source')})"
    try:
        from report_telegram import send
        send(msg, None)
    except (Exception, SystemExit):
        pass
    return msg


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("status"); sp.add_parser("off")
    o = sp.add_parser("on"); o.add_argument("--hours", type=float)
    a = ap.parse_args()
    if a.cmd == "on":
        if KILL_FILE.exists():
            raise SystemExit("KILL file present — remove it first")
        if not reporting_ready():
            raise SystemExit("RISK=ON needs TG_REPORT_BOT_TOKEN + TG_REPORT_CHAT_ID (every auto action is reported)")
        set_mode("on", "cli", a.hours)
        report("RISK mode -> ON", "cli", {"expires_hours": a.hours if a.hours is not None else cfg().get("max_hours", 24)})
    elif a.cmd == "off":
        set_mode("off", "cli")
        report("RISK mode -> OFF", "cli", {})
    st = state()
    out({**st, "effective_on": is_on(), "reporting_ready": reporting_ready(), "caps": cfg().get("chains", {}), "wallet_labels": cfg().get("wallet_labels", [])})


if __name__ == "__main__":
    main()
