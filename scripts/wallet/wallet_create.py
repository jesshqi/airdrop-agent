#!/usr/bin/env python3
"""Create dedicated burner wallets (EVM, optional Solana). Prints ONLY public addresses.

usage: wallet_create.py --count 1 --label main-burner [--solana]
       (count>1 -> labels main-burner-1, main-burner-2 ...)
Never import the owner's main seed here. Back up ~/.airdrop-agent/vault + VAULT_PASSWORD offline.
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl; _sys.path[:0] = [str(_d) for _d in sorted(_pl.Path(__file__).resolve().parents[1].iterdir()) if _d.is_dir() and not _d.name.startswith(("_", "."))]  # noqa: E702 (script-group import path)

import argparse

from common import check_kill, get_logger, out
import vault

log = get_logger("wallet_create")


def main() -> None:
    check_kill()
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--solana", action="store_true")
    a = ap.parse_args()
    if a.count > 5:
        raise SystemExit("refusing >5 wallets: multi-account farming = sybil risk (see references/sybil-tos.md)")

    from eth_account import Account
    idx = vault.index()
    created = []
    for i in range(a.count):
        label = a.label if a.count == 1 else f"{a.label}-{i + 1}"
        if label in idx:
            raise SystemExit(f"label exists: {label}")
        acct = Account.create()
        vault.store_evm(label, acct)
        entry = {"evm": acct.address}
        del acct
        if a.solana:
            from solders.keypair import Keypair
            kp = Keypair()
            vault.store_sol(label, bytes(kp))
            entry["solana"] = str(kp.pubkey())
            del kp
        idx[label] = entry
        created.append({"label": label, **entry})
        log.info("created wallet %s", label)
    vault.save_index(idx)
    out({"created": created, "note": "keys encrypted in vault; fund with small amounts only"})


if __name__ == "__main__":
    main()
