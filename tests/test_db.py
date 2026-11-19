def test_identity_and_wallet_rows(ident):
    from aa import db

    assert db.identity(ident)["label"] == "tester"
    assert len(db.wallets(ident, "evm")) == 2
    assert len(db.wallets(ident, "sol")) == 1
    w = db.wallets(ident, "evm")[0]
    assert w["address"].startswith("0x")


def test_spend_window(ident):
    from aa import db

    w = db.wallets(ident, "evm")[0]
    db.add_spend("sepolia", w["address"], 10)
    assert db.spent_today("sepolia", w["address"]) == 10
    assert db.spent_today("base", w["address"]) == 0


def test_kv(ident):
    from aa import db

    assert db.kv_get("k") is None
    db.kv_set("k", "v")
    assert db.kv_get("k") == "v"


def test_identity_resolve_by_label(ident):
    from aa import db

    assert db.identity("tester")["id"] == ident
    assert db.identity(ident)["id"] == ident
