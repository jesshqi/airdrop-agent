#!/usr/bin/env python3
"""The ONLY allowed way for the agent to send an EVM transaction.

Pipeline: kill-switch -> chain allowlist -> calldata decode (refuse unlimited approvals)
-> contract allowlist -> per-tx/daily caps -> estimateGas + eth_call simulation
-> human gate if needed -> sign locally -> broadcast -> receipt -> spend ledger + proof.

Default is DRY RUN. Add --broadcast to actually send.
RISK=ON (risk_mode.py): gate reasons are auto-approved ONLY for labels in policy.risk_on.wallet_labels on chains with
risk_on caps, and only within those per-tx/daily/gas caps; over a cap -> normal gate. Unlimited approvals, blocklist,
setApprovalForAll(true) and KILL are never automatic. Every broadcast in RISK=ON is reported to Telegram with tx hash.

examples:
  safe_send.py --chain sepolia --label main-burner --to 0xSelf --value-eth 0.0001
  safe_send.py --chain sepolia --label main-burner --to 0xNFT --sig "mint(uint256)" --args 1 --broadcast
  safe_send.py --chain sepolia --label main-burner --deploy-bytecode out/Counter.bin --broadcast
  safe_send.py ... --broadcast --gate-id 12      (after human approved gate 12)
exit codes: 0 ok, 2 refused by policy, 3 simulation failed, 10 waiting for human gate, 99 kill
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl; _sys.path[:0] = [str(_d) for _d in sorted(_pl.Path(__file__).resolve().parents[1].iterdir()) if _d.is_dir() and not _d.name.startswith(("_", "."))]  # noqa: E702 (script-group import path)

import argparse
import json
import sys
import time
from decimal import Decimal

from common import PROOF_DIR, check_kill, get_logger, load_policy, out
from chains import w3_for
import task_queue as tq
import vault
import risk_mode as RM

log = get_logger("safe_send")
MAX_UINT_HALF = 2 ** 255
SEL = {
    "0x095ea7b3": "approve(address,uint256)",
    "0x39509351": "increaseAllowance(address,uint256)",
    "0xa22cb465": "setApprovalForAll(address,bool)",
    "0xa9059cbb": "transfer(address,uint256)",
    "0x23b872dd": "transferFrom(address,address,uint256)",
    "0x42842e0e": "safeTransferFrom(address,address,uint256)",
}


def encode_call(sig: str, args: list[str]) -> str:
    from eth_abi import encode
    from eth_utils import keccak
    types = sig[sig.index("(") + 1:sig.rindex(")")]
    tlist = [t.strip() for t in types.split(",")] if types.strip() else []
    if len(tlist) != len(args):
        raise SystemExit(f"{sig} expects {len(tlist)} args, got {len(args)}")
    conv = []
    for t, v in zip(tlist, args):
        if t.startswith(("uint", "int")):
            conv.append(int(v, 0))
        elif t == "bool":
            conv.append(v.lower() in ("1", "true", "yes"))
        elif t.startswith("bytes") and v.startswith("0x"):
            conv.append(bytes.fromhex(v[2:]))
        else:
            conv.append(v)
    return "0x" + (keccak(text=sig.replace(" ", ""))[:4] + encode(tlist, conv)).hex()


def classify(data: str) -> tuple[str | None, list[str]]:
    """Return (function name, reasons_to_gate). Raises SystemExit on hard refusals."""
    reasons: list[str] = []
    if not data or data == "0x":
        return None, reasons
    sel = data[:10].lower()
    fn = SEL.get(sel)
    if fn in ("approve(address,uint256)", "increaseAllowance(address,uint256)"):
        amount = int(data[74:138], 16) if len(data) >= 138 else 0
        if amount >= MAX_UINT_HALF:
            log.error("REFUSED unlimited approval")
            out({"refused": "unlimited approval is never allowed; use exact amount"}); sys.exit(2)
        reasons.append(f"token approval {fn} amount={amount}")
    elif fn == "setApprovalForAll(address,bool)":
        if len(data) >= 138 and int(data[74:138], 16) == 1:
            reasons.append("setApprovalForAll(true) — operator gets ALL NFTs")
    return fn, reasons


def main() -> None:
    check_kill()
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--to")
    ap.add_argument("--value-eth", default="0")
    ap.add_argument("--value-wei", type=int, help="exact wei (overrides --value-eth)")
    ap.add_argument("--origin", default="cli", help="who asked (cli, page host) — shown in the gate")
    ap.add_argument("--data", default="0x")
    ap.add_argument("--sig"); ap.add_argument("--args", nargs="*", default=[])
    ap.add_argument("--deploy-bytecode", help="file with hex bytecode (contract creation)")
    ap.add_argument("--broadcast", action="store_true")
    ap.add_argument("--gate-id", type=int)
    ap.add_argument("--task-id", type=int)
    ap.add_argument("--no-wait", action="store_true")
    a = ap.parse_args()

    pol = load_policy()
    w3, cfg = w3_for(a.chain)
    sender = vault.address(a.label)
    data = encode_call(a.sig, a.args) if a.sig else a.data
    deploy = bool(a.deploy_bytecode)
    if deploy:
        data = open(a.deploy_bytecode).read().strip()
        data = data if data.startswith("0x") else "0x" + data
        to = None
    else:
        if not a.to:
            raise SystemExit("--to required")
        to = w3.to_checksum_address(a.to)
    value = a.value_wei if a.value_wei is not None else w3.to_wei(Decimal(a.value_eth), "ether")

    gate_reasons: list[str] = []
    fn, r = classify(data)
    gate_reasons += r

    # chain class
    if not cfg.get("testnet", False) and pol.get("mainnet_requires_gate", True):
        gate_reasons.append(f"mainnet chain {a.chain}")

    # contract allowlist
    allow = {x.lower() for x in pol.get("contracts_allowlist", {}).get(a.chain, [])}
    if deploy:
        if not (cfg.get("testnet") and pol.get("allow_deploy_on_testnet", True)):
            gate_reasons.append("contract deployment")
    else:
        is_contract = len(w3.eth.get_code(to)) > 0
        if (is_contract or data != "0x") and to.lower() not in allow and to.lower() != sender.lower():
            gate_reasons.append(f"new contract not in allowlist: {to}")
        blocked = {x.lower() for x in pol.get("blocklist", [])}
        if to.lower() in blocked:
            out({"refused": "destination is blocklisted"}); sys.exit(2)

    # caps
    max_tx = w3.to_wei(Decimal(str(cfg.get("max_tx_native", 0))), "ether")
    max_day = w3.to_wei(Decimal(str(cfg.get("max_daily_native", 0))), "ether")
    if value > max_tx:
        gate_reasons.append(f"value {w3.from_wei(value,'ether')} > per-tx cap {cfg.get('max_tx_native')}")

    # build + simulate
    tx = {"from": sender, "value": value, "data": data, "chainId": cfg["chain_id"],
          "nonce": w3.eth.get_transaction_count(sender, "pending")}
    if to:
        tx["to"] = to
    try:
        call_tx = {k: v for k, v in tx.items() if k in ("from", "to", "value", "data")}
        w3.eth.call(call_tx)
        gas = int(w3.eth.estimate_gas(call_tx) * 1.2)
    except Exception as e:
        log.error("simulation failed: %s", e)
        out({"simulation": "FAILED", "error": str(e)[:300], "action": "not broadcasting"}); sys.exit(3)
    tx["gas"] = gas
    try:
        base = w3.eth.get_block("latest")["baseFeePerGas"]
        prio = w3.eth.max_priority_fee
        tx["maxPriorityFeePerGas"] = prio
        tx["maxFeePerGas"] = int(base * 2 + prio)
        fee_cap = gas * tx["maxFeePerGas"]
    except Exception:
        tx["gasPrice"] = w3.eth.gas_price
        fee_cap = gas * tx["gasPrice"]
    # RISK=ON: separate risk_on caps; auto only for burner labels on chains that have risk_on caps
    rcaps = RM.caps(a.chain) if RM.is_on() and RM.label_ok(a.label) else None
    risk_block: list[str] = []
    if rcaps:
        r_tx = w3.to_wei(Decimal(str(rcaps["max_tx_native"])), "ether")
        r_day = w3.to_wei(Decimal(str(rcaps["max_daily_native"])), "ether")
        r_gas = w3.to_wei(Decimal(str(rcaps["max_gas_native"])), "ether")
        if value > r_tx:
            risk_block.append(f"risk_on per-tx cap {rcaps['max_tx_native']}")
        if fee_cap > r_gas:
            risk_block.append(f"risk_on gas cap {rcaps['max_gas_native']}")
        if tq.spent_today(a.chain, a.label) + value + fee_cap > r_day:
            risk_block.append(f"risk_on daily cap {rcaps['max_daily_native']}")
        if any(x.startswith("setApprovalForAll(true)") for x in gate_reasons):
            risk_block.append("setApprovalForAll(true) is never automatic")
    max_gas = w3.to_wei(Decimal(str(cfg.get("max_gas_native", 0.01))), "ether")
    if rcaps and not risk_block:
        max_gas = max(max_gas, w3.to_wei(Decimal(str(rcaps["max_gas_native"])), "ether"))
    if fee_cap > max_gas:
        out({"refused": f"gas cost cap exceeded ({w3.from_wei(fee_cap,'ether')} > {cfg.get('max_gas_native')})"}); sys.exit(2)
    if tq.spent_today(a.chain, a.label) + value + fee_cap > max_day:
        gate_reasons.append("daily spend cap would be exceeded")
    bal = w3.eth.get_balance(sender)
    if bal < value + fee_cap:
        out({"refused": "insufficient balance", "balance": str(w3.from_wei(bal, "ether"))}); sys.exit(2)

    summary = (f"{a.chain} · from {a.label} {sender} · to {to or 'NEW CONTRACT'} · value "
               f"{w3.from_wei(value,'ether')} {cfg.get('native','ETH')} · fn {fn or (data[:10] if data!='0x' else 'native')}"
               f" · max fee {w3.from_wei(fee_cap,'ether')}")
    payload = {"chain": a.chain, "label": a.label, "to": to, "value": str(value), "data": data}
    result = {"summary": summary, "simulation": "OK", "gas": gas, "gate_reasons": gate_reasons}
    risk_auto = bool(rcaps) and not risk_block
    if RM.is_on():
        result["risk_mode"] = "ON:auto" if risk_auto else f"ON:gated ({'; '.join(risk_block) or 'no risk_on caps/label'})"

    if not a.broadcast:
        result["mode"] = "DRY_RUN (add --broadcast)"
        return out(result)

    if gate_reasons and risk_auto:
        log.warning("RISK=ON auto-approve tx (%s)", "; ".join(gate_reasons))
    elif gate_reasons:
        if a.gate_id and tq.gate_approved(a.gate_id, payload):
            log.info("gate %s approved, proceeding", a.gate_id)
        elif not a.gate_id and (gid := tq.consume_approved(payload)):
            log.info("matching approved gate %s found, proceeding", gid)
        else:
            gid = tq.pending_gate_for(payload) or tq.create_gate(
                "tx", f"[{a.origin}] " + summary + "\nAlasan: " + "; ".join(gate_reasons), payload, a.task_id)
            result.update(mode="WAITING_FOR_HUMAN", gate_id=gid,
                          next=f"after approval rerun with --broadcast --gate-id {gid}")
            out(result); sys.exit(10)

    check_kill()
    acct = vault.load_evm(a.label)
    signed = acct.sign_transaction(tx)
    del acct
    h = w3.eth.send_raw_transaction(signed.raw_transaction).hex()
    h = h if h.startswith("0x") else "0x" + h
    log.info("broadcast %s %s", a.chain, h)
    tq.add_spend(a.chain, a.label, value + fee_cap)
    result.update(mode="BROADCAST", tx_hash=h, explorer=f"{cfg.get('explorer','').rstrip('/')}/tx/{h}" if cfg.get("explorer") else None)
    if not a.no_wait:
        rc = w3.eth.wait_for_transaction_receipt(h, timeout=180)
        result.update(status="success" if rc.status == 1 else "reverted", block=rc.blockNumber,
                      contract=rc.contractAddress)
    if RM.is_on():
        RM.report("tx broadcast" + (" (auto, no approval)" if gate_reasons and risk_auto else ""), f"{a.chain} · {a.origin}",
                  {"from": f"{a.label} {sender}", "to": to or "NEW CONTRACT", "value": f"{w3.from_wei(value,'ether')} {cfg.get('native','ETH')}",
                   "fn": fn or "native", "tx": h, "explorer": result.get("explorer"), "bypassed": "; ".join(gate_reasons) or "-"})
    (PROOF_DIR / f"tx_{a.chain}_{int(time.time())}.json").write_text(json.dumps(result, default=str, indent=2))
    out(result)


if __name__ == "__main__":
    main()
