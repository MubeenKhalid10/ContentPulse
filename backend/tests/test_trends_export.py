"""Admin CSV export of the active organization's trends seen in the last
seven days: authorization, tenant isolation, the [start, end) window and
CSV safety."""

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.models.enums import TrendStatus
from app.models.organization import Organization
from app.models.trend import Trend, TrendMention
from app.services.trends import export
from tests.conftest import add_member, create_org, register

API = "/api/v1/trends"
CSV = f"{API}/export.csv"
# Seven days before this crosses the end of British Summer Time (2026-10-25).
END = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
START = END - timedelta(days=7)
TICK = timedelta(microseconds=1)


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch):
    monkeypatch.setattr(export, "_now", lambda: END)


async def add_trend(db, org_id, title, last_seen, *, sources=("google_trends",), **fields):
    trend = Trend(
        organization_id=uuid.UUID(org_id),
        canonical_key=f"{title}-{uuid.uuid4().hex[:8]}"[:200],
        topic=title,
        title=title,
        first_seen_at=fields.pop("first_seen_at", last_seen - timedelta(days=1)),
        last_seen_at=last_seen,
        mention_count=len(sources),
        **fields,
    )
    db.add(trend)
    await db.flush()
    for i, source in enumerate(sources):
        db.add(
            TrendMention(
                organization_id=trend.organization_id,
                trend_id=trend.id,
                source=source,
                source_item_id=f"{trend.id}-{i}",
                topic=title,
                detected_at=last_seen,
                raw_data={"token": "provider-secret-payload"},
            )
        )
    await db.commit()
    return trend


def parse(resp) -> list[dict]:
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "text/csv; charset=utf-8"
    text = resp.content.decode("utf-8")
    assert text.startswith("﻿")
    rows = list(csv.reader(io.StringIO(text[1:], newline="")))
    assert rows[0] == list(export.COLUMNS)
    return [dict(zip(rows[0], r, strict=True)) for r in rows[1:]]


async def admin_with_org(client, email="admin@acme.example.com", name="Acme Software"):
    admin = await register(client, email)
    org = await create_org(admin, name=name)  # timezone Europe/London
    return admin, org


# --- authorization and tenant isolation ------------------------------------


async def test_unauthenticated_requests_are_rejected(client):
    for path in (CSV, f"{API}/export/window"):
        resp = await client.get(path)
        assert resp.status_code == 401, path
        assert "text/csv" not in resp.headers.get("content-type", "")


@pytest.mark.parametrize("role", ["creator", "viewer"])
async def test_non_admins_cannot_export(client, db, role):
    admin, org = await admin_with_org(client)
    await add_trend(db, org["id"], "Visible to members", END - timedelta(days=1))
    member = await add_member(client, admin, org["id"], f"{role}@acme.example.com", role)
    headers = {"X-Organization-Id": org["id"]}
    assert (await member.get(f"{API}", headers=headers)).status_code == 200  # can read
    for path in (CSV, f"{API}/export/window"):
        resp = await member.get(path, headers=headers)
        assert resp.status_code == 403, (role, path)
        assert "Visible to members" not in resp.text


async def test_admin_cannot_export_another_organization(client, db):
    admin, org = await admin_with_org(client)
    other_admin, other = await admin_with_org(client, "owner@other.example.com", "Other Co")
    await add_trend(db, other["id"], "Other secret trend", END - timedelta(days=1))
    # Pointing the selected organization at a foreign org is not enough.
    for path in (CSV, f"{API}/export/window"):
        resp = await admin.get(path, headers={"X-Organization-Id": other["id"]})
        assert resp.status_code == 404, path
        assert "Other secret trend" not in resp.text
    # Being an admin elsewhere grants nothing here: a garbage id is a 422.
    resp = await admin.get(CSV, headers={"X-Organization-Id": "not-a-uuid"})
    assert resp.status_code == 422
    # The other admin still exports their own data.
    rows = parse(await other_admin.get(CSV, headers={"X-Organization-Id": other["id"]}))
    assert [r["Trend"] for r in rows] == ["Other secret trend"]
    assert parse(await admin.get(CSV, headers={"X-Organization-Id": org["id"]})) == []


