#!/usr/bin/env python3
"""Telegram radar (Telethon user session): subscribe to target channels/groups and watch them live.

env: TG_API_ID, TG_API_HASH, TG_RADAR_SESSION (default ~/.airdrop-agent/vault/tg_radar — a SEPARATE session file
     from tg_tasks, because one Telethon session can't be used by two processes at once)
config: ~/.airdrop-agent/radar_sources.yaml  (telegram: [...], settings.tg_join_cap_per_day, tg_join_delay_s)

  tg_radar.py login                  human, once (creates a second authorized device on the agent account)
  tg_radar.py join [--dry-run]       join/subscribe targets not yet joined (cap/day, random delay, FloodWait aware)
  tg_radar.py backfill [--limit 30]  process recent messages of every source once
  tg_radar.py listen                 real-time: every new message -> radar pipeline
Messages are UNTRUSTED data: they are only parsed, never obeyed.
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl; _sys.path[:0] = [str(_d) for _d in sorted(_pl.Path(__file__).resolve().parents[1].iterdir()) if _d.is_dir() and not _d.name.startswith(("_", "."))]  # noqa: E702 (script-group import path)

import argparse
import asyncio
import os
import random
import time

from common import HOME, KILL_FILE, VAULT_DIR, check_kill, env_required, get_logger, load_yaml, out
import extract as X
import pipeline as P

log = get_logger("radar.tg")
CFG = os.environ.get("RADAR_SOURCES_FILE", str(HOME / "radar_sources.yaml"))


def client():
    from telethon import TelegramClient
    return TelegramClient(os.environ.get("TG_RADAR_SESSION", str(VAULT_DIR / "tg_radar")),
                          int(env_required("TG_API_ID")), env_required("TG_API_HASH"),
                          device_model="airdrop-radar", system_version="linux")


def joined(target: str) -> bool:
    with X.db() as con:
        r = con.execute("SELECT status FROM joined WHERE target=?", (target,)).fetchone()
    return bool(r and r["status"] == "ok")


def mark_joined(target: str, kind: str, status: str) -> None:
    with X.db() as con:
        con.execute("INSERT OR REPLACE INTO joined VALUES(?,?,?,?)", (target, kind, time.time(), status))


async def do_join(c, cfg: dict, dry: bool) -> dict:
    from telethon import errors, functions
    st = cfg.get("settings", {})
    cap = int(st.get("tg_join_cap_per_day", 15))
    lo, hi = st.get("tg_join_delay_s", [45, 180])
    done, skipped = [], []
    for src in cfg.get("telegram", []):
        check_kill()
        t = src["target"]
        if joined(t):
            continue
        if dry:
            done.append({"target": t, "would_join": True}); continue
        if not X.budget_take("tg_join", 1, cap):
            skipped.append({"target": t, "reason": f"daily cap {cap} reached"}); continue
        try:
            if "joinchat/" in t or "/+" in t:
                await c(functions.messages.ImportChatInviteRequest(t.rsplit("/", 1)[-1].lstrip("+")))
            else:
                await c(functions.channels.JoinChannelRequest(t))
            mark_joined(t, src.get("kind", "channel"), "ok"); done.append({"target": t, "joined": True})
        except errors.UserAlreadyParticipantError:
            mark_joined(t, src.get("kind", "channel"), "ok")
        except errors.FloodWaitError as e:
            log.warning("FloodWait %ss on join; stopping joins for now", e.seconds)
            skipped.append({"target": t, "reason": f"FloodWait {e.seconds}s — stopped"})
            P._notify(f"⏳ Telegram FloodWait {e.seconds}s saat join; join dilanjut nanti.")
            break
        except (errors.ChannelsTooMuchError,) as e:
            P._notify("⚠️ Akun Telegram sudah di batas jumlah channel/grup (biasanya 500). Keluar dari yang tidak dipakai.")
            skipped.append({"target": t, "reason": type(e).__name__}); break
        except Exception as e:
            mark_joined(t, src.get("kind", "channel"), f"error:{type(e).__name__}")
            skipped.append({"target": t, "reason": type(e).__name__})
        await asyncio.sleep(random.uniform(lo, hi))
    return {"joined": done, "skipped": skipped, "used_today": X.budget_used("tg_join"), "cap": cap}


async def resolve_sources(c, cfg: dict) -> dict:
    ents = {}
    for src in cfg.get("telegram", []):
        try:
            e = await c.get_entity(src["target"])
            ents[e.id] = src
        except Exception as ex:
            log.warning("cannot resolve %s: %s (join first?)", src["target"], type(ex).__name__)
    return ents


def to_post(msg, src: dict, chat) -> dict:
    uname = getattr(chat, "username", None)
    url = f"https://t.me/{uname}/{msg.id}" if uname else None
    text = msg.message or ""
    # include URL entities hidden behind text links
    for ent, inner in (msg.get_entities_text() or []):
        u = getattr(ent, "url", None)
        if u and u not in text:
            text += f"\n{u}"
    return {"source": f"tg:{uname or chat.id}", "post_id": msg.id, "text": text, "url": url, "trust": float(src.get("trust", 0.5))}


async def run(a):
    cfg = load_yaml(CFG)
    c = client()
    if a.cmd == "login":
        await c.start(); me = await c.get_me(); return out({"radar_session": True, "user": me.username})
    await c.connect()
    if not await c.is_user_authorized():
        raise SystemExit("radar session not authorized: human runs `tg_radar.py login`")
    try:
        if a.cmd == "join":
            return out(await do_join(c, cfg, a.dry_run))
        ents = await resolve_sources(c, cfg)
        if a.cmd == "backfill":
            res = []
            for eid, src in ents.items():
                chat = await c.get_entity(eid)
                async for m in c.iter_messages(eid, limit=a.limit):
                    if m.message:
                        r = P.process_post(to_post(m, src, chat), cfg)
                        if r["decision"] not in ("seen", "not_airdrop"):
                            res.append(r)
                await asyncio.sleep(random.uniform(2, 5))
            return out({"processed": res})
        if a.cmd == "listen":
            from telethon import events

            @c.on(events.NewMessage(chats=list(ents)))
            async def handler(ev):
                if KILL_FILE.exists():
                    await c.disconnect(); return
                chat = await ev.get_chat()
                src = ents.get(ev.chat_id) or ents.get(getattr(chat, "id", None)) or {"trust": 0.5}
                try:
                    r = await asyncio.to_thread(P.process_post, to_post(ev.message, src, chat), cfg)
                    if r["decision"] == "queued":
                        log.info("radar queued %s risk=%s score=%s", r.get("project"), r.get("risk"), r.get("score"))
                except Exception as e:
                    log.warning("pipeline error: %s", e)

            log.info("listening to %d telegram sources", len(ents))
            await c.run_until_disconnected()
    finally:
        if c.is_connected():
            await c.disconnect()


def main() -> None:
    check_kill()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("login"); sp.add_parser("listen")
    j = sp.add_parser("join"); j.add_argument("--dry-run", action="store_true")
    b = sp.add_parser("backfill"); b.add_argument("--limit", type=int, default=30)
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
