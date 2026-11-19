from pathlib import Path

import yaml

from aa.quest import dsl

CFG = Path(__file__).resolve().parents[1] / "config" / "quests"


def test_every_shipped_quest_is_valid():
    files = sorted(CFG.glob("*.yaml"))
    assert files, "no example quests shipped"
    ids = set()
    for f in files:
        q = yaml.safe_load(f.read_text())
        assert q["id"] not in ids, f"duplicate id in {f}"
        ids.add(q["id"])
        assert dsl.validate(q) == [], f
