import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.deps import DB, OrgContext, active_org_permission
from app.core.permissions import Permission
from app.models.enums import ApprovalStatus, Platform
from app.schemas.approval import (
    ApprovalDetail,
    ApprovalPage,
    ChangeRequestPage,
    ChangesRequest,
    CommentCreate,
    DecisionRequest,
)
from app.schemas.design import ChangeRequestRead
from app.services.approvals import change_requests, service

router = APIRouter(prefix="/approvals", tags=["approvals"])

CanRead = Annotated[OrgContext, Depends(active_org_permission(Permission.APPROVAL_READ))]
CanReview = Annotated[OrgContext, Depends(active_org_permission(Permission.APPROVAL_MANAGE))]


@router.get("", response_model=ApprovalPage)
async def list_approvals(
    ctx: CanRead,
    db: DB,
    status_filter: Annotated[
        Literal["pending", "reviewed", "approved", "changes_requested", "rejected", "all"],
        Query(alias="status"),
    ] = "pending",
    platform: Platform | None = None,
    stage: Literal["copy", "design"] | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await service.list_approvals(
        db,
        ctx.organization_id,
        status=status_filter,
        platform=platform.value if platform else None,
        stage=stage,
        limit=limit,
        offset=offset,
    )


@router.get("/change-requests", response_model=ChangeRequestPage)
async def list_change_requests(
    ctx: CanReview,
    db: DB,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await change_requests.list_pending(db, ctx.organization_id, limit=limit, offset=offset)


@router.post("/change-requests/{request_id}/accept", response_model=ChangeRequestRead)
async def accept_change_request(request_id: uuid.UUID, ctx: CanReview, db: DB):
    return await change_requests.accept(db, ctx.organization_id, ctx.user.id, request_id)


@router.post("/change-requests/{request_id}/decline", response_model=ChangeRequestRead)
async def decline_change_request(
    request_id: uuid.UUID, data: DecisionRequest, ctx: CanReview, db: DB
):
    return await change_requests.decline(
        db, ctx.organization_id, ctx.user.id, request_id, data.comment
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


@router.post("/{approval_id}/reopen", response_model=ApprovalDetail)
async def reopen(approval_id: uuid.UUID, data: ChangesRequest, ctx: CanReview, db: DB):
    """Request changes to already-approved work (approved work is locked)."""
    return await service.reopen(
        db, ctx.organization_id, ctx.user.id, approval_id, data.comment, data.scope
    )


@router.post("/{approval_id}/comments", response_model=ApprovalDetail)
async def add_comment(approval_id: uuid.UUID, data: CommentCreate, ctx: CanReview, db: DB):
    return await service.add_comment(db, ctx.organization_id, ctx.user.id, approval_id, data.body)
