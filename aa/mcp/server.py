"""Minimal MCP server (stdio JSON-RPC) so Hermes, Muse, Claude Desktop, Cursor or any
MCP client can drive the agent without shell access.

Tools return the same JSON envelope as the CLI. Nothing is printed on stdout except
protocol frames; logs go to stderr.
"""
from __future__ import annotations

import asyncio
import json
import sys

from .. import __version__, cli

TOOLS = [
    ("aa_status", "Agent status: mode, kill switch, identities, gates", {}),
    ("aa_identity_new", "Create a new identity (persona + proxy + wallet set)",
     {"label": {"type": "string"}, "with_email": {"type": "boolean"}, "wallet_count": {"type": "integer"}}),
    ("aa_wallet_new", "Generate burner wallets for an identity",
     {"identity": {"type": "string"}, "chain": {"type": "string"}, "count": {"type": "integer"}}),
    ("aa_wallet_list", "List wallets (addresses only)", {"identity": {"type": "string"}}),
    ("aa_wallet_balance", "Balances for an identity", {"identity": {"type": "string"}}),
    ("aa_tx_send", "Send native value through the guarded pipeline",
     {"chain": {"type": "string"}, "identity": {"type": "string"}, "label": {"type": "string"},
      "to": {"type": "string"}, "amount": {"type": "number"}, "broadcast": {"type": "boolean"}}),
    ("aa_sign_message", "Sign a message under the sign policy",
     {"identity": {"type": "string"}, "label": {"type": "string"}, "message": {"type": "string"}}),
    ("aa_telegram_join", "Join a Telegram channel/group", {"identity": {"type": "string"}, "target": {"type": "string"}}),
    ("aa_x_follow", "Follow X accounts", {"identity": {"type": "string"}, "handles": {"type": "array"}}),
    ("aa_discord_grind", "Grind chat roles in one server",
     {"identity": {"type": "string"}, "server": {"type": "string"}, "minutes": {"type": "integer"}}),
    ("aa_email_otp", "Read the latest OTP from the agent inbox",
     {"identity": {"type": "string"}, "sender": {"type": "string"}}),
    ("aa_quest_list", "List quests", {"status": {"type": "string"}}),
    ("aa_quest_run", "Run a quest", {"quest": {"type": "string"}, "identity": {"type": "string"}}),
    ("aa_radar_scan", "Scan radar sources and queue finds", {"identity": {"type": "string"}}),
    ("aa_autopilot_tick", "Run one autopilot tick", {}),
    ("aa_gate_list", "List pending approval gates", {}),
    ("aa_gate_approve", "Approve a gate with its code", {"id": {"type": "integer"}, "code": {"type": "string"}}),
    ("aa_daily_run", "Run daily check-ins for an identity", {"identity": {"type": "string"}}),
    ("aa_session_status", "Login state per platform for an identity", {"identity": {"type": "string"}}),
    ("aa_session_warm", "Warm logged-in sessions so they do not rot", {"identity": {"type": "string"}}),
    ("aa_cf_status", "Cached Cloudflare clearances", {}),
]


def _schema(params: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": params, "required": required or [],
            "additionalProperties": False}


def tool_list() -> list[dict]:
    out = []
    for name, desc, props in TOOLS:
        out.append({"name": name, "description": desc, "inputSchema": _schema(props)})
    return out


def dispatch(name: str, a: dict) -> dict:
    from .. import autopilot, gates, guard, db
    from ..email import imap
    from ..quest import dsl, runner
    from ..radar import pipeline
    from ..social import discord, telegram, x
    from ..wallet import evm as evmw

    if name == "aa_status":
        return {"version": __version__, "guard": guard.status(), "identities": len(db.identities()),
                "gates_pending": len(gates.list_gates())}
    if name == "aa_identity_new":
        return cli.identity_new(a["label"], a.get("with_email", False), a.get("wallet_count", 1))
    if name == "aa_wallet_new":
        return {"wallets": evmw.derive(a["identity"], a.get("count", 1))}
    if name == "aa_wallet_list":
        return {"wallets": [{k: w[k] for k in ("label", "address", "chain")} for w in db.rows(
            "SELECT label,address,chain FROM wallets WHERE identity_id=?", (a["identity"],))]}
    if name == "aa_wallet_balance":
        return cli.wallet_balance(a["identity"], a.get("chain"))
    if name == "aa_tx_send":
        return cli.do_send(a["chain"], a["identity"], a.get("label", "first"), a["to"],
                           a.get("amount", 0), broadcast=a.get("broadcast", False))
    if name == "aa_sign_message":
        return cli.do_sign(a["identity"], a.get("label", "first"), a["message"])
    if name == "aa_telegram_join":
        return asyncio.run(telegram.join(a["identity"], a["target"]))
    if name == "aa_x_follow":
        return {"results": asyncio.run(x.follow(a["identity"], a["handles"]))}
    if name == "aa_discord_grind":
        return discord.grind(a["identity"], a["server"], minutes=a.get("minutes", 15))
    if name == "aa_email_otp":
        return imap.wait_otp(a.get("identity"), sender=a.get("sender", ""), timeout=120)
    if name == "aa_quest_list":
        return {"quests": dsl.listing(a.get("status"))}
    if name == "aa_quest_run":
        q = dsl.load(a["quest"])
        return asyncio.run(runner.run(q, a["identity"], headless=True))
    if name == "aa_radar_scan":
        return asyncio.run(pipeline.scan(a["identity"]))
    if name == "aa_autopilot_tick":
        return asyncio.run(autopilot.tick(headless=True))
    if name == "aa_gate_list":
        return {"gates": gates.list_gates()}
    if name == "aa_gate_approve":
        return gates.approve(a["id"], a["code"])
    if name == "aa_daily_run":
        return asyncio.run(cli.do_daily(a["identity"]))
    if name == "aa_session_status":
        from .. import session

        return {"platforms": session.status(a["identity"])}
    if name == "aa_session_warm":
        from .. import session

        return {"results": asyncio.run(session.warm_all(a["identity"]))}
    if name == "aa_cf_status":
        from ..browser import cf

        return {"clearance": cf.status()}
    raise KeyError(name)


def _send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def serve() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            _send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        rid, method = req.get("id"), req.get("method")
        try:
            if method == "initialize":
                _send({"jsonrpc": "2.0", "id": rid, "result": {
                    "protocolVersion": req.get("params", {}).get("protocolVersion", "2024-11-05"),
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "airdrop-agent", "version": __version__}}})
            elif method in ("notifications/initialized", "initialized"):
                continue
            elif method == "tools/list":
                _send({"jsonrpc": "2.0", "id": rid, "result": {"tools": tool_list()}})
            elif method == "ping":
                _send({"jsonrpc": "2.0", "id": rid, "result": {}})
            elif method == "tools/call":
                params = req.get("params") or {}
                name, args = params.get("name"), params.get("arguments") or {}
                result = dispatch(name, args)
                _send({"jsonrpc": "2.0", "id": rid, "result": {
                    "content": [{"type": "text", "text": json.dumps(result, default=str, indent=2)}],
                    "isError": False}})
            else:
                _send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"unknown method {method}"}})
        except Exception as e:  # noqa: BLE001
            _send({"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}})


if __name__ == "__main__":
    serve()
