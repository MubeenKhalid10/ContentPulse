"""Topic phrase extraction and canonical keys for de-duplication (spec §12).

Headlines rarely name a topic directly ("Fed holds rates as inflation cools").
Candidate topics are entity-like phrases (capitalized runs, acronyms, product
names with digits), tracked keywords, and content bigrams. Phrases that recur
across several items in a run are what is actually trending.
"""

import re
import unicodedata

STOPWORDS = frozenset(
    """
    a about above after again against all am an and any are as at be because been before being
    below between both but by can could did do does doing down during each few for from further
    had has have having he her here hers herself him himself his how i if in into is it its itself
    just me more most my myself no nor not now of off on once only or other our ours ourselves out
    over own same she should so some such than that the their theirs them themselves then there
    these they this those through to too under until up very was we were what when where which
    while who whom why will with would you your yours yourself yourselves
    s t don shouldn wasn weren won wouldn isn aren couldn didn doesn hadn hasn haven
    """.split()
)

# Words common in headlines that never make a topic on their own.
HEADLINE_NOISE = frozenset(
    """
    says said say new news report reports reported update updates live watch video videos photos
    today week weeks year years day days month months time times first last latest top best
    breaking exclusive analysis opinion review guide how why what amid via vs versus could may
    might get gets got make makes made one two three people man woman world big small next back
    show shows here look looks inside full official officially announce announces announced
    ask tell hn january february march april june july august september october november
    december monday tuesday wednesday thursday friday saturday sunday tonight yesterday tomorrow
    """.split()
)

CONNECTORS = frozenset({"of", "and", "&", "de", "for"})
TOKEN = re.compile(r"[#@]?[\w][\w'’.+-]*[\w+]|[\w]", re.UNICODE)


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def tokens(text: str) -> list[str]:
    return [t.strip("'’.") for t in TOKEN.findall(text) if t.strip("'’.")]


def _singular(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def normalize_terms(text: str) -> list[str]:
    """Lowercase significant terms, possessives and plurals folded."""
    out = []
    for token in tokens(_strip_accents(text).lower()):
        token = re.sub(r"['’]s$", "", token).lstrip("#@")
        if not token or token in STOPWORDS or token in HEADLINE_NOISE:
            continue
        out.append(_singular(token))
    return out


def canonical_key(phrase: str) -> str:
    """Order-insensitive key: 'Interest Rates' == 'rate interest'."""
    terms = sorted(set(normalize_terms(phrase)))
    return " ".join(terms)[:200]


def is_title_case(text: str) -> bool:
    """Headlines Written Like This: capitals carry no entity signal."""
    words = [w for w in tokens(text) if len(w) > 3 and w[:1].isalpha()]
    return len(words) >= 3 and sum(w[:1].isupper() for w in words) / len(words) >= 0.7


def _is_entityish(token: str, position: int, title_case: bool = False) -> bool:
    lower = token.lower()
    if lower in (STOPWORDS | HEADLINE_NOISE) - CONNECTORS:
        return False  # "How", "Is", "The" break runs even when capitalized
    if token[:1] in "#@":
        return True
    if any(ch.isdigit() for ch in token) and any(ch.isalpha() for ch in token):
        return True  # GPT-5, iPhone17, Q3
    if len(token) >= 2 and token.isupper():
        return True  # AI, NASA, EU
    if token[:1].isupper():
        # In Title Case headlines every word is capitalized: not evidence.
        return not title_case
    return token[:1].islower() and any(ch.isupper() for ch in token[1:])  # iPhone, eBay


def candidate_phrases(text: str) -> list[str]:
    """Entity-like phrases from a headline, longest runs first."""
    words = tokens(text)
    title_case = is_title_case(text)
    phrases: list[str] = []
    run: list[str] = []

    def flush() -> None:
        # Trim connectors and noise words ("How Russia" -> "Russia").
        edge_noise = CONNECTORS | STOPWORDS | HEADLINE_NOISE
        while run and run[-1].lower() in edge_noise:
            run.pop()
        while run and run[0].lower() in edge_noise:
            run.pop(0)
        if run:
            phrase = " ".join(run)
            if canonical_key(phrase):
                phrases.append(phrase)
        run.clear()

    for i, word in enumerate(words):
        if _is_entityish(word, i, title_case):
            run.append(word)
        elif run and word.lower() in CONNECTORS:
            run.append(word)
        else:
            flush()
    flush()
    # Long runs often glue two entities ("Apple Vision Pro Launch Event"); keep
    # up to 4 words and also offer each word pair inside longer runs.
    out: list[str] = []
    for phrase in phrases:
        parts = phrase.split()
        out.append(" ".join(parts[:4]))
        if len(parts) > 2:
            out.extend(" ".join(parts[i : i + 2]) for i in range(len(parts) - 1))
    return list(dict.fromkeys(out))


def bigrams(text: str) -> list[str]:
    terms = normalize_terms(text)
    return [f"{a} {b}" for a, b in zip(terms, terms[1:], strict=False) if a != b]


def keyword_matches(text: str, keywords: list[str]) -> list[str]:
    """Tracked keywords that appear in text (case/punctuation-insensitive)."""
    haystack = f" {' '.join(normalize_terms(text))} "
    found = []
    for keyword in keywords:
        needle = " ".join(normalize_terms(keyword))
        if needle and f" {needle} " in haystack:
            found.append(keyword)
    return found


def top_terms(texts: list[str], limit: int = 8) -> list[str]:
    counts: dict[str, int] = {}
    for text in texts:
        for term in set(normalize_terms(text)):
            if len(term) > 2:
                counts[term] = counts.get(term, 0) + 1
    # With several texts, a term seen only once is incidental ("adds", "already").
    min_count = 2 if len(texts) >= 3 else 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [t for t, n in ranked if n >= min_count][:limit]


def display_topic(phrase: str) -> str:
    """Search queries arrive lowercase ('airport'); capitalize for display."""
    phrase = re.sub(r"['’]s", "", phrase).strip(" :-–—")
    return phrase[:1].upper() + phrase[1:] if phrase and phrase.islower() else phrase
