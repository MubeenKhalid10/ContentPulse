from app.core.permissions import Permission, Role, has_permission, permissions_for


def test_admin_has_every_permission():
    assert set(permissions_for(Role.ADMIN)) == {p.value for p in Permission}


def test_viewer_is_read_only():
    perms = permissions_for(Role.VIEWER)
    assert perms
    assert all(p.endswith(".read") for p in perms)


def test_there_are_three_roles():
    assert [r.value for r in Role] == ["admin", "creator", "viewer"]


def test_creator_finds_writes_designs_and_submits_but_never_approves():
    for allowed in (
        Permission.TOPICS_MANAGE,
        Permission.CONTENT_GENERATE,
        Permission.CONTENT_EDIT,
        Permission.DESIGN_UPLOAD,
        Permission.DESIGN_SUBMIT,
        Permission.APPROVAL_READ,
    ):
        assert has_permission(Role.CREATOR, allowed), allowed
    for denied in (
        Permission.APPROVAL_MANAGE,
        Permission.ORGANIZATION_WRITE,
        Permission.USERS_MANAGE,
        Permission.KNOWLEDGE_WRITE,
        Permission.DESIGN_MANAGE,
    ):
        assert not has_permission(Role.CREATOR, denied), denied