async def test_export_never_includes_other_organizations_rows_or_sources(client, db):
    admin, org = await admin_with_org(client)
    _, other = await admin_with_org(client, "owner@other.example.com", "Other Co")
    mine = await add_trend(db, org["id"], "Shared topic", END - timedelta(hours=2))
    await add_trend(db, other["id"], "Shared topic", END - timedelta(hours=2), sources=("hn",))
    # A mention row carrying another organization's id must not leak its source.
    db.add(
        TrendMention(
            organization_id=uuid.UUID(other["id"]),
            trend_id=mine.id,
            source="reddit",
            source_item_id="foreign-1",
            topic="Shared topic",
            detected_at=END - timedelta(hours=1),
        )
    )
    await db.commit()
    rows = parse(await admin.get(CSV))
    assert len(rows) == 1
    assert rows[0]["Sources"] == "google_trends"
    assert "provider-secret-payload" not in str(rows)


# --- date window ------------------------------------------------------------


async def test_window_is_half_open_on_last_seen_at(client, db):
    admin, org = await admin_with_org(client)
    cases = {
        "at start": START,
        "just before end": END - TICK,
        "middle": END - timedelta(days=3),
        "just before start": START - TICK,
        "at end": END,
        "after end": END + timedelta(minutes=5),
        "old": END - timedelta(days=30),
    }
    for title, last_seen in cases.items():
        await add_trend(db, org["id"], title, last_seen)
    # First seen long before the window still counts: the filter is last_seen_at.
    await add_trend(
        db,
        org["id"],
        "old but seen again",
        END - timedelta(days=1),
        first_seen_at=END - timedelta(days=60),
    )
    rows = parse(await admin.get(CSV))
    assert {r["Trend"] for r in rows} == {
        "at start",
        "just before end",
        "middle",
        "old but seen again",
    }
    # Newest first.
    assert rows[0]["Trend"] == "just before end"


async def test_range_is_the_same_in_query_headers_filename_and_preview(client, db):
    admin, _ = await admin_with_org(client)
    resp = await admin.get(CSV)
    preview = (await admin.get(f"{API}/export/window")).json()
    # Europe/London: the start is in BST (+01:00), the end in GMT (+00:00);
    # the window is exactly 168 hours either way.
    assert resp.headers["x-export-start"] == "2026-10-23T13:00:00+01:00"
    assert resp.headers["x-export-end"] == "2026-10-30T12:00:00+00:00"
    assert resp.headers["x-export-timezone"] == "Europe/London"
    assert resp.headers["x-export-rows"] == "0"
    filename = "contentpulse-trends_acme-software_20261023T130000+0100_to_20261030T120000+0000.csv"
    assert resp.headers["content-disposition"] == f'attachment; filename="{filename}"'
    assert resp.headers["cache-control"] == "no-store"
    assert preview["filename"] == filename
    assert preview["timezone"] == "Europe/London"
    assert preview["organization_name"] == "Acme Software"
    start = datetime.fromisoformat(preview["start"])
    end = datetime.fromisoformat(preview["end"])
    assert (start, end) == (START, END)
    assert end - start == timedelta(hours=168)


async def test_timestamps_are_shown_in_the_organization_timezone(client, db):
    admin, org = await admin_with_org(client)
    await add_trend(
        db,
        org["id"],
        "Summer",
        datetime(2026, 10, 24, 9, 30, tzinfo=UTC),
        first_seen_at=datetime(2026, 10, 20, 23, 15, tzinfo=UTC),
    )
    await add_trend(db, org["id"], "Winter", datetime(2026, 10, 26, 9, 30, tzinfo=UTC))
    rows = {r["Trend"]: r for r in parse(await admin.get(CSV))}
    assert rows["Summer"]["Last seen"] == "2026-10-24T10:30:00+01:00"
    assert rows["Summer"]["First seen"] == "2026-10-21T00:15:00+01:00"
    assert rows["Winter"]["Last seen"] == "2026-10-26T09:30:00+00:00"


