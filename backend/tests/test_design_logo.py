"""The organization's real logo on AI-generated images, at the chosen position."""

import io

import pytest
from PIL import Image

from app.core.config import Settings
from app.services.design import logo as logo_module
from app.services.design.logo import (
    POSITIONS,
    LogoError,
    effective_position,
    fetch_logo,
    place_logo,
)
from app.workers.runner import runner
from tests.conftest import add_member
from tests.test_alignment import internet, setup_org  # noqa: F401  (fixtures)
from tests.test_design import API, FakeImages, design_ai, in_design  # noqa: F401

RED, WHITE = (220, 20, 20, 255), (255, 255, 255, 255)


def png(size: tuple[int, int], color: tuple[int, int, int, int]) -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", size, color).save(out, format="PNG")
    return out.getvalue()


def red_box(image_bytes: bytes) -> tuple[int, int, int, int]:
    """Bounding box of the (red) logo on a white image."""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    mask = Image.eval(image.split()[1], lambda g: 255 if g < 128 else 0)  # red = low green
    box = mask.getbbox()
    assert box, "no logo found"
    return box


# --- Placement -----------------------------------------------------------------------


@pytest.mark.parametrize("position", POSITIONS)
def test_logo_lands_in_each_position(position):
    base = png((1000, 500), WHITE)
    placed = place_logo(base, png((400, 200), RED), position)
    assert placed.mime_type == "image/png"
    left, top, right, bottom = red_box(placed.data)
    width, height = right - left, bottom - top
    # Scaled into the box (18% wide, 12% tall), proportions kept.
    assert width <= 180 and height <= 60 and abs(width / height - 2) < 0.05
    margin = 20  # 4% of the short side
    vertical, horizontal = position.split("_")
    assert (top == margin) if vertical == "top" else (bottom == 500 - margin)
    if horizontal == "left":
        assert left == margin
    elif horizontal == "right":
        assert right == 1000 - margin
    else:
        assert abs((left + right) / 2 - 500) <= 1


def test_small_logo_is_not_upscaled_and_transparency_shows_through():
    logo = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    logo.paste(RED, (10, 10, 30, 30))  # a red square inside a transparent frame
    out = io.BytesIO()
    logo.save(out, format="PNG")
    placed = place_logo(png((1000, 1000), WHITE), out.getvalue(), "top_left")
    left, top, right, bottom = red_box(placed.data)
    assert (right - left, bottom - top) == (20, 20)  # same size: never enlarged
    image = Image.open(io.BytesIO(placed.data)).convert("RGBA")
    assert image.getpixel((40 + 2, 40 + 2)) == WHITE  # transparent edge stays white


def test_unusable_logos_and_images_raise_a_readable_error():
    with pytest.raises(LogoError, match="PNG, JPG or WebP"):
        place_logo(png((100, 100), WHITE), b"<svg></svg>", "top_left")
    with pytest.raises(LogoError, match="generated image"):
        place_logo(b"not an image", png((10, 10), RED), "top_left")


async def test_logo_links_to_private_addresses_are_refused():
    settings = Settings(_env_file=None, crawler_allow_private_networks=False)
    with pytest.raises(LogoError, match="couldn't be opened"):
        await fetch_logo("http://127.0.0.1/logo.png", settings)


def test_effective_position():
    assert effective_position({}, "top_left") == "top_left"
    assert effective_position({"logo_position": "bottom_center"}, "top_left") == "bottom_center"
    assert effective_position({}, None) == "bottom_right"
    assert effective_position({"logo_position": "none"}, "top_left") is None
    assert effective_position({}, "none") is None


# --- End to end: brand default, post override, failures --------------------------------


class SizedImages(FakeImages):
    """A real 800x800 white image, so the logo can be found on it."""

    async def generate(self, prompt: str, ratio: str):
        from app.ai.images import GeneratedImage

        self.prompts.append((prompt, ratio))
        return GeneratedImage(
            data=png((800, 800), WHITE), mime_type="image/png", provider=self.name, model=self.model
        )


@pytest.fixture
def sized_images():
    from app.ai.images import set_image_provider

    images = SizedImages()
    set_image_provider(images)
    yield images
    set_image_provider(None)


