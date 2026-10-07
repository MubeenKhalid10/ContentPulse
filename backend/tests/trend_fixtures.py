"""Synthetic payloads shaped like each provider's real responses."""

import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx

NOW = datetime.now(UTC)


def rfc822(hours_ago: float) -> str:
    return format_datetime(NOW - timedelta(hours=hours_ago))


def iso(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


GOOGLE_TRENDS_RSS = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel>
<item><title>openai gpt-6</title><ht:approx_traffic>200K+</ht:approx_traffic>
<pubDate>{rfc822(2)}</pubDate>
<ht:news_item><ht:news_item_title>OpenAI launches GPT-6 for enterprise automation</ht:news_item_title>
<ht:news_item_url>https://news.example.com/gpt6</ht:news_item_url>
<ht:news_item_source>Example News</ht:news_item_source></ht:news_item></item>
<item><title>naomi osaka</title><ht:approx_traffic>50K+</ht:approx_traffic>
<pubDate>{rfc822(3)}</pubDate></item>
</channel></rss>"""

GOOGLE_NEWS_RSS = f"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
<item><title>OpenAI GPT-6 arrives with autonomous agents - Reuters</title>
<link>https://news.google.com/rss/articles/a1</link><guid>a1</guid>
<pubDate>{rfc822(1)}</pubDate><source url="https://reuters.com">Reuters</source></item>
<item><title>What GPT-6 means for finance teams - Financial Times</title>
<link>https://news.google.com/rss/articles/a2</link><guid>a2</guid>
<pubDate>{rfc822(4)}</pubDate><source url="https://ft.com">Financial Times</source></item>
<item><title>Local bakery wins regional award - Town Gazette</title>
<link>https://news.google.com/rss/articles/a3</link><guid>a3</guid>
<pubDate>{rfc822(5)}</pubDate><source url="https://gazette.example">Town Gazette</source></item>
<item><title>Old story from last week - Archive</title>
<link>https://news.google.com/rss/articles/old</link><guid>old</guid>
<pubDate>{rfc822(24 * 8)}</pubDate><source url="https://archive.example">Archive</source></item>
</channel></rss>"""

HN_FRONT_PAGE = {
    "hits": [
        {
            "objectID": "101",
            "title": "GPT-6 benchmarks: agents finally beat humans at spreadsheets",
            "url": "https://blog.example.com/gpt6-benchmarks",
            "points": 450,
            "num_comments": 230,
            "created_at_i": int((NOW - timedelta(hours=6)).timestamp()),
            "author": "pg",
        },
        {
            "objectID": "102",
            "title": "Show HN: A tiny Rust database for embedded devices",
            "url": None,
            "points": 180,
            "num_comments": 40,
            "created_at_i": int((NOW - timedelta(hours=3)).timestamp()),
            "author": "dev",
        },
        {
            "objectID": "103",
            "title": "Some low-signal post",
            "url": "https://x.example.com",
            "points": 3,
            "num_comments": 0,
            "created_at_i": int((NOW - timedelta(hours=1)).timestamp()),
            "author": "anon",
        },
    ]
}

REDDIT_LISTING = {
    "data": {
        "children": [
            {
                "data": {
                    "id": "abc1",
                    "title": "GPT-6 just automated our entire invoicing workflow",
                    "permalink": "/r/automation/comments/abc1/gpt6/",
                    "score": 3400,
                    "num_comments": 410,
                    "created_utc": (NOW - timedelta(hours=5)).timestamp(),
                    "subreddit": "automation",
                    "author": "ops_lead",
                }
            },
            {"data": {"id": "nsfw", "title": "nsfw post", "over_18": True, "score": 9999}},
            {"data": {"id": "pin", "title": "Weekly thread", "stickied": True, "score": 10}},
        ]
    }
}

REDDIT_RSS = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry><id>t3_rss1</id><title>GPT-6 discussion megathread</title>
<link href="https://www.reddit.com/r/technology/comments/rss1/" />
<author><name>/u/someone</name></author>
<category term="technology" label="r/technology"/>
<published>{iso(2)}</published></entry>
</feed>"""

ATOM_FEED = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Industry Blog</title>
<entry><id>post-1</id><title>Why GPT-6 changes back-office automation</title>
<link rel="alternate" href="https://blog.example.com/gpt6"/>
<updated>{iso(8)}</updated><summary>&lt;p&gt;Agents everywhere.&lt;/p&gt;</summary></entry>
</feed>"""

NEWSAPI = {
    "status": "ok",
    "articles": [
        {
            "title": "GPT-6 sets new bar for enterprise AI",
            "description": "OpenAI's model targets automation.",
            "url": "https://wire.example.com/gpt6",
            "source": {"name": "Wire"},
            "publishedAt": iso(2),
        },
        {"title": "[Removed]", "url": "https://removed.example.com"},
    ],
}

GNEWS = {
    "articles": [
        {
            "title": "GPT-6 and the future of work",
            "description": "Analysts weigh in.",
            "url": "https://g.example.com/gpt6",
            "publishedAt": iso(3),
            "source": {"name": "G Example"},
        }
    ]
}

X_SEARCH = {
    "data": [
        {
            "id": "1",
            "text": "GPT-6 is wild for automation",
            "created_at": iso(1),
            "public_metrics": {
                "like_count": 900,
                "retweet_count": 120,
                "reply_count": 40,
                "quote_count": 5,
            },
        },
        {
            "id": "2",
            "text": "automation thoughts",
            "created_at": iso(3),
            "public_metrics": {
                "like_count": 10,
                "retweet_count": 1,
                "reply_count": 0,
                "quote_count": 0,
            },
        },
    ]
}


class FakeInternet:
    """Routes requests by host. Hosts can be switched to fail per test."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.failures: dict[str, httpx.Response] = {}

    def fail(self, host: str, status: int, body: str = "") -> None:
        self.failures[host] = httpx.Response(status, text=body)

    def handler(self, request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        self.calls.append(f"{host}{path}")
        if host in self.failures:
            return self.failures[host]
        if host == "trends.google.com":
            return httpx.Response(200, text=GOOGLE_TRENDS_RSS)
        if host == "news.google.com":
            return httpx.Response(200, text=GOOGLE_NEWS_RSS)
        if host == "hn.algolia.com":
            params = request.url.params
            if params.get("tags") == "front_page":
                return httpx.Response(200, json=HN_FRONT_PAGE)
            return httpx.Response(200, json={"hits": []})
        if host == "www.reddit.com" and path == "/api/v1/access_token":
            return httpx.Response(200, json={"access_token": "reddit-token"})
        if host == "oauth.reddit.com":
            return httpx.Response(200, json=REDDIT_LISTING)
        if host == "www.reddit.com":
            return httpx.Response(200, text=REDDIT_RSS)
        if host == "newsapi.org":
            return httpx.Response(200, json=NEWSAPI)
        if host == "gnews.io":
            return httpx.Response(200, json=GNEWS)
        if host == "api.x.com" and path == "/oauth2/token":
            return httpx.Response(200, json={"access_token": "x-token"})
        if host == "api.x.com":
            return httpx.Response(200, json=X_SEARCH)
        if host == "graph.facebook.com":
            if "ig_hashtag_search" in path:
                return httpx.Response(200, json={"data": [{"id": "17841"}]})
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "m1",
                            "caption": "automation tips",
                            "like_count": 1200,
                            "comments_count": 80,
                            "permalink": "https://instagram.com/p/m1",
                            "timestamp": iso(4),
                        }
                    ]
                },
            )
        if host == "blog.example.com":
            return httpx.Response(
                200, text=ATOM_FEED, headers={"content-type": "application/atom+xml"}
            )
        return httpx.Response(404, text=json.dumps({"error": "unknown host in test"}))