async def test_unknown_timezone_falls_back_to_karachi(client, db):
    admin, org = await admin_with_org(client)
    await db.execute(
        update(Organization)
        .where(Organization.id == uuid.UUID(org["id"]))
        .values(timezone="Not/AZone")
    )
    await db.commit()
    resp = await admin.get(CSV)
    assert resp.headers["x-export-timezone"] == "Asia/Karachi"
    assert resp.headers["x-export-end"] == "2026-10-30T17:00:00+05:00"


# --- CSV correctness --------------------------------------------------------


async def test_csv_escaping_unicode_and_formula_injection(client, db):
    admin, org = await admin_with_org(client)
    seen = END - timedelta(hours=1)
    titles = [
        'AI, chips and "agents"',
        "Line one\nline two",
        "Café über 東京 🚀",
        '=HYPERLINK("http://evil.example","click")',
        "+1 for open models",
        "-5 reasons",
        "@mention trends",
    ]
    for i, title in enumerate(titles):
        await add_trend(
            db, org["id"], title, seen - timedelta(minutes=i), category="=cmd|' /C calc'!A0"
        )
    rows = parse(await admin.get(CSV))
    got = [r["Trend"] for r in rows]
    assert got == [
        'AI, chips and "agents"',
        "Line one\nline two",
        "Café über 東京 🚀",
        '\'=HYPERLINK("http://evil.example","click")',
        "'+1 for open models",
        "'-5 reasons",
        "'@mention trends",
    ]
    assert all(r["Category"] == "'=cmd|' /C calc'!A0" for r in rows)
    # The stored values are untouched.
    stored = await db.scalar(select(Trend.title).where(Trend.topic == "-5 reasons"))
    assert stored == "-5 reasons"


async def test_mentions_are_aggregated_into_one_row(client, db):
    admin, org = await admin_with_org(client)
    await add_trend(
        db,
        org["id"],
        "GPT-6 launch",
        END - timedelta(hours=3),
        sources=("reddit", "google_trends", "reddit", "hacker_news"),
        keywords=["gpt-6", "openai"],
        category="AI",
        opportunity_score=81.26,
        status=TrendStatus.SHORTLISTED,
    )
    rows = parse(await admin.get(CSV))
    assert len(rows) == 1
    row = rows[0]
    assert row["Sources"] == "google_trends, hacker_news, reddit"
    assert row["Mentions"] == "4"
    assert row["Keywords"] == "gpt-6, openai"
    assert row["Category"] == "AI"
    assert row["Opportunity score"] == "81.3"
    assert row["Status"] == "shortlisted"
    assert row["Relevance"] == ""


async def test_empty_export_is_a_valid_csv_with_headers(client):
    admin, _ = await admin_with_org(client)
    resp = await admin.get(CSV)
    assert parse(resp) == []
    assert resp.content.decode("utf-8") == "﻿" + ",".join(export.COLUMNS) + "\r\n"


def test_safe_cell_only_touches_formula_prefixes():
    assert export.safe_cell("plain") == "plain"
    assert export.safe_cell("") == ""
    assert export.safe_cell("a=b") == "a=b"
    for prefix in ("=", "+", "-", "@", "\t", "\r"):
        assert export.safe_cell(f"{prefix}x") == f"'{prefix}x"


# --- /trends page: only the last seven days ---------------------------------


async def test_trends_page_hides_trends_not_seen_for_seven_days(client, db):
    admin, org = await admin_with_org(client)
    now = datetime.now(UTC)
    await add_trend(db, org["id"], "Fresh", now - timedelta(days=6, hours=23))
    old = await add_trend(db, org["id"], "Stale", now - timedelta(days=7, minutes=5))

    page = (await admin.get(API, params={"seen_within_days": 7})).json()
    assert [t["title"] for t in page["items"]] == ["Fresh"]
    assert page["total"] == 1
    # Hidden, not deleted: still in the database and in the unfiltered list.
    assert await db.get(Trend, old.id) is not None
    assert {t["title"] for t in (await admin.get(API)).json()["items"]} == {"Fresh", "Stale"}
    assert (await admin.get(API, params={"seen_within_days": 0})).status_code == 422