@pytest.fixture
def logo_link(monkeypatch):
    fetched: list[str] = []

    async def fake_fetch(url, settings, resolver=None):
        fetched.append(url)
        return png((300, 100), RED)

    monkeypatch.setattr(logo_module, "fetch_logo", fake_fetch)
    return fetched


async def _org_with_logo(client, position: str | None = "top_left"):
    admin, org = await setup_org(client)
    profile = await admin.patch(
        f"/api/v1/organizations/{org['id']}", json={"logo_url": "https://acme.example.com/logo.png"}
    )
    assert profile.status_code == 200, profile.text
    if position:
        brand = await admin.patch(
            f"/api/v1/organizations/{org['id']}/brand", json={"logo_position": position}
        )
        assert brand.status_code == 200, brand.text
        assert brand.json()["logo_position"] == position
    return admin, org


async def _generate(admin, task_id: str) -> dict:
    url = f"{API}/{task_id}"
    assert (await admin.post(f"{url}/generate-image")).status_code == 202
    await runner.wait_idle()
    return (await admin.get(url)).json()


async def test_brand_logo_is_placed_where_the_admin_chose(
    client, internet, design_ai, sized_images, logo_link
):
    admin, org = await _org_with_logo(client, "top_left")
    _, task = await in_design(admin, org)
    assert task["brand"]["logo_url"] == "https://acme.example.com/logo.png"
    assert task["brand"]["logo_position"] == "top_left"

    task = await _generate(admin, task["id"])
    assert task["image_job"]["status"] == "succeeded"
    [version] = task["creatives"]
    assert version["note"] == "Generated with AI · your logo in the top-left corner"
    stored = (await client.get(version["files"][0]["url"])).content
    left, top, _, _ = red_box(stored)
    assert (left, top) == (32, 32)  # 4% margin of 800
    assert logo_link == ["https://acme.example.com/logo.png"]  # the real logo, as is
    prompt, _ = sized_images.prompts[0]
    assert "Don't draw any logo" in prompt and "Keep the top-left corner plain" in prompt


async def test_creator_moves_the_logo_for_one_post_or_turns_it_off(
    client, internet, design_ai, sized_images, logo_link
):
    admin, org = await _org_with_logo(client, "top_left")
    _, task = await in_design(admin, org)
    url = f"{API}/{task['id']}"
    creator = await add_member(client, admin, org["id"], "cleo@acme.example.com", "creator")

    moved = await creator.patch(url, json={"logo_position": "bottom_center"})
    assert moved.status_code == 200, moved.text
    assert moved.json()["brand_requirements"]["logo_position"] == "bottom_center"
    assert moved.json()["brand"]["logo_position"] == "top_left"  # brand default untouched

    task = await _generate(admin, task["id"])
    assert task["creatives"][0]["note"].endswith("your logo in the bottom centre")
    _, _, _, bottom = red_box((await client.get(task["creatives"][0]["files"][0]["url"])).content)
    assert bottom == 800 - 32
    assert "Keep the bottom centre plain" in sized_images.prompts[-1][0]

    off = await creator.patch(url, json={"logo_position": "none"})
    assert off.json()["brand_requirements"]["logo_position"] == "none"
    task = await _generate(admin, task["id"])
    assert task["creatives"][0]["note"] == "Generated with AI"
    assert "Keep the" not in sized_images.prompts[-1][0]

    back = await creator.patch(url, json={"logo_position": None})
    assert "logo_position" not in back.json()["brand_requirements"]
    assert (await creator.patch(url, json={"logo_position": "middle"})).status_code == 422
    viewer = await add_member(client, admin, org["id"], "vic@acme.example.com", "viewer")
    assert (await viewer.patch(url, json={"logo_position": "top_right"})).status_code == 403


