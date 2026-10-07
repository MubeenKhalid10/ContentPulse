import hashlib
import math
import re
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.ai.embeddings import EmbeddingError, set_embedding_provider
from app.models.enums import KnowledgeJobKind, KnowledgeJobStatus
from app.models.knowledge import EMBEDDING_DIMENSIONS, KnowledgeChunk, KnowledgeCrawlJob
from app.workers import knowledge_tasks
from app.workers.runner import runner
from tests.conftest import add_member, create_org, register

ORG_SITE = "https://acme.example.com"


def page(title: str, body: str, links: str = "") -> str:
    nav = (
        '<nav><a href="/">Home</a><a href="/services">Services</a><a href="/about">About</a></nav>'
    )
    return f"""<html><head><title>{title}</title></head><body>
    <header>{nav}</header><main>{body}{links}</main><footer>Acme Ltd</footer></body></html>"""


LONG_SERVICES = (
    "<h1>Services</h1><h2>AI Solutions</h2><p>"
    + "We build AI agents and intelligent automation that remove repetitive manual work "
    "from finance and operations teams. "
    * 6
    + "</p><h2>Custom Software Development</h2><p>"
    + "Our engineers design and ship web platforms, integrations and internal tools. " * 6
    + "</p>"
)
ABOUT = (
    "<h1>About Acme</h1><p>"
    + "Acme is a software consultancy founded in 2015 in Leeds. " * 8
    + "</p>"
)


class FakeSite:
    """An in-memory website served through httpx.MockTransport."""

    def __init__(self) -> None:
        self.pages: dict[str, httpx.Response] = {}
        self.requests: list[str] = []
        self.reset()

    def reset(self) -> None:
        self.pages = {
            "/robots.txt": httpx.Response(
                200,
                text=f"User-agent: *\nDisallow: /private\nSitemap: {ORG_SITE}/sitemap.xml\n",
            ),
            "/sitemap.xml": httpx.Response(
                200,
                text=f"""<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
                <url><loc>{ORG_SITE}/about</loc></url>
                <url><loc>{ORG_SITE}/private/secret</loc></url></urlset>""",
                headers={"content-type": "application/xml"},
            ),
            "/": httpx.Response(
                200,
                html=page(
                    "Acme",
                    "<h1>Acme</h1><p>"
                    + "We help mid-size companies modernise operations. " * 8
                    + "</p>",
                    '<a href="/services/">Services</a><a href="/contact">Contact</a>'
                    '<a href="/old-page">Old</a><a href="/brochure.pdf">PDF</a>'
                    '<a href="https://other.example.com/">Partner</a>',
                ),
            ),
            "/services": httpx.Response(200, html=page("Services | Acme", LONG_SERVICES)),
            "/about": httpx.Response(200, html=page("About | Acme", ABOUT)),
            "/contact": httpx.Response(
                200, html=page("Contact", "<h1>Contact</h1><p>Email us.</p>")
            ),
            "/old-page": httpx.Response(404, text="Not found"),
            "/private/secret": httpx.Response(200, html=page("Secret", "<p>do not crawl</p>")),
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request.url.path)
        assert request.url.host == "acme.example.com", f"crawled off-site: {request.url}"
        return self.pages.get(request.url.path, httpx.Response(404))


class FakeEmbeddings:
    """Deterministic bag-of-words vectors: texts sharing words are close."""

    model = "fake-embed"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.fail:
            raise EmbeddingError("Embedding provider returned 401: bad key", retryable=False)
        out = []
        for text in texts:
            vec = [0.0] * EMBEDDING_DIMENSIONS
            for word in re.findall(r"[a-z]+", text.lower()):
                stem = word[:5]
                vec[int(hashlib.md5(stem.encode()).hexdigest(), 16) % EMBEDDING_DIMENSIONS] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


@pytest.fixture
def site(monkeypatch):
    fake = FakeSite()

    def client_factory(settings):
        return httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))

    async def resolver(host: str) -> list[str]:
        return ["93.184.216.34"]  # a public address

    monkeypatch.setattr(knowledge_tasks, "http_client_factory", client_factory)
    monkeypatch.setattr(knowledge_tasks, "resolver", resolver)
    monkeypatch.setattr("app.services.knowledge.crawler.DEFAULT_DELAY", 0)
    return fake


@pytest.fixture
def embeddings():
    fake = FakeEmbeddings()
    set_embedding_provider(fake)
    yield fake
    set_embedding_provider(None)


async def setup_org(client):
    admin = await register(client, "admin@acme.example.com")
    org = await create_org(admin)
    base = f"/api/v1/organizations/{org['id']}/knowledge"
    return admin, org, base


async def crawl(admin, base, **body) -> dict:
    resp = await admin.post(f"{base}/crawl", json=body)
    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "queued"
    await runner.wait_idle()
    job = (await admin.get(f"{base}/jobs/{resp.json()['job_id']}")).json()
    return job


