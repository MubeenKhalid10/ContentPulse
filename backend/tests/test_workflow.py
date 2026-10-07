import pytest

from app.core.errors import InvalidStateTransition
from app.models.design import CreativeAsset
from app.models.enums import Platform, PostStatus, TopicStatus
from app.models.organization import Organization
from app.models.post import Post
from app.services.workflow import POST_MACHINE, TOPIC_MACHINE, transition_post

P = PostStatus

HAPPY_PATH = [
    P.DRAFT,
    P.DESIGN_PENDING,
    P.DESIGN_IN_PROGRESS,
    P.DESIGN_UPLOADED,
    P.PENDING_APPROVAL,
    P.APPROVED,
    P.FINAL,
]


def test_post_happy_path_is_valid():
    for current, target in zip(HAPPY_PATH, HAPPY_PATH[1:], strict=False):
        assert POST_MACHINE.can(current, target), f"{current} -> {target}"


def test_revision_loop_is_valid():
    assert POST_MACHINE.can(P.PENDING_APPROVAL, P.CHANGES_REQUESTED)
    assert POST_MACHINE.can(P.CHANGES_REQUESTED, P.DESIGN_UPLOADED)
    assert POST_MACHINE.can(P.DESIGN_UPLOADED, P.PENDING_APPROVAL)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (P.DRAFT, P.APPROVED),  # spec rule 5
        (P.DRAFT, P.PENDING_APPROVAL),
        (P.DESIGN_PENDING, P.APPROVED),
        (P.REJECTED, P.APPROVED),
        (P.FINAL, P.DRAFT),
        (P.ARCHIVED, P.DRAFT),
    ],
)
def test_invalid_post_transitions_raise(current, target):
    with pytest.raises(InvalidStateTransition) as exc:
        POST_MACHINE.assert_can(current, target)
    assert exc.value.code == "INVALID_STATE_TRANSITION"
    assert exc.value.status_code == 409
    assert exc.value.details["from"] == current.value
    assert exc.value.details["to"] == target.value


def test_every_status_has_an_entry():
    for status in PostStatus:
        POST_MACHINE.allowed(status)  # does not raise
    assert POST_MACHINE.allowed(P.ARCHIVED) == []


def test_topic_rejected_can_be_reconsidered():
    assert TOPIC_MACHINE.can(TopicStatus.REJECTED, TopicStatus.REVIEWED)
    assert not TOPIC_MACHINE.can(TopicStatus.ARCHIVED, TopicStatus.SHORTLISTED)


async def test_submission_requires_uploaded_creative(db):
    org = Organization(name="Org", slug="org")
    db.add(org)
    await db.flush()
    post = Post(organization_id=org.id, platform=Platform.LINKEDIN, status=P.DESIGN_IN_PROGRESS)
    db.add(post)
    await db.flush()

    with pytest.raises(InvalidStateTransition, match="creative"):
        await transition_post(db, post, P.DESIGN_UPLOADED, user_id=None)

    db.add(
        CreativeAsset(
            organization_id=org.id,
            post_id=post.id,
            file_name="slide-1.png",
            file_type="image/png",
            storage_key="org/post/slide-1.png",
            version=1,
        )
    )
    await db.flush()
    await transition_post(db, post, P.DESIGN_UPLOADED, user_id=None)
    await transition_post(db, post, P.PENDING_APPROVAL, user_id=None)
    assert post.status == P.PENDING_APPROVAL
    await db.commit()
