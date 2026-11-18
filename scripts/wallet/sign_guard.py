#!/usr/bin/env python3
"""Message / typed-data signing policy (merged from airdrop-hunter tx_guard, made stricter).

Decisions: allow | ask (human gate) | block.
- personal_sign: SIWE only when message domain == page origin AND domain in policy.siwe_domain_allowlist.
  Plain-text verification messages only on allowlisted origins. Blind 32-byte hashes / non-UTF8 blobs -> block.
- eth_signTypedData: Permit/Permit2/Seaport/meta-tx/delegation -> block on mainnet, ask on testnet.
  Unlimited amounts (>= 2^160-1) in any typed data -> block (also in RISK=ON).
- RISK=ON only turns "ask" into allow (in browser_session / siwe_sign) when scam_check(origin) == ok; "block" stays block.
  Any asset-like field (spender, amount, token, offer...) -> ask. Non-asset typed data on allowlisted origin -> allow.

CLI: sign_guard.py message --text "..." --origin galxe.com
     sign_guard.py typed --file typed.json [--testnet]
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl; _sys.path[:0] = [str(_d) for _d in sorted(_pl.Path(__file__).resolve().parents[1].iterdir()) if _d.is_dir() and not _d.name.startswith(("_", "."))]  # noqa: E702 (script-group import path)

import argparse
import json
import re

from common import HOME, load_policy, out

PERMIT2 = "0x000000000022d473030f116ddee9f6b43ac78ba3"
DANGEROUS_TYPED = {
    "Permit", "PermitSingle", "PermitBatch", "PermitTransferFrom", "PermitBatchTransferFrom",
    "PermitWitnessTransferFrom", "OrderComponents", "Order", "BulkOrder", "MetaTransaction",
    "ForwardRequest", "Delegation",
}
VALUE_KEYS = {"spender", "amount", "value", "token", "offer", "consideration", "operator", "allowance",
              "permitted", "recipient", "to"}
SIWE_RE = re.compile(r"^(?:https?://)?(?P<domain>[^\s/]+) wants you to sign in with your Ethereum account", re.M)
SCAM_TEXT = re.compile(r"(?i)(seed|mnemonic|private key|recovery phrase|transfer all|withdraw all|approve|permit)")


def _host(s: str) -> str:
    s = re.sub(r"^https?://", "", (s or "").lower()).split("/")[0].split(":")[0]
    return s[4:] if s.startswith("www.") else s


def _allowed(host: str) -> bool:
    allow = [d.lower() for d in load_policy().get("siwe_domain_allowlist", [])]
    extra = HOME / "allowlist_domains.txt"  # domains the owner approved via Telegram code (radar allow_domain gates)
    if extra.exists():
        allow += [d.strip().lower() for d in extra.read_text().split() if d.strip()]
    return any(host == d or host.endswith("." + d) for d in allow)


def evaluate_message(text: str | None, origin: str) -> dict:
    if text is None:
        return {"decision": "block", "reasons": ["non-UTF8 / binary payload (blind signing)"]}
    t = text.strip()
    if re.fullmatch(r"(0x)?[0-9a-fA-F]{64}", t):
        return {"decision": "block", "reasons": ["blind 32-byte hash signing"]}
    if SCAM_TEXT.search(t):
        return {"decision": "block", "reasons": ["message mentions seed/key/approve/permit/transfer-all"]}
    od = _host(origin)
    m = SIWE_RE.search(t)
    if m:
        sd = _host(m.group("domain"))
        if od and not (od == sd or od.endswith("." + sd)):
            return {"decision": "block", "reasons": [f"SIWE for {sd} but page is {od} (phishing)"]}
        if not _allowed(sd):
            return {"decision": "ask", "reasons": [f"SIWE domain {sd} not in allowlist"]}
        return {"decision": "allow", "reasons": ["SIWE, domain matches + allowlisted"]}
    if not _allowed(od):
        return {"decision": "ask", "reasons": [f"plain message on non-allowlisted origin {od}"]}
    return {"decision": "allow", "reasons": ["plain verification text on allowlisted origin"]}


def _walk_keys(obj, acc: set) -> set:
    if isinstance(obj, dict):
        for k, v in obj.items():
            acc.add(str(k).lower())
            _walk_keys(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _walk_keys(v, acc)
    return acc


UNLIMITED = 2 ** 160 - 1


def _has_unlimited(obj) -> bool:
    if isinstance(obj, dict):
        return any(_has_unlimited(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_unlimited(v) for v in obj)
    try:
        v = int(obj, 0) if isinstance(obj, str) and re.fullmatch(r"(0x[0-9a-fA-F]+|\d+)", obj) and len(obj) > 30 else obj
        return isinstance(v, int) and not isinstance(v, bool) and v >= UNLIMITED
    except ValueError:
        return False


def add_allowlist(domain: str) -> bool:
    """Append a domain to HOME/allowlist_domains.txt (approved gate or RISK=ON + scam_check ok). True if added."""
    d = _host(domain)
    f = HOME / "allowlist_domains.txt"
    existing = set(f.read_text().split()) if f.exists() else set()
    if not d or d in existing:
        return False
    with open(f, "a") as fh:
        fh.write(d + "\n")
    return True


def evaluate_typed(typed: dict, testnet: bool, origin: str = "") -> dict:
    pt = typed.get("primaryType", "")
    if _has_unlimited(typed.get("message", {})):
        return {"decision": "block", "reasons": ["typed data contains an unlimited amount"]}
    vc = str((typed.get("domain") or {}).get("verifyingContract", "")).lower()
    if pt in DANGEROUS_TYPED or vc == PERMIT2:
        return {"decision": "ask" if testnet else "block", "reasons": [f"dangerous typed data: {pt or 'Permit2'}"]}
    hit = _walk_keys(typed.get("message", {}), set()) & VALUE_KEYS
    if hit:
        return {"decision": "ask", "reasons": [f"typed data has asset fields {sorted(hit)}"]}
    if origin and not _allowed(_host(origin)):
        return {"decision": "ask", "reasons": [f"typed data on non-allowlisted origin {_host(origin)}"]}
    return {"decision": "allow", "reasons": [f"typed data {pt} without asset fields"]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    m = sp.add_parser("message"); m.add_argument("--text", required=True); m.add_argument("--origin", default="")
    t = sp.add_parser("typed"); t.add_argument("--file", required=True); t.add_argument("--testnet", action="store_true")
    t.add_argument("--origin", default="")
    a = ap.parse_args()
    out(evaluate_message(a.text, a.origin) if a.cmd == "message"
        else evaluate_typed(json.load(open(a.file)), a.testnet, a.origin))
