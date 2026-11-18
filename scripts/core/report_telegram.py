#!/usr/bin/env python3
"""Send a report to the owner's Telegram (bot -> group forum topic).

env: TG_REPORT_BOT_TOKEN, TG_REPORT_CHAT_ID (e.g. -100123...), TG_REPORT_TOPIC_ID (optional)
usage: report_telegram.py "text"   |   echo text | report_telegram.py -
       report_telegram.py --photo proofs/x.png "caption"
"""
from __future__ import annotations

import sys as _sys, pathlib as _pl; _sys.path[:0] = [str(_d) for _d in sorted(_pl.Path(__file__).resolve().parents[1].iterdir()) if _d.is_dir() and not _d.name.startswith(("_", "."))]  # noqa: E702 (script-group import path)

import argparse
import os
import sys
import time

import requests

from common import env_required, get_logger
from redact import redact

log = get_logger("report")
API = "https://api.telegram.org/bot{token}/{method}"


def _post(method: str, data: dict, files: dict | None = None) -> dict:
    token = env_required("TG_REPORT_BOT_TOKEN")
    for attempt in range(4):
        r = requests.post(API.format(token=token, method=method), data=data, files=files, timeout=30)
        j = r.json()
        if j.get("ok"):
            return j
        retry = j.get("parameters", {}).get("retry_after")
        if retry:
            time.sleep(int(retry) + 1)
            continue
        log.warning("telegram %s failed: %s", method, j.get("description"))
        break
    return {}


def send(text: str, parse_mode: str | None = "HTML") -> bool:
    text = redact(text)
    base = {"chat_id": env_required("TG_REPORT_CHAT_ID"), "disable_web_page_preview": "true"}
    if os.environ.get("TG_REPORT_TOPIC_ID"):
        base["message_thread_id"] = os.environ["TG_REPORT_TOPIC_ID"]
    ok = True
    for i in range(0, len(text), 4000):  # Telegram limit 4096
        chunk = text[i:i + 4000]
        data = dict(base, text=chunk)
        if parse_mode:
            data["parse_mode"] = parse_mode
        res = _post("sendMessage", data)
        if not res and parse_mode:  # retry as plain text if HTML parse failed
            data.pop("parse_mode", None)
            res = _post("sendMessage", data)
        ok = ok and bool(res)
    return ok


def send_photo(path: str, caption: str = "") -> bool:
    data = {"chat_id": env_required("TG_REPORT_CHAT_ID"), "caption": redact(caption)[:1000]}
    if os.environ.get("TG_REPORT_TOPIC_ID"):
        data["message_thread_id"] = os.environ["TG_REPORT_TOPIC_ID"]
    with open(path, "rb") as f:
        return bool(_post("sendPhoto", data, {"photo": f}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("--photo")
    ap.add_argument("--plain", action="store_true")
    a = ap.parse_args()
    txt = sys.stdin.read() if a.text == "-" else a.text
    ok = send_photo(a.photo, txt) if a.photo else send(txt, None if a.plain else "HTML")
    print("sent" if ok else "failed")
    sys.exit(0 if ok else 1)
