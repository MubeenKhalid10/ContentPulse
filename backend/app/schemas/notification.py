import uuid
from datetime import datetime

from pydantic import BaseModel


class NotificationRead(BaseModel):
    id: uuid.UUID
    post_id: uuid.UUID | None
    kind: str
    scope: str | None
    title: str
    body: str | None
    link: str
    read_at: datetime | None
    created_at: datetime


class NotificationPage(BaseModel):
    items: list[NotificationRead]
    unread: int
