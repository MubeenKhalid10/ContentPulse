"""In-app notifications for the approval workflow. Each event tells each person once:
the (person, dedupe key) pair is unique, so a retry or a double click adds nothing."""

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.core.errors import NotFound
from app.core.permissions import Role
from app.models.approval import Notification
from app.models.enums import MemberStatus
from app.models.organization import OrganizationMember
from app.models.post import Post
from app.schemas.notification import NotificationPage, NotificationRead

SCOPE_WORD = {"copy": "content", "design": "design"}


async def notify(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_ids: set[uuid.UUID],
    post: Post,
    kind: str,
    title: str,
    dedupe_key: str,
    link: str,
    body: str | None = None,
    scope: str | None = None,
    skip: uuid.UUID | None = None,
) -> None:
    """Queue a notification for each person (never the one who caused it). It commits with
    the caller's transaction."""
    rows = [
        {
            "organization_id": organization_id,
            "user_id": u,
            "post_id": post.id,
            "kind": kind,
            "scope": scope,
            "title": title[:300],
            "body": body,
            "link": link,
            "dedupe_key": dedupe_key,
        }
        for u in user_ids
        if u and u != skip
    ]
    if rows:
        await db.execute(insert(Notification).values(rows).on_conflict_do_nothing())


async def admin_ids(db: AsyncSession, organization_id: uuid.UUID) -> set[uuid.UUID]:
    return set(
        await db.scalars(
            select(OrganizationMember.user_id).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.role == Role.ADMIN,
                OrganizationMember.status == MemberStatus.ACTIVE,
            )
        )
    )


def post_name(post: Post) -> str:
    return post.title or "Untitled post"


async def list_for(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID, *, limit: int
) -> NotificationPage:
    mine = (Notification.organization_id == organization_id, Notification.user_id == user_id)
    rows = list(
        await db.scalars(
            select(Notification).where(*mine).order_by(Notification.created_at.desc()).limit(limit)
        )
    )
    unread = await db.scalar(
        select(func.count()).select_from(Notification).where(*mine, Notification.read_at.is_(None))
    )
    return NotificationPage(
        items=[NotificationRead.model_validate(n, from_attributes=True) for n in rows],
        unread=unread or 0,
    )


async def mark_read(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID, notification_id: uuid.UUID
) -> None:
    result = await db.execute(
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.organization_id == organization_id,
            Notification.user_id == user_id,
        )
        .values(read_at=func.coalesce(Notification.read_at, utcnow()))
    )
    if result.rowcount == 0:
        raise NotFound("Notification")
    await db.commit()


async def mark_all_read(db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID) -> None:
    await db.execute(
        update(Notification)
        .where(
            Notification.organization_id == organization_id,
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=utcnow())
    )
    await db.commit()
