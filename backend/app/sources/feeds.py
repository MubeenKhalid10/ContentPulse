"""Minimal RSS 2.0 / Atom parsing shared by feed-based sources."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup, Tag


@dataclass
class FeedEntry:
    id: str
    title: str
    link: str | None
    published: datetime | None
    summary: str | None
    author: str | None
    source: str | None  # e.g. the publisher in Google News items
    categories: list[str] = field(default_factory=list)
    element: Tag | None = None  # for source-specific extensions


def _text(node: Tag | None) -> str | None:
    if node is None:
        return None
    value = node.get_text(" ", strip=True)
    return value or None


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)  # RFC 822 (RSS)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))  # RFC 3339 (Atom)
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _strip_html(value: str | None) -> str | None:
    if not value:
        return None
    text = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    return text[:1000] or None


def parse_feed(content: bytes) -> list[FeedEntry]:
    soup = BeautifulSoup(content, "xml")
    entries: list[FeedEntry] = []

    for item in soup.find_all("item"):  # RSS 2.0
        link = _text(item.find("link"))
        guid = _text(item.find("guid"))
        title = _text(item.find("title"))
        if not title:
            continue
        entries.append(
            FeedEntry(
                id=guid or link or title,
                title=title,
                link=link,
                published=parse_date(_text(item.find("pubDate"))),
                summary=_strip_html(_text(item.find("description"))),
                author=_text(item.find("author")) or _text(item.find("dc:creator")),
                source=_text(item.find("source")),
                categories=[c.get_text(strip=True) for c in item.find_all("category")],
                element=item,
            )
        )

    for entry in soup.find_all("entry"):  # Atom
        title = _text(entry.find("title"))
        if not title:
            continue
        link_tag = entry.find("link", rel="alternate") or entry.find("link")
        link = link_tag.get("href") if isinstance(link_tag, Tag) else None
        author = entry.find("author")
        entries.append(
            FeedEntry(
                id=_text(entry.find("id")) or (link if isinstance(link, str) else None) or title,
                title=title,
                link=link if isinstance(link, str) else None,
                published=parse_date(
                    _text(entry.find("published")) or _text(entry.find("updated"))
                ),
                summary=_strip_html(_text(entry.find("summary")) or _text(entry.find("content"))),
                author=_text(author.find("name")) if isinstance(author, Tag) else None,
                source=None,
                categories=[
                    str(c.get("label") or c.get("term"))
                    for c in entry.find_all("category")
                    if c.get("label") or c.get("term")
                ],
                element=entry,
            )
        )
    return entries
