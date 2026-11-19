"""Discord: browser login, token capture, channel follow, humanised role grinding.

User-token ("self") automation is the only way to chat, so it carries ToS risk on a
dedicated account — the CLI says so and never touches a main account's identity.

Chat behaviour: read the room first, reply to a real message most of the time, type
in bursts with human delays, vary length, react occasionally, respect per-channel
cooldowns and stop as soon as the target role/level is reached.
"""
from __future__ import annotations

import asyncio
import random
import re
import time

import requests

from .. import config, db, humanize, ratelimit, vault
from ..browser.engine import Browser
from ..jsonio import Denied
from ..log import get_logger
from . import totp

log = get_logger("discord")
API = "https://discord.com/api/v10"
LEVEL_RX = re.compile(r"(?i)(?:level|level up|naik level|lvl)\D{0,12}(\d+)")


# ---------------- login ----------------
def token(identity_id: str) -> str:
    t = vault.get_secret(f"dc:{identity_id}")
    if not t:
        raise Denied(f"identity {identity_id} has no Discord token (aa dc login --identity ...)")
    return t


def headers(identity_id: str) -> dict:
    return {"authorization": token(identity_id), "content-type": "application/json",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}


TOKEN_JS = r"""
async () => {
  try {
    const raw = localStorage.getItem('token');
    if (raw) { try { const t = JSON.parse(raw); if (typeof t === 'string' && t.length > 20) return t; } catch (_) { if (raw.length > 20) return raw.replace(/"/g, ''); } }
  } catch (_) {}
  const w = window.webpackChunkdiscord_app;
  if (!w) return null;
  const mods = [];
  try { w.push([[Symbol()], {}, (r) => { for (const k in r.c) mods.push(r.c[k]); }]); } catch (_) {}
  for (const m of mods) {
    try {
      const e = m && m.exports;
      const cand = (e && e.default && e.default.getToken && e.default.getToken()) || (e && e.getToken && e.getToken());
      if (cand) return cand;
    } catch (_) {}
  }
  return null;
}
"""


async def login(identity_id: str, email: str, password: str, totp_secret: str = "") -> dict:
    async with Browser(identity_id, profile="discord") as b:
        await b.page.goto("https://discord.com/login", wait_until="domcontentloaded")
        await b.human_wait(2.5, 4.5)
        await b.fill(email, selector='input[name="email"]')
        await b.fill(password, selector='input[name="password"]')
        await b.human_wait(0.6, 1.4)
        await b.click(selector='button[type="submit"]')
        await b.human_wait(3.0, 5.0)

        cap = await b.solve_captcha_if_present()
        if cap.get("state") == "manual":
            log.warning("captcha needs a human on the VNC/desktop session")

        # TOTP prompt
        for _ in range(3):
            code_input = b.page.locator('input[name="code"], input[autocomplete="one-time-code"], input[aria-label*="code" i]').first
            if await code_input.count():
                code = totp.code(totp_secret) if totp_secret else ""
                if not code:
                    return {"logged_in": False, "needs": "totp", "url": b.page.url}
                await code_input.fill(code)
                await b.page.keyboard.press("Enter")
                await b.human_wait(3.0, 5.0)
            else:
                break

        for _ in range(10):
            t = await b.page.evaluate(TOKEN_JS)
            if t:
                vault.put_secret(f"dc:{identity_id}", t)
                me = whoami(identity_id)
                db.add_social(identity_id, "discord", me.get("username", ""), {"id": me.get("id")})
                db.event("discord", "logged in", identity_id)
                return {"logged_in": True, "user": me.get("username"), "id": me.get("id")}
            await asyncio.sleep(2)
        return {"logged_in": False, "url": b.page.url,
                "hint": "captcha or new-device verification likely — open the profile headfully"}


def whoami(identity_id: str) -> dict:
    r = requests.get(f"{API}/users/@me", headers=headers(identity_id), timeout=20)
    if r.status_code == 401:
        raise Denied("Discord token expired — log in again")
    r.raise_for_status()
    return r.json()


def status(identity_id: str) -> dict:
    try:
        me = whoami(identity_id)
        return {"ok": True, "user": f"{me.get('username')}#{me.get('discriminator')}", "id": me.get("id")}
    except Denied as e:
        return {"ok": False, "error": str(e)}


# ---------------- REST helpers ----------------
def guilds(identity_id: str) -> list[dict]:
    r = requests.get(f"{API}/users/@me/guilds", headers=headers(identity_id), timeout=30)
    r.raise_for_status()
    return r.json()


def channels(identity_id: str, guild_id: str) -> list[dict]:
    r = requests.get(f"{API}/guilds/{guild_id}/channels", headers=headers(identity_id), timeout=30)
    r.raise_for_status()
    return [c for c in r.json() if c.get("type") in (0, 5)]


