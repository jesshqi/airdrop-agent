"""Encrypted local key vault. Keys are decrypted in-process only, never returned to the LLM.

Layout (chmod 700):
  ~/.airdrop-agent/vault/index.json        public: label -> {evm, solana}
  ~/.airdrop-agent/vault/evm/<label>.json  Ethereum V3 keystore (scrypt), password = VAULT_PASSWORD
  ~/.airdrop-agent/vault/sol/<label>.json  scrypt + AES-GCM encrypted Solana secret key
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl; _sys.path[:0] = [str(_d) for _d in sorted(_pl.Path(__file__).resolve().parents[1].iterdir()) if _d.is_dir() and not _d.name.startswith(("_", "."))]  # noqa: E702 (script-group import path)

import base64
import json
import os

from common import VAULT_DIR, env_required

INDEX = VAULT_DIR / "index.json"


def _write_private(path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)  # never overwrite existing keys
    with os.fdopen(fd, "w") as f:
        f.write(data)


def index() -> dict:
    return json.loads(INDEX.read_text()) if INDEX.exists() else {}


def save_index(idx: dict) -> None:
    INDEX.write_text(json.dumps(idx, indent=2))
    os.chmod(INDEX, 0o600)


def address(label: str, kind: str = "evm") -> str:
    a = index().get(label, {}).get(kind)
    if not a:
        raise SystemExit(f"no {kind} wallet with label '{label}'")
    return a


# ---------- EVM ----------
def store_evm(label: str, acct) -> None:
    from eth_account import Account
    ks = Account.encrypt(acct.key, env_required("VAULT_PASSWORD"))
    _write_private(VAULT_DIR / "evm" / f"{label}.json", json.dumps(ks))


def load_evm(label: str):
    """Return eth_account LocalAccount. Caller must never print/log it."""
    from eth_account import Account
    ks = json.loads((VAULT_DIR / "evm" / f"{label}.json").read_text())
    return Account.from_key(Account.decrypt(ks, env_required("VAULT_PASSWORD")))


# ---------- Solana ----------
def _kdf(salt: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    return Scrypt(salt=salt, length=32, n=2 ** 15, r=8, p=1).derive(env_required("VAULT_PASSWORD").encode())


def store_sol(label: str, secret: bytes) -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, nonce = os.urandom(16), os.urandom(12)
    ct = AESGCM(_kdf(salt)).encrypt(nonce, secret, label.encode())
    blob = {k: base64.b64encode(v).decode() for k, v in {"salt": salt, "nonce": nonce, "ct": ct}.items()}
    _write_private(VAULT_DIR / "sol" / f"{label}.json", json.dumps(blob))


def load_sol(label: str):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from solders.keypair import Keypair
    blob = {k: base64.b64decode(v) for k, v in json.loads((VAULT_DIR / "sol" / f"{label}.json").read_text()).items()}
    return Keypair.from_bytes(AESGCM(_kdf(blob["salt"])).decrypt(blob["nonce"], blob["ct"], label.encode()))
