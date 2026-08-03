import re
from dataclasses import dataclass

from code_reviewer.models import ReviewResult, Verdict
from code_reviewer.verdict import CRITERIA, failing_criteria

MARKER = "<!-- ai-code-review -->"

DISCLAIMER = (
    "This review was generated automatically by an AI agent and is advisory "
    "only. It does not represent human endorsement, and passing it grants no "
    "special status — a human should still read the diff."
)

_CRITERION_LABELS = {
    "implementation_correctness": "Implementation correctness",
    "idiomaticity": "Idiomaticity",
    "complexity": "Complexity",
    "test_coverage": "Test coverage",
    "security_and_safety": "Security and safety",
    "review_integrity": "Review integrity",
}

_RATIONALE_MAX = 500
_SUMMARY_MAX = 2000
_REASON_MAX = 1000

_HTML_TAG = re.compile(r"<[^>]*>")
_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MENTION = re.compile(r"@(?=\S)")
_BREAKS_TABLE = re.compile(r"\s*\n+\s*|\|")


def sanitize(text: str, *, max_length: int = _RATIONALE_MAX) -> str:
    text = _HTML_TAG.sub("", text)
    text = _MD_IMAGE.sub(r"\1", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _MENTION.sub("@​", text)
    text = _BREAKS_TABLE.sub(" ", text).strip()
    if len(text) > max_length:
        text = text[: max_length - 1].rstrip() + "…"
    return text


@dataclass
class CommentMeta:
    reason: str | None = None


def render_comment(
    result: ReviewResult | None, verdict: Verdict, meta: CommentMeta | None = None
) -> str:
    meta = meta or CommentMeta()

    if verdict in (Verdict.ERROR, Verdict.SKIPPED):
        return _render_incomplete(verdict, meta)

    if result is None:
        raise ValueError(f"render_comment: result is required for verdict={verdict!r}")
    return _render_reviewed(result, verdict)


def _render_incomplete(verdict: Verdict, meta: CommentMeta) -> str:
    lines = [MARKER, "", DISCLAIMER, ""]
    if verdict is Verdict.ERROR:
        lines.append("**The reviewer did not complete: it malfunctioned.**")
    else:
        lines.append(
            "**The reviewer did not complete: the diff was too large to review.**"
        )
    if meta.reason:
        lines.append("")
        lines.append(sanitize(meta.reason, max_length=_REASON_MAX))
    return "\n".join(lines) + "\n"


def _render_reviewed(result: ReviewResult, verdict: Verdict) -> str:
    lines = [MARKER, "", DISCLAIMER, ""]
    if verdict is Verdict.PASS:
        lines.append("**Verdict: `ai-cr:passed`**")
    else:
        names = ", ".join(_CRITERION_LABELS[name] for name in failing_criteria(result))
        lines.append(f"**Verdict: `ai-cr:failed`** — below floor on: {names}")
    lines.append("")
    lines.append("| Criterion | Score | Rationale |")
    lines.append("|---|---|---|")
    for name in CRITERIA:
        criterion = getattr(result, name)
        rationale = sanitize(criterion.rationale, max_length=_RATIONALE_MAX)
        lines.append(
            f"| {_CRITERION_LABELS[name]} | {criterion.score}/10 | {rationale} |"
        )
    lines.append("")
    lines.append(sanitize(result.summary, max_length=_SUMMARY_MAX))
    return "\n".join(lines) + "\n"
