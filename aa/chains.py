"""Chain resolution with RPC verification.

A policy entry names an RPC env var; we verify `chain_id` before every session so a
hijacked RPC that reports the wrong network cannot move funds to the wrong chain.
"""
from __future__ import annotations

from . import config, policy
from .jsonio import Denied


def cfg(name: str, verify: bool = True) -> dict:
    c = dict(policy.chain(name))
    c["name"] = name
    rpc = config.env(c.get("rpc_env", "")) if c.get("rpc_env") else ""
    c["rpc"] = rpc or c.get("rpc", "")
    if not c["rpc"]:
        raise Denied(f"no RPC configured for {name} (set {c.get('rpc_env') or 'rpc'} in policy.yaml/.env)")
    c.setdefault("kind", "evm")
    c["testnet"] = bool(c.get("testnet"))
    if verify and c["kind"] == "evm":
        cid = web3_chain_id(c["rpc"])
        if cid != int(c["chain_id"]):
            raise Denied(f"RPC reports chain {cid} but policy says {c['chain_id']} for {name}")
    return c


def web3_chain_id(rpc: str) -> int:
    import requests

    r = requests.post(rpc, json={"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}, timeout=15)
    r.raise_for_status()
    return int(r.json()["result"], 16)


def w3(name: str):
    from web3 import Web3

    c = cfg(name)
    return Web3(Web3.HTTPProvider(c["rpc"], request_kwargs={"timeout": 30})), c


def sol(name: str) -> dict:
    c = cfg(name, verify=False)
    if c.get("kind") != "solana":
        raise Denied(f"{name} is not a solana chain")
    return c


def testnets() -> list[str]:
    return [n for n, c in (policy.cfg().get("chains") or {}).items() if c.get("testnet")]


def all_chains() -> list[str]:
    return list((policy.cfg().get("chains") or {}).keys())


def explorer(name: str, tx: str) -> str:
    base = (policy.chain(name).get("explorer") or "").rstrip("/")
    return f"{base}/tx/{tx}" if base else ""
