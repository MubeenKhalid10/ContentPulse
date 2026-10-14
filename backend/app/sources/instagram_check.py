"""Check the Instagram (Facebook Login) setup step by step, without exposing secrets.

    python -m app.sources.instagram_check            # token, permissions, account, Page link
    python -m app.sources.instagram_check --hashtag technology   # also try one hashtag search

The hashtag probe is opt-in: every unique hashtag counts toward Instagram's
30-per-7-days limit. Output never contains the token, only its kind and Meta's
(scrubbed) error codes.
"""

import argparse
import asyncio
from dataclasses import dataclass, field

import httpx

from app.core.config import Settings, get_settings
from app.sources.base import SourceError
from app.sources.instagram import INSTAGRAM_LOGIN_TOKEN, graph_get, token_kind

REQUIRED_PERMISSIONS = ("instagram_basic",)
RECOMMENDED_PERMISSIONS = ("pages_show_list", "pages_read_engagement")


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


@dataclass
class InstagramReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def add(self, name: str, ok: bool, detail: str) -> bool:
        self.checks.append(Check(name, ok, detail))
        return ok


async def check_instagram(
    settings: Settings, client: httpx.AsyncClient, *, hashtag: str | None = None
) -> InstagramReport:
    report = InstagramReport()
    token = settings.instagram_access_token
    account_id = (settings.instagram_business_account_id or "").strip()
    if not report.add(
        "Credentials set",
        bool(token and account_id),
        "INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_BUSINESS_ACCOUNT_ID are set"
        if token and account_id
        else "Set INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_BUSINESS_ACCOUNT_ID",
    ):
        return report

    kind = token_kind(token)
    if not report.add(
        "Token type",
        kind != "instagram_login",
        {
            "facebook": "Facebook-issued token (Facebook Login path)",
            "unknown": "Unrecognized prefix; continuing (Facebook tokens start with EAA)",
            "instagram_login": INSTAGRAM_LOGIN_TOKEN,
        }[kind],
    ):
        return report

    try:
        me = await graph_get(client, settings, "me", {"fields": "id,name"})
    except SourceError as exc:
        report.add("Token valid", False, exc.message)
        return report
    report.add("Token valid", True, f"Token belongs to {me.get('name') or me.get('id')}")

    page_token = False
    try:
        perms = await graph_get(client, settings, "me/permissions")
        granted = {p["permission"] for p in perms.get("data", []) if p.get("status") == "granted"}
        missing = [p for p in REQUIRED_PERMISSIONS if p not in granted]
        weak = [p for p in RECOMMENDED_PERMISSIONS if p not in granted]
        report.add(
            "Permissions",
            not missing,
            "Missing: " + ", ".join(missing + weak)
            if missing
            else ("Granted; also recommended: " + ", ".join(weak) if weak else "All granted"),
        )
    except SourceError:
        # Page access tokens have no /me/permissions; the Page check below covers them.
        page_token = True
        report.add("Permissions", True, "Page access token (permissions come from the user)")

    try:
        account = await graph_get(client, settings, account_id, {"fields": "id,username"})
        report.add(
            "Instagram account ID",
            True,
            f"{account_id} is @{account.get('username') or '?'}",
        )
    except SourceError as exc:
        report.add("Instagram account ID", False, exc.message)

    try:
        if page_token:
            page = await graph_get(
                client, settings, "me", {"fields": "name,instagram_business_account"}
            )
            pages = [page]
        else:
            data = await graph_get(
                client,
                settings,
                "me/accounts",
                {"fields": "name,instagram_business_account", "limit": "100"},
            )
            pages = data.get("data") or []
        linked = {
            (p.get("instagram_business_account") or {}).get("id"): p.get("name") for p in pages
        }
        linked.pop(None, None)
        if account_id in linked:
            report.add("Page link", True, f"Linked to the Facebook Page '{linked[account_id]}'")
        elif linked:
            report.add(
                "Page link",
                False,
                f"No Page this token can see is linked to {account_id}. Linked IG account "
                f"IDs found: {', '.join(sorted(linked))}. Use one of these, or link the "
                "Instagram account to a Page this user manages.",
            )
        else:
            report.add(
                "Page link",
                False,
                "This token sees no Facebook Page with a linked Instagram professional "
                "account. Link the Instagram account to a Page (Instagram settings or Meta "
                "Business Suite) and grant pages_show_list.",
            )
    except SourceError as exc:
        report.add("Page link", False, exc.message)

    if hashtag:
        try:
            found = await graph_get(
                client, settings, "ig_hashtag_search", {"user_id": account_id, "q": hashtag}
            )
            report.add(
                "Hashtag search",
                bool(found.get("data")),
                f"#{hashtag} found" if found.get("data") else f"#{hashtag} returned no hashtag",
            )
        except SourceError as exc:
            report.add("Hashtag search", False, exc.message)
    return report


async def _main(hashtag: str | None) -> int:
    async with httpx.AsyncClient(timeout=20) as client:
        report = await check_instagram(get_settings(), client, hashtag=hashtag)
    for c in report.checks:
        print(f"[{'ok' if c.ok else 'FAIL'}] {c.name}: {c.detail}")
    if not hashtag:
        print("[skip] Hashtag search: pass --hashtag <tag> to test Public Content Access")
    return 0 if report.ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hashtag", help="also run one hashtag search (uses weekly quota)")
    raise SystemExit(asyncio.run(_main(parser.parse_args().hashtag)))
