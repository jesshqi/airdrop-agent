#!/usr/bin/env python3
"""Airdrop legitimacy + priority scoring.

Automated checks on a URL: https, punycode/lookalike vs official domain, domain age (RDAP),
drainer/scam keywords on the page. Manual checklist answers come from --facts YAML (filled by the
agent after reading OFFICIAL docs/X, never from the suspicious page itself).

usage:
  research_score.py --url https://claim-example.xyz --official example.org [--facts facts.yaml]
facts.yaml example:
  funding_usd: 20000000        # from CryptoRank / DefiLlama raises
  tier1_investors: true
  token_launched: false
  points_program: true
  official_airdrop_confirmed: false
  docs_url: https://docs.example.org
  team_public: true
  cost_to_farm_usd: 5
  requires_kyc: false
Score >= 70: go · 50-69: low effort only · < 50 or any CRITICAL flag: skip + warn.
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl; _sys.path[:0] = [str(_d) for _d in sorted(_pl.Path(__file__).resolve().parents[1].iterdir()) if _d.is_dir() and not _d.name.startswith(("_", "."))]  # noqa: E702 (script-group import path)

import argparse
import datetime as dt
import difflib
import re
from urllib.parse import urlparse

import requests

from common import check_kill, load_yaml, out

BRANDS = ["metamask", "rabby", "phantom", "uniswap", "opensea", "galxe", "zealy", "layer3", "binance",
          "arbitrum", "optimism", "zksync", "starknet", "linea", "scroll", "layerzero", "eigenlayer",
          "hyperliquid", "kinetiq", "monad", "berachain", "jupiter"]
SCAM_TEXT = re.compile(r"(?i)(enter (your )?(seed|recovery|secret) phrase|import wallet|validate wallet|"
                       r"claim (your )?airdrop now|connect wallet to claim|eligible.*claim.*\d+|rectify|"
                       r"setApprovalForAll|increaseAllowance|permit2)")
DRAINER_JS = re.compile(r"(?i)(seaport|inferno|angel ?drainer|pink ?drainer|ace ?drainer|wallet-connect-v2-modal-drain)")


def domain_age_days(host: str) -> int | None:
    root = ".".join(host.split(".")[-2:])
    try:
        j = requests.get(f"https://rdap.org/domain/{root}", timeout=15).json()
        for ev in j.get("events", []):
            if ev.get("eventAction") == "registration":
                d = dt.datetime.fromisoformat(ev["eventDate"].replace("Z", "+00:00"))
                return (dt.datetime.now(dt.timezone.utc) - d).days
    except Exception:
        return None
    return None


def main() -> None:
    check_kill()
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True); ap.add_argument("--official"); ap.add_argument("--facts")
    a = ap.parse_args()
    host = (urlparse(a.url).hostname or "").lower()
    flags, crit, score = [], [], 50

    if not a.url.startswith("https://"):
        crit.append("not https")
    if "xn--" in host:
        crit.append("punycode domain (lookalike)")
    if a.official:
        off = a.official.lower()
        if host == off or host.endswith("." + off):
            score += 15
        else:
            ratio = difflib.SequenceMatcher(None, host.split(".")[-2] if "." in host else host, off.split(".")[0]).ratio()
            if ratio > 0.7:
                crit.append(f"lookalike of official domain {off} (similarity {ratio:.2f})")
            else:
                flags.append(f"not the official domain {off}")
                score -= 15
    for b in BRANDS:
        if b in host and a.official and b not in a.official:
            crit.append(f"brand '{b}' in non-official domain")
    age = domain_age_days(host)
    if age is not None:
        if age < 30:
            crit.append(f"domain only {age} days old")
        elif age < 180:
            flags.append(f"domain {age} days old"); score -= 5
        else:
            score += 5
    try:
        r = requests.get(a.url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        body = r.text[:400000]
        if SCAM_TEXT.search(body):
            crit.append("scam/drainer wording on page: " + SCAM_TEXT.search(body).group(0)[:60])
        if DRAINER_JS.search(body):
            crit.append("known drainer kit signature in page source")
    except Exception as e:
        flags.append(f"fetch failed: {str(e)[:80]}")

    if a.facts:
        f = load_yaml(a.facts)
        fund = f.get("funding_usd") or 0
        score += 15 if fund >= 20_000_000 else 8 if fund >= 5_000_000 else 0
        score += 8 if f.get("tier1_investors") else 0
        score += 10 if f.get("token_launched") is False else -20
        score += 7 if f.get("points_program") else 0
        score += 5 if f.get("official_airdrop_confirmed") else 0
        score += 5 if f.get("team_public") else -5
        score -= 10 if (f.get("cost_to_farm_usd") or 0) > 50 else 0
        if f.get("requires_kyc"):
            flags.append("requires KYC (identity exposure)")
    score = max(0, min(100, score))
    verdict = "SKIP (critical)" if crit else "GO" if score >= 70 else "LOW-EFFORT" if score >= 50 else "SKIP"
    out({"url": a.url, "host": host, "score": score, "verdict": verdict, "critical": crit, "flags": flags,
         "domain_age_days": age})


if __name__ == "__main__":
    main()
