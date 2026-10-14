"""Instagram (Facebook Login) authentication: token types, Meta error codes,
the setup diagnostic, and that tokens never leak. Meta is mocked throughout."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core.config import Settings
from app.sources import SOURCES, instagram
from app.sources.base import SourceContext, SourceError, SourceErrorKind, SourceInputs
from app.sources.instagram import token_kind
from app.sources.instagram_check import check_instagram
from app.sources.locations import resolve_markets

FB_TOKEN = "EAAB" + "x" * 60
IG_TOKEN = "IGAA" + "y" * 60
ACCOUNT = "17841400000000001"
SETTINGS = Settings(
    _env_file=None, instagram_access_token=FB_TOKEN, instagram_business_account_id=ACCOUNT
)


@pytest.fixture(autouse=True)
def no_gaps(monkeypatch):
    monkeypatch.setattr(instagram, "HASHTAG_GAP", 0)


def meta_error(code, subcode=None, message="Error", status=400):
    err = {"message": message, "type": "OAuthException", "code": code, "fbtrace_id": "A1"}
    if subcode is not None:
        err["error_subcode"] = subcode
    return httpx.Response(status, json={"error": err})


class FakeMeta:
    """Graph API stand-in; `errors` maps a path fragment to a canned error."""

    def __init__(self, errors: dict[str, httpx.Response] | None = None, pages=None) -> None:
        self.errors = errors or {}
        self.requests: list[httpx.Request] = []
        self.pages = (
            pages
            if pages is not None
            else [{"name": "Acme", "id": "p1", "instagram_business_account": {"id": ACCOUNT}}]
        )

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        for fragment, response in self.errors.items():
            if fragment in path:
                return response
        if path.endswith("/me/permissions"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"permission": p, "status": "granted"}
                        for p in ("instagram_basic", "pages_show_list", "pages_read_engagement")
                    ]
                },
            )
        if path.endswith("/me/accounts"):
            return httpx.Response(200, json={"data": self.pages})
        if path.endswith("/me"):
            return httpx.Response(200, json={"id": "u1", "name": "Ada"})
        if path.endswith("/ig_hashtag_search"):
            return httpx.Response(200, json={"data": [{"id": "h1"}]})
        if path.endswith("/top_media"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "m1",
                            "caption": "AI tips",
                            "like_count": 900,
                            "comments_count": 100,
                            "permalink": "https://instagram.com/p/m1",
                            "timestamp": "2026-10-12T08:00:00+0000",
                        }
                    ]
                },
            )
        if path.endswith(f"/{ACCOUNT}"):
            return httpx.Response(200, json={"id": ACCOUNT, "username": "acme"})
        return meta_error(100, 33, "Unsupported get request. Object does not exist")


async def collect(meta: FakeMeta, settings: Settings = SETTINGS, keywords=("ai", "cloud")):
    async with httpx.AsyncClient(transport=httpx.MockTransport(meta.handler)) as client:
        ctx = SourceContext(
            client=client,
            settings=settings,
            inputs=SourceInputs(locations=resolve_markets(["USA"])[0], keywords=list(keywords)),
            since=datetime.now(UTC) - timedelta(hours=48),
        )
        return await SOURCES["instagram"].collect(ctx)


async def collect_error(meta: FakeMeta, settings: Settings = SETTINGS) -> SourceError:
    with pytest.raises(SourceError) as err:
        await collect(meta, settings)
    return err.value


def assert_no_token(meta: FakeMeta, *texts: str) -> None:
    for request in meta.requests:
        assert "access_token" not in str(request.url)
        assert FB_TOKEN not in str(request.url)
        assert request.headers["Authorization"] == f"Bearer {FB_TOKEN}"
    for text in texts:
        assert FB_TOKEN not in text and IG_TOKEN not in text


# --- Successful requests ------------------------------------------------------------


async def test_hashtag_search_succeeds_with_the_token_in_the_header():
    meta = FakeMeta()
    items = await collect(meta)
    assert [i.topic for i in items] == ["#ai", "#cloud"]
    assert items[0].engagement == 1000
    search = meta.requests[0]
    assert search.url.path == "/v21.0/ig_hashtag_search"
    assert search.url.params["user_id"] == ACCOUNT and search.url.params["q"] == "ai"
    assert_no_token(meta)


def test_token_kinds():
    assert token_kind(FB_TOKEN) == "facebook"
    assert token_kind(IG_TOKEN) == "instagram_login"
    assert token_kind("IGQWR" + "z" * 40) == "instagram_login"
    assert token_kind(None) == "unknown"


# --- Wrong token type ---------------------------------------------------------------


async def test_instagram_login_token_is_rejected_before_any_request():
    settings = Settings(
        _env_file=None, instagram_access_token=IG_TOKEN, instagram_business_account_id=ACCOUNT
    )
    meta = FakeMeta()
    err = await collect_error(meta, settings)
    assert err.kind == SourceErrorKind.AUTH
    assert "Instagram Login token" in err.message and "Facebook Login" in err.message
    assert meta.requests == []

    inputs = SourceInputs(locations=resolve_markets([])[0], keywords=["ai"])
    config = SOURCES["instagram"].configuration(settings, inputs)
    assert config.configured is False and "EAA" in config.note


# --- Meta error codes -> actionable messages ----------------------------------------


@pytest.mark.parametrize(
    ("response", "kind", "phrase"),
    [
        (meta_error(190, 463, "Session has expired"), SourceErrorKind.AUTH, "has expired"),
        (meta_error(190, 460, "Password changed"), SourceErrorKind.AUTH, "was revoked"),
        (meta_error(190, 458, "App not installed"), SourceErrorKind.AUTH, "was revoked"),
        (
            meta_error(190, None, "Invalid OAuth access token - Cannot parse access token", 401),
            SourceErrorKind.AUTH,
            "rejected INSTAGRAM_ACCESS_TOKEN as invalid",
        ),
        (
            meta_error(
                10,
                None,
                "(#10) To use 'Instagram Public Content Access', your use of "
                "this endpoint must be reviewed and approved by Facebook.",
                403,
            ),
            SourceErrorKind.AUTH,
            "Instagram Public Content Access",
        ),
        (
            meta_error(200, None, "(#200) Requires instagram_basic permission", 403),
            SourceErrorKind.AUTH,
            "missing a permission",
        ),
        (
            meta_error(100, 33, "Unsupported get request. Object with ID does not exist"),
            SourceErrorKind.AUTH,
            "INSTAGRAM_BUSINESS_ACCOUNT_ID was not found",
        ),
        (
            meta_error(24, 2207024, "The maximum number of hashtags has been reached"),
            SourceErrorKind.RATE_LIMITED,
            "30 unique hashtags",
        ),
        (
            meta_error(4, None, "Application request limit reached"),
            SourceErrorKind.RATE_LIMITED,
            "rate limiting",
        ),
        (
            meta_error(2, None, "Service temporarily unavailable", 500),
            SourceErrorKind.UNAVAILABLE,
            "unavailable",
        ),
    ],
)
async def test_meta_errors_become_actionable(response, kind, phrase):
    meta = FakeMeta({"ig_hashtag_search": response})
    err = await collect_error(meta)
    assert err.kind == kind
    assert phrase in err.message
    assert f"code {response.json()['error']['code']}" in err.message  # Meta's own code kept
    # Auth/limit errors stop the remaining hashtags; a transient outage does not.
    assert len(meta.requests) == (1 if kind in instagram.STOP_ON else 2)
    assert_no_token(meta, err.message)


async def test_meta_messages_are_scrubbed_of_tokens():
    leaky = meta_error(190, None, f"Bad token {FB_TOKEN} and {IG_TOKEN}")
    meta = FakeMeta({"ig_hashtag_search": leaky})
    err = await collect_error(meta)
    assert_no_token(meta, err.message)
    assert "***" in err.message


async def test_network_errors_do_not_echo_the_url():
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"failed {request.url}?access_token={FB_TOKEN}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as client:
        ctx = SourceContext(
            client=client,
            settings=SETTINGS,
            inputs=SourceInputs(locations=resolve_markets(["USA"])[0], keywords=["ai"]),
            since=datetime.now(UTC),
        )
        with pytest.raises(SourceError) as err:
            await SOURCES["instagram"].collect(ctx)
    assert err.value.message == "Connection to Meta failed (ConnectError)."
    assert err.value.__cause__ is None and err.value.__suppress_context__


async def test_new_credentials_are_used_on_the_next_run():
    """A rotated token is used at once: responses are only shared under the same token."""
    meta = FakeMeta()
    await collect(meta, keywords=["ai"])
    rotated = "EAAB" + "r" * 60
    settings = Settings(
        _env_file=None, instagram_access_token=rotated, instagram_business_account_id=ACCOUNT
    )
    await collect(meta, settings, keywords=["ai"])
    assert meta.requests[-1].headers["Authorization"] == f"Bearer {rotated}"
    assert len(meta.requests) == 4  # second run went to Meta, not to a cache


# --- Setup diagnostic ---------------------------------------------------------------


async def diagnose(meta: FakeMeta, settings: Settings = SETTINGS, hashtag=None):
    async with httpx.AsyncClient(transport=httpx.MockTransport(meta.handler)) as client:
        return await check_instagram(settings, client, hashtag=hashtag)


async def test_diagnostic_passes_for_a_correct_setup():
    meta = FakeMeta()
    report = await diagnose(meta)
    assert report.ok, report.checks
    assert [c.name for c in report.checks] == [
        "Credentials set",
        "Token type",
        "Token valid",
        "Permissions",
        "Instagram account ID",
        "Page link",
    ]
    assert "Acme" in report.checks[-1].detail
    assert not any("ig_hashtag_search" in r.url.path for r in meta.requests)  # quota spared
    assert_no_token(meta, *(c.detail for c in report.checks))


async def test_diagnostic_stops_on_instagram_login_token():
    settings = Settings(
        _env_file=None, instagram_access_token=IG_TOKEN, instagram_business_account_id=ACCOUNT
    )
    meta = FakeMeta()
    report = await diagnose(meta, settings)
    assert not report.ok and report.checks[-1].name == "Token type"
    assert meta.requests == []


async def test_diagnostic_reports_expired_token():
    report = await diagnose(FakeMeta({"/me": meta_error(190, 463, "Session has expired")}))
    assert report.checks[-1].name == "Token valid" and not report.checks[-1].ok
    assert "expired" in report.checks[-1].detail


async def test_diagnostic_reports_wrong_account_and_unlinked_page():
    settings = Settings(
        _env_file=None, instagram_access_token=FB_TOKEN, instagram_business_account_id="999"
    )
    report = await diagnose(FakeMeta(), settings)
    by_name = {c.name: c for c in report.checks}
    assert not by_name["Instagram account ID"].ok
    assert "INSTAGRAM_BUSINESS_ACCOUNT_ID was not found" in by_name["Instagram account ID"].detail
    assert not by_name["Page link"].ok and ACCOUNT in by_name["Page link"].detail


async def test_diagnostic_reports_missing_permissions_and_no_pages():
    meta = FakeMeta(pages=[])
    meta.errors["/me/permissions"] = httpx.Response(
        200, json={"data": [{"permission": "instagram_basic", "status": "declined"}]}
    )
    report = await diagnose(meta)
    by_name = {c.name: c for c in report.checks}
    assert not by_name["Permissions"].ok and "instagram_basic" in by_name["Permissions"].detail
    assert not by_name["Page link"].ok and "no Facebook Page" in by_name["Page link"].detail


async def test_diagnostic_hashtag_probe_reports_public_content_access():
    meta = FakeMeta(
        {"ig_hashtag_search": meta_error(10, None, "Instagram Public Content Access required", 403)}
    )
    report = await diagnose(meta, hashtag="technology")
    assert report.checks[-1].name == "Hashtag search" and not report.checks[-1].ok
    assert "App Review" in report.checks[-1].detail