async def test_crawl_builds_searchable_knowledge(client, site, embeddings):
    admin, org, base = await setup_org(client)
    job = await crawl(admin, base)

    assert job["status"] == "succeeded", job
    assert job["root_url"] == "https://acme.example.com/"
    assert job["pages_indexed"] == 3  # home, services, about
    assert job["pages_skipped"] == 1  # contact: too little text
    assert job["pages_failed"] == 1  # old-page 404
    assert job["chunks_created"] >= 3
    # robots.txt disallows /private; off-site links, PDFs never fetched.
    assert "/private/secret" not in site.requests
    assert "/brochure.pdf" not in site.requests

    docs = (await admin.get(f"{base}/documents")).json()
    assert docs["total"] == 3
    services = next(d for d in docs["items"] if d["source_url"].endswith("/services"))
    assert services["crawl_status"] == "embedded"
    assert services["title"] == "Services | Acme"

    detail = (await admin.get(f"{base}/documents/{services['id']}")).json()
    assert "## AI Solutions" in detail["content"]
    assert "Acme Ltd" not in detail["content"]  # footer removed
    assert {c["heading"] for c in detail["chunks"]} == {
        "Services › AI Solutions",
        "Services › Custom Software Development",
    }
    assert all(c["embedded"] for c in detail["chunks"])

    summary = (await admin.get(f"{base}/summary")).json()
    assert summary["indexed_documents"] == 3
    assert summary["embedded_chunks"] == summary["chunks"]
    assert summary["embeddings_enabled"] is True
    assert summary["active_job"] is None
    assert summary["last_job"]["id"] == job["id"]

    resp = await admin.post(f"{base}/search", json={"query": "intelligent automation agents"})
    body = resp.json()
    assert body["mode"] == "hybrid"
    top = body["results"][0]
    assert top["heading"] == "Services › AI Solutions"
    assert top["match"] == "both"
    assert "⟦" in top["snippet"]  # keyword highlights


async def test_recrawl_detects_unchanged_changed_and_removed_pages(client, site, embeddings):
    admin, org, base = await setup_org(client)
    await crawl(admin, base)
    calls_after_first = embeddings.calls

    job = await crawl(admin, base)
    assert job["pages_unchanged"] == 3 and job["pages_indexed"] == 0
    assert embeddings.calls == calls_after_first  # nothing re-embedded

    site.pages["/about"] = httpx.Response(
        200, html=page("About | Acme", ABOUT.replace("Leeds", "Manchester"))
    )
    site.pages["/services"] = httpx.Response(404)
    job = await crawl(admin, base)
    assert job["pages_indexed"] == 1  # about changed

    docs = {d["source_url"]: d for d in (await admin.get(f"{base}/documents")).json()["items"]}
    gone = docs["https://acme.example.com/services"]
    assert gone["crawl_status"] == "failed" and gone["chunk_count"] == 0
    hits = (await admin.post(f"{base}/search", json={"query": "Manchester"})).json()["results"]
    assert hits and hits[0]["url"].endswith("/about")


async def test_keyword_only_without_embeddings(client, site):
    admin, org, base = await setup_org(client)
    job = await crawl(admin, base)
    assert job["status"] == "succeeded" and job["warnings"] == []

    summary = (await admin.get(f"{base}/summary")).json()
    assert summary["embeddings_enabled"] is False and summary["embedded_chunks"] == 0
    resp = (await admin.post(f"{base}/search", json={"query": "custom software engineers"})).json()
    assert resp["mode"] == "keyword"
    assert resp["results"][0]["heading"] == "Services › Custom Software Development"
    assert resp["results"][0]["match"] == "keyword"


async def test_embedding_failure_degrades_gracefully(client, site):
    set_embedding_provider(FakeEmbeddings(fail=True))
    try:
        admin, org, base = await setup_org(client)
        job = await crawl(admin, base)
    finally:
        set_embedding_provider(None)
    assert job["status"] == "succeeded"
    assert job["pages_indexed"] == 3
    assert "Semantic indexing paused" in job["warnings"][0]
    docs = (await admin.get(f"{base}/documents")).json()["items"]
    assert {d["crawl_status"] for d in docs} == {"extracted"}


async def test_exclude_and_reindex(client, site, embeddings):
    admin, org, base = await setup_org(client)
    await crawl(admin, base)
    about = next(
        d
        for d in (await admin.get(f"{base}/documents")).json()["items"]
        if d["source_url"].endswith("/about")
    )
    resp = await admin.patch(f"{base}/documents/{about['id']}", json={"excluded": True})
    assert resp.json()["excluded"] is True and resp.json()["chunks"] == []
    hits = (await admin.post(f"{base}/search", json={"query": "consultancy Leeds"})).json()[
        "results"
    ]
    assert about["id"] not in {h["document_id"] for h in hits}

    site.requests.clear()
    await crawl(admin, base)
    assert "/about" not in site.requests  # excluded pages are not re-fetched

    resp = await admin.post(f"{base}/reindex")
    assert resp.status_code == 202
    await runner.wait_idle()
    job = (await admin.get(f"{base}/jobs/{resp.json()['job_id']}")).json()
    assert job["kind"] == "reindex" and job["status"] == "succeeded"
    assert job["pages_indexed"] == 2  # excluded document skipped


