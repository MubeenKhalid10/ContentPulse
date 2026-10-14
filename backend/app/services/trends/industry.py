"""Industry-aware collection inputs.

An organization that hasn't listed tracked keywords or services still told us
its industry. Its searches start from that industry instead of a generic
"technology" query, and technology-only sources are only switched on by
default for organizations that work in technology.
"""

import re

# (words that identify the industry, seed searches). First match wins, so
# more specific groups come first.
INDUSTRY_SEEDS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("health", "medical", "clinic", "hospital", "pharma", "dental", "biotech", "care"),
        ("healthcare", "medical technology", "digital health"),
    ),
    (
        ("marketing", "advertising", "agency", "seo", "public relations", "branding", "media"),
        ("digital marketing", "social media marketing", "advertising"),
    ),
    (
        ("fintech", "finance", "financial", "bank", "insurance", "accounting", "invest"),
        ("fintech", "banking", "personal finance"),
    ),
    (
        ("education", "edtech", "school", "university", "training", "e-learning"),
        ("education technology", "online learning", "higher education"),
    ),
    (
        ("ecommerce", "e-commerce", "retail", "consumer goods", "fashion"),
        ("ecommerce", "retail", "consumer trends"),
    ),
    (
        ("real estate", "property", "construction", "architecture"),
        ("real estate", "housing market", "construction industry"),
    ),
    (
        ("legal", "law"),
        ("legal technology", "law firms", "regulation"),
    ),
    (
        ("hospitality", "travel", "tourism", "hotel", "restaurant", "food"),
        ("travel industry", "hospitality", "restaurant industry"),
    ),
    (
        ("manufacturing", "logistics", "supply chain", "industrial", "automotive"),
        ("manufacturing", "supply chain", "logistics"),
    ),
    (
        ("energy", "renewable", "solar", "utilities", "climate"),
        ("renewable energy", "energy industry", "climate tech"),
    ),
    (
        (
            "software",
            "saas",
            "technology",
            "tech",
            "it services",
            "cloud",
            "ai",
            "artificial intelligence",
            "cybersecurity",
            "web development",
            "data",
            "developer",
        ),
        ("software development", "SaaS", "artificial intelligence"),
    ),
)
TECH_SEEDS = INDUSTRY_SEEDS[-1][1]


def _matches(text: str, word: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", text) is not None


def industry_terms(industry: str | None) -> list[str]:
    """Seed searches for an industry: known groups map to a few broad searches;
    anything else is searched as written."""
    text = " ".join((industry or "").split())
    if not text:
        return []
    lowered = text.casefold()
    for words, seeds in INDUSTRY_SEEDS:
        if any(_matches(lowered, w) for w in words):
            return list(seeds)
    return [text[:80]]


def is_technology(industry: str | None) -> bool:
    return industry_terms(industry) == list(TECH_SEEDS)
