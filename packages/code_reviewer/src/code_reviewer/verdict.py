from collections.abc import Mapping

from code_reviewer.models import ReviewResult, Verdict

DEFAULT_FLOORS: Mapping[str, int] = {
    "_default": 6,
    "security_and_safety": 7,
    "review_integrity": 7,
}

CRITERIA = (
    "implementation_correctness",
    "idiomaticity",
    "complexity",
    "test_coverage",
    "security_and_safety",
    "review_integrity",
)


def failing_criteria(
    result: ReviewResult, floors: Mapping[str, int] = DEFAULT_FLOORS
) -> list[str]:
    return [
        name
        for name in CRITERIA
        if getattr(result, name).score < floors.get(name, floors["_default"])
    ]


def compute(
    result: ReviewResult, floors: Mapping[str, int] = DEFAULT_FLOORS
) -> Verdict:
    return Verdict.FAIL if failing_criteria(result, floors) else Verdict.PASS
