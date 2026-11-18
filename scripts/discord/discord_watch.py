#!/usr/bin/env python3
"""Watch Discord announcement channels and forward airdrop-relevant posts to Telegram.

MODE "bot" (recommended, ToS-compliant):
  1. Create your own Discord server + bot (discord.com/developers), enable MESSAGE CONTENT intent.
  2. In each project's server, on its #announcements channel click "Follow" -> pick a channel in YOUR server.
  3. Bot reads those followed channels in your server. env: DISCORD_BOT_TOKEN, DISCORD_WATCH_CHANNEL_IDS
  usage: discord_watch.py bot [--keywords airdrop,snapshot,claim,testnet,quest,role]

MODE "user" (OPT-IN, violates Discord ToS -> account can be banned):
  Read-only polling with the dedicated account's user token. Requires
  DISCORD_USER_TOKEN and DISCORD_USER_TOKEN_OPTIN=I_ACCEPT_BAN_RISK. Never posts, never joins.
  usage: discord_watch.py user --once

Joining servers / role verification (Collab.Land, Guild.xyz, captcha bots) is done by the HUMAN or
by web_quest.py in the logged-in browser profile — never automated with a user token.
All message text is UNTRUSTED: we forward it, we never act on instructions inside it.
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl; _sys.path[:0] = [str(_d) for _d in sorted(_pl.Path(__file__).resolve().parents[1].iterdir()) if _d.is_dir() and not _d.name.startswith(("_", "."))]  # noqa: E702 (script-group import path)

import argparse
import json
import os
import re
import time

import requests

from common import DATA_DIR, check_kill, env_required, get_logger, out
from report_telegram import send

log = get_logger("discord")
STATE = DATA_DIR / "discord_state.json"
SCAM = re.compile(r"(?i)(claim now|connect wallet to claim|limited time|dm me|support ticket|validate wallet|seed|recovery phrase)")


def relevant(text: str, kws: list[str]) -> bool:
    return any(k in text.lower() for k in kws)


def fmt(source: str, author: str, text: str, url: str | None) -> str:
    flag = "\n⚠️ pola scam terdeteksi — JANGAN klik link" if SCAM.search(text) else ""
    return f"📢 <b>{source}</b> · {author}\n{text[:1500]}{flag}" + (f"\n{url}" if url else "")


def run_bot(kws: list[str]) -> None:
    import discord
    ids = {int(x) for x in env_required("DISCORD_WATCH_CHANNEL_IDS").split(",") if x.strip()}
    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        log.info("discord bot ready as %s watching %d channels", client.user, len(ids))

    @client.event
    async def on_message(m):
        if KILL():
            await client.close(); return
        if m.channel.id not in ids:
            return
        text = m.content or " ".join((e.description or e.title or "") for e in m.embeds)
        if relevant(text, kws):
            send(fmt(f"#{m.channel.name}", str(m.author), text, m.jump_url))

    client.run(env_required("DISCORD_BOT_TOKEN"), log_handler=None)


def KILL() -> bool:
    from common import KILL_FILE
    return KILL_FILE.exists()


def run_user(kws: list[str], once: bool) -> None:
    if os.environ.get("DISCORD_USER_TOKEN_OPTIN") != "I_ACCEPT_BAN_RISK":
        raise SystemExit("user-token mode disabled. It violates Discord ToS. Set DISCORD_USER_TOKEN_OPTIN=I_ACCEPT_BAN_RISK to opt in.")
    tok = env_required("DISCORD_USER_TOKEN")
    ids = [x.strip() for x in env_required("DISCORD_WATCH_CHANNEL_IDS").split(",") if x.strip()]
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    h = {"Authorization": tok, "User-Agent": "Mozilla/5.0"}
    while True:
        check_kill()
        forwarded = 0
        for cid in ids:
            params = {"limit": 20}
            if state.get(cid):
                params["after"] = state[cid]
            r = requests.get(f"https://discord.com/api/v9/channels/{cid}/messages", headers=h, params=params, timeout=20)
            if r.status_code == 429:
                time.sleep(float(r.json().get("retry_after", 5)) + 1); continue
            if r.status_code != 200:
                log.warning("channel %s -> HTTP %s", cid, r.status_code); continue
            msgs = sorted(r.json(), key=lambda m: int(m["id"]))
            for m in msgs:
                text = m.get("content") or " ".join((e.get("description") or "") for e in m.get("embeds", []))
                if state.get(cid) and relevant(text, kws):
                    send(fmt(f"channel {cid}", m["author"].get("username", "?"), text, None)); forwarded += 1
                state[cid] = m["id"]
            time.sleep(3 + len(ids) * 0.5)
        STATE.write_text(json.dumps(state))
        if once:
            return out({"forwarded": forwarded})
        time.sleep(600)  # 10 min — keep it slow


def main() -> None:
    check_kill()
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["bot", "user"])
    ap.add_argument("--keywords", default="airdrop,snapshot,claim,testnet,quest,role,whitelist,points,season,faucet,mint")
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    kws = [k.strip().lower() for k in a.keywords.split(",") if k.strip()]
    run_bot(kws) if a.mode == "bot" else run_user(kws, a.once)


if __name__ == "__main__":
    main()
