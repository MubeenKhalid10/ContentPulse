"""The organization's uploaded logo: validated once, stored with the design files,
and placed as is on AI-generated images (preferred over Profile > Logo URL)."""

import io
import uuid

from PIL import Image, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ErrorCode, NotFound
from app.models.organization import Organization
from app.services import audit
from app.services.audit import AuditAction
from app.storage import get_storage

# Small enough to go through any proxy in front of the API (Vercel: 4.5 MB).
MAX_LOGO_BYTES = 2_000_000
MAX_LOGO_PIXELS = 25_000_000
FORMATS = {
    "PNG": ("image/png", "png"),
    "JPEG": ("image/jpeg", "jpg"),
    "WEBP": ("image/webp", "webp"),
}


def _invalid(message: str) -> AppError:
    return AppError(ErrorCode.FILE_UPLOAD_FAILED, message)


def check_logo(data: bytes) -> tuple[str, str]:
    """Return (content type, extension) for a usable logo, or raise."""
    if not data:
        raise _invalid("Choose an image file to upload.")
    if len(data) > MAX_LOGO_BYTES:
        raise _invalid("The logo is larger than 2 MB. Export a smaller PNG.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > MAX_LOGO_PIXELS:
                raise _invalid("The logo image is too large.")
            fmt = image.format
            image.verify()  # reads the whole file: catches truncated uploads
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise _invalid("Upload a PNG, JPG or WebP image (SVG isn't supported yet).") from exc
    if fmt not in FORMATS:
        raise _invalid("Upload a PNG, JPG or WebP image (SVG isn't supported yet).")
    return FORMATS[fmt]


async def upload_logo(
    db: AsyncSession, organization: Organization, user_id: uuid.UUID, data: bytes
) -> Organization:
    content_type, extension = check_logo(data)
    key = f"orgs/{organization.id}/brand/logo-{uuid.uuid4().hex[:12]}.{extension}"
    storage = get_storage()
    await storage.put(key, data, content_type)
    previous = organization.logo_storage_key
    organization.logo_storage_key = key
    audit.record(
        db,
        organization_id=organization.id,
        user_id=user_id,
        action=AuditAction.ORGANIZATION_UPDATED,
        entity_type="organization",
        entity_id=organization.id,
        old_value={"logo_file": previous is not None},
        new_value={"logo_file": True},
    )
    await db.commit()
    await db.refresh(organization)
    if previous and previous != key:
        await storage.delete(previous)  # best effort: the new one is already live
    return organization


async def remove_logo(
    db: AsyncSession, organization: Organization, user_id: uuid.UUID
) -> Organization:
    previous = organization.logo_storage_key
    if previous is None:
        return organization
    organization.logo_storage_key = None
    audit.record(
        db,
        organization_id=organization.id,
        user_id=user_id,
        action=AuditAction.ORGANIZATION_UPDATED,
        entity_type="organization",
        entity_id=organization.id,
        old_value={"logo_file": True},
        new_value={"logo_file": False},
    )
    await db.commit()
    await db.refresh(organization)
    await get_storage().delete(previous)
    return organization


async def logo_link(organization: Organization) -> str:
    """A short-lived signed link to the uploaded logo."""
    if organization.logo_storage_key is None:
        raise NotFound("Logo")
    extension = organization.logo_storage_key.rsplit(".", 1)[-1]
    return await get_storage().download_url(
        organization.logo_storage_key, f"logo.{extension}", inline=True
    )
