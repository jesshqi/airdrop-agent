#!/usr/bin/env python3
"""Environment sanity check. Prints only NAMES of env vars, never values."""
from __future__ import annotations

import sys as _sys, pathlib as _pl; _sys.path[:0] = [str(_d) for _d in sorted(_pl.Path(__file__).resolve().parents[1].iterdir()) if _d.is_dir() and not _d.name.startswith(("_", "."))]  # noqa: E702 (script-group import path)

import importlib
import os
import stat

from common import DB_PATH, HOME, KILL_FILE, VAULT_DIR, out

REQUIRED = ["VAULT_PASSWORD", "TG_REPORT_BOT_TOKEN", "TG_REPORT_CHAT_ID"]
OPTIONAL = ["TG_REPORT_TOPIC_ID", "TG_API_ID", "TG_API_HASH", "IMAP_USER", "IMAP_PASSWORD", "DISCORD_BOT_TOKEN",
            "DISCORD_WATCH_CHANNEL_IDS", "RPC_SEPOLIA", "BROWSER_EXTENSION_DIRS", "TG_OWNER_USER_ID",
            "DISCORD_USER_TOKEN", "I_ACCEPT_BAN_RISK", "GRIND_LLM_BASE_URL", "X_BEARER_TOKEN", "TG_RADAR_SESSION",
            "X_API_FOLLOW_MODE", "X_BROWSER_FOLLOW_OPTIN", "RADAR_LLM_BASE_URL", "RISK_MODE"]
MODULES = ["yaml", "requests", "web3", "eth_account", "eth_abi", "cryptography", "telethon", "playwright", "discord"]


def main() -> None:
    res = {"home": str(HOME), "kill_switch": KILL_FILE.exists()}
    res["env_missing_required"] = [k for k in REQUIRED if not os.environ.get(k)]
    res["env_optional_set"] = [k for k in OPTIONAL if os.environ.get(k)]
    mods = {}
    for m in MODULES:
        try:
            importlib.import_module(m); mods[m] = "ok"
        except Exception as e:
            mods[m] = f"missing ({type(e).__name__})"
    res["python_modules"] = mods
    envf = HOME / ".env"
    res["env_file_mode"] = oct(stat.S_IMODE(envf.stat().st_mode)) if envf.exists() else "missing"
    res["vault_mode"] = oct(stat.S_IMODE(VAULT_DIR.stat().st_mode))
    res["policy"] = (HOME / "policy.yaml").exists()
    res["projects"] = (HOME / "projects.yaml").exists()
    res["db"] = DB_PATH.exists()
    # radar
    res["radar_sources"] = (HOME / "radar_sources.yaml").exists()
    if res["radar_sources"]:
        from common import load_yaml
        rc = load_yaml(HOME / "radar_sources.yaml")
        srcs = [s.get("target", "") for s in rc.get("telegram", [])] + [a.get("handle", "") for a in rc.get("x_accounts", [])]
        res["radar_placeholders_left"] = sum(1 for x in srcs if "example" in str(x).lower())
        res["radar_auto_approve_low_risk"] = bool(rc.get("settings", {}).get("auto_approve_low_risk"))
    # RISK mode
    import risk_mode as RM
    st = RM.state()
    res["risk_mode"] = {"requested_on": st["on"], "effective_on": RM.is_on(), "source": st.get("source"),
                        "expires": st.get("expires"), "risk_on_caps_chains": sorted((RM.cfg().get("chains") or {})),
                        "wallet_labels": RM.cfg().get("wallet_labels", [])}
    warnings = []
    if st["on"]:
        warnings.append("RISK MODE ON: radar tasks + connect/SIWE/tx run WITHOUT approval (within risk_on caps)")
        if not RM.reporting_ready():
            warnings.append("RISK requested but Telegram reporting not configured -> treated as OFF")
        if not RM.cfg():
            warnings.append("policy.yaml has no risk_on section -> no automatic tx")
        if any(RM.FORBIDDEN_LABEL.match(l) for l in RM.cfg().get("wallet_labels", [])):
            warnings.append("risk_on.wallet_labels contains a main-wallet-like label (ignored)")
    if res.get("radar_placeholders_left"):
        warnings.append("radar_sources.yaml still has example placeholders")
    if res["radar_sources"] and not os.environ.get("X_BEARER_TOKEN"):
        warnings.append("X_BEARER_TOKEN not set -> X radar polling disabled")
    res["warnings"] = warnings
    problems = []
    if res["env_missing_required"]: problems.append("missing required env")
    if res["env_file_mode"] not in ("0o600", "0o400"): problems.append(".env must be chmod 600")
    if res["vault_mode"] != "0o700": problems.append("vault dir must be chmod 700")
    if not res["policy"] or not res["projects"]: problems.append("copy templates/policy.yaml + projects.yaml to ~/.airdrop-agent/")
    if res["kill_switch"]: problems.append("KILL switch active")
    res["ok"] = not problems
    res["problems"] = problems
    out(res)


if __name__ == "__main__":
    main()