async def test_a_broken_logo_link_never_costs_the_image(
    client, internet, design_ai, sized_images, monkeypatch
):
    async def broken(url, settings, resolver=None):
        raise LogoError("the logo link answered HTTP 404")

    monkeypatch.setattr(logo_module, "fetch_logo", broken)
    admin, org = await _org_with_logo(client, "top_right")
    _, task = await in_design(admin, org)
    task = await _generate(admin, task["id"])
    assert task["image_job"]["status"] == "succeeded"
    assert task["creatives"][0]["note"] == (
        "Generated with AI · logo not added: the logo link answered HTTP 404"
    )


async def test_without_a_logo_url_nothing_is_fetched(
    client, internet, design_ai, sized_images, logo_link
):
    admin, org = await setup_org(client)
    _, task = await in_design(admin, org)
    assert task["brand"]["logo_url"] is None
    task = await _generate(admin, task["id"])
    assert task["creatives"][0]["note"] == "Generated with AI" and logo_link == []


# --- Uploaded logo file (preferred over Logo URL) ----------------------------------


async def _put_logo(actor, org_id: str, data: bytes, content_type: str = "image/png"):
    return await actor.request(
        "PUT",
        f"/api/v1/organizations/{org_id}/logo",
        content=data,
        headers={"Content-Type": content_type},
    )


async def test_upload_view_replace_and_remove_the_logo(client, internet):
    from app.storage import get_storage

    admin, org = await setup_org(client)
    base = f"/api/v1/organizations/{org['id']}"
    first = png((300, 100), RED)

    resp = await _put_logo(admin, org["id"], first)
    assert resp.status_code == 200, resp.text
    assert resp.json()["has_logo_file"] is True

    # Any member sees it, through a fresh signed link.
    viewer = await add_member(client, admin, org["id"], "vi@acme.example.com", "viewer")
    seen = await viewer.get(f"{base}/logo")
    assert seen.status_code == 307
    assert (await client.get(seen.headers["location"])).content == first
    assert (await _put_logo(viewer, org["id"], first)).status_code == 403

    # Replacing it removes the old file.
    from app.models.organization import Organization

    async def stored_key() -> str | None:
        from app.db.session import SessionLocal

        async with SessionLocal() as db:
            return (await db.get(Organization, org["id"])).logo_storage_key

    old_key = await stored_key()
    assert (await _put_logo(admin, org["id"], png((50, 50), WHITE))).status_code == 200
    new_key = await stored_key()
    assert new_key != old_key and new_key.endswith(".png")
    assert await get_storage().get(old_key) is None

    removed = await admin.delete(f"{base}/logo")
    assert removed.json()["has_logo_file"] is False
    assert await get_storage().get(new_key) is None
    assert (await admin.get(f"{base}/logo")).status_code == 404


async def test_only_real_small_images_are_accepted(client, internet):
    admin, org = await setup_org(client)
    not_image = await _put_logo(admin, org["id"], b"<svg xmlns='http://www.w3.org/2000/svg'/>")
    assert (
        not_image.status_code == 400 and "PNG, JPG or WebP" in not_image.json()["error"]["message"]
    )
    empty = await _put_logo(admin, org["id"], b"")
    assert empty.status_code == 400
    huge = await _put_logo(admin, org["id"], b"\x89PNG" + b"0" * 2_100_000)
    assert huge.status_code == 400 and "2 MB" in huge.json()["error"]["message"]


async def test_uploaded_logo_wins_over_the_logo_url(
    client, internet, design_ai, sized_images, logo_link
):
    admin, org = await _org_with_logo(client, "top_right")  # also has a Logo URL
    assert (await _put_logo(admin, org["id"], png((300, 100), RED))).status_code == 200
    _, task = await in_design(admin, org)
    # The page gets a signed link to the uploaded file (works in any <img>).
    assert (await client.get(task["brand"]["logo_url"])).status_code == 200
    link = (await admin.get(f"/api/v1/organizations/{org['id']}/logo/link")).json()["url"]
    assert (await client.get(link)).status_code == 200

    task = await _generate(admin, task["id"])
    assert task["creatives"][0]["note"].endswith("your logo in the top-right corner")
    assert logo_link == []  # the URL was never fetched
    _, top, right, _ = red_box((await client.get(task["creatives"][0]["files"][0]["url"])).content)
    assert (top, right) == (32, 800 - 32)
