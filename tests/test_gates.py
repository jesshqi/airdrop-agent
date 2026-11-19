import secrets

import pytest

from aa.jsonio import Gate


def make(payload=None):
    from aa import gates

    payload = payload if payload is not None else {"rand": secrets.token_hex(4)}
    try:
        gates.require("tx", "kirim 0.001", payload)
    except Gate:
        from aa import db

        return db.one("SELECT * FROM gates ORDER BY id DESC LIMIT 1")  # code is stored for local use


def test_require_and_approve(home):
    from aa import gates

    g = make({"_kind": "tx", "chain": "sepolia"})
    assert g["status"] == "pending"
    assert len(g["code"]) == 6
    assert gates.consume({"_kind": "tx", "chain": "sepolia"}) is None
    gates.approve(g["id"], g["code"])
    out = gates.consume({"_kind": "tx", "chain": "sepolia"})
    assert out["gate"] == g["id"]


def test_approve_wrong_code(home):
    from aa import gates

    g = make({"_kind": "tx"})
    with pytest.raises(Exception):
        gates.approve(g["id"], "000000")
    assert gates.list_gates()[0]["status"] == "pending"


def test_double_use(home):
    from aa import gates

    g = make({"a": 1})
    gates.approve(g["id"], g["code"])
    assert gates.consume({"a": 1})
    assert gates.consume({"a": 1}) is None


def test_reject(home):
    from aa import gates

    g = make({"b": 2})
    gates.reject(g["id"])
    assert gates.consume({"b": 2}) is None


def test_expired_not_usable(home, monkeypatch):
    from aa import gates

    g = make({"c": 3})
    gates.approve(g["id"], g["code"])
    monkeypatch.setattr(gates, "_ttl", lambda: -1)
    assert gates.consume({"c": 3}) is None


def test_kill_blocks_require(home):
    from aa import gates, guard

    guard.kill("test")
    with pytest.raises(Exception):
        gates.require("tx", "x", {"z": 9})
    guard.unkill()
    assert make({"d": 4})
