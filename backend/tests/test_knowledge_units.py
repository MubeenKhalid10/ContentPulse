import asyncio

import httpx
import pytest

from app.core.config import Settings
from app.services.knowledge.chunker import chunk_markdown
from app.services.knowledge.extractor import extract_page
from app.services.knowledge.fetcher import FetchError, SafeFetcher, is_public_address
from app.services.knowledge.urls import in_scope, normalize_url, should_skip

# --- URLs -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("HTTPS://Acme.Example.com:443/About/", "https://acme.example.com/About"),
        ("http://acme.example.com:80", "http://acme.example.com/"),
        ("https://acme.example.com/a/./b/../c?utm_source=x#team", "https://acme.example.com/a/c"),
        ("https://acme.example.com//services//ai", "https://acme.example.com/services/ai"),
        ("mailto:hello@acme.example.com", None),
        ("javascript:alert(1)", None),
    ],
)
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected


def test_relative_urls_and_scope():
    assert normalize_url("../pricing", "https://acme.example.com/services/ai") == (
        "https://acme.example.com/pricing"
    )
    assert in_scope("https://www.acme.example.com/x", "https://acme.example.com/")
    assert not in_scope("https://evil.example.com/", "https://acme.example.com/")
    assert should_skip("https://acme.example.com/brochure.pdf")
    assert should_skip("https://acme.example.com/wp-admin/edit")
    assert not should_skip("https://acme.example.com/services/ai-solutions")


# --- SSRF protection ----------------------------------------------------------


@pytest.mark.parametrize(
    ("ip", "public"),
    [
        ("93.184.216.34", True),
        ("127.0.0.1", False),
        ("10.0.0.5", False),
        ("192.168.1.1", False),
        ("169.254.169.254", False),  # cloud metadata
        ("::1", False),
        ("::ffff:127.0.0.1", False),  # IPv4-mapped loopback
        ("fd00::1", False),
    ],
)
def test_is_public_address(ip, public):
    assert is_public_address(ip) is public


async def _resolver(host: str) -> list[str]:
    return {"acme.example.com": ["93.184.216.34"], "internal.example.com": ["10.1.2.3"]}[host]


async def test_fetcher_blocks_private_targets_including_redirects():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/go-internal":
            return httpx.Response(302, headers={"location": "http://internal.example.com/admin"})
        return httpx.Response(200, html="<p>ok</p>")

    settings = Settings(_env_file=None, crawler_allow_private_networks=False)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fetcher = SafeFetcher(client, settings, _resolver)
        assert (await fetcher.get("https://acme.example.com/")).status_code == 200
        with pytest.raises(FetchError, match="not a public address"):
            await fetcher.get("http://169.254.169.254/latest/meta-data/")
        with pytest.raises(FetchError, match="not a public address"):
            await fetcher.get("https://internal.example.com/")
        with pytest.raises(FetchError, match="not a public address"):
            await fetcher.get("https://acme.example.com/go-internal")
        with pytest.raises(FetchError, match="http and https"):
            await fetcher.get("file:///etc/passwd")


async def test_fetcher_enforces_size_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 5000, headers={"content-type": "text/html"})

    settings = Settings(_env_file=None, crawler_max_page_bytes=1000)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(FetchError, match="too large"):
            await SafeFetcher(client, settings, _resolver).get("https://acme.example.com/")


# --- Extraction ---------------------------------------------------------------

PAGE = b"""<!doctype html>
<html lang="en"><head>
  <title>AI Solutions | Acme</title>
  <meta name="description" content="Agents that automate work.">
  <link rel="canonical" href="/services/ai/">
</head><body>
  <header><nav><a href="/">Home</a><a href="/services">Services</a></nav></header>
  <div class="cookie-banner">We use cookies. <button>Accept</button></div>
  <main>
    <h1>AI Solutions</h1>
    <p>We design <strong>AI agents</strong> that automate repetitive operations work.</p>
    <h2>How we work</h2>
    <ul><li>Discovery workshop</li><li>Pilot in four weeks</li></ul>
    <div>Loose text inside a div still counts.</div>
    <script>track()</script>
  </main>
  <footer>&copy; Acme 2026 <a href="/privacy">Privacy</a></footer>
</body></html>"""