def follow_channel(identity_id: str, channel_id: str) -> dict:
    """Subscribe the user to an announcement channel (best effort; endpoint differs per client)."""
    for body in ({"webhook_channel_id": channel_id}, {}):
        r = requests.post(f"{API}/channels/{channel_id}/followers", headers=headers(identity_id), json=body, timeout=30)
        if r.status_code in (200, 201, 204):
            db.event("follow", f"discord follow channel {channel_id}", identity_id)
            return {"followed": channel_id}
    return {"followed": channel_id, "status": r.status_code, "body": r.text[:200]}


def react(identity_id: str, channel_id: str, message_id: str, emoji: str = "👍") -> dict:
    from urllib.parse import quote

    r = requests.put(f"{API}/channels/{channel_id}/messages/{message_id}/reactions/{quote(emoji)}/@me",
                     headers=headers(identity_id), timeout=30)
    return {"reacted": r.status_code in (200, 204), "status": r.status_code}


def read(identity_id: str, channel_id: str, limit: int = 20) -> list[dict]:
    r = requests.get(f"{API}/channels/{channel_id}/messages", headers=headers(identity_id),
                     params={"limit": limit}, timeout=30)
    if r.status_code == 429:
        raise Denied(f"discord rate limited: retry after {r.json().get('retry_after')}s")
    r.raise_for_status()
    return r.json()


def send(identity_id: str, channel_id: str, text: str, reply_to: str | None = None) -> dict:
    body = {"content": text, "tts": False}
    if reply_to:
        body["message_reference"] = {"message_id": reply_to, "channel_id": channel_id}
    r = requests.post(f"{API}/channels/{channel_id}/messages", headers=headers(identity_id), json=body, timeout=30)
    if r.status_code == 429:
        wait = float(r.json().get("retry_after", 5))
        time.sleep(min(wait, 30))
        r = requests.post(f"{API}/channels/{channel_id}/messages", headers=headers(identity_id), json=body, timeout=30)
    if r.status_code not in (200, 201):
        raise Denied(f"discord send {r.status_code}: {r.text[:200]}")
    return r.json()


def typing(identity_id: str, channel_id: str) -> None:
    requests.post(f"{API}/channels/{channel_id}/typing", headers=headers(identity_id), timeout=15)


# ---------------- config ----------------
def servers() -> dict:
    return config.load_yaml("discord_servers.yaml").get("servers", {})


def server_cfg(name_or_id: str) -> tuple[str, dict]:
    all_s = servers()
    for key, cfg in all_s.items():
        if key == name_or_id or cfg.get("id") == name_or_id or cfg.get("name") == name_or_id:
            return key, cfg
    raise Denied(f"server '{name_or_id}' not in discord_servers.yaml")


def resolve_channels(identity_id: str, cfg: dict) -> list[dict]:
    gid = cfg.get("id")
    found = channels(identity_id, gid) if gid else []
    by_name = {c["name"].lower(): c for c in found}
    out = []
    for want in cfg.get("channels", []):
        if isinstance(want, dict):
            name, weight = want.get("name", ""), want.get("weight", 1)
        else:
            name, weight = str(want), 1
        c = by_name.get(name.lower())
        if not c:
            c = next((x for x in found if x["name"].lower().startswith(name.lower())), None)
        if c:
            out.append({**c, "weight": weight})
    return out


def current_level(messages: list[dict], level_bot: str, role_bot: str = "") -> int | None:
    for m in messages:
        author = ((m.get("author") or {}).get("username") or "").lower()
        if level_bot and level_bot.lower() in author or (role_bot and role_bot.lower() in author):
            mm = LEVEL_RX.search(m.get("content") or "")
            if mm:
                return int(mm.group(1))
    return None


def has_role(identity_id: str, guild_id: str, role_name: str) -> bool:
    me = whoami(identity_id)
    r = requests.get(f"{API}/guilds/{guild_id}/members/{me['id']}", headers=headers(identity_id), timeout=30)
    if r.status_code != 200:
        return False
    roles = r.json().get("roles", [])
    role_map = {x["id"]: x["name"] for x in requests.get(f"{API}/guilds/{guild_id}/roles",
                                                          headers=headers(identity_id), timeout=30).json()}
    return any(role_map.get(rid, "").lower() == role_name.lower() for rid in roles)


# ---------------- grinding ----------------
def pick_channel(identity_id: str, cfg: dict, chans: list[dict]) -> dict | None:
    if not chans:
        return None
    w = [c.get("weight", 1) for c in chans]
    return random.choices(chans, weights=w, k=1)[0]


def context_from(msgs: list[dict], identity_id: str) -> tuple[list[str], dict | None]:
    humans = [m for m in reversed(msgs) if not (m.get("author") or {}).get("bot")
              and (m.get("author") or {}).get("id") != whoami(identity_id).get("id")
              and (m.get("content") or "").strip() and not (m.get("content") or "").startswith("!")]
    texts = [(m.get("content") or "")[:160] for m in humans]
    reply_target = humans[0] if humans and random.random() < 0.7 else None
    return texts, reply_target