async def test_manual_documents(client, embeddings):
    admin, org, base = await setup_org(client)
    resp = await admin.post(
        f"{base}/documents",
        json={
            "title": "Positioning",
            "content": "## Who we serve\n\nRegional logistics firms with 50-500 staff.",
        },
    )
    assert resp.status_code == 201
    doc = resp.json()
    assert doc["document_type"] == "manual" and doc["crawl_status"] == "embedded"
    hits = (await admin.post(f"{base}/search", json={"query": "logistics firms"})).json()["results"]
    assert hits[0]["document_id"] == doc["id"]

    resp = await admin.patch(
        f"{base}/documents/{doc['id']}", json={"content": "We serve healthcare providers."}
    )
    assert "healthcare" in resp.json()["chunks"][0]["content"]
    assert (await admin.delete(f"{base}/documents/{doc['id']}")).status_code == 204
    assert (await admin.get(f"{base}/documents/{doc['id']}")).status_code == 404


async def test_crawled_pages_cannot_be_edited(client, site):
    admin, org, base = await setup_org(client)
    await crawl(admin, base)
    doc = (await admin.get(f"{base}/documents")).json()["items"][0]
    resp = await admin.patch(f"{base}/documents/{doc['id']}", json={"content": "fake"})
    assert resp.status_code == 422


async def test_one_active_job_and_cancellation(client, site, monkeypatch):
    submitted = []
    monkeypatch.setattr(runner, "submit", lambda coro, name: submitted.append(coro))
    admin, org, base = await setup_org(client)

    first = (await admin.post(f"{base}/crawl", json={})).json()
    resp = await admin.post(f"{base}/crawl", json={})
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["job_id"] == first["job_id"]

    resp = await admin.post(f"{base}/jobs/{first['job_id']}/cancel")
    assert resp.json()["cancel_requested"] is True
    await submitted[0]  # the worker picks it up and honours the cancel
    job = (await admin.get(f"{base}/jobs/{first['job_id']}")).json()
    assert job["status"] == "cancelled" and job["pages_crawled"] == 0
    assert (await admin.post(f"{base}/jobs/{first['job_id']}/cancel")).status_code == 409


async def test_crawl_requires_website_and_blocks_private_targets(client, monkeypatch):
    def client_factory(settings):
        return httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))

    monkeypatch.setattr(knowledge_tasks, "http_client_factory", client_factory)
    admin = await register(client, "admin@acme.example.com")
    org = (await admin.post("/api/v1/organizations", json={"name": "No Site"})).json()
    base = f"/api/v1/organizations/{org['id']}/knowledge"

    resp = await admin.post(f"{base}/crawl", json={})
    assert resp.status_code == 422 and "website" in resp.json()["error"]["message"]

    job = await crawl(admin, base, url="http://127.0.0.1:8080/")
    assert job["status"] == "failed"
    assert "not a public address" in job["error"]


async def test_stale_jobs_are_recovered(client, db):
    admin, org, base = await setup_org(client)
    old = datetime.now(UTC) - timedelta(minutes=10)
    db.add(
        KnowledgeCrawlJob(
            organization_id=org["id"],
            kind=KnowledgeJobKind.CRAWL,
            status=KnowledgeJobStatus.RUNNING,
            max_pages=10,
            heartbeat_at=old,
        )
    )
    await db.commit()
    assert await knowledge_tasks.recover_stale_jobs() == 1
    job = (await admin.get(f"{base}/jobs")).json()[0]
    assert job["status"] == "failed" and "restarted" in job["error"]


async def test_knowledge_rbac_and_isolation(client, site, embeddings):
    admin, org, base = await setup_org(client)
    await crawl(admin, base)
    viewer = await add_member(client, admin, org["id"], "viewer@acme.example.com", "viewer")
    designer = await add_member(client, admin, org["id"], "designer@acme.example.com", "creator")

    assert (await viewer.get(f"{base}/documents")).status_code == 200
    assert (await viewer.post(f"{base}/search", json={"query": "agents"})).status_code == 200
    assert (await viewer.post(f"{base}/crawl", json={})).status_code == 403
    assert (await viewer.post(f"{base}/reindex")).status_code == 403
    assert (await designer.get(f"{base}/documents")).status_code == 200  # creators read it
    assert (await designer.post(f"{base}/crawl", json={})).status_code == 403  # admins change it

    outsider = await register(client, "outsider@other.example.com")
    other = await create_org(outsider, "Other Co")
    other_base = f"/api/v1/organizations/{other['id']}/knowledge"
    assert (await outsider.get(f"{base}/documents")).status_code == 404
    results = (await outsider.post(f"{other_base}/search", json={"query": "agents"})).json()
    assert results["results"] == []  # never sees Acme's chunks


async def test_search_handles_stopword_only_queries(client, site, db):
    admin, org, base = await setup_org(client)
    await crawl(admin, base)
    resp = await admin.post(f"{base}/search", json={"query": "the and of"})
    assert resp.status_code == 200 and resp.json()["results"] == []
    assert (await db.scalar(select(KnowledgeChunk.id).limit(1))) is not None
