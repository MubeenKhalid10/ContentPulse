"""Map free-text target markets ("USA", "United Kingdom") to source geo codes."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Location:
    code: str  # ISO 3166-1 alpha-2, or GLOBAL
    name: str
    language: str = "en"

    @property
    def is_global(self) -> bool:
        return self.code == "GLOBAL"


GLOBAL_LOCATION = Location("GLOBAL", "Global")

# code, name, primary content language, aliases
_COUNTRIES: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("US", "United States", "en", ("usa", "us", "united states of america", "america")),
    (
        "GB",
        "United Kingdom",
        "en",
        ("uk", "great britain", "britain", "england", "scotland", "wales"),
    ),
    ("CA", "Canada", "en", ()),
    ("AU", "Australia", "en", ()),
    ("NZ", "New Zealand", "en", ()),
    ("IE", "Ireland", "en", ()),
    ("IN", "India", "en", ()),
    ("PK", "Pakistan", "en", ()),
    ("SG", "Singapore", "en", ()),
    ("ZA", "South Africa", "en", ()),
    ("NG", "Nigeria", "en", ()),
    ("KE", "Kenya", "en", ()),
    ("PH", "Philippines", "en", ()),
    ("MY", "Malaysia", "en", ()),
    ("AE", "United Arab Emirates", "en", ("uae", "dubai", "emirates")),
    ("SA", "Saudi Arabia", "ar", ("ksa",)),
    ("EG", "Egypt", "ar", ()),
    ("DE", "Germany", "de", ()),
    ("AT", "Austria", "de", ()),
    ("CH", "Switzerland", "de", ()),
    ("FR", "France", "fr", ()),
    ("BE", "Belgium", "fr", ()),
    ("NL", "Netherlands", "nl", ("holland",)),
    ("ES", "Spain", "es", ()),
    ("MX", "Mexico", "es", ()),
    ("AR", "Argentina", "es", ()),
    ("CO", "Colombia", "es", ()),
    ("BR", "Brazil", "pt", ()),
    ("PT", "Portugal", "pt", ()),
    ("IT", "Italy", "it", ()),
    ("SE", "Sweden", "sv", ()),
    ("NO", "Norway", "no", ()),
    ("DK", "Denmark", "da", ()),
    ("FI", "Finland", "fi", ()),
    ("PL", "Poland", "pl", ()),
    ("TR", "Turkey", "tr", ("turkiye", "türkiye")),
    ("JP", "Japan", "ja", ()),
    ("KR", "South Korea", "ko", ("korea",)),
    ("ID", "Indonesia", "id", ()),
    ("VN", "Vietnam", "vi", ()),
    ("TH", "Thailand", "th", ()),
]

_INDEX: dict[str, Location] = {}
for code, name, language, aliases in _COUNTRIES:
    location = Location(code, name, language)
    for alias in (code.lower(), name.lower(), *aliases):
        _INDEX[alias] = location
for alias in ("global", "worldwide", "world", "international", "all"):
    _INDEX[alias] = GLOBAL_LOCATION


def resolve(market: str) -> Location | None:
    key = re.sub(r"\s+", " ", market.strip().lower().replace(".", ""))
    return _INDEX.get(key)


def resolve_markets(markets: list[str]) -> tuple[list[Location], list[str]]:
    """Return (locations, unrecognized). Empty input means global."""
    locations: list[Location] = []
    unknown: list[str] = []
    for market in markets:
        location = resolve(market)
        if location is None:
            unknown.append(market)
        elif location not in locations:
            locations.append(location)
    return (locations or [GLOBAL_LOCATION]), unknown


def country_codes(locations: list[Location], fallback: str = "US") -> list[str]:
    """Concrete countries for sources that need one (global → fallback)."""
    codes = [loc.code for loc in locations if not loc.is_global]
    return codes or [fallback]


def name_for(code: str) -> str:
    if code == "GLOBAL":
        return "Global"
    loc = _INDEX.get(code.lower())
    return loc.name if loc else code


def supported_markets() -> list[dict[str, str]]:
    return [{"code": "GLOBAL", "name": "Global"}] + [
        {"code": code, "name": name} for code, name, _, _ in _COUNTRIES
    ]
