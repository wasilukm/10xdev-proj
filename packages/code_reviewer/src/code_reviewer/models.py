from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(max_length=500)
    description: str = Field(max_length=20_000)
    diff: str = Field(max_length=200_000)


class CriterionScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=1, le=10)
    rationale: str = Field(max_length=2_000)


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    implementation_correctness: CriterionScore
    idiomaticity: CriterionScore
    complexity: CriterionScore
    test_coverage: CriterionScore
    security_and_safety: CriterionScore
    review_integrity: CriterionScore
    summary: str = Field(max_length=4_000)


class Verdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIPPED = "skipped"
