def test_scaffold_validates(home):
    from aa.quest import dsl

    q = dsl.scaffold("Test Quest", "https://example.com", "generic", "sepolia")
    assert dsl.validate(q) == []


def test_bad_step_rejected(home):
    from aa.quest import dsl

    q = dsl.scaffold("T", "https://example.com", "generic")
    q["steps"].append({"teleport": True})
    assert any("teleport" in e for e in dsl.validate(q))


def test_missing_url_rejected(home):
    from aa.quest import dsl

    q = dsl.scaffold("T", "https://example.com", "generic")
    q["url"] = ""
    assert any("url" in e for e in dsl.validate(q))


def test_roundtrip_file(home):
    from aa.quest import dsl

    q = dsl.scaffold("Round Trip", "https://example.com", "galxe")
    p = dsl.write_file(q)
    assert p.exists()
    dsl.save(q, status="pending", source="test")
    loaded = dsl.load(q["id"])
    assert loaded["name"] == "Round Trip"
    assert dsl.validate(loaded) == []


def test_due_respects_cooldown(home):
    from aa.quest import dsl

    q = dsl.scaffold("Daily", "https://example.com", "generic")
    dsl.save(q, status="pending", source="test", cooldown_hours=24)
    assert q["id"] in [x["id"] for x in dsl.next_due(5)]


def test_import_rejects_duplicate(home, tmp_path):
    from aa.quest import dsl

    q = dsl.scaffold("Dup", "https://example.com", "generic")
    p = dsl.write_file(q)
    dsl.import_file(p)
    import pytest

    with pytest.raises(Exception):
        dsl.import_file(p)


def test_remove(home):
    from aa.quest import dsl

    q = dsl.scaffold("Gone", "https://example.com", "generic")
    dsl.save(q, status="pending", source="test")
    dsl.remove(q["id"])
    import pytest

    with pytest.raises(Exception):
        dsl.load(q["id"])
