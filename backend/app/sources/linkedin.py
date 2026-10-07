from app.core.config import Settings
from app.sources.base import (
    Configuration,
    RawTrendItem,
    SourceContext,
    SourceError,
    SourceErrorKind,
    SourceInputs,
    TrendSource,
)


class LinkedInSource(TrendSource):
    """Listed for completeness (spec §10). LinkedIn offers no API for trend data."""

    key = "linkedin"
    name = "LinkedIn"
    description = "Trending professional conversations."
    pricing = "unavailable"
    docs_url = "https://learn.microsoft.com/en-us/linkedin/marketing/"

    def configuration(self, settings: Settings, inputs: SourceInputs) -> Configuration:
        return Configuration(
            configured=False,
            note=(
                "LinkedIn has no public API for trending topics or searching posts; that data "
                "is limited to approved LinkedIn partners. This source stays off. Publishing to "
                "LinkedIn is planned for Phase 2."
            ),
        )

    async def collect(self, ctx: SourceContext) -> list[RawTrendItem]:
        raise SourceError(SourceErrorKind.NOT_CONFIGURED, "LinkedIn has no trends API.")
