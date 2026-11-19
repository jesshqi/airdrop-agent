def test_ok_domain(home):
    from aa import scam_check

    v = scam_check.check_url("https://app.uniswap.org/swap")
    assert v["verdict"] in ("ok", "warn")


def test_lookalike(home):
    from aa import scam_check

    v = scam_check.check_url("https://app-uniswap.org")
    assert v["verdict"] in ("warn", "bad")


def test_punycode(home):
    from aa import scam_check

    v = scam_check.check_url("https://xn--uniswap-ycd.com")
    assert v["verdict"] != "ok"


def test_drainer_words(home):
    from aa import scam_check

    v = scam_check.check_page_text("Connect wallet and sign to claim. Approve all to continue.")
    assert v["verdict"] in ("ok", "warn")


def test_bad_host(home):
    from aa import scam_check

    assert scam_check.check_url("http://127.0.0.1:8080")["verdict"] == "warn"
