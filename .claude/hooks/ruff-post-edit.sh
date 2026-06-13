#!/usr/bin/env bash
# PostToolUse hook: run ruff format + check --fix on every .py edit.
# All feedback to the agent uses ONE mechanism — a JSON object on stdout (exit 0).
#   - non-blocking note:  hookSpecificOutput.additionalContext
#   - blocking finding:    decision:block + reason
# (The exit-2/stderr path can only block, not inform, so JSON is the single form
# that covers both cases.)

PAYLOAD=$(cat)
FILE=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('tool_input',{}).get('file_path',''))" "$PAYLOAD" 2>/dev/null)

[[ -z "$FILE" || "$FILE" != *.py || ! -f "$FILE" ]] && exit 0

# Emit a PostToolUse result as JSON. Usage: emit block|context "message"
emit() {
    python3 - "$1" "$2" <<'PY'
import json, sys
mode, msg = sys.argv[1], sys.argv[2]
if mode == "block":
    out = {"decision": "block", "reason": msg}
else:
    out = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}}
print(json.dumps(out))
PY
}

FORMAT_OUT=$(uv run ruff format "$FILE" 2>&1)

LINT_OUT=$(uv run ruff check --fix "$FILE" 2>&1)
LINT_EXIT=$?

if [[ $LINT_EXIT -ne 0 ]]; then
    emit block "$(printf 'ruff: non-auto-fixable issues in %s — fix before proceeding:\n%s' "$FILE" "$LINT_OUT")"
    exit 0
fi

CHANGED=false
echo "$FORMAT_OUT" | grep -q "reformatted" && CHANGED=true
echo "$LINT_OUT" | grep -qi "fixed" && CHANGED=true

if [[ "$CHANGED" == "true" ]]; then
    emit context "ruff auto-fixed ${FILE} — re-read the file before further edits."
fi
