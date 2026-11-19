"""Extract opportunities out of a post (Telegram message, tweet, page).

Output is structured and untrusted-by-design: links are classified, contracts are
flagged, and a task kind is guessed from the wording.
"""
from __future__ import annotations

import re

URL_RX = re.compile(r"https?://[^\s\"'<>)\]]+")
TG_RX = re.compile(r"(?:https?://)?(?:t\.me|telegram\.me)/(?:joinchat/\+?|\+)?([A-Za-z0-9_+-]{4,})")
X_RX = re.compile(r"(?:https?://)?(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})")
DISCORD_RX = re.compile(r"(?:https?://)?(?:discord\.(?:gg|com/invite))/([A-Za-z0-9-]{4,})")
ADDR_RX = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
SOL_RX = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")

KEYWORDS = {
    "airdrop": ["airdrop", "drop", "claim", "reward", "bag", "token launch", "tge"],
    "testnet": ["testnet", "devnet", "faucet", "sepolia", "base sepolia", "arbitrum sepolia",
                "monad", "berachain", "linea", "scroll", "zksync", "test network"],
    "quest": ["quest", "task", "mission", "points", "xp", "galxe", "zealy", "layer3", "questn", "intract"],
    "follow": ["follow", "retweet", "repost", "like", "rt", "share", "tag"],
    "discord": ["discord", "role", "grinding role", "server"],
    "telegram": ["telegram", "channel", "group", "join"],
    "whitelist": ["whitelist", "allowlist", "wl", "og", "spot", "waitlist", "mint pass"],
    "nft": ["nft", "mint", "opensea", "collection", "free mint"],
    "miniapp": ["mini app", "miniapp", "tap", "tapswap", "telegram app"],
    "points": ["points", "season", "leaderboard", "rank", "streak", "daily"],
}

CHAIN_HINTS = {
    "sepolia": ["sepolia"], "base-sepolia": ["base sepolia", "base testnet"],
    "arbitrum-sepolia": ["arbitrum sepolia", "arb sepolia"],
    "solana-devnet": ["solana devnet", "devnet"],
    "base": ["base mainnet", "on base"], "solana": ["solana"],
}

NOISE = ["gm", "good morning", "price", "chart", "listing", "giveaway ended"]


def clean(text: str) -> str:
    t = re.sub(r"<[^>]+>", " ", text or "")
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()[:8000]


def classify(text: str) -> str:
    low = (text or "").lower()
    best, score = "unknown", 0
    for kind, words in KEYWORDS.items():
        s = sum(2 if w in low else 0 for w in words)
        if s > score:
            best, score = kind, s
    if best == "airdrop" and "testnet" in low:
        return "testnet"
    return best


def links(text: str) -> list[dict]:
    out = []
    for url in URL_RX.findall(text or ""):
        url = url.rstrip(".,;)")
        out.append({"url": url, "type": _url_type(url)})
    for h in TG_RX.findall(text or ""):
        u = "https://t.me/" + h.lstrip("+")
        if not any(x["url"].endswith(h) for x in out):
            out.append({"url": u, "type": "telegram"})
    for h in DISCORD_RX.findall(text or ""):
        u = "https://discord.gg/" + h
        if not any(x["url"].endswith(h) for x in out):
            out.append({"url": u, "type": "discord"})
    for h in X_RX.findall(text or ""):
        if h.lower() in ("i", "home", "hashtag", "search"):
            continue
        if not any(x["url"].lower().endswith(h.lower()) for x in out):
            out.append({"url": f"https://x.com/{h}", "type": "x"})
    seen, uniq = set(), []
    for l in out:
        key = l["url"].lower().rstrip("/")
        if key not in seen:
            seen.add(key)
            uniq.append(l)
    return uniq


def _url_type(url: str) -> str:
    u = url.lower()
    if "t.me/" in u or "telegram.me/" in u:
        return "telegram"
    if "discord.gg/" in u or "discord.com/invite" in u:
        return "discord"
    if "x.com/" in u or "twitter.com/" in u:
        return "x"
    if any(k in u for k in ("galxe.", "zealy.", "layer3.", "questn.", "intract.", "guild.xyz")):
        return "quest"
    if any(k in u for k in ("opensea.", "zora.", "manifold.", "mint")):
        return "nft"
    if any(k in u for k in ("docs.", "gitbook.", "notion.site")):
        return "docs"
    return "web"


def hints(text: str) -> dict:
    low = (text or "").lower()
    chains = [c for c, words in CHAIN_HINTS.items() if any(w in low for w in words)]
    return {"chains": chains,
            "has_contract": bool(ADDR_RX.search(text or "")),
            "contracts": ADDR_RX.findall(text or "")[:3],
            "wants_follow": any(w in low for w in ("follow", "retweet", "repost")),
            "wants_join": any(w in low for w in ("join", "masuk")),
            "noise": sum(1 for n in NOISE if n in low)}


def project_name(text: str, source: str = "") -> str:
    first = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    for sep in ("—", "-", ":", "|"):
        if sep in first:
            cand = first.split(sep)[0].strip(" 🚀🔥✨")
            if 2 < len(cand) < 40:
                return cand
    m = re.search(r"(?i)(?:project|token|protocol)\s*[:\-]?\s*([A-Z][\w .]{2,30})", text or "")
    if m:
        return m.group(1).strip()
    words = re.findall(r"\b[A-Z][A-Za-z0-9]{2,20}\b", (text or "")[:300])
    return words[0] if words else (source or "radar")


def extract(text: str, source: str = "") -> dict:
    t = clean(text)
    return {"text": t, "kind": classify(t), "links": links(t), "hints": hints(t),
            "project": project_name(t, source), "noise": hints(t)["noise"]}


normalize = extract  # old name kept for callers
