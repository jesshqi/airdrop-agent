def test_extract_link_and_kind():
    from aa.radar import extract

    e = extract.extract("Airdrop baru di https://claim.example.xyz/jackpot whitelist mint free")
    assert e["links"][0]["url"].startswith("https://claim.example.xyz")
    assert e["kind"] in ("claim", "whitelist", "airdrop")


def test_extract_no_link():
    from aa.radar import extract

    e = extract.extract("testnet monad lagi rame, pada farming")
    assert e["links"] == []
    assert e["kind"] == "testnet"


def test_score_explained():
    from aa.radar import score

    s = score.score({"project": "Monad", "kind": "testnet", "trust": 3, "links": [{"url": "https://monad.xyz", "type": "web"}],
                     "text": "incentivized testnet with points program", "scam": "ok", "age_days": 400})
    assert 0 <= s["score"] <= 100
    assert s["reasons"]


def test_score_penalises_scam():
    from aa.radar import score

    clean = {"project": "X", "kind": "airdrop", "trust": 1, "text": "", "scam": "ok",
             "links": [{"url": "https://app.uniswap.org", "type": "web"}]}
    dirty = dict(clean, links=[{"url": "https://xn--uniswap-ycd.com", "type": "web"}])
    assert score.score(clean)["score"] > score.score(dirty)["score"]


def test_worth_it_threshold(home):
    from aa.radar import score

    assert score.worth_it({"kind": "airdrop", "trust": 3,
                                                      "links": [{"url": "https://app.uniswap.org", "type": "web"}]})[0]
    assert not score.worth_it({"kind": "unknown"})[0]
