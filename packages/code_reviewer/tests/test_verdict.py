from code_reviewer.models import CriterionScore, ReviewResult, Verdict
from code_reviewer.verdict import DEFAULT_FLOORS, compute

_DEFAULT_FLOOR_CRITERIA = (
    "implementation_correctness",
    "idiomaticity",
    "complexity",
    "test_coverage",
)
_ELEVATED_FLOOR_CRITERIA = ("security_and_safety", "review_integrity")


def _result(**overrides: int) -> ReviewResult:
    scores = {name: DEFAULT_FLOORS["_default"] for name in _DEFAULT_FLOOR_CRITERIA}
    scores.update({name: DEFAULT_FLOORS[name] for name in _ELEVATED_FLOOR_CRITERIA})
    scores.update(overrides)
    return ReviewResult(
        **{
            name: CriterionScore(score=score, rationale="ok")
            for name, score in scores.items()
        },
        summary="summary",
    )


def test_all_at_floor_passes() -> None:
    assert compute(_result()) is Verdict.PASS


def test_each_default_floor_criterion_one_below_fails() -> None:
    for name in _DEFAULT_FLOOR_CRITERIA:
        result = _result(**{name: DEFAULT_FLOORS["_default"] - 1})
        assert compute(result) is Verdict.FAIL, name


def test_each_elevated_floor_criterion_one_below_fails() -> None:
    for name in _ELEVATED_FLOOR_CRITERIA:
        result = _result(**{name: DEFAULT_FLOORS[name] - 1})
        assert compute(result) is Verdict.FAIL, name


def test_security_and_review_integrity_fail_at_default_floor_while_others_pass() -> (
    None
):
    assert (
        compute(_result(security_and_safety=DEFAULT_FLOORS["_default"])) is Verdict.FAIL
    )
    assert compute(_result(review_integrity=DEFAULT_FLOORS["_default"])) is Verdict.FAIL


def test_perfect_score_on_five_does_not_rescue_one_below_floor() -> None:
    result = _result(
        implementation_correctness=10,
        idiomaticity=10,
        complexity=10,
        test_coverage=10,
        security_and_safety=10,
        review_integrity=1,
    )
    assert compute(result) is Verdict.FAIL
