import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.deps import DB, OrgContext, active_org_any_permission, active_org_permission
from app.core.permissions import Permission
from app.core.ratelimit import AI_PER_USER, per_user
from app.models.enums import Platform
from app.schemas.approval import ResubmitRequest
from app.schemas.design import (
    AssignRequest,
    BriefUpdate,
    RegisterAssets,
    TaskDetail,
    TaskPage,
    UploadRequest,
    UploadTicket,
)
from app.services.design import images, service

router = APIRouter(prefix="/design/tasks", tags=["design"])

CanRead = Annotated[OrgContext, Depends(active_org_permission(Permission.DESIGN_READ))]
CanUpload = Annotated[OrgContext, Depends(active_org_permission(Permission.DESIGN_UPLOAD))]
CanSubmit = Annotated[OrgContext, Depends(active_org_permission(Permission.DESIGN_SUBMIT))]
# Managers assign anyone; designers can take a task themselves.
CanAssign = Annotated[
    OrgContext,
    Depends(active_org_any_permission(Permission.DESIGN_MANAGE, Permission.DESIGN_UPLOAD)),
]
# The brief belongs to whoever owns the copy or runs design.
CanEditBrief = Annotated[
    OrgContext,
    Depends(active_org_any_permission(Permission.CONTENT_EDIT, Permission.DESIGN_MANAGE)),
]


@router.get("", response_model=TaskPage)
async def list_tasks(
    ctx: CanRead,
    db: DB,
    status_filter: Annotated[
        Literal["todo", "submitted", "done", "cancelled", "all"], Query(alias="status")
    ] = "todo",
    mine: bool = False,
    platform: Platform | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await service.list_tasks(
        db,
        ctx.organization_id,
        ctx.user.id,
        status=status_filter,
        mine=mine,
        platform=platform.value if platform else None,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get("/{task_id}", response_model=TaskDetail)
async def get_task(task_id: uuid.UUID, ctx: CanRead, db: DB):
    return await service.task_detail(db, ctx.organization_id, task_id)


@router.patch("/{task_id}", response_model=TaskDetail)
async def update_brief(task_id: uuid.UUID, data: BriefUpdate, ctx: CanEditBrief, db: DB):
    return await service.update_brief(
        db, ctx.organization_id, ctx.user.id, task_id, data.model_dump(exclude_unset=True)
    )


@router.post("/{task_id}/assign", response_model=TaskDetail)
async def assign(task_id: uuid.UUID, data: AssignRequest, ctx: CanAssign, db: DB):
    return await service.assign(
        db, ctx.organization_id, ctx.user.id, ctx.role, task_id, data.assignee_id
    )


@router.post(
    "/{task_id}/generate-image",
    response_model=TaskDetail,
    status_code=202,
    dependencies=[per_user(AI_PER_USER)],
)
async def generate_image(task_id: uuid.UUID, ctx: CanUpload, db: DB):
    """Create an image from the brief and the post with AI (in the background).
    It becomes the task's next creative version."""
    return await images.start(db, ctx.organization_id, ctx.user.id, ctx.role, task_id)


@router.post("/{task_id}/start", response_model=TaskDetail)
async def start(task_id: uuid.UUID, ctx: CanUpload, db: DB):
    return await service.start(db, ctx.organization_id, ctx.user.id, ctx.role, task_id)


@router.post("/{task_id}/uploads", response_model=UploadTicket)
async def request_upload(task_id: uuid.UUID, data: UploadRequest, ctx: CanUpload, db: DB):
    """Step 1 of an upload: a short-lived signed URL to send the file to."""
    target = await service.upload_ticket(
        db,
        ctx.organization_id,
        ctx.user.id,
        ctx.role,
        task_id,
        data.file_name,
        data.file_type,
        data.file_size,
    )
    return UploadTicket(
        url=target.url,
        method=target.method,
        headers=target.headers,
        storage_key=target.key,
        expires_at=target.expires_at,
    )


@router.post("/{task_id}/assets", response_model=TaskDetail)
async def register_assets(task_id: uuid.UUID, data: RegisterAssets, ctx: CanUpload, db: DB):
    """Step 2: record the uploaded files as the next creative version."""
    return await service.register_assets(
        db,
        ctx.organization_id,
        ctx.user.id,
        ctx.role,
        task_id,
        [f.model_dump() for f in data.files],
        data.note,
    )


@router.post("/{task_id}/submit", response_model=TaskDetail)
async def submit(task_id: uuid.UUID, ctx: CanSubmit, db: DB, data: ResubmitRequest | None = None):
    note = data.note if data else None
    return await service.submit(db, ctx.organization_id, ctx.user.id, ctx.role, task_id, note)
