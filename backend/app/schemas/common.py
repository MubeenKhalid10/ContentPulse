from typing import Annotated, Any, ClassVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator,
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    model_validator,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PatchModel(BaseModel):
    """PATCH body: omitted fields are untouched; null clears nullable fields only."""

    non_nullable: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def _reject_null_for_required(self) -> "PatchModel":
        for field in self.non_nullable & self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"'{field}' cannot be null")
        return self

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


def _valid_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown timezone '{value}'") from exc
    return value


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=10_000)]
TagList = Annotated[list[Tag], Field(max_length=100)]
Timezone = Annotated[str, AfterValidator(_valid_timezone)]
_http_url = TypeAdapter(AnyHttpUrl)


def _valid_http_url(value: str) -> str:
    return str(_http_url.validate_python(value))


HttpUrlStr = Annotated[str, StringConstraints(max_length=2048), AfterValidator(_valid_http_url)]
