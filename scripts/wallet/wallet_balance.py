#!/usr/bin/env python3
"""Show native (+ optional ERC20) balance for a burner label on a policy chain.

usage: wallet_balance.py --chain sepolia --label main-burner [--token 0xTokenAddr]
       wallet_balance.py --all     (every label x every chain in policy.yaml)
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl; _sys.path[:0] = [str(_d) for _d in sorted(_pl.Path(__file__).resolve().parents[1].iterdir()) if _d.is_dir() and not _d.name.startswith(("_", "."))]  # noqa: E702 (script-group import path)

import argparse

from common import check_kill, out
from chains import w3_for
import vault

ERC20_ABI = [
    {"name": "balanceOf", "type": "function", "stateMutability": "view", "inputs": [{"name": "a", "type": "address"}], "outputs": [{"type": "uint256"}]},
    {"name": "decimals", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint8"}]},
    {"name": "symbol", "type": "function", "stateMutability": "view", "inputs": [], "outputs": [{"type": "string"}]},
]


def bal(chain: str, label: str, token: str | None = None) -> dict:
    w3, cfg = w3_for(chain)
    addr = vault.address(label)
    res = {"chain": chain, "label": label, "address": addr,
           "native": str(w3.from_wei(w3.eth.get_balance(addr), "ether")), "symbol": cfg.get("native", "ETH")}
    if token:
        c = w3.eth.contract(address=w3.to_checksum_address(token), abi=ERC20_ABI)
        d = c.functions.decimals().call()
        res["token"] = {"symbol": c.functions.symbol().call(), "balance": c.functions.balanceOf(addr).call() / 10 ** d}
    return res


def main() -> None:
    check_kill()
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain"); ap.add_argument("--label"); ap.add_argument("--token")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    if a.all:
        from common import load_policy
        rows = []
        for label, e in vault.index().items():
            if "evm" not in e:
                continue
            for ch in load_policy().get("chains", {}):
                try:
                    rows.append(bal(ch, label))
                except Exception as ex:
                    rows.append({"chain": ch, "label": label, "error": str(ex)[:120]})
        return out(rows)
    if not (a.chain and a.label):
        raise SystemExit("--chain and --label required (or --all)")
    out(bal(a.chain, a.label, a.token))


if __name__ == "__main__":
    main()
