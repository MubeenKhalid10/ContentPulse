"""Blog-only fields. A blog version stores its SEO details in
`post_versions.metadata["blog"]`; social platforms never have them."""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"

Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class BlogMeta(BaseModel):
    """PATCH /content/{id} `blog`: only the fields sent are changed."""

    seo_title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = (
        None
    )
    meta_title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = (
        None
    )
    meta_description: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=400)] | None
    ) = None
    slug: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, max_length=120, pattern=SLUG_PATTERN)
        ]
        | None
    ) = None
    keywords: Annotated[list[Keyword], Field(max_length=15)] | None = None
