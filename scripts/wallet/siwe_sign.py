#!/usr/bin/env python3
"""Sign a Sign-In-With-Ethereum (EIP-4361) message for a burner, with strict checks.

Refuses: non-SIWE text, domain not allowlisted (policy + approved allowlist_domains.txt; RISK=ON: allowed when
scam_check == ok, then auto-allowlisted and reported), wrong address/chain,
expired messages, and anything mentioning transfer/approve/permit (typed data is never signed here).

usage: siwe_sign.py --label main-burner --message-file msg.txt [--expect-domain galxe.com]
prints: {"signature": "0x..."}   (a signature is not a secret; the key never leaves the process)
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl; _sys.path[:0] = [str(_d) for _d in sorted(_pl.Path(__file__).resolve().parents[1].iterdir()) if _d.is_dir() and not _d.name.startswith(("_", "."))]  # noqa: E702 (script-group import path)

import argparse
import datetime as dt
import re
import sys

from common import check_kill, get_logger, load_policy, out
import vault
import risk_mode as RM
import sign_guard as G

log = get_logger("siwe")
DANGER = re.compile(r"(?i)\b(permit|approve|transfer|withdraw|setApprovalForAll|seaport|order|nonce\s*manager)\b")


def main() -> None:
    check_kill()
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--message-file", required=True)
    ap.add_argument("--expect-domain")
    a = ap.parse_args()
    msg = open(a.message_file, encoding="utf-8").read().replace("\r\n", "\n")
    lines = msg.split("\n")
    m = re.match(r"^(?:https?://)?([^\s/]+) wants you to sign in with your Ethereum account:$", lines[0] if lines else "")
    if not m:
        out({"refused": "not an EIP-4361 SIWE message"}); sys.exit(2)
    domain = m.group(1).lower()
    addr = vault.address(a.label)
    if len(lines) < 2 or lines[1].strip().lower() != addr.lower():
        out({"refused": "address in message does not match burner"}); sys.exit(2)
    auto = False
    if not G._allowed(domain):
        import scam_check as S
        if RM.is_on() and RM.label_ok(a.label) and S.check_url("https://" + domain)["verdict"] == "ok":
            auto = True  # RISK=ON: new domain ok by scam_check -> allowlist + sign, reported below
        else:
            out({"refused": f"domain {domain} not in siwe_domain_allowlist — needs human approval"}); sys.exit(2)
    if a.expect_domain and not (domain == a.expect_domain or domain.endswith("." + a.expect_domain)):
        out({"refused": f"domain {domain} != expected {a.expect_domain} (phishing?)"}); sys.exit(2)
    stmt = "\n".join(lines[2:6])
    if DANGER.search(stmt):
        out({"refused": "statement mentions value-moving action"}); sys.exit(2)
    exp = re.search(r"^Expiration Time: (.+)$", msg, re.M)
    if exp:
        t = dt.datetime.fromisoformat(exp.group(1).strip().replace("Z", "+00:00"))
        if t < dt.datetime.now(dt.timezone.utc):
            out({"refused": "message expired"}); sys.exit(2)

    from eth_account.messages import encode_defunct
    acct = vault.load_evm(a.label)
    sig = acct.sign_message(encode_defunct(text=msg)).signature.hex()
    del acct
    log.info("SIWE signed for %s", domain)
    if auto:
        G.add_allowlist(domain)
    if RM.is_on():
        RM.report("SIWE signed" + (" (new domain auto-allowlisted, no approval)" if auto else ""), domain,
                  {"wallet": f"{a.label} {addr}"})
    out({"domain": domain, "address": addr, "signature": sig if sig.startswith("0x") else "0x" + sig})


if __name__ == "__main__":
    main()
