#!/usr/bin/env bash
# PostToolUse hook: run ruff format + check --fix on every .py edit.
# Exit 0 + announce if ruff made changes; exit 2 if residual findings remain.

PAYLOAD=$(cat)
FILE=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); print(d.get('tool_input',{}).get('file_path',''))" "$PAYLOAD" 2>/dev/null)

[[ -z "$FILE" || "$FILE" != *.py || ! -f "$FILE" ]] && exit 0

FORMAT_OUT=$(uv run ruff format "$FILE" 2>&1)

LINT_OUT=$(uv run ruff check --fix "$FILE" 2>&1)
LINT_EXIT=$?

if [[ $LINT_EXIT -ne 0 ]]; then
    printf 'ruff: non-auto-fixable issues in %s — fix before proceeding:\n%s\n' "$FILE" "$LINT_OUT"
    exit 2
fi

CHANGED=false
echo "$FORMAT_OUT" | grep -q "reformatted" && CHANGED=true
echo "$LINT_OUT" | grep -qi "fixed" && CHANGED=true

if [[ "$CHANGED" == "true" ]]; then
    printf 'ruff auto-fixed %s — re-read the file before further edits.\n' "$FILE"
fi
