"""Prompt templates (spec §58, §59).

Prompts live in this directory as text files, never inline in Python. Each
has an explicit version; bump it whenever the text changes so every AI result
records exactly which prompt produced it (`prompt_templates` + the
`ai_generation_jobs.prompt_template_id` link).
"""

import uuid
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import PromptTemplate

PROMPT_DIR = Path(__file__).parent

# name -> version. Bump when the file changes.
VERSIONS = {
    "organization_alignment": 1,
    "content_strategy": 1,
    "linkedin_post": 1,
    "x_post": 1,
    "instagram_post": 1,
    "facebook_post": 1,
    "blog_strategy": 1,
    "blog_post": 1,
    "design_brief": 1,
}


@dataclass(frozen=True)
class Prompt:
    name: str
    version: int
    template: str

    def render(self, **values: str) -> str:
        text = self.template
        for key, value in values.items():
            text = text.replace("{" + key + "}", value)
        return text


@cache
def load(name: str) -> Prompt:
    template = (PROMPT_DIR / f"{name}.txt").read_text(encoding="utf-8").strip()
    return Prompt(name=name, version=VERSIONS[name], template=template)


async def register(db: AsyncSession, prompt: Prompt, model: str | None) -> uuid.UUID:
    """Record (name, version) in prompt_templates; return its id."""
    await db.execute(
        insert(PromptTemplate)
        .values(
            id=uuid.uuid4(),
            name=prompt.name,
            version=prompt.version,
            template=prompt.template,
            model=model,
            active=True,
        )
        .on_conflict_do_nothing(index_elements=["name", "version"])
    )
    template_id = await db.scalar(
        select(PromptTemplate.id).where(
            PromptTemplate.name == prompt.name, PromptTemplate.version == prompt.version
        )
    )
    assert template_id is not None
    return template_id
