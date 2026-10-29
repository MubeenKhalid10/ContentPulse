"""The search box on every list page: Find trends, Shortlist, Write posts, Add designs."""

import uuid

from app.models.design import DesignBrief
from app.models.enums import DesignBriefStatus, Platform, PostStatus, VersionSource
from app.models.post import Post, PostVersion
from app.models.topic import TopicCandidate
from app.models.trend import Trend
from tests.conftest import create_org, register
from tests.test_discovery_sources import seed_trend


async def titles(client, url: str) -> set[str]:
    resp = await client.get(url)
    assert resp.status_code == 200, resp.text
    return {i["title"] if "title" in i else i["post"]["title"] for i in resp.json()["items"]}


async def test_every_list_search_matches_text_case_insensitively(client, db):
    admin = await register(client, "admin@acme.example.com")
    org_id = (await create_org(admin))["id"]
    org = uuid.UUID(org_id)

    news = await db.get(Trend, uuid.UUID(await seed_trend(db, org_id, "Gemini 4", ["google_news"])))
    news.title = "Gemini 4 carbon hits 59 on index"
    await seed_trend(db, org_id, "PHP security flaw", ["google_news"], 80)
    await seed_trend(db, org_id, "Growth of 100% remote teams", ["google_news"], 70)
    await seed_trend(db, org_id, "Growth of 1000 remote teams", ["google_news"], 60)
    db.add_all(
        [
            TopicCandidate(organization_id=org, trend_id=news.id, title="Gemini 4 for builders"),
            TopicCandidate(organization_id=org, title="snake_case naming"),
            TopicCandidate(organization_id=org, title="snakeXcase naming"),
        ]
    )
    posts = {
        title: Post(
            organization_id=org, platform=Platform.LINKEDIN, title=title, status=PostStatus.DRAFT
        )
        for title in ("Development company", "PHP", "Oct 2026")
    }
    db.add_all(posts.values())
    await db.flush()
    db.add(
        PostVersion(
            organization_id=org,
            post_id=posts["Oct 2026"].id,
            version_number=1,
            hook="Agency rankings shouldn't decide",
            body="Pick a partner on evidence.",
            source=VersionSource.MANUAL,
        )
    )
    for title in ("Development company", "PHP"):
        posts[title].status = PostStatus.DESIGN_PENDING
        db.add(
            DesignBrief(
                organization_id=org,
                post_id=posts[title].id,
                format="single_image",
                headline="Unpatched flaw" if title == "PHP" else "Own your software",
                status=DesignBriefStatus.OPEN,
            )
        )
    await db.commit()

    trends = "/api/v1/trends?status=all"
    assert await titles(admin, f"{trends}&q=gemini") == {"Gemini 4 carbon hits 59 on index"}
    # The headline is searched too, not just the topic.
    assert await titles(admin, f"{trends}&q=CARBON") == {"Gemini 4 carbon hits 59 on index"}
    # "%" is a character, not a wildcard: "100%" doesn't also match "1000".
    resp = await admin.get(f"{trends}&q=100%25")
    assert {i["topic"] for i in resp.json()["items"]} == {"Growth of 100% remote teams"}
    assert await titles(admin, f"{trends}&q=nothing-like-this") == set()

    topics = "/api/v1/topics?status=all"
    assert await titles(admin, f"{topics}&q=GEMINI") == {"Gemini 4 for builders"}
    # "_" is a character, not a single-character wildcard.
    assert await titles(admin, f"{topics}&q=snake_case") == {"snake_case naming"}

    content = "/api/v1/content?status=all"
    assert await titles(admin, f"{content}&q=php") == {"PHP"}
    # Matches the copy as well as the title.
    assert await titles(admin, f"{content}&q=rankings") == {"Oct 2026"}
    assert await titles(admin, f"{content}&q=%20%20php%20") == {"PHP"}  # surrounding spaces

    design = "/api/v1/design/tasks?status=all"
    assert await titles(admin, f"{design}&q=development") == {"Development company"}
    # Matches the brief's headline as well as the post title.
    assert await titles(admin, f"{design}&q=unpatched") == {"PHP"}


async def test_an_over_long_search_is_refused_with_a_clear_field(client):
    admin = await register(client, "admin@acme.example.com")
    await create_org(admin)
    resp = await admin.get(f"/api/v1/content?q={'a' * 201}")
    assert resp.status_code == 422
    assert resp.json()["error"]["details"][0] | {"message": ""} == {
        "field": "q",
        "message": "",
        "in": "query",
    }
