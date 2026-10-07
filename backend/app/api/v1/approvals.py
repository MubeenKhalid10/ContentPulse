import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.deps import DB, OrgContext, active_org_any_permission, active_org_permission
from app.core.permissions import Permission
from app.models.enums import ApprovalStatus, Platform
from app.schemas.approval import (
    ApprovalDetail,
    ApprovalPage,
    ChangesRequest,
    CommentCreate,
    DecisionRequest,
)
from app.services.approvals import service

router = APIRouter(prefix="/approvals", tags=["approvals"])

CanRead = Annotated[OrgContext, Depends(active_org_permission(Permission.APPROVAL_READ))]
CanReview = Annotated[OrgContext, Depends(active_org_permission(Permission.APPROVAL_MANAGE))]
# Reviewers and the people who own the copy can discuss a submission.
CanComment = Annotated[
    OrgContext,
    Depends(active_org_any_permission(Permission.APPROVAL_MANAGE, Permission.CONTENT_EDIT)),
]


@router.get("", response_model=ApprovalPage)
async def list_approvals(
    ctx: CanRead,
    db: DB,
    status_filter: Annotated[
        Literal["pending", "reviewed", "approved", "changes_requested", "rejected", "all"],
        Query(alias="status"),
    ] = "pending",
    platform: Platform | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await service.list_approvals(
        db,
        ctx.organization_id,
        status=status_filter,
        platform=platform.value if platform else None,
        limit=limit,
        offset=offset,
    )


@router.get("/{approval_id}", response_model=ApprovalDetail)
async def get_approval(approval_id: uuid.UUID, ctx: CanRead, db: DB):
    return await service.approval_detail(db, ctx.organization_id, approval_id)


@router.post("/{approval_id}/approve", response_model=ApprovalDetail)
async def approve(approval_id: uuid.UUID, data: DecisionRequest, ctx: CanReview, db: DB):
    return await service.decide(
        db, ctx.organization_id, ctx.user.id, approval_id, ApprovalStatus.APPROVED, data.comment
    )


@router.post("/{approval_id}/request-changes", response_model=ApprovalDetail)
async def request_changes(approval_id: uuid.UUID, data: ChangesRequest, ctx: CanReview, db: DB):
    return await service.decide(
        db,
        ctx.organization_id,
        ctx.user.id,
        approval_id,
        ApprovalStatus.CHANGES_REQUESTED,
        data.comment,
        data.scope,
    )


@router.post("/{approval_id}/reject", response_model=ApprovalDetail)
async def reject(approval_id: uuid.UUID, data: DecisionRequest, ctx: CanReview, db: DB):
    return await service.decide(
        db, ctx.organization_id, ctx.user.id, approval_id, ApprovalStatus.REJECTED, data.comment
    )


@router.post("/{approval_id}/finalize", response_model=ApprovalDetail)
async def finalize(approval_id: uuid.UUID, ctx: CanReview, db: DB):
    return await service.finalize(db, ctx.organization_id, ctx.user.id, approval_id)


@router.post("/{approval_id}/comments", response_model=ApprovalDetail)
async def add_comment(approval_id: uuid.UUID, data: CommentCreate, ctx: CanComment, db: DB):
    return await service.add_comment(db, ctx.organization_id, ctx.user.id, approval_id, data.body)