def test_extract_page_keeps_content_and_drops_chrome():
    page = extract_page(PAGE, "https://acme.example.com/services/ai")
    assert page.title == "AI Solutions | Acme"
    assert page.description == "Agents that automate work."
    assert page.canonical_url == "https://acme.example.com/services/ai"
    assert page.language == "en"
    assert page.noindex is False
    assert page.markdown.startswith("# AI Solutions")
    assert "## How we work" in page.markdown
    assert "We design AI agents that automate" in page.markdown
    assert "Pilot in four weeks" in page.markdown
    assert "Loose text inside a div" in page.markdown
    for noise in ("cookies", "Privacy", "track()", "Home"):
        assert noise not in page.markdown
    # Navigation links are still collected for discovery.
    assert {"/", "/services", "/privacy"} <= set(page.links)
    assert page.headings == ["AI Solutions", "How we work"]


def test_extract_page_noindex():
    html = (
        b'<html><head><meta name="robots" content="noindex, follow"></head>'
        b"<body><p>x</p></body></html>"
    )
    assert extract_page(html, "https://acme.example.com/").noindex is True


# --- Chunking -----------------------------------------------------------------


def _para(words: int, word: str = "lorem") -> str:
    return " ".join([word] * words) + "."


def test_chunks_carry_heading_paths():
    md = "\n\n".join(
        [
            "# Services",
            "## AI Solutions",
            _para(120, "agents"),
            "## Custom Software",
            _para(130, "software"),
        ]
    )
    chunks = chunk_markdown(md)
    assert [c.heading for c in chunks] == ["Services › AI Solutions", "Services › Custom Software"]
    assert "agents" in chunks[0].content and "software" not in chunks[0].content


def test_long_sections_split_with_overlap():
    sentences = " ".join(f"Sentence number {i} talks about automation." for i in range(150))
    chunks = chunk_markdown(f"## Guide\n\n{sentences}")
    assert len(chunks) >= 3
    assert all(c.heading == "Guide" for c in chunks)
    assert all(c.word_count <= 400 for c in chunks)
    # Consecutive chunks overlap so context isn't cut mid-thought.
    tail = chunks[0].content.split()[-10:]
    assert " ".join(tail) in chunks[1].content


def test_small_sections_are_merged():
    md = "## Mission\n\nShort mission statement.\n\n## Values\n\nHonest work, done well."
    [chunk] = chunk_markdown(md)
    assert "Short mission statement." in chunk.content
    assert "Values" in chunk.content  # merged section keeps its heading inline


def test_empty_markdown_has_no_chunks():
    assert chunk_markdown("") == []


# --- Crawl loop -----------------------------------------------------------------


async def test_crawl_terminates_when_consumer_never_yields(monkeypatch):
    """Regression: the loop used to wait forever when the consumer didn't await
    between results, because finished tasks were still in the task set."""
    monkeypatch.setattr("app.services.knowledge.crawler.DEFAULT_DELAY", 0)
    links = "".join(f'<a href="/p{i}">p{i}</a>' for i in range(20))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, html=f"<main><p>{'word ' * 60}</p>{links}</main>")

    from app.services.knowledge.crawler import SiteCrawler

    settings = Settings(_env_file=None)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        crawler = SiteCrawler(
            SafeFetcher(client, settings, _resolver),
            "https://acme.example.com/",
            max_pages=5,
            concurrency=2,
            user_agent="test",
        )

        async def consume() -> list:
            return [r async for r in crawler.crawl()]

        results = await asyncio.wait_for(consume(), timeout=10)
    assert len(results) == 5


def test_merged_chunks_keep_every_sub_heading():
    """Regression: the first section of a merged chunk lost its heading."""
    md = (
        "# Services\n\n## AI agents\n\nWe build agents that reconcile invoices.\n\n"
        "## Custom software\n\nWe build web platforms.\n\n## Reporting\n\nDashboards for managers."
    )
    [chunk] = chunk_markdown(md)
    assert chunk.heading == "Services"
    assert chunk.content.startswith("AI agents\nWe build agents")
    assert "Custom software\nWe build web platforms." in chunk.content
    assert "Reporting\nDashboards for managers." in chunk.content
