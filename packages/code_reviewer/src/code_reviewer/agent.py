import tempfile
from dataclasses import dataclass

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from pydantic import ValidationError

from code_reviewer.models import ReviewRequest, ReviewResult
from code_reviewer.prompt import SYSTEM_PROMPT, build_user_turn

# Defense-in-depth alongside tools=[]: removes each tool from the model's
# context entirely, so a future edit that reintroduces `tools` still has no
# built-in tool available.
_DISALLOWED_TOOLS = [
    "Task",
    "Bash",
    "BashOutput",
    "KillShell",
    "Glob",
    "Grep",
    "Read",
    "Edit",
    "Write",
    "NotebookEdit",
    "WebFetch",
    "WebSearch",
    "TodoWrite",
    "ExitPlanMode",
    "SlashCommand",
]


class ReviewerError(Exception):
    """Base class for reviewer failures. All subclasses fail closed."""


class NoResultMessageError(ReviewerError):
    """The query stream ended without ever yielding a ResultMessage."""


class MissingStructuredOutputError(ReviewerError):
    """The ResultMessage reported success but carried no structured_output."""


class InvalidStructuredOutputError(ReviewerError):
    """structured_output did not validate against ReviewResult."""


class TransportError(ReviewerError):
    """The SDK raised while streaming the query (API error, auth failure, etc.)."""


@dataclass
class AgentConfig:
    model: str
    max_turns: int
    max_budget_usd: float


async def review(request: ReviewRequest, config: AgentConfig) -> ReviewResult:
    with tempfile.TemporaryDirectory() as tmp_dir:
        options = ClaudeAgentOptions(
            tools=[],
            disallowed_tools=list(_DISALLOWED_TOOLS),
            permission_mode="dontAsk",
            setting_sources=[],
            strict_mcp_config=True,
            system_prompt=SYSTEM_PROMPT,
            output_format={
                "type": "json_schema",
                "schema": ReviewResult.model_json_schema(),
            },
            max_turns=config.max_turns,
            max_budget_usd=config.max_budget_usd,
            model=config.model,
            cwd=tmp_dir,
            add_dirs=[],
            env={"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"},
        )

        result_message: ResultMessage | None = None
        try:
            async for message in query(
                prompt=build_user_turn(request), options=options
            ):
                if isinstance(message, ResultMessage):
                    result_message = message
        except Exception as exc:
            raise TransportError(str(exc)) from exc

    if result_message is None:
        raise NoResultMessageError("query stream ended without a ResultMessage")
    if result_message.structured_output is None:
        raise MissingStructuredOutputError(
            f"ResultMessage.structured_output is absent "
            f"(subtype={result_message.subtype!r})"
        )

    try:
        return ReviewResult.model_validate(result_message.structured_output)
    except ValidationError as exc:
        raise InvalidStructuredOutputError(str(exc)) from exc
