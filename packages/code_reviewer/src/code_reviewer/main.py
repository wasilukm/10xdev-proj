import argparse
import asyncio
import os
import sys
from pathlib import Path

from pydantic import ValidationError

from code_reviewer.agent import AgentConfig, ReviewerError, review
from code_reviewer.models import ReviewRequest, Verdict
from code_reviewer.render import CommentMeta, render_comment
from code_reviewer.verdict import compute

_EXIT_CODES = {
    Verdict.PASS: 0,
    Verdict.FAIL: 1,
    Verdict.ERROR: 2,
    Verdict.SKIPPED: 3,
}


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="code-reviewer")
    parser.add_argument(
        "diff_path", type=Path, help="path to a file containing the PR diff"
    )
    parser.add_argument("--comment-path", type=Path, required=True)
    parser.add_argument("--result-json-path", type=Path, required=True)
    parser.add_argument("--max-diff-bytes", type=int, default=200_000)
    parser.add_argument("--model", default="claude-sonnet-5")
    parser.add_argument("--max-turns", type=int, default=5)
    parser.add_argument("--max-budget-usd", type=float, default=0.50)
    return parser.parse_args(argv)


def _write_github_output(verdict: Verdict) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a") as fh:
        fh.write(f"verdict={verdict.value}\n")


def _finish(
    verdict: Verdict, comment: str, result_json: str, args: argparse.Namespace
) -> int:
    args.comment_path.write_text(comment)
    args.result_json_path.write_text(result_json)
    _write_github_output(verdict)
    print(f"verdict={verdict.value}", file=sys.stderr)
    return _EXIT_CODES[verdict]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    diff_bytes = args.diff_path.read_bytes()
    if len(diff_bytes) > args.max_diff_bytes:
        reason = (
            f"diff is {len(diff_bytes)} bytes, exceeding the "
            f"{args.max_diff_bytes}-byte limit"
        )
        print(reason, file=sys.stderr)
        comment = render_comment(None, Verdict.SKIPPED, CommentMeta(reason=reason))
        return _finish(Verdict.SKIPPED, comment, "{}", args)

    title = os.environ.get("PR_TITLE", "")
    body = os.environ.get("PR_BODY", "")

    try:
        request = ReviewRequest(
            title=title,
            description=body,
            diff=diff_bytes.decode("utf-8", errors="replace"),
        )
    except ValidationError as exc:
        reason = f"invalid review input: {exc}"
        print(reason, file=sys.stderr)
        comment = render_comment(None, Verdict.ERROR, CommentMeta(reason=reason))
        return _finish(Verdict.ERROR, comment, "{}", args)

    config = AgentConfig(
        model=args.model, max_turns=args.max_turns, max_budget_usd=args.max_budget_usd
    )

    try:
        result = asyncio.run(review(request, config))
    except ReviewerError as exc:
        reason = f"{type(exc).__name__}: {exc}"
        print(reason, file=sys.stderr)
        comment = render_comment(None, Verdict.ERROR, CommentMeta(reason=reason))
        return _finish(Verdict.ERROR, comment, "{}", args)

    verdict = compute(result)
    comment = render_comment(result, verdict)
    return _finish(verdict, comment, result.model_dump_json(indent=2), args)


if __name__ == "__main__":
    sys.exit(main())
