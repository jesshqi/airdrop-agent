"""Chain config from policy.yaml -> Web3 instance."""
from __future__ import annotations

import sys as _sys, pathlib as _pl; _sys.path[:0] = [str(_d) for _d in sorted(_pl.Path(__file__).resolve().parents[1].iterdir()) if _d.is_dir() and not _d.name.startswith(("_", "."))]  # noqa: E702 (script-group import path)

import os

from common import load_policy


def chain_cfg(chain: str) -> dict:
    cfg = load_policy().get("chains", {}).get(chain)
    if not cfg:
        raise SystemExit(f"chain '{chain}' not in policy.yaml allowlist")
    return cfg


def w3_for(chain: str):
    from web3 import Web3
    cfg = chain_cfg(chain)
    rpc = os.environ.get(cfg.get("rpc_env", ""), "") or cfg.get("rpc")
    if not rpc:
        raise SystemExit(f"no RPC for {chain}")
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
    cid = w3.eth.chain_id
    if cid != cfg["chain_id"]:
        raise SystemExit(f"RPC chain_id {cid} != policy {cfg['chain_id']} for {chain} (wrong/malicious RPC?)")
    return w3, cfg
