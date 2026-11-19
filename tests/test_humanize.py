def test_offline_craft_never_empty(home):
    from aa import humanize

    for _ in range(5):
        msg = humanize.craft("casual-id", "gm semua, lagi ngapain?")
        assert msg
        assert len(msg) < 400


def test_llm_mock_cascade(home, monkeypatch):
    from aa import humanize

    monkeypatch.setenv("LLM_MOCK", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert humanize.llm_available() is False
    assert humanize.craft("casual-id", "airdrop apa ini")


def test_typo_mutates_long_words_only(home):
    from aa import humanize

    assert humanize.typo("hi ok") == "hi ok"
    assert humanize.typo("beautiful transaction") != "beautiful transaction"


def test_duplicate_detection(ident):
    from aa import humanize

    humanize.remember(ident, "dc", "agent", "halo semua")
    assert humanize.is_duplicate(ident, "dc", "halo semua")
    assert not humanize.is_duplicate(ident, "dc", "halo bro")


def test_persona_typing(home):
    from aa import humanize

    lo = humanize.typing_seconds("x" * 200, "casual-id")
    assert 1 <= lo <= 120


def test_plan_burst(home):
    from aa import humanize

    parts = humanize.plan_burst("satu dua tiga empat lima enam tujuh delapan sembilan sepuluh", "casual-id")
    assert 1 <= len(parts) <= 3
