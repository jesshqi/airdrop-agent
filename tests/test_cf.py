import json
import time

from aa.browser import cf
from aa import vault


def test_detect_managed_and_turnstile():
    assert cf.detect("<html>Just a moment...</html>", "Just a moment...", 403) == "turnstile"
    assert cf.detect("<script src='/cdn-cgi/challenge-platform/x'></script>", "Just a moment...", 403) == "managed"
    assert cf.detect("<div class='cf-turnstile' data-sitekey='k'></div>", "App", 200) == "turnstile"
    assert cf.detect("<html>hello</html>", "Hello", 200) == ""


def test_detect_title_markers():
    assert cf.is_challenge_title("Performing security verification")
    assert cf.is_challenge_title("Attention Required! | Cloudflare")
    assert not cf.is_challenge_title("Dashboard")


def test_cache_roundtrip_and_ua_binding():
    host = "example.com"
    cookies = [{"name": "cf_clearance", "value": "abc", "domain": ".example.com", "path": "/"}]
    assert cf.remember("id-test1", host, cookies, "UA-1") == 1
    assert cf.cached("id-test1", host, "UA-1")
    assert cf.cached("id-test1", host, "UA-2") == []
    cf.forget("id-test1", host)
    assert cf.cached("id-test1", host, "UA-1") == []


def test_cache_ttl(monkeypatch):
    host = "ttl.test"
    cookies = [{"name": "cf_clearance", "value": "x", "domain": ".ttl.test", "path": "/"}]
    cf.remember("id-test2", host, cookies, "UA")
    name = cf._name("id-test2", host)
    blob = json.loads(vault.get_secret(name))
    blob["at"] = time.time() - 9999
    vault.put_secret(name, json.dumps(blob))
    assert cf.cached("id-test2", host, "UA") == []
    cf.forget("id-test2", host)


def test_forget_all_for_identity():
    cf.remember("id-a", "a.test", [{"name": "cf_clearance", "value": "1", "domain": "a.test", "path": "/"}], "U")
    cf.remember("id-b", "b.test", [{"name": "cf_clearance", "value": "2", "domain": "b.test", "path": "/"}], "U")
    assert cf.forget("id-a") >= 1
    assert all(r["identity"] != "id-a" for r in cf.status())
