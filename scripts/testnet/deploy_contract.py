#!/usr/bin/env python3
"""Build a Foundry project and deploy a contract through safe_send (simulation + caps + gates).

usage: deploy_contract.py --project-dir ~/contracts/counter --contract Counter --chain sepolia --label main-burner [--broadcast]
Constructor args: not supported here (keep testnet demo contracts arg-less, or append ABI-encoded args with --ctor-hex).
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl; _sys.path[:0] = [str(_d) for _d in sorted(_pl.Path(__file__).resolve().parents[1].iterdir()) if _d.is_dir() and not _d.name.startswith(("_", "."))]  # noqa: E702 (script-group import path)

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from common import check_kill, out, script


def main() -> None:
    check_kill()
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", required=True); ap.add_argument("--contract", required=True)
    ap.add_argument("--chain", required=True); ap.add_argument("--label", required=True)
    ap.add_argument("--ctor-hex", default=""); ap.add_argument("--broadcast", action="store_true")
    ap.add_argument("--gate-id")
    a = ap.parse_args()
    d = Path(os.path.expanduser(a.project_dir))
    b = subprocess.run(["forge", "build"], cwd=d, capture_output=True, text=True)
    if b.returncode != 0:
        return out({"build": "failed", "stderr": b.stderr[-500:]})
    art = json.loads((d / "out" / f"{a.contract}.sol" / f"{a.contract}.json").read_text())
    code = art["bytecode"]["object"] + a.ctor_hex.removeprefix("0x")
    with tempfile.NamedTemporaryFile("w", suffix=".bin", delete=False) as f:
        f.write(code)
    cmd = [sys.executable, script("safe_send.py"), "--chain", a.chain, "--label", a.label,
           "--deploy-bytecode", f.name]
    if a.broadcast: cmd.append("--broadcast")
    if a.gate_id: cmd += ["--gate-id", a.gate_id]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout or r.stderr)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
