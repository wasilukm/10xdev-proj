import asyncio
import re
import sys

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)
from pydantic import ValidationError

from code_reviewer.models import ReviewRequest, ReviewResult

_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)

_PROMPT_TEMPLATE = (
    "Review the code at '{target}'. Give a short, high-level assessment of "
    "code quality and flag any obvious issues. This is read-only — do not "
    "edit anything.\n\n"
    "End your reply with a fenced ```json code block containing ONLY an "
    'object matching this schema: {{"summary": str, "issues": [str, ...]}}.'
)


async def review(request: ReviewRequest) -> ReviewResult:
    options = ClaudeAgentOptions(
        allowed_tools=["Read", "Grep", "Glob"],
        permission_mode="bypassPermissions",
    )
    prompt = _PROMPT_TEMPLATE.format(target=request.target)

    final_text = ""
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text)
                    final_text = block.text
                elif isinstance(block, ToolUseBlock):
                    print(f"[tool] {block.name}")
        elif isinstance(message, ResultMessage):
            print(f"[done] {message.subtype}")

    match = _JSON_BLOCK.search(final_text)
    if not match:
        raise ValueError("agent response did not contain a fenced JSON block")
    return ReviewResult.model_validate_json(match.group(1))


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    try:
        request = ReviewRequest(target=target)
    except ValidationError as exc:
        print(f"Invalid input:\n{exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    result = asyncio.run(review(request))
    print("\n--- validated result ---")
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
