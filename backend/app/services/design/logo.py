"""Place the organization's real logo on AI-generated images.

Image models can't reproduce a logo faithfully, so they are told to leave the
spot empty, and the logo from Profile > Logo URL is pasted on afterwards,
unchanged, at the position the brand (or the post) asks for.

The logo URL is user-supplied, so it is fetched like a crawled page: every
redirect hop must resolve to a public address, and the download is capped.
"""

import asyncio
import io
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

from app.core.config import Settings
from app.services.knowledge.fetcher import FetchError, Resolver, SafeFetcher, build_http_client
from app.services.knowledge.fetcher import system_resolver as default_resolver

POSITIONS = (
    "top_left",
    "top_center",
    "top_right",
    "bottom_left",
    "bottom_center",
    "bottom_right",
)
DEFAULT_POSITION = "bottom_right"

# In words, for the image prompt and version notes.
POSITION_LABEL = {
    "top_left": "top-left corner",
    "top_center": "top centre",
    "top_right": "top-right corner",
    "bottom_left": "bottom-left corner",
    "bottom_center": "bottom centre",
    "bottom_right": "bottom-right corner",
}

# The logo's box, as a share of the image: wide enough to read, small enough
# to stay out of the way. Margin from the edges, as a share of the short side.
MAX_WIDTH_SHARE = 0.18
MAX_HEIGHT_SHARE = 0.12
MARGIN_SHARE = 0.04
# Refuse absurd logos (decompression bombs) before decoding them fully.
MAX_LOGO_PIXELS = 25_000_000


class LogoError(Exception):
    """The logo couldn't be placed. `reason` is safe to show to users."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class PlacedImage:
    data: bytes
    mime_type: str


def effective_position(requirements: dict | None, brand_default: str | None) -> str | None:
    """The post's choice, else the brand's; None when the logo is turned off."""
    position = (requirements or {}).get("logo_position") or brand_default or DEFAULT_POSITION
    return position if position in POSITIONS else None


async def fetch_logo(url: str, settings: Settings, resolver: Resolver = default_resolver) -> bytes:
    async with build_http_client(settings) as client:
        try:
            result = await SafeFetcher(client, settings, resolver).get(url)
        except FetchError as exc:
            raise LogoError(f"the logo link couldn't be opened ({exc.reason})") from exc
    if result.status_code != 200:
        raise LogoError(f"the logo link answered HTTP {result.status_code}")
    if result.content_type in ("image/svg+xml", "text/html"):
        raise LogoError(
            "the logo link must point to a PNG, JPG or WebP image"
            + (" (SVG isn't supported yet)" if result.content_type == "image/svg+xml" else "")
        )
    return result.content


def place_logo(image_bytes: bytes, logo_bytes: bytes, position: str) -> PlacedImage:
    """Paste the logo, untouched apart from scaling, at `position`."""
    if position not in POSITIONS:
        raise ValueError(f"Unknown logo position {position!r}")
    try:
        logo = Image.open(io.BytesIO(logo_bytes))
        if logo.width * logo.height > MAX_LOGO_PIXELS:
            raise LogoError("the logo image is too large")
        logo.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise LogoError("the logo link must point to a PNG, JPG or WebP image") from exc

    try:
        base = Image.open(io.BytesIO(image_bytes))
        base.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise LogoError("the generated image couldn't be read to place the logo") from exc
    canvas = base.convert("RGBA")
    logo = logo.convert("RGBA")

    # Fit inside the box, keeping the logo's proportions; never upscale it.
    box_w, box_h = canvas.width * MAX_WIDTH_SHARE, canvas.height * MAX_HEIGHT_SHARE
    scale = min(box_w / logo.width, box_h / logo.height, 1.0)
    size = (max(1, round(logo.width * scale)), max(1, round(logo.height * scale)))
    if size != logo.size:
        logo = logo.resize(size, Image.Resampling.LANCZOS)

    margin = round(min(canvas.width, canvas.height) * MARGIN_SHARE)
    vertical, horizontal = position.split("_")
    x = {
        "left": margin,
        "center": (canvas.width - logo.width) // 2,
        "right": canvas.width - logo.width - margin,
    }[horizontal]
    y = margin if vertical == "top" else canvas.height - logo.height - margin
    canvas.alpha_composite(logo, (x, y))

    out = io.BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return PlacedImage(out.getvalue(), "image/png")


def has_logo(organization) -> bool:
    """An uploaded logo file, or a Profile > Logo URL."""
    return bool(organization and (organization.logo_storage_key or organization.logo_url))


async def load_logo(organization, settings: Settings) -> bytes:
    """The uploaded logo file if there is one, else the one at Profile > Logo URL."""
    if organization.logo_storage_key:
        from app.storage import get_storage
        from app.storage.s3 import StorageUnavailable

        try:
            data = await get_storage().get(organization.logo_storage_key)
        except StorageUnavailable as exc:
            raise LogoError("the uploaded logo couldn't be read from storage") from exc
        if data is None:
            raise LogoError("the uploaded logo file is missing; upload it again in Profile")
        return data
    if organization.logo_url:
        return await fetch_logo(organization.logo_url, settings)
    raise LogoError("no logo is set in Profile")


async def add_logo(
    image_bytes: bytes, organization, position: str, settings: Settings
) -> PlacedImage:
    logo_bytes = await load_logo(organization, settings)
    # Decoding and resizing are CPU work: keep them off the event loop.
    return await asyncio.to_thread(place_logo, image_bytes, logo_bytes, position)
