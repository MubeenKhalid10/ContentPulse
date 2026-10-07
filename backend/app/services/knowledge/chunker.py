"""Heading-aware chunking of document markdown.

Chunks follow the document's section structure so each one is about a single
topic and carries its heading path (e.g. "Services › AI Solutions") for
retrieval context and citations. Long sections are split on paragraph and
sentence boundaries with a small overlap; tiny neighbouring sections are
merged so retrieval does not return fragments.
"""

import re
from dataclasses import dataclass

HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
WORD = re.compile(r"\S+")

TARGET_WORDS = 250
MAX_WORDS = 400
MIN_WORDS = 60
OVERLAP_WORDS = 40
PATH_SEPARATOR = " › "


@dataclass(frozen=True)
class Chunk:
    index: int
    heading: str | None
    content: str
    word_count: int

    @property
    def token_estimate(self) -> int:
        return round(self.word_count * 1.35)


def _words(text: str) -> int:
    return len(WORD.findall(text))


def _sections(markdown: str) -> list[tuple[tuple[str, ...], list[str]]]:
    """Split markdown into (heading path, paragraphs)."""
    sections: list[tuple[tuple[str, ...], list[str]]] = []
    stack: list[tuple[int, str]] = []
    paragraphs: list[str] = []

    def emit() -> None:
        if paragraphs:
            sections.append((tuple(h for _, h in stack), paragraphs.copy()))
            paragraphs.clear()

    for block in re.split(r"\n\s*\n", markdown):
        block = block.strip()
        if not block:
            continue
        match = HEADING.match(block) if "\n" not in block else None
        if match:
            emit()
            level = len(match.group(1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, match.group(2)))
        else:
            paragraphs.append(" ".join(block.split()))
    emit()
    return sections


def _split_long(paragraph: str) -> list[str]:
    """Break a paragraph above MAX_WORDS into sentence-aligned pieces."""
    if _words(paragraph) <= MAX_WORDS:
        return [paragraph]
    pieces: list[str] = []
    current: list[str] = []
    for sentence in SENTENCE_END.split(paragraph):
        candidate = " ".join([*current, sentence])
        if current and _words(candidate) > TARGET_WORDS:
            pieces.append(" ".join(current))
            current = [sentence]
        else:
            current.append(sentence)
    if current:
        pieces.append(" ".join(current))
    # A single run-on "sentence" can still be huge: hard-wrap by words.
    out: list[str] = []
    for piece in pieces:
        words = piece.split()
        for start in range(0, len(words), MAX_WORDS):
            out.append(" ".join(words[start : start + MAX_WORDS]))
    return out


def _tail(text: str, words: int) -> str:
    return " ".join(text.split()[-words:])


def _common_prefix(paths: list[tuple[str, ...]]) -> tuple[str, ...]:
    prefix = paths[0]
    for path in paths[1:]:
        n = 0
        while n < min(len(prefix), len(path)) and prefix[n] == path[n]:
            n += 1
        prefix = prefix[:n]
    return prefix


def chunk_markdown(markdown: str) -> list[Chunk]:
    raw: list[tuple[tuple[str, ...], str]] = []

    for path, paragraphs in _sections(markdown):
        pieces = [p for paragraph in paragraphs for p in _split_long(paragraph)]
        current: list[str] = []
        for piece in pieces:
            if current and _words(" ".join([*current, piece])) > TARGET_WORDS:
                text = "\n\n".join(current)
                raw.append((path, text))
                current = [_tail(text, OVERLAP_WORDS), piece]
            else:
                current.append(piece)
        if current:
            raw.append((path, "\n\n".join(current)))

    # Merge undersized neighbours into one chunk.
    groups: list[list[tuple[tuple[str, ...], str]]] = []
    for path, text in raw:
        if groups:
            group = groups[-1]
            previous_words = sum(_words(t) for _, t in group)
            if (previous_words < MIN_WORDS or _words(text) < MIN_WORDS) and (
                previous_words + _words(text) <= MAX_WORDS
            ):
                group.append((path, text))
                continue
        groups.append([(path, text)])

    chunks: list[Chunk] = []
    for index, group in enumerate(groups):
        prefix = _common_prefix([path for path, _ in group])
        # Headings below the shared prefix stay inline so no part loses its
        # section name (e.g. "AI Solutions" inside a merged "Services" chunk).
        parts: list[str] = []
        previous_label: str | None = None
        for path, text in group:
            label = PATH_SEPARATOR.join(path[len(prefix) :]) or None
            parts.append(f"{label}\n{text}" if label and label != previous_label else text)
            previous_label = label
        content = "\n\n".join(parts)
        chunks.append(
            Chunk(
                index=index,
                heading=PATH_SEPARATOR.join(prefix)[:500] if prefix else None,
                content=content,
                word_count=_words(content),
            )
        )
    return chunks
