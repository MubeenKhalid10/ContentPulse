"""Group raw items into canonical trends (spec §12): one opportunity per topic,
with every source mention attached, instead of five near-duplicates."""

from collections import Counter
from dataclasses import dataclass, field

from app.services.trends.text import (
    bigrams,
    candidate_phrases,
    canonical_key,
    display_topic,
    keyword_matches,
    normalize_terms,
    top_terms,
)
from app.sources.base import RawTrendItem

# Sources whose items carry real engagement: a single strong item can be a trend.
ENGAGEMENT_SOURCES = {"google_trends", "hacker_news", "reddit", "x", "instagram"}
STANDALONE_MIN_ENGAGEMENT = {"hacker_news": 100, "reddit": 500, "x": 50, "instagram": 500}
# These providers return searched news articles without an engagement metric.
# A tracked keyword is enough signal to retain an otherwise unique article.
KEYWORD_STANDALONE_SOURCES = {"world_news", "newsdata"}
BIGRAM_WEIGHT = 0.6


@dataclass
class Cluster:
    key: str
    items: list[RawTrendItem] = field(default_factory=list)
    phrasings: Counter = field(default_factory=Counter)
    matched_keywords: set[str] = field(default_factory=set)

    @property
    def topic(self) -> str:
        phrase, _ = self.phrasings.most_common(1)[0]
        return display_topic(phrase)

    @property
    def tokens(self) -> set[str]:
        return set(self.key.split())

    def keywords(self) -> list[str]:
        explicit = [k for item in self.items for k in item.keywords]
        derived = top_terms([f"{i.title} {i.description or ''}" for i in self.items])
        return list(dict.fromkeys([*self.matched_keywords, *explicit, *derived]))[:12]

    def absorb(self, other: "Cluster") -> None:
        self.items.extend(other.items)
        self.phrasings.update(other.phrasings)
        self.matched_keywords |= other.matched_keywords


def similar_keys(a: str, b: str) -> bool:
    """Same topic under different wording ('OpenAI GPT-5' vs 'GPT-5')."""
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    small, large = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    jaccard = len(ta & tb) / len(ta | tb)
    # Subsets merge only when the smaller key is specific (2+ terms or a long term).
    specific = len(small) >= 2 or any(len(t) >= 6 or any(c.isdigit() for c in t) for t in small)
    return jaccard >= 0.6 or (small <= large and specific and len(large) <= len(small) + 2)


def _item_text(item: RawTrendItem) -> str:
    news = " ".join(n.get("title") or "" for n in item.raw_data.get("news", []))
    return f"{item.title} {news}"


def cluster_items(
    items: list[RawTrendItem], tracked_keywords: list[str]
) -> tuple[list[Cluster], int]:
    """Return (clusters, items left unclustered as low-signal noise)."""
    # 1. Candidate phrases per item, and how many items each phrase appears in.
    candidates: list[list[str]] = []
    document_frequency: Counter = Counter()
    for item in items:
        if item.topic:
            phrases = [(item.topic, 1.0)]
        else:
            # Entity phrases are strong evidence; content bigrams weaker.
            phrases = [(p, 1.0) for p in candidate_phrases(item.title)]
            phrases += [(b, BIGRAM_WEIGHT) for b in bigrams(item.title)]
        keys = {canonical_key(p) for p, _ in phrases if canonical_key(p)}
        document_frequency.update(keys)
        candidates.append(phrases)

    # 2. Pick each item's topic: explicit topic > the phrase shared with the most
    #    other items. Tracked keywords inform relevance scoring; they become a
    #    topic only when they appear as an entity phrase.
    clusters: dict[str, Cluster] = {}
    unclustered = 0
    tracked_keys = {canonical_key(k) for k in tracked_keywords}
    for item, phrases in zip(items, candidates, strict=True):
        matched = keyword_matches(_item_text(item), tracked_keywords) if tracked_keywords else []
        chosen: str | None = None
        if item.topic:
            chosen = item.topic
        else:
            scored = []
            for phrase, weight in phrases:
                key = canonical_key(phrase)
                df = document_frequency[key]
                min_df = 2 if weight == 1.0 else 3
                # A tracked keyword found only as plain words ("automation") would
                # lump unrelated stories together; as an entity ("GPT-6") it's a topic.
                generic_keyword = key in tracked_keys and weight != 1.0
                if df >= min_df and not generic_keyword:
                    scored.append((_specificity(key) * df * weight, len(key.split()), phrase))
            if scored:
                chosen = max(scored)[2]
            elif matched and item.source in KEYWORD_STANDALONE_SOURCES:
                # News search APIs can return a genuinely relevant article only
                # once. Do not discard it just because no second headline shares
                # its entity phrase.
                chosen = max(matched, key=lambda keyword: len(normalize_terms(keyword)))
            elif _is_standalone(item):
                # A single strong item (e.g. a top Hacker News story) is its own
                # trend; its headline describes it better than any fragment.
                chosen = " ".join(item.title.split()[:12])
        if not chosen:
            unclustered += 1
            continue
        key = canonical_key(chosen)
        if not key:
            unclustered += 1
            continue
        cluster = clusters.setdefault(key, Cluster(key=key))
        cluster.items.append(item)
        cluster.phrasings[chosen] += 1
        cluster.matched_keywords.update(matched)

    # 3. Merge clusters whose keys describe the same topic.
    merged: list[Cluster] = []
    for cluster in sorted(clusters.values(), key=lambda c: -len(c.items)):
        target = next((m for m in merged if similar_keys(m.key, cluster.key)), None)
        if target:
            target.absorb(cluster)
        else:
            merged.append(cluster)
    return merged, unclustered


def _specificity(key: str) -> float:
    """Multi-word topics beat broad single tokens like 'AI' or 'tech'."""
    terms = key.split()
    if len(terms) == 1:
        return 0.5 if len(terms[0]) <= 3 else 1.0
    return 1.0 + 0.75 * (len(terms) - 1)


def _is_standalone(item: RawTrendItem) -> bool:
    threshold = STANDALONE_MIN_ENGAGEMENT.get(item.source)
    return threshold is not None and (item.engagement or 0) >= threshold


def topic_terms(text: str) -> set[str]:
    return set(normalize_terms(text))
