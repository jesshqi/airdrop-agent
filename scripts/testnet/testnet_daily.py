#!/usr/bin/env python3
"""Daily testnet activity: N small self-transfers (and optional allowlisted contract calls) via safe_send.

usage: testnet_daily.py --chain sepolia --label main-burner [--txs 2] [--max-eth 0.0002]
       testnet_daily.py ... --call "0xContract|mint(uint256)|1"      (contract must be in policy allowlist)
Only runs on chains marked testnet: true in policy.yaml.
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl; _sys.path[:0] = [str(_d) for _d in sorted(_pl.Path(__file__).resolve().parents[1].iterdir()) if _d.is_dir() and not _d.name.startswith(("_", "."))]  # noqa: E702 (script-group import path)

import argparse
import json
import random
import subprocess
import sys
import time
from pathlib import Path

from common import check_kill, get_logger, out, script
from chains import chain_cfg
import vault

log = get_logger("testnet_daily")
HERE = Path(__file__).parent


def safe_send(args: list[str]) -> dict:
    r = subprocess.run([sys.executable, script("safe_send.py"), *args, "--broadcast"], capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
    except Exception:
        d = {"raw": (r.stdout or r.stderr)[-300:]}
    d["exit"] = r.returncode
    return d


def main() -> None:
    check_kill()
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain", required=True); ap.add_argument("--label", required=True)
    ap.add_argument("--txs", type=int, default=2); ap.add_argument("--max-eth", type=float, default=0.0002)
    ap.add_argument("--call", action="append", default=[])
    a = ap.parse_args()
    if not chain_cfg(a.chain).get("testnet"):
        raise SystemExit("testnet_daily only runs on testnet chains")
    me = vault.address(a.label)
    res = []
    for i in range(a.txs):
        check_kill()
        amt = f"{random.uniform(a.max_eth / 10, a.max_eth):.6f}"
        res.append(safe_send(["--chain", a.chain, "--label", a.label, "--to", me, "--value-eth", amt]))
        time.sleep(random.uniform(20, 90))
    for c in a.call:
        parts = c.split("|")
        addr, sig = parts[0], parts[1]
        extra = ["--args", *parts[2].split(",")] if len(parts) > 2 and parts[2] else []
        res.append(safe_send(["--chain", a.chain, "--label", a.label, "--to", addr, "--sig", sig, *extra]))
    out({"chain": a.chain, "results": res})


if __name__ == "__main__":
    main()
