"""Turn an HTML page into clean, heading-structured text (spec §9).

Output is lightweight markdown: "## Heading" lines and paragraphs separated by
blank lines. Navigation, footers, cookie banners, forms and scripts are removed
so only meaningful page content reaches the knowledge base.
"""

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, NavigableString, Tag

from app.services.knowledge.urls import normalize_url

HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
TEXT_BLOCKS = frozenset(
    "p li blockquote pre td th dd dt figcaption summary caption address".split()
)
REMOVE_TAGS = frozenset(
    "script style noscript template svg canvas iframe form button input select textarea "
    "nav footer aside dialog video audio picture object embed".split()
)
REMOVE_ROLES = frozenset("navigation banner contentinfo search dialog alertdialog menu".split())
# Matched against id/class tokens. Conservative to avoid stripping real content.
NOISE = re.compile(
    r"(^|[-_ ])(cookie|cookies|consent|gdpr|breadcrumbs?|share|sharing|social|newsletter|"
    r"popup|modal|skip-link|navbar|nav-menu|offcanvas|sr-only|visually-hidden)([-_ ]|$)",
    re.I,
)
WHITESPACE = re.compile(r"\s+")


@dataclass
class ExtractedPage:
    title: str | None
    description: str | None
    canonical_url: str | None
    language: str | None
    markdown: str
    word_count: int
    noindex: bool
    links: list[str] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)


def _clean(text: str) -> str:
    return WHITESPACE.sub(" ", text).strip()


def _meta(soup: BeautifulSoup, *, name: str | None = None, prop: str | None = None) -> str | None:
    tag = soup.find("meta", attrs={"name": name} if name else {"property": prop})
    content = tag.get("content") if isinstance(tag, Tag) else None
    return _clean(content) if isinstance(content, str) and content.strip() else None


def _is_noise(tag: Tag) -> bool:
    if tag.get("aria-hidden") == "true" or tag.has_attr("hidden"):
        return True
    if tag.get("role") in REMOVE_ROLES:
        return True
    tokens = " ".join([tag.get("id") or "", *(tag.get("class") or [])])
    return bool(tokens.strip()) and bool(NOISE.search(tokens))


def _strip_noise(root: Tag) -> None:
    for tag in root.find_all(REMOVE_TAGS):
        tag.decompose()
    # Page-level <header> is site chrome; a <header> inside main/article is content.
    for tag in root.find_all("header"):
        if not tag.find_parent(["main", "article"]):
            tag.decompose()
    for tag in root.find_all(True):
        if not tag.decomposed and _is_noise(tag):
            tag.decompose()


def _content_root(soup: BeautifulSoup) -> Tag:
    main = soup.find("main") or soup.find(attrs={"role": "main"})
    if isinstance(main, Tag):
        return main
    articles = soup.find_all("article")
    if len(articles) == 1:
        return articles[0]
    return soup.body or soup


def _blocks(node: Tag) -> list[tuple[int, str]]:
    """Walk in document order: (heading level, text) or (0, paragraph)."""
    out: list[tuple[int, str]] = []
    loose: list[str] = []

    def flush_loose() -> None:
        text = _clean(" ".join(loose))
        if text:
            out.append((0, text))
        loose.clear()

    for child in node.children:
        if isinstance(child, NavigableString):
            if child.__class__ is NavigableString:  # skip comments/CDATA
                loose.append(str(child))
            continue
        if not isinstance(child, Tag):
            continue
        if child.name in HEADINGS:
            flush_loose()
            text = _clean(child.get_text(" "))
            if text:
                out.append((HEADINGS[child.name], text))
        elif child.name in TEXT_BLOCKS:
            flush_loose()
            text = _clean(child.get_text(" "))
            if text:
                out.append((0, text))
        elif child.name in ("br",):
            flush_loose()
        elif child.name in ("a", "span", "strong", "em", "b", "i", "small", "mark", "code"):
            loose.append(child.get_text(" "))
        else:
            flush_loose()
            out.extend(_blocks(child))
    flush_loose()
    return out


def _to_markdown(blocks: list[tuple[int, str]]) -> tuple[str, list[str]]:
    lines: list[str] = []
    headings: list[str] = []
    previous = None
    for level, text in blocks:
        if text == previous:  # repeated blocks (e.g. duplicated mobile/desktop copy)
            continue
        previous = text
        if level:
            headings.append(text)
            lines.append(f"{'#' * level} {text}")
        elif len(text) >= 3:
            lines.append(text)
    return "\n\n".join(lines).strip(), headings


def extract_page(content: bytes, url: str, encoding: str | None = None) -> ExtractedPage:
    soup = BeautifulSoup(content, "lxml", from_encoding=encoding)

    robots = (_meta(soup, name="robots") or "").lower()
    canonical_tag = soup.find("link", rel="canonical")
    canonical_href = canonical_tag.get("href") if isinstance(canonical_tag, Tag) else None
    html_tag = soup.find("html")
    language = html_tag.get("lang") if isinstance(html_tag, Tag) else None

    # Links are collected before noise removal: navigation is how pages are found.
    links = [a["href"] for a in soup.find_all("a", href=True) if isinstance(a["href"], str)]

    title_tag = soup.find("title")
    title = _meta(soup, prop="og:title") or (
        _clean(title_tag.get_text()) if isinstance(title_tag, Tag) else None
    )
    description = _meta(soup, name="description") or _meta(soup, prop="og:description")

    root = _content_root(soup)
    _strip_noise(root)
    markdown, headings = _to_markdown(_blocks(root))
    if not title and headings:
        title = headings[0]

    return ExtractedPage(
        title=title[:500] if title else None,
        description=description,
        canonical_url=normalize_url(canonical_href, url)
        if isinstance(canonical_href, str)
        else None,
        language=language if isinstance(language, str) else None,
        markdown=markdown,
        word_count=len(re.findall(r"\w+", markdown)),
        noindex="noindex" in robots,
        links=links,
        headings=headings[:50],
    )
