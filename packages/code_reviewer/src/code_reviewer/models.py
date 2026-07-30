from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class ReviewRequest(BaseModel):
    target: Path

    @field_validator("target")
    @classmethod
    def target_must_exist(cls, value: Path) -> Path:
        if not value.exists():
            raise ValueError(f"target path does not exist: {value}")
        return value.resolve()


class ReviewResult(BaseModel):
    summary: str
    issues: list[str] = Field(default_factory=list)
