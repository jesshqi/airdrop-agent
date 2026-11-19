"""Platform adapters — the small amount of per-site knowledge.

They never decide steps; they bias selectors, pre-navigate, and take a completion
screenshot. Unknown platforms fall back to `generic`, which relies on the DSL.
"""
from __future__ import annotations

import re

from ..browser import flows
from ..log import get_logger

log = get_logger("adapter")
GATED = {"galxe", "zealy", "layer3", "questn", "intract"}


class Base:
    name = "generic"
    connect_texts = ["Connect Wallet", "Connect wallet", "Hubungkan Wallet", "Connect"]
    wallet_pick = ["MetaMask", "Rabby", "Injected", "Browser Wallet", "WalletConnect"]
    verify_texts = ["Verify", "Claim", "Complete", "Check", "Klaim"]
    done_markers = ["completed", "verified", "claimed", "success", "selesai"]
    url = ""

    async def prepare(self, b, q):
        self.url = q.get("url", "")
        if self.url:
            await b.goto(self.url)
            await flows.dismiss(b)
        await b.human_wait(1.0, 2.5)

    async def after(self, b, q, proof):
        txt = (await b.text()).lower()
        hit = [m for m in self.done_markers if m in txt]
        proof.append({"adapter": self.name, "completion_markers": hit})
        proof.append({"screenshot": await b.screenshot(f"{self.name}_final")})


class Galxe(Base):
    name = "galxe"
    connect_texts = ["Connect Wallet", "Connect"]
    verify_texts = ["Verify", "Claim", "Check eligibility"]

    async def prepare(self, b, q):
        await super().prepare(b, q)
        try:
            if await b.page.get_by_text(re.compile("accept", re.I)).count():
                await flows.dismiss(b)
        except Exception:  # noqa: BLE001
            pass


class Zealy(Base):
    name = "zealy"
    connect_texts = ["Connect wallet", "Login", "Connect"]
    verify_texts = ["Verify", "Claim", "Complete quest"]


class Layer3(Base):
    name = "layer3"
    connect_texts = ["Connect Wallet", "Connect"]
    verify_texts = ["Verify", "Claim", "Complete"]


class QuestN(Base):
    name = "questn"
    connect_texts = ["Connect Wallet", "Connect"]
    verify_texts = ["Verify", "Claim"]


class Intract(Base):
    name = "intract"
    connect_texts = ["Connect Wallet", "Connect"]
    verify_texts = ["Verify", "Claim"]


REGISTRY = {c.name: c() for c in (Galxe, Zealy, Layer3, QuestN, Intract, Base)}


def get(platform: str) -> Base:
    return REGISTRY.get(platform or "generic", REGISTRY["generic"])
