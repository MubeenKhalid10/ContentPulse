"""HTTP fetching for the crawler with SSRF protection.

The crawler fetches URLs supplied by users, from inside our network. Every
request (including every redirect hop) is checked so the target host resolves
only to public addresses: no localhost, private ranges, link-local (cloud
metadata at 169.254.169.254), or other reserved space.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpcore
import httpx

from app.core.config import Settings

Resolver = Callable[[str], Awaitable[list[str]]]

MAX_REDIRECTS = 5


class FetchError(Exception):
    """A page could not be fetched. `reason` is safe to show to users."""

    def __init__(self, reason: str, *, status_code: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


@dataclass(frozen=True)
class FetchResult:
    url: str  # final URL after redirects
    status_code: int
    content_type: str
    content: bytes
    encoding: str | None

    @property
    def is_html(self) -> bool:
        return self.content_type in ("text/html", "application/xhtml+xml")


async def system_resolver(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


def is_public_address(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


class SafeFetcher:
    def __init__(
        self,
        client: httpx.AsyncClient,
        settings: Settings,
        resolver: Resolver = system_resolver,
    ) -> None:
        self._client = client
        self._settings = settings
        self._resolver = resolver
        self._host_checks: dict[str, bool] = {}

    async def _ensure_public(self, url: str) -> None:
        host = urlsplit(url).hostname
        if not host:
            raise FetchError("Invalid URL.")
        if self._settings.crawler_allow_private_networks:
            return
        if host not in self._host_checks:
            try:
                ipaddress.ip_address(host)
                addresses = [host]
            except ValueError:
                try:
                    addresses = await self._resolver(host)
                except OSError as exc:
                    raise FetchError(f"Could not resolve {host}.") from exc
            self._host_checks[host] = bool(addresses) and all(
                is_public_address(a) for a in addresses
            )
        if not self._host_checks[host]:
            raise FetchError(f"{host} is not a public address and cannot be crawled.")

    async def get(self, url: str) -> FetchResult:
        """GET with manual redirect handling so every hop is checked."""
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            if urlsplit(current).scheme not in ("http", "https"):
                raise FetchError("Only http and https URLs can be crawled.")
            await self._ensure_public(current)
            try:
                async with self._client.stream("GET", current, follow_redirects=False) as resp:
                    if resp.is_redirect and "location" in resp.headers:
                        current = urljoin(current, resp.headers["location"])
                        continue
                    content_type = (
                        resp.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    )
                    body = bytearray()
                    async for part in resp.aiter_bytes():
                        body.extend(part)
                        if len(body) > self._settings.crawler_max_page_bytes:
                            raise FetchError("Page is too large to index.")
                    return FetchResult(
                        url=current,
                        status_code=resp.status_code,
                        content_type=content_type,
                        content=bytes(body),
                        encoding=resp.charset_encoding,
                    )
            except httpx.TimeoutException as exc:
                raise FetchError("The site took too long to respond.") from exc
            except httpx.HTTPError as exc:
                raise FetchError(f"Could not connect: {type(exc).__name__}.") from exc
        raise FetchError("Too many redirects.")


class _PublicOnlyBackend(httpcore.AsyncNetworkBackend):
    """Resolves and validates at connect time, then dials the validated IP.

    Checking a hostname and then letting the HTTP client resolve it again lets
    a rebinding domain answer "public" the first time and "169.254.169.254"
    the second. Here the address that was checked is the one connected to; the
    URL, Host header and TLS server name are untouched, so TLS still verifies
    the original hostname.
    """

    def __init__(self, inner: httpcore.AsyncNetworkBackend) -> None:
        self._inner = inner

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 (httpcore interface)
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            addresses = list(dict.fromkeys(await system_resolver(host)))
        except OSError as exc:
            raise httpcore.ConnectError(f"Could not resolve {host}.") from exc
        public = [a for a in addresses if is_public_address(a)]
        if not public or len(public) != len(addresses):
            raise httpcore.ConnectError(f"{host} is not a public address.")
        error: Exception | None = None
        for address in public:
            try:
                return await self._inner.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except httpcore.ConnectError as exc:
                error = exc
        raise error or httpcore.ConnectError(f"Could not connect to {host}.")

    async def connect_unix_socket(self, *args: Any, **kwargs: Any) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError("Unix sockets are not allowed.")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def public_only_transport(
    settings: Settings, limits: httpx.Limits | None = None
) -> httpx.AsyncHTTPTransport | None:
    """A transport that only ever connects to public addresses, or None when
    private networks are explicitly allowed (local development)."""
    if settings.crawler_allow_private_networks:
        return None
    transport = httpx.AsyncHTTPTransport(limits=limits or httpx.Limits())
    pool = transport._pool
    if not hasattr(pool, "_network_backend"):  # fail closed if httpcore changes
        raise RuntimeError("Cannot install the public-address connection guard.")
    pool._network_backend = _PublicOnlyBackend(pool._network_backend)
    return transport


def build_http_client(settings: Settings) -> httpx.AsyncClient:
    limits = httpx.Limits(max_connections=settings.crawler_concurrency * 2)
    return httpx.AsyncClient(
        transport=public_only_transport(settings, limits),
        # No proxy/CA settings from the environment: a proxy would do the
        # connecting, past the address check above.
        trust_env=False,
        timeout=httpx.Timeout(settings.crawler_timeout_seconds),
        headers={
            "User-Agent": settings.crawler_user_agent,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
            "Accept-Language": "en;q=1.0, *;q=0.5",
        },
        limits=limits,
    )
