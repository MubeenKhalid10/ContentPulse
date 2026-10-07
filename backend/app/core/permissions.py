"""Role-based access control (spec §6).

Permissions are plain strings so they can be checked anywhere and returned
to the frontend (which uses them only to hide controls — the backend is the
source of truth).
"""

from enum import StrEnum


class Role(StrEnum):
    # Everything, including approving posts and managing the team.
    ADMIN = "admin"
    # Finds topics, writes posts, adds the design and submits for approval.
    CREATOR = "creator"
    # Reads everything and shares finished posts.
    VIEWER = "viewer"


class Permission(StrEnum):
    ORGANIZATION_READ = "organization.read"
    ORGANIZATION_WRITE = "organization.write"
    KNOWLEDGE_READ = "knowledge.read"
    KNOWLEDGE_WRITE = "knowledge.write"
    TRENDS_READ = "trends.read"
    TRENDS_MANAGE = "trends.manage"
    TOPICS_READ = "topics.read"
    TOPICS_MANAGE = "topics.manage"
    CONTENT_READ = "content.read"
    CONTENT_GENERATE = "content.generate"
    CONTENT_EDIT = "content.edit"
    DESIGN_READ = "design.read"
    DESIGN_MANAGE = "design.manage"
    DESIGN_UPLOAD = "design.upload"
    DESIGN_SUBMIT = "design.submit"
    APPROVAL_READ = "approval.read"
    APPROVAL_MANAGE = "approval.manage"
    USERS_MANAGE = "users.manage"


P = Permission

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(
        {
            P.ORGANIZATION_READ,
            P.ORGANIZATION_WRITE,
            P.KNOWLEDGE_READ,
            P.KNOWLEDGE_WRITE,
            P.TRENDS_READ,
            P.TRENDS_MANAGE,
            P.TOPICS_READ,
            P.TOPICS_MANAGE,
            P.CONTENT_READ,
            P.CONTENT_GENERATE,
            P.CONTENT_EDIT,
            P.DESIGN_READ,
            P.DESIGN_MANAGE,
            P.DESIGN_UPLOAD,
            P.DESIGN_SUBMIT,
            P.APPROVAL_READ,
            P.APPROVAL_MANAGE,
            P.USERS_MANAGE,
        }
    ),
    Role.CREATOR: frozenset(
        {
            P.ORGANIZATION_READ,
            P.KNOWLEDGE_READ,
            P.TRENDS_READ,
            P.TOPICS_READ,
            P.TOPICS_MANAGE,
            P.CONTENT_READ,
            P.CONTENT_GENERATE,
            P.CONTENT_EDIT,
            P.DESIGN_READ,
            P.DESIGN_UPLOAD,
            P.DESIGN_SUBMIT,
            P.APPROVAL_READ,
        }
    ),
    Role.VIEWER: frozenset(p for p in Permission if p.value.endswith(".read")),
}


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]


def permissions_for(role: Role) -> list[str]:
    return sorted(p.value for p in ROLE_PERMISSIONS[role])
