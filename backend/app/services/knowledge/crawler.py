"""Site discovery and crawling (spec §9: discover pages → fetch → extract).

Seeds come from the root URL and the site's sitemaps; more pages are found by
following in-scope links. Shallow URLs are crawled first (an /services page
matters more than /blog/2019/03/post), robots.txt is respected, and requests
are spread across a small number of concurrent workers with a polite delay.
"""

import asyncio
import gzip
import heapq
import itertools
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from app.core.logging import logger
from app.services.knowledge.extractor import ExtractedPage, extract_page
from app.services.knowledge.fetcher import FetchError, SafeFetcher
from app.services.knowledge.urls import in_scope, normalize_url, path_depth, should_skip

MAX_SITEMAP_FILES = 10
MAX_SITEMAP_URLS = 5000
DEFAULT_DELAY = 0.25
MAX_DELAY = 5.0


@dataclass
class PageResult:
    url: str  # normalized requested URL
    final_url: str | None = None
    status_code: int | None = None
    page: ExtractedPage | None = None
    error: str | None = None
    skipped: str | None = None  # reason the page was fetched but not indexable


@dataclass
class CrawlStats:
    discovered: int = 0
    warnings: list[str] = field(default_factory=list)


class SiteCrawler:
    def __init__(
        self,
        fetcher: SafeFetcher,
        root_url: str,
        *,
        max_pages: int,
        concurrency: int,
        user_agent: str,
        skip_urls: set[str] | None = None,
    ) -> None:
        root = normalize_url(root_url)
        if root is None:
            raise ValueError("Invalid root URL")
        self.root = root
        self.fetcher = fetcher
        self.max_pages = max_pages
        self.concurrency = concurrency
        self.user_agent = user_agent
        self.skip_urls = skip_urls or set()
        self.stats = CrawlStats()
        self._robots: RobotFileParser | None = None
        self._delay = DEFAULT_DELAY
        self._seen: set[str] = set()
        self._frontier: list[tuple[int, int, str]] = []
        self._counter = itertools.count()

    # -- discovery -----------------------------------------------------------
    def _allowed(self, url: str) -> bool:
        return self._robots is None or self._robots.can_fetch(self.user_agent, url)

    def _enqueue(self, raw: str, base: str | None = None) -> None:
        url = normalize_url(raw, base)
        if (
            url is None
            or url in self._seen
            or not in_scope(url, self.root)
            or should_skip(url)
            or url in self.skip_urls
            or not self._allowed(url)
        ):
            return
        self._seen.add(url)
        self.stats.discovered += 1
        heapq.heappush(self._frontier, (path_depth(url), next(self._counter), url))

    async def _load_robots(self) -> list[str]:
        """Parse robots.txt; return the sitemap URLs it declares."""
        robots_url = normalize_url("/robots.txt", self.root)
        assert robots_url
        try:
            result = await self.fetcher.get(robots_url)
        except FetchError:
            return []
        if result.status_code != 200:
            return []
        parser = RobotFileParser()
        parser.parse(result.content.decode("utf-8", errors="replace").splitlines())
        self._robots = parser
        delay = parser.crawl_delay(self.user_agent)
        if delay:
            self._delay = min(float(delay), MAX_DELAY)
        return list(parser.site_maps() or [])

    async def _sitemap_urls(self, declared: list[str]) -> list[str]:
        pending = [*declared, *(u for u in ("/sitemap.xml", "/sitemap_index.xml"))]
        visited: set[str] = set()
        found: list[str] = []
        while pending and len(visited) < MAX_SITEMAP_FILES and len(found) < MAX_SITEMAP_URLS:
            sitemap = normalize_url(pending.pop(0), self.root)
            if not sitemap or sitemap in visited or not in_scope(sitemap, self.root):
                continue
            visited.add(sitemap)
            try:
                result = await self.fetcher.get(sitemap)
            except FetchError:
                continue
            if result.status_code != 200:
                continue
            body = result.content
            if body[:2] == b"\x1f\x8b":
                try:
                    body = gzip.decompress(body)
                except OSError:
                    continue
            soup = BeautifulSoup(body, "xml")
            for loc in soup.select("sitemap > loc"):
                pending.append(loc.get_text(strip=True))
            found.extend(loc.get_text(strip=True) for loc in soup.select("url > loc"))
        return found[:MAX_SITEMAP_URLS]

    # -- fetching ------------------------------------------------------------
    async def _fetch_page(self, url: str) -> PageResult:
        await asyncio.sleep(self._delay)
        try:
            result = await self.fetcher.get(url)
        except FetchError as exc:
            return PageResult(url=url, error=exc.reason)
        final = normalize_url(result.url) or url
        out = PageResult(url=url, final_url=final, status_code=result.status_code)
        if result.status_code >= 400:
            out.error = f"HTTP {result.status_code}"
        elif not in_scope(final, self.root):
            out.skipped = "Redirects to another site"
        elif not result.is_html:
            out.skipped = f"Not an HTML page ({result.content_type or 'unknown type'})"
        else:
            try:
                out.page = await asyncio.to_thread(
                    extract_page, result.content, final, result.encoding
                )
            except Exception:  # malformed markup should never kill the crawl
                logger.exception("Extraction failed for %s", final)
                out.error = "Could not read this page"
        return out

    async def crawl(self) -> AsyncIterator[PageResult]:
        """Yield one result per fetched page until the frontier or budget runs out."""
        declared = await self._load_robots()
        if self._robots and not self._allowed(self.root):
            self.stats.warnings.append("robots.txt does not allow crawling this site.")
            return
        self._enqueue(self.root)
        for url in await self._sitemap_urls(declared):
            self._enqueue(url)

        results: asyncio.Queue[PageResult] = asyncio.Queue()
        tasks: set[asyncio.Task] = set()
        started = 0
        # Results not yet consumed. Counted explicitly: a task's done-callback
        # runs after its result is queued, so the task set lags behind.
        pending = 0

        async def worker(target: str) -> None:
            # Always deliver a result, or the loop below would wait forever.
            try:
                result = await self._fetch_page(target)
            except Exception:
                logger.exception("Unexpected crawl error for %s", target)
                result = PageResult(url=target, error="Unexpected error")
            await results.put(result)

        try:
            while True:
                while self._frontier and pending < self.concurrency and started < self.max_pages:
                    _, _, url = heapq.heappop(self._frontier)
                    task = asyncio.create_task(worker(url))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
                    started += 1
                    pending += 1
                if pending == 0:
                    break
                result = await results.get()
                pending -= 1
                if result.page:
                    for link in result.page.links:
                        self._enqueue(link, result.final_url or result.url)
                yield result
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