def grind_once(identity_id: str, cfg: dict, chans: list[dict], persona: str) -> dict:
    ch = pick_channel(identity_id, cfg, chans)
    if not ch:
        raise Denied("no usable channel")
    msgs = read(identity_id, ch["id"], 25)
    ratelimit.acquire(identity_id, "chat")
    texts, reply_to = context_from(msgs, identity_id)
    kind = "reply" if reply_to else random.choice(["reply", "question", "comment"])
    text = humanize.craft(identity_id, ch["id"], persona, kind=kind,
                          topic=random.choice((humanize.persona(persona).get("interests") or ["airdrop"])),
                          context=texts[-10:])
    plan = humanize.plan_burst(text, humanize.persona(persona))
    latency = humanize.read_delay()
    typing(identity_id, ch["id"])
    time.sleep(typing_ok(latency))
    first = plan[0]
    send(identity_id, ch["id"], first, reply_to=(reply_to or {}).get("id"))
    for extra in plan[1:]:
        time.sleep(random.uniform(1.0, 3.0))
        typing(identity_id, ch["id"])
        time.sleep(typing_ok(len(extra)))
        send(identity_id, ch["id"], extra)
    if random.random() < 0.5 and msgs:
        try:
            react(identity_id, ch["id"], random.choice(msgs)["id"], random.choice(["👍", "🔥", "👀"]))
        except Exception:  # noqa: BLE001
            pass
    db.event("chat", f"discord {ch['name']} {len(text)} chars", identity_id)
    return {"channel": ch["name"], "sent": text, "reply_to": (reply_to or {}).get("id"), "parts": len(plan)}


def typing_ok(seconds: float) -> float:
    return max(0.8, min(seconds, 25.0))


def grind(identity_id: str, server: str, *, minutes: int = 30, max_messages: int = 0,
          persona: str | None = None, dry: bool = False) -> dict:
    key, cfg = server_cfg(server)
    persona = persona or humanize.pick_persona_for(identity_id)
    gid = cfg.get("id") or next((g["id"] for g in guilds(identity_id) if g["name"] == cfg.get("name")), None)
    if not gid:
        raise Denied("server id unknown; set `id` in discord_servers.yaml")
    chans = resolve_channels(identity_id, cfg)
    if not chans:
        raise Denied("no configured channel found in this server (check names/permissions)")
    target_role = cfg.get("target_role", "")
    level_bot = cfg.get("level_bot", "")
    target_level = int(cfg.get("target_level") or 0)
    if target_role and has_role(identity_id, gid, target_role):
        return {"status": "already-done", "role": target_role}

    per_hour = int(cfg.get("max_per_hour") or 12)
    lo, hi = cfg.get("gap_minutes") or [4, 11]
    started, sent, seen = time.time(), 0, 0
    report = []
    while (time.time() - started) < minutes * 60:
        if config.KILL_FILE.exists():
            break
        hist = read(identity_id, chans[0]["id"], 10)
        lvl = current_level(hist, level_bot)
        if target_level and lvl and lvl >= target_level:
            report.append({"stop": "target level reached", "level": lvl})
            break
        if target_role and seen % 6 == 0 and seen and has_role(identity_id, gid, target_role):
            report.append({"stop": "role obtained", "role": target_role})
            break
        try:
            r = grind_once(identity_id, cfg, chans, persona)
            sent += 1
            seen += 1
            report.append(r)
        except Denied as e:
            log.warning("grind paused: %s", e)
            report.append({"pause": str(e)})
            time.sleep(180)
        if max_messages and sent >= max_messages:
            break
        gap = random.uniform(float(lo), float(hi)) * 60
        if sent % per_hour == 0:
            gap *= random.uniform(1.6, 2.4)
        time.sleep(gap)
    return {"server": key, "sent": sent, "minutes": round((time.time() - started) / 60, 1),
            "role": target_role or None, "report": report[-20:]}


def grind_all(identity_id: str, minutes_per_server: int = 20) -> list[dict]:
    out = []
    for name, cfg in servers().items():
        if not cfg.get("enabled", True):
            continue
        try:
            out.append({"server": name, **grind(identity_id, name, minutes=minutes_per_server)})
        except Exception as e:  # noqa: BLE001
            out.append({"server": name, "error": str(e)[:200]})
    return out


def progress(identity_id: str) -> list[dict]:
    out = []
    for name, cfg in servers().items():
        row = {"server": name, "name": cfg.get("name"), "target_role": cfg.get("target_role"),
               "target_level": cfg.get("target_level")}
        gid = cfg.get("id")
        if gid:
            try:
                row["role_held"] = has_role(identity_id, gid, cfg.get("target_role", "")) if cfg.get("target_role") else False
                chans = resolve_channels(identity_id, cfg)
                if chans:
                    row["level"] = current_level(read(identity_id, chans[0]["id"], 15), cfg.get("level_bot", ""))
            except Exception as e:  # noqa: BLE001
                row["error"] = str(e)[:120]
        out.append(row)
    return out
