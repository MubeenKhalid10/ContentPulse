import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import DB, OrgContext, active_org_permission
from app.core.permissions import Permission
from app.core.ratelimit import AI_PER_USER, per_user
from app.models.enums import Platform, StrategyStatus, TopicStatus
from app.schemas.topic import (
    PlatformRuleRead,
    PlatformRuleUpdate,
    StrategyCreate,
    StrategyRead,
    StrategySuggestion,
    StrategyUpdate,
    SuggestRequest,
    TopicDetail,
    TopicPage,
    TopicUpdate,
)
from app.services.topics import platforms, service, strategies

AI_LIMIT = per_user(AI_PER_USER)
router = APIRouter(prefix="/topics", tags=["topics"])
rules_router = APIRouter(prefix="/platform-rules", tags=["topics"])

CanRead = Annotated[OrgContext, Depends(active_org_permission(Permission.TOPICS_READ))]
CanManage = Annotated[OrgContext, Depends(active_org_permission(Permission.TOPICS_MANAGE))]
CanReadOrg = Annotated[OrgContext, Depends(active_org_permission(Permission.ORGANIZATION_READ))]
CanWriteOrg = Annotated[OrgContext, Depends(active_org_permission(Permission.ORGANIZATION_WRITE))]


@router.get("", response_model=TopicPage)
async def list_topics(
    ctx: CanRead,
    db: DB,
    status_filter: Annotated[
        Literal["open", "new", "reviewed", "shortlisted", "rejected", "archived", "all"],
        Query(alias="status"),
    ] = "open",
    relevance: Literal["relevant", "highly_relevant", "weakly_relevant", "not_relevant"]
    | None = None,
    platform: Platform | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    sort: Literal["score", "recent", "relevance"] = "score",
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await service.list_topics(
        db,
        ctx.organization_id,
        status=status_filter,
        relevance=relevance,
        platform=platform.value if platform else None,
        q=q,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("/{topic_id}", response_model=TopicDetail)
async def get_topic(topic_id: uuid.UUID, ctx: CanRead, db: DB):
    return await service.topic_detail(db, ctx.organization_id, topic_id)


@router.patch("/{topic_id}", response_model=TopicDetail)
async def update_topic(topic_id: uuid.UUID, data: TopicUpdate, ctx: CanManage, db: DB):
    return await service.update_topic(
        db, ctx.organization_id, ctx.user.id, topic_id, data.changes()
    )


@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_topic(topic_id: uuid.UUID, ctx: CanManage, db: DB) -> None:
    await service.delete_topic(db, ctx.organization_id, ctx.user.id, topic_id)


def _transition(target: TopicStatus):
    async def endpoint(topic_id: uuid.UUID, ctx: CanManage, db: DB) -> TopicDetail:
        return await service.transition(db, ctx.organization_id, ctx.user.id, topic_id, target)

    return endpoint


for _path, _target in (
    ("shortlist", TopicStatus.SHORTLISTED),
    ("reject", TopicStatus.REJECTED),
    ("review", TopicStatus.REVIEWED),
    ("restore", TopicStatus.REVIEWED),
    ("archive", TopicStatus.ARCHIVED),
):
    router.add_api_route(
        f"/{{topic_id}}/{_path}",
        _transition(_target),
        methods=["POST"],
        response_model=TopicDetail,
        name=f"topic_{_path}",
    )


# --- Strategies (spec §21, §39) -------------------------------------------------


@router.get("/{topic_id}/strategies", response_model=list[StrategyRead])
async def list_strategies(topic_id: uuid.UUID, ctx: CanRead, db: DB):
    await service.get_topic(db, ctx.organization_id, topic_id)
    return await service.list_strategies(db, ctx.organization_id, topic_id)


@router.post(
    "/{topic_id}/strategies", response_model=StrategyRead, status_code=status.HTTP_201_CREATED
)
async def create_strategy(topic_id: uuid.UUID, data: StrategyCreate, ctx: CanManage, db: DB):
    return await strategies.create_strategy(
        db, ctx.organization_id, ctx.user.id, topic_id, data.model_dump()
    )


@router.post(
    "/{topic_id}/strategies/suggest", response_model=StrategySuggestion, dependencies=[AI_LIMIT]
)
async def suggest_strategy(topic_id: uuid.UUID, data: SuggestRequest, ctx: CanManage, db: DB):
    return await strategies.suggest_strategy(db, ctx.organization_id, topic_id, data.platform)


@router.patch("/{topic_id}/strategies/{strategy_id}", response_model=StrategyRead)
async def update_strategy(
    topic_id: uuid.UUID, strategy_id: uuid.UUID, data: StrategyUpdate, ctx: CanManage, db: DB
):
    return await strategies.update_strategy(
        db, ctx.organization_id, ctx.user.id, topic_id, strategy_id, data.changes()
    )


def _strategy_transition(target: StrategyStatus):
    async def endpoint(
        topic_id: uuid.UUID, strategy_id: uuid.UUID, ctx: CanManage, db: DB
    ) -> StrategyRead:
        return await strategies.transition_strategy(
            db, ctx.organization_id, ctx.user.id, topic_id, strategy_id, target
        )

    return endpoint


for _path, _target in (
    ("approve", StrategyStatus.APPROVED),
    ("reopen", StrategyStatus.DRAFT),
    ("archive", StrategyStatus.ARCHIVED),
):
    router.add_api_route(
        f"/{{topic_id}}/strategies/{{strategy_id}}/{_path}",
        _strategy_transition(_target),
        methods=["POST"],
        response_model=StrategyRead,
        name=f"strategy_{_path}",
    )


# --- Platform playbooks (spec §22) ----------------------------------------------


@rules_router.get("", response_model=list[PlatformRuleRead])
async def list_rules(ctx: CanReadOrg, db: DB):
    rules = await platforms.get_rules(db, ctx.organization_id)
    await db.commit()  # keep seeded defaults
    return list(rules.values())


@rules_router.patch("/{platform}", response_model=PlatformRuleRead)
async def update_rule(platform: Platform, data: PlatformRuleUpdate, ctx: CanWriteOrg, db: DB):
    return await platforms.update_rule(
        db, ctx.organization_id, ctx.user.id, platform, data.changes()
    )


@rules_router.post("/{platform}/reset", response_model=PlatformRuleRead)
async def reset_rule(platform: Platform, ctx: CanWriteOrg, db: DB):
    return await platforms.reset_rule(db, ctx.organization_id, ctx.user.id, platform)
