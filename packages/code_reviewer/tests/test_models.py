import pytest
from code_reviewer.models import CriterionScore, ReviewRequest, ReviewResult
from pydantic import ValidationError

_CRITERIA = (
    "implementation_correctness",
    "idiomaticity",
    "complexity",
    "test_coverage",
    "security_and_safety",
    "review_integrity",
)


def _valid_scores() -> dict[str, CriterionScore]:
    return {name: CriterionScore(score=8, rationale="ok") for name in _CRITERIA}


def test_score_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        CriterionScore(score=0, rationale="x")


def test_score_eleven_rejected() -> None:
    with pytest.raises(ValidationError):
        CriterionScore(score=11, rationale="x")


def test_review_result_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        ReviewResult.model_validate(
            {**_valid_scores(), "summary": "ok", "extra_field": "nope"}
        )


def test_review_request_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        ReviewRequest.model_validate(
            {"title": "t", "description": "d", "diff": "x", "extra_field": "nope"}
        )


def test_overlong_diff_rejected() -> None:
    with pytest.raises(ValidationError):
        ReviewRequest(title="t", description="d", diff="x" * 200_001)


def test_review_result_schema_has_defs_and_no_schema_key() -> None:
    schema = ReviewResult.model_json_schema()
    assert "$defs" in schema
    assert "$schema" not in schema
    assert "CriterionScore" in schema["$defs"]
