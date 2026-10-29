"""Plain "contains" matching for the list search boxes."""

ESCAPE = "\\"


def contains(q: str) -> str:
    """An ILIKE pattern matching `q` anywhere, case-insensitively. `%` and `_` are escaped
    so a search for "100%" or "snake_case" means those characters, not wildcards.
    Use with `.ilike(contains(q), escape=ESCAPE)`."""
    text = q.strip()
    for char in (ESCAPE, "%", "_"):
        text = text.replace(char, ESCAPE + char)
    return f"%{text}%"
