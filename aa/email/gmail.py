"""Webmail: Gmail login/signup assistance with TOTP and screenshot handoff.

Google account creation still ends in a phone check most of the time; the flow runs as
far as it can and returns `manual` with a screenshot instead of pretending success.
"""
from __future__ import annotations


from .. import config, db, vault
from ..browser.engine import Browser
from ..jsonio import Denied
from ..log import get_logger
from ..social import totp

log = get_logger("gmail")
SIGNUP = "https://accounts.google.com/signup/v2/createaccount?flowName=GlifWebSignIn"


async def login(identity_id: str, address: str, password: str, totp_secret: str = "") -> dict:
    async with Browser(identity_id, profile="mail", headless=config.env_bool("BROWSER_HEADLESS", True)) as b:
        await b.page.goto("https://mail.google.com/", wait_until="domcontentloaded")
        await b.human_wait(2, 3.5)
        await b.fill(address, selector='input[type="email"]')
        await b.press("Enter")
        await b.human_wait(2, 4)
        await b.fill(password, selector='input[type="password"]')
        await b.press("Enter")
        await b.human_wait(3, 5)
        for _ in range(3):
            if await b.page.get_by_text("Verify it", exact=False).count() or "challenge" in b.page.url:
                if totp_secret:
                    await b.fill(totp.code(totp_secret),
                                 selector='input[type="tel"], input[name="totpPin"], input[type="text"]')
                    await b.press("Enter")
                    await b.human_wait(3, 5)
                else:
                    shot = await b.screenshot("gmail_challenge")
                    return {"logged_in": False, "needs": "manual", "screenshot": shot, "url": b.page.url}
            else:
                break
        ok = "mail.google.com/mail" in b.page.url and "signin" not in b.page.url
        if ok:
            db.add_email(identity_id, address, "gmail")
            db.event("email", "gmail logged in", identity_id)
        return {"logged_in": ok, "url": b.page.url,
                "next": "aa email add --identity ... (IMAP app password)" if ok else None}


async def signup(identity_id: str, first: str, last: str, username: str, password: str,
                 birthday: tuple[int, int, int] = (1996, 5, 14)) -> dict:
    async with Browser(identity_id, profile="mail", headless=config.env_bool("BROWSER_HEADLESS", True)) as b:
        await b.page.goto(SIGNUP, wait_until="domcontentloaded")
        await b.human_wait(2.5, 4)
        await b.fill(first, selector='input[name="firstName"]')
        await b.fill(last, selector='input[name="lastName"]')
        await b.press("Enter")
        await b.human_wait(2, 3)
        for sel, val in (('select#month', str(birthday[1])), ('input#day', str(birthday[2])), ('input#year', str(birthday[0]))):
            try:
                if sel.startswith("select"):
                    await b.select(sel, val)
                else:
                    await b.fill(val, selector=sel)
            except Exception:  # noqa: BLE001
                continue
        try:
            await b.select('select#gender', "1")
        except Exception:  # noqa: BLE001
            pass
        await b.press("Enter")
        await b.human_wait(2, 3)

        # custom address
        try:
            await b.click(text="Create your own Gmail address")
            await b.human_wait(0.8, 1.4)
        except Exception:  # noqa: BLE001
            pass
        await b.fill(username, selector='input[name="Username"]')
        await b.fill(password, selector='input[name="Passwd"]')
        await b.fill(password, selector='input[name="ConfirmPasswd"]')
        await b.press("Enter")
        await b.human_wait(3, 4.5)

        shot = await b.screenshot("gmail_signup")
        txt = (await b.text()).lower()
        if "phone" in txt or "verify your phone" in txt:
            vault.put_secret(f"pw:{identity_id}", password)
            return {"created": False, "needs": "phone", "screenshot": shot, "url": b.page.url,
                    "note": "fill the phone number manually, then rerun email add"}
        return {"created": True, "address": f"{username}@gmail.com", "screenshot": shot}


async def inbox_check(identity_id: str) -> dict:
    async with Browser(identity_id, profile="mail") as b:
        await b.page.goto("https://mail.google.com/mail/u/0/#inbox", wait_until="domcontentloaded")
        await b.human_wait(3, 5)
        rows = await b.page.locator('tr.zA').count()
        return {"unread_rows": rows}


async def verify_signup(identity_id: str, phone: str) -> dict:
    """Resume a signup that stopped at the phone step (browser profile holds state)."""
    async with Browser(identity_id, profile="mail") as b:
        await b.page.goto(SIGNUP, wait_until="domcontentloaded")
        await b.human_wait(2, 3)
        if not await b.page.locator('input[type="tel"]').count():
            raise Denied("no phone step on this profile; run aa email signup first")
        await b.fill(phone, selector='input[type="tel"]')
        await b.press("Enter")
        await b.human_wait(3, 5)
        shot = await b.screenshot("gmail_phone")
        txt = (await b.text()).lower()
        ok = any(w in txt for w in ("verify", "code", "enter the code", "sent"))
        return {"waiting_code": ok, "screenshot": shot,
                "next": "read the SMS code, then aa email signup-code --code 123456"}
