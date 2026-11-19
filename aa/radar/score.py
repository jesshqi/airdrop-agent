"""Opportunity scoring (0-100) — decides whether an item is worth a wallet.

Score is heuristic and explainable: every point has a reason, so the digest shows why.
No LLM is required; an LLM classifier is available but optional.
"""
from __future__ import annotations

from .. import config, scam_check

POSITIVE = {
    "airdrop": 20, "testnet": 18, "quest": 16, "points": 12, "whitelist": 14,
    "miniapp": 10, "follow": 6, "nft": 6, "discord": 5, "telegram": 4,
}
RECENT_MIN = 3600


def _score(item: dict, source_trust: int = 1) -> tuple[int, list[str]]:
    s, why = 40, []
    kind = item.get("kind", "unknown")
    if kind == "unknown":
        s -= 12
        why.append("kind unclear")
    else:
        s += POSITIVE.get(kind, 0)
        why.append(f"kind={kind}")

    h = item.get("hints", {})
    if h.get("has_contract"):
        s += 6
        why.append("contract address present")
    if h.get("chains"):
        s += 6
        why.append("chain hint " + ",".join(h["chains"]))
    if h.get("wants_follow"):
        s += 4
        why.append("social asks")
    if h.get("wants_join"):
        s += 3

    qlinks = [l for l in item.get("links", []) if l["type"] in ("quest", "web")]
    if qlinks:
        s += 8
        why.append(f"{len(qlinks)} actionable link(s)")
    if any(l["type"] == "docs" for l in item.get("links", [])):
        s += 3
        why.append("docs link")
    for l in qlinks[:3]:
        v = scam_check.check_url(l["url"])
        if v["verdict"] == "bad":
            s -= 10
            why.append(f"drainer-ish domain {l['url'][:40]}")
        elif v["verdict"] == "warn":
            s -= 3
            why.append("domain warning")

    s += int(max(0, min(10, (source_trust - 1) * 4)))
    if source_trust >= 3:
        why.append("trusted source")

    eng = int(item.get("likes") or 0) + 2 * int(item.get("replies") or 0)
    if eng >= 200:
        s += 8
        why.append("high engagement")
    elif eng >= 30:
        s += 4
    if item.get("noise", 0) >= 2:
        s -= 6
        why.append("noisy post")

    if not item.get("links") and kind not in ("whitelist", "nft"):
        s -= 8
        why.append("no link")
    return max(0, min(100, s)), why


def label(s: int) -> str:
    if s >= 75:
        return "high"
    if s >= 55:
        return "medium"
    return "low"


def score(item: dict, source_trust: int = 1) -> dict:
    """Public form: {'score': 0-100, 'reasons': [...]}."""
    s, why = _score(item, source_trust)
    return {"score": s, "reasons": why, "label": label(s)}


def worth_it(item: dict, source_trust: int = 1) -> tuple[bool, int, list[str]]:
    s, why = _score(item, source_trust)
    threshold = int(config.load_yaml("radar_sources.yaml").get("min_score", 55))
    return s >= threshold, s, why
