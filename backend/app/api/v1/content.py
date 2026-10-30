import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import DB, OrgContext, active_org_permission
from app.core.permissions import Permission
from app.core.ratelimit import AI_PER_USER, per_user
from app.models.enums import Platform
from app.schemas.approval import (
    ChangeRequestCreate,
    CommentCreate,
    CommentRead,
    ResubmitRequest,
)
from app.schemas.content import (
    GenerateRequest,
    PostDetail,
    PostPage,
    PostUpdate,
    RegenerateRequest,
    RestoreRequest,
    VersionRead,
)
from app.schemas.design import ChangeRequestRead
from app.services.approvals import change_requests
from app.services.content import service

AI_LIMIT = per_user(AI_PER_USER)
router = APIRouter(prefix="/content", tags=["content"])

CanRead = Annotated[OrgContext, Depends(active_org_permission(Permission.CONTENT_READ))]
CanGenerate = Annotated[OrgContext, Depends(active_org_permission(Permission.CONTENT_GENERATE))]
CanEdit = Annotated[OrgContext, Depends(active_org_permission(Permission.CONTENT_EDIT))]


@router.post(
    "/generate",
    response_model=PostDetail,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[AI_LIMIT],
)
async def generate(data: GenerateRequest, ctx: CanGenerate, db: DB):
    return await service.generate(db, ctx.organization_id, ctx.user.id, data.strategy_id)


@router.get("", response_model=PostPage)
async def list_posts(
    ctx: CanRead,
    db: DB,
    status_filter: Annotated[
        Literal[
            "drafts",
            "changes",
            "design",
            "approval",
            "approval_pending",
            "approval_done",
            "approved",
            "archived",
            "all",
        ],
        Query(alias="status"),
    ] = "drafts",
    platform: Platform | None = None,
    topic_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await service.list_posts(
        db,
        ctx.organization_id,
        status=status_filter,
        platform=platform.value if platform else None,
        topic_id=topic_id,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get("/{post_id}", response_model=PostDetail)
async def get_post(post_id: uuid.UUID, ctx: CanRead, db: DB):
    return await service.post_detail(db, ctx.organization_id, post_id)


@router.post(
    "/{post_id}/change-requests",
    response_model=ChangeRequestRead,
    status_code=status.HTTP_201_CREATED,
)
async def request_change(post_id: uuid.UUID, data: ChangeRequestCreate, ctx: CanEdit, db: DB):
    """Ask an admin to reopen locked copy or a locked design."""
    return await change_requests.create(
        db, ctx.organization_id, ctx.user.id, post_id, data.scope, data.note
    )


@router.get("/{post_id}/comments", response_model=list[CommentRead])
async def list_comments(post_id: uuid.UUID, ctx: CanRead, db: DB):
    return await change_requests.post_comments(db, ctx.organization_id, post_id)


@router.post("/{post_id}/comments", response_model=list[CommentRead])
async def add_comment(post_id: uuid.UUID, data: CommentCreate, ctx: CanEdit, db: DB):
    return await change_requests.add_post_comment(
        db, ctx.organization_id, ctx.user.id, post_id, data.body
    )


@router.patch("/{post_id}", response_model=PostDetail)
async def update_post(post_id: uuid.UUID, data: PostUpdate, ctx: CanEdit, db: DB):
    changes = data.model_dump(exclude_unset=True)
    for field in ("hashtags", "mentions"):
        if field in changes and changes[field] is None:
            changes[field] = []
    return await service.update_post(db, ctx.organization_id, ctx.user.id, post_id, changes)


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: uuid.UUID, ctx: CanEdit, db: DB):
    await service.delete_post(
        db,
        ctx.organization_id,
        ctx.user.id,
        post_id,
        any_stage=ctx.can(Permission.ORGANIZATION_WRITE),
    )


@router.get("/{post_id}/versions", response_model=list[VersionRead])
async def list_versions(post_id: uuid.UUID, ctx: CanRead, db: DB):
    return await service.list_versions(db, ctx.organization_id, post_id)


@router.post("/{post_id}/versions/{number}/restore", response_model=PostDetail)
async def restore_version(
    post_id: uuid.UUID, number: int, data: RestoreRequest, ctx: CanEdit, db: DB
):
    return await service.restore_version(
        db, ctx.organization_id, ctx.user.id, post_id, number, data.base_version
    )


@router.post(
    "/{post_id}/regenerate",
    response_model=PostDetail,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[AI_LIMIT],
)
async def regenerate(post_id: uuid.UUID, data: RegenerateRequest, ctx: CanGenerate, db: DB):
    return await service.regenerate(
        db, ctx.organization_id, ctx.user.id, post_id, data.instructions
    )


@router.post(
    "/{post_id}/variants",
    response_model=PostDetail,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[AI_LIMIT],
)
async def create_variant(post_id: uuid.UUID, ctx: CanGenerate, db: DB):
    return await service.create_variant(db, ctx.organization_id, ctx.user.id, post_id)


@router.post("/{post_id}/resubmit", response_model=PostDetail)
async def resubmit(post_id: uuid.UUID, data: ResubmitRequest, ctx: CanEdit, db: DB):
    return await service.resubmit(db, ctx.organization_id, ctx.user.id, post_id, data.note)


def _transition(action: str):
    async def endpoint(post_id: uuid.UUID, ctx: CanEdit, db: DB) -> PostDetail:
        return await service.transition(
            db,
            ctx.organization_id,
            ctx.user.id,
            post_id,
            action,
            can_review=ctx.can(Permission.APPROVAL_MANAGE),
        )

    return endpoint


for _action in service.ACTIONS:
    router.add_api_route(
        f"/{{post_id}}/{_action}",
        _transition(_action),
        methods=["POST"],
        response_model=PostDetail,
        name=f"post_{_action.replace('-', '_')}",
    )
