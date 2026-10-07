"""URL normalization and crawl scope."""

import posixpath
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

# Assets and documents the HTML crawler never fetches.
_SKIP_EXTENSIONS = frozenset(
    """
    7z avi bmp css csv doc docx eot exe gif gz ico jpeg jpg js json m4a mov mp3 mp4 mpeg
    odp ods odt ogg otf pdf png ppt pptx rar rss svg tar tif tiff ttf txt wav webm webp
    woff woff2 xls xlsx xml zip
    """.split()
)

# Path segments that are never useful company knowledge.
_SKIP_SEGMENTS = frozenset(
    """
    account admin cart checkout feed login logout my-account password register search
    signin sign-in signup sign-up tag tags author wp-admin wp-json wp-login.php xmlrpc.php
    """.split()
)

_MULTI_SLASH = re.compile(r"/{2,}")


def normalize_url(url: str, base: str | None = None) -> str | None:
    """Canonical form used for de-duplication and fetching.

    Lowercases scheme/host, drops default ports, query strings and fragments,
    resolves dot segments and strips trailing slashes (except the root).
    Returns None for non-HTTP(S) or malformed URLs.
    """
    try:
        absolute = urljoin(base, url.strip()) if base else url.strip()
        parts = urlsplit(absolute)
        scheme = parts.scheme.lower()
        if scheme not in ("http", "https") or not parts.hostname:
            return None
        host = parts.hostname.lower().rstrip(".")
        port = parts.port
    except ValueError:
        return None

    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"

    path = _MULTI_SLASH.sub("/", parts.path or "/")
    path = posixpath.normpath(path) if path not in ("", "/") else "/"
    if not path.startswith("/"):
        path = "/" + path
    if len(path) > 1:
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


def site_key(url: str) -> str:
    """Host without a leading 'www.' — pages on either variant are one site."""
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.")


def in_scope(url: str, root_url: str) -> bool:
    return site_key(url) == site_key(root_url)


def should_skip(url: str) -> bool:
    path = urlsplit(url).path.lower()
    last = path.rsplit("/", 1)[-1]
    if "." in last and last.rsplit(".", 1)[-1] in _SKIP_EXTENSIONS:
        return True
    return any(segment in _SKIP_SEGMENTS for segment in path.split("/"))


def path_depth(url: str) -> int:
    return len([s for s in urlsplit(url).path.split("/") if s])
