import asyncio
import json

from aa import db, session, vault


class FakeCtx:
    def __init__(self):
        self.added = []

    async def storage_state(self):
        return {"cookies": [{"name": "auth_token", "value": "t", "domain": ".x.com", "path": "/"}], "origins": []}

    async def add_cookies(self, cookies):
        self.added.extend(cookies)


class FakeBrowser:
    def __init__(self):
        self.context = FakeCtx()


def test_save_and_restore_roundtrip():
    b = FakeBrowser()
    out = asyncio.run(session.save("id-sess", b))
    assert out["saved"] is True
    b2 = FakeBrowser()
    assert asyncio.run(session.restore("id-sess", b2)) == 1
    assert b2.context.added[0]["name"] == "auth_token"
    vault.put_secret("session-id-sess", json.dumps({"at": 0, "state": {"cookies": []}}))


def test_status_shape():
    iid = db.create_identity("sess")["id"]
    rows = session.status(iid)
    assert any(r.get("platform") == "x" for r in rows)
    assert any("state_blob" in r for r in rows)
