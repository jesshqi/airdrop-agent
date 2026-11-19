"""Contract deployment for testnet activity (ERC20 / ERC721 / counter).

Uses Foundry when installed (fast, tested), otherwise `solc --standard-json`. The key
is handed to forge via `--private-key` (local process only) and never logged.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from .. import db, gates, guard, policy
from ..jsonio import Denied
from ..log import get_logger
from ..wallet import send as sender

log = get_logger("deploy")

SOURCES = {
    "counter": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
contract Counter {
    uint256 public count;
    function increment() external { count += 1; }
}
""",
    "erc20": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
contract TestToken {
    string public name = "Test Token";
    string public symbol = "TEST";
    uint8 public decimals = 18;
    uint256 public totalSupply = 1_000_000 ether;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    event Transfer(address indexed from, address indexed to, uint256 value);
    constructor() { balanceOf[msg.sender] = totalSupply; emit Transfer(address(0), msg.sender, totalSupply); }
    function transfer(address to, uint256 v) external returns (bool) {
        balanceOf[msg.sender] -= v; balanceOf[to] += v; emit Transfer(msg.sender, to, v); return true;
    }
    function approve(address s, uint256 v) external returns (bool) { allowance[msg.sender][s] = v; return true; }
}
""",
    "erc721": """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
contract TestNFT {
    string public name = "Test NFT";
    string public symbol = "TNFT";
    uint256 public nextId;
    mapping(uint256 => address) public ownerOf;
    mapping(address => uint256) public balanceOf;
    function mint() external {
        uint256 id = nextId++;
        ownerOf[id] = msg.sender; balanceOf[msg.sender] += 1;
    }
}
""",
}


def toolchain() -> str | None:
    if shutil.which("forge"):
        return "forge"
    if shutil.which("solc"):
        return "solc"
    return None


def compile_solc(src: str) -> tuple[str, str]:
    inp = {"language": "Solidity", "sources": {"C.sol": {"content": src}},
           "settings": {"optimizer": {"enabled": True, "runs": 200},
                        "outputSelection": {"*": {"*": ["abi", "evm.bytecode.object"]}}}}
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "in.json"
        p.write_text(json.dumps(inp))
        out = subprocess.run(["solc", "--standard-json"], input=json.dumps(inp), capture_output=True,
                             text=True, timeout=180, cwd=td)
    try:
        data = json.loads(out.stdout)
        contracts = data["contracts"]["C.sol"]
        name = next(iter(contracts))
        return "0x" + contracts[name]["evm"]["bytecode"]["object"], json.dumps(contracts[name]["abi"])
    except (ValueError, KeyError) as e:
        raise Denied(f"solc failed: {e} {out.stderr[:400]}")


def compile_forge(src: str, kind: str) -> tuple[str, str]:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "src").mkdir()
        name = "Counter" if kind == "counter" else "TestToken" if kind == "erc20" else "TestNFT"
        (root / "src" / f"{name}.sol").write_text(src)
        (root / "foundry.toml").write_text('[profile.default]\nsrc = "src"\nout = "out"\n')
        r = subprocess.run(["forge", "build", "--json"], cwd=td, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            raise Denied(f"forge build failed: {r.stderr[:400]}")
        try:
            data = json.loads(r.stdout) if r.stdout.strip().startswith("{") else None
            if data is None:
                art = next((root / "out").rglob(f"{name}.json"))
                data = {name: json.loads(art.read_text())}
            entry = next(iter(data.values()))
            bytecode = entry.get("bytecode", {}).get("object") if isinstance(entry.get("bytecode"), dict) else entry.get("bytecode")
            return bytecode, json.dumps(entry.get("abi", []))
        except (StopIteration, ValueError, KeyError) as e:
            raise Denied(f"cannot read forge artifacts: {e}")


def run(chain: str, identity_id: str, kind: str = "erc20", args: dict | None = None) -> dict:
    guard.check_kill()
    if not policy.chain(chain).get("testnet") and not policy.cfg().get("allow_deploy_mainnet", False):
        raise Denied("mainnet deploy disabled (allow_deploy_mainnet: false)")
    if kind not in SOURCES:
        raise Denied(f"unknown contract kind {kind}")
    ws = db.wallets(identity_id, "evm")
    if not ws:
        raise Denied("identity has no EVM wallet")
    label = (args or {}).get("label") or ws[0]["label"]
    src = SOURCES[kind]
    tool = toolchain()
    if not tool:
        raise Denied("no solc/forge installed — `brew install foundry` or `npm i -g solc`")
    bytecode, abi = (compile_forge(src, kind) if tool == "forge" else compile_solc(src))
    if not bytecode:
        raise Denied("empty bytecode from compiler")
    if not bytecode.startswith("0x"):
        bytecode = "0x" + bytecode

    payload = {"_kind": "deploy", "chain": chain, "identity": identity_id, "kind": kind, "label": label}
    if not gates.consume(payload):
        want, reasons = policy.needs_gate("deploy", chain=chain, mainnet=not policy.chain(chain).get("testnet"))
        if want:
            gates.require("deploy", f"Deploy {kind} di {chain} dari {label} ({len(bytecode)//2} bytes)\n"
                                    f"alasan: {'; '.join(reasons)}", payload)
    out = sender.send(chain, identity_id, label, to=None, calldata=bytecode,
                      broadcast=True, via="deploy", contract_creation=True)
    db.event("deploy", f"{kind} {out.get('tx')}", identity_id)
    return {**out, "kind": kind, "abi": json.loads(abi), "source_bytes": len(src)}


def status() -> dict:
    return {"forge": bool(shutil.which("forge")), "solc": bool(shutil.which("solc")),
            "kinds": list(SOURCES)}
