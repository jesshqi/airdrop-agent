"""EVM wallets: generate, import, resolve, balance.

Keys stay in the vault; the CLI only ever sees addresses.
"""
from __future__ import annotations

from web3 import Web3

from .. import db, vault
from ..jsonio import Denied
from ..log import get_logger
from . import hd

log = get_logger("wallet.evm")


def _addr(a: str) -> str:
    if not Web3.is_address(a):
        raise SystemExit(f"invalid EVM address: {a}")
    return Web3.to_checksum_address(a)


def create(identity_id: str, count: int = 1, prefix: str = "evm") -> list[dict]:
    """Standalone random keys (not HD-derived) — independent identities."""
    from eth_account import Account

    out = []
    for _ in range(count):
        acct = Account.create()
        label = f"{identity_id}-{prefix}-{acct.address[2:8].lower()}"
        vault.store_evm(label, bytes(acct.key))
        db.add_wallet(identity_id, "evm", acct.address, label)
        out.append({"label": label, "address": acct.address})
        del acct
    db.event("wallet", f"created {count} evm wallet(s)", identity_id)
    return out


def derive(identity_id: str, count: int = 1) -> list[dict]:
    return hd.provision(identity_id, "evm", count, prefix="e")


def import_key(identity_id: str, private_key: str, label: str | None = None) -> dict:
    from eth_account import Account

    pk = private_key.strip()
    if pk.startswith("0x"):
        pk = pk[2:]
    acct = Account.from_key(bytes.fromhex(pk))
    label = label or f"{identity_id}-imp-{acct.address[2:8].lower()}"
    vault.store_evm(label, bytes(acct.key))
    db.add_wallet(identity_id, "evm", acct.address, label, kind="imported")
    return {"label": label, "address": acct.address}


def import_mnemonic(identity_id: str, mnemonic: str, count: int = 1) -> list[dict]:
    if not hd.valid(mnemonic):
        raise SystemExit("invalid mnemonic")
    out = []
    for i in range(count):
        pk, addr = hd.derive_evm(mnemonic, i)
        label = f"{identity_id}-mn-{addr[2:8].lower()}"
        vault.store_evm(label, pk)
        db.add_wallet(identity_id, "evm", addr, label, kind="imported")
        out.append({"label": label, "address": addr})
    return out


def resolve(identity_id: str, ref: str) -> dict:
    """Find a wallet by label, address or 'first'."""
    ws = db.wallets(identity_id, "evm")
    if not ws:
        raise Denied(f"identity {identity_id} has no EVM wallet (aa wallet new --identity ...)")
    if ref in ("first", "default", ""):
        return ws[0]
    ref_l = ref.lower()
    for w in ws:
        if w["label"] == ref or w["address"].lower() == ref_l:
            return w
    raise SystemExit(f"wallet not found: {ref}")


def balance(chain_cfg: dict, address: str) -> dict:
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(chain_cfg["rpc"], request_kwargs={"timeout": 20}))
    wei = w3.eth.get_balance(_addr(address))
    return {"address": address, "wei": wei, "native": wei / 1e18}


def label_matches(identity_id: str, label: str) -> bool:
    return any(w["label"] == label for w in db.wallets(identity_id))
