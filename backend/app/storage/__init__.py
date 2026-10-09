"""Creative file storage (spec §29, §41): files never pass through the
database, and uploads go straight to storage through short-lived signed URLs.

    S3Storage     S3 or any S3-compatible store, used when S3_BUCKET is set
    LocalStorage  signed URLs served by this API, the default with no setup
"""

import mimetypes
import re
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from typing import Protocol

from app.core.config import Settings, get_settings
from app.core.logging import logger

# Creatives designers deliver: images, PDFs (print/slide decks) and short videos.
ALLOWED_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "image/svg+xml",
    "application/pdf",
    "video/mp4",
    "video/quicktime",
    "video/webm",
}
SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_.\-]*$")


@dataclass
class UploadTarget:
    url: str
    method: str
    headers: dict[str, str]
    key: str
    expires_at: datetime


@dataclass
class ObjectInfo:
    size: int
    content_type: str | None


class Storage(Protocol):
    name: str

    async def upload_target(self, key: str, content_type: str, max_bytes: int) -> UploadTarget: ...

    async def head(self, key: str) -> ObjectInfo | None: ...

    async def download_url(self, key: str, filename: str, *, inline: bool = True) -> str: ...

    async def delete(self, key: str) -> None: ...

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        """Store bytes produced on the server (e.g. an AI-generated image)."""
        ...

    async def get(self, key: str) -> bytes | None:
        """Read a small stored file on the server (e.g. the brand logo); None if missing."""
        ...


def safe_filename(name: str) -> str:
    """Keep a readable, path-free version of the uploaded file's name."""
    base = re.split(r"[\\/]", name)[-1]
    base = re.sub(r"[^A-Za-z0-9._\-]+", "-", base).strip("-.") or "file"
    stem, dot, ext = base.rpartition(".")
    stem = stem.strip("-.")
    if dot and stem:
        return f"{stem[:80]}.{ext[:10]}".lower() if ext.isalnum() else stem[:90]
    return base[:90]


def guess_type(filename: str) -> str | None:
    return mimetypes.guess_type(filename)[0]


def check_key(key: str) -> str:
    if not SAFE_KEY.match(key) or ".." in key.split("/"):
        raise ValueError(f"Unsafe storage key: {key!r}")
    return key


@cache
def _storage(provider: str) -> Storage:
    settings = get_settings()
    if provider == "s3":
        from app.storage.s3 import S3Storage

        return S3Storage(settings)
    from app.storage.local import LocalStorage

    return LocalStorage(settings)


_override: Storage | None = None


@cache
def _s3_ready() -> bool:
    """S3 is configured but its client must also start (credentials, extras)."""
    try:
        _storage("s3")
    except Exception as exc:  # e.g. botocore MissingDependency, bad profile
        logger.error(
            "S3_BUCKET is set but the S3 client could not start (%s: %s). "
            "Files are stored on this server until it is fixed.",
            exc.__class__.__name__,
            exc,
        )
        return False
    return True


def storage_provider(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return "s3" if settings.s3_bucket and _s3_ready() else "local"


def get_storage() -> Storage:
    if _override is not None:
        return _override
    return _storage(storage_provider())


def set_storage(storage: Storage | None) -> None:
    """Swap the storage backend (tests)."""
    global _override
    _override = storage
