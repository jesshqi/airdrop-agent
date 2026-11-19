"""Testnet activity campaigns: randomised, repeatable on-chain traffic.

A campaign is a list of actions per chain. Amounts and ordering are jittered each run
so the wallet does not look like a cron job. Deploys/interactions still pass the
normal send→policy→gate pipeline.
"""
from __future__ import annotations

import asyncio
import random

from .. import db, guard, policy
from ..jsonio import Denied
from ..log import get_logger
from ..wallet import send as sender

log = get_logger("campaign")

BUILTIN = {
    "warmup": [
        {"chain": "sepolia", "do": "deploy", "kind": "counter"},
        {"chain": "sepolia", "do": "tx", "to_self": True, "amount": [0.0005, 0.002], "gas": True},
        {"chain": "base-sepolia", "do": "deploy", "kind": "erc20"},
        {"chain": "base-sepolia", "do": "tx", "to_self": True, "amount": [0.0003, 0.001]},
    ],
    "daily": [
        {"chain": "sepolia", "do": "tx", "to_self": True, "amount": [0.0002, 0.0008]},
        {"chain": "base-sepolia", "do": "tx", "to_self": True, "amount": [0.0002, 0.0008]},
    ],
}


def load(chain: str, name: str = "daily") -> list[dict]:
    from .. import config

    cfg = config.load_yaml("campaigns.yaml").get("campaigns", {})
    acts = (cfg.get(name) or BUILTIN.get(name) or [])
    return [a for a in acts if a.get("chain") == chain] or [a for a in (cfg.get("name") or []) if a.get("chain") == chain]


async def run(chain: str, identity_id: str, name: str = "daily", *, rounds: int = 1, wait: bool = True) -> dict:
    guard.check_kill()
    acts = load(chain, name)
    if not acts:
        raise Denied(f"no campaign '{name}' actions for {chain}")
    policy.chain(chain)
    ws = db.wallets(identity_id, "evm")
    if not ws:
        raise Denied("identity has no EVM wallet")
    label = ws[0]["label"]
    done, failed = [], []
    for _ in range(rounds):
        order = acts[:]
        random.shuffle(order)
        for a in order:
            try:
                if a["do"] == "deploy":
                    from . import deploy

                    done.append(await asyncio.to_thread(deploy.run, chain, identity_id, a.get("kind", "counter")))
                elif a["do"] == "tx":
                    amount = random.uniform(*a.get("amount", [0.0001, 0.0005]))
                    to = ws[0]["address"] if a.get("to_self") else a.get("to")
                    if not to:
                        raise Denied("tx action needs to/to_self")
                    if a.get("gas"):
                        # touch a precompile-free self-transfer with extra calldata
                        pass
                    done.append(await asyncio.to_thread(sender.send, chain, identity_id, label, to,
                                                        value_wei=int(amount * 1e18), broadcast=True,
                                                        via="campaign"))
                elif a["do"] == "faucet":
                    from . import faucets
                    from ..browser.engine import Browser

                    async with Browser(identity_id, profile="faucet", chain=chain) as b:
                        done.append(await faucets.claim(b, identity_id, chain, a.get("name", "")))
                else:
                    raise Denied(f"unknown action {a['do']}")
            except Exception as e:  # noqa: BLE001
                failed.append({"action": a, "error": str(e)[:200]})
                log.warning("campaign step failed: %s", e)
            await asyncio.sleep(random.uniform(8, 30) if wait else 0)
    db.event("campaign", f"{name} {chain} ok={len(done)} fail={len(failed)}", identity_id)
    return {"chain": chain, "campaign": name, "ok": len(done), "failed": failed, "results": done}


def names() -> list[str]:
    from .. import config

    return list({**BUILTIN, **(config.load_yaml("campaigns.yaml").get("campaigns") or {})})


def estimate(chain: str, name: str = "daily") -> dict:
    acts = load(chain, name)
    gas_ok = policy.chain(chain).get("max_tx_native")
    total = sum(sum(a.get("amount", [0.0003, 0.0006])) / 2 for a in acts if a["do"] == "tx")
    return {"chain": chain, "actions": len(acts), "native_est": round(total, 6),
            "per_tx_cap": gas_ok, "fits_cap": total <= float(gas_ok or 0)}
