#!/usr/bin/env bash
# Unit tests for sticky-comment.sh, driven against a fake `gh` on PATH so no
# network or real GitHub state is needed. Run: .github/scripts/tests/test_sticky-comment.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sticky_comment="$script_dir/../sticky-comment.sh"

# The exact filter sticky-comment.sh passes to `gh api --jq`. Asserted verbatim
# below so a typo in the real script fails the test even when jq isn't
# available locally to execute it (GitHub-hosted ubuntu runners always have
# jq, so the real-execution checks run for real in CI).
readonly EXPECTED_JQ_FILTER='[.[] | select(.body | startswith("<!-- ai-code-review -->"))][0].id // empty'

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

pass_count=0
fail_count=0
skip_count=0

assert_equal() {
  local expected="$1" actual="$2" msg="$3"
  if [ "$expected" = "$actual" ]; then
    pass_count=$((pass_count + 1))
  else
    fail_count=$((fail_count + 1))
    echo "FAIL: $msg" >&2
    echo "  expected: $expected" >&2
    echo "  actual:   $actual" >&2
  fi
}

assert_contains() {
  local haystack="$1" needle="$2" msg="$3"
  if [[ "$haystack" == *"$needle"* ]]; then
    pass_count=$((pass_count + 1))
  else
    fail_count=$((fail_count + 1))
    echo "FAIL: $msg" >&2
    echo "  expected to contain: $needle" >&2
    echo "  actual: $haystack" >&2
  fi
}

assert_not_contains() {
  local haystack="$1" needle="$2" msg="$3"
  if [[ "$haystack" == *"$needle"* ]]; then
    fail_count=$((fail_count + 1))
    echo "FAIL: $msg" >&2
    echo "  expected NOT to contain: $needle" >&2
    echo "  actual: $haystack" >&2
  else
    pass_count=$((pass_count + 1))
  fi
}

skip() {
  skip_count=$((skip_count + 1))
  echo "SKIP: $1" >&2
}

# Installs a fake `gh` on PATH that logs every invocation (args space-joined,
# one line per call) to $GH_CALL_LOG. The --paginate list call is answered by
# running the *real* jq filter the caller passed against $FAKE_COMMENTS_JSON
# when jq is on PATH (true on every GitHub-hosted runner) — so the actual
# marker-matching expression in sticky-comment.sh is exercised, not just its
# branch outcome. Falls back to a fixed answer when jq is unavailable
# (e.g. this sandbox), so the create/update branch tests still run everywhere.
install_fake_gh() {
  local bin_dir="$1"
  cat >"$bin_dir/gh" <<'FAKE_GH'
#!/usr/bin/env bash
echo "$*" >> "$GH_CALL_LOG"
if [ "$1" = "api" ] && [ "$2" = "--paginate" ]; then
  filter=""
  prev=""
  for arg in "$@"; do
    if [ "$prev" = "--jq" ]; then
      filter="$arg"
    fi
    prev="$arg"
  done
  if command -v jq >/dev/null 2>&1 && [ -n "$filter" ]; then
    printf '%s' "$FAKE_COMMENTS_JSON" | jq -r "$filter"
  else
    printf '%s' "$FAKE_LIST_OUTPUT"
  fi
  exit 0
fi
exit 0
FAKE_GH
  chmod +x "$bin_dir/gh"
}

have_jq() { command -v jq >/dev/null 2>&1; }

# --- Test 1: no existing marker comment -> creates (POST), real filter run when jq is present ---
test_creates_when_no_existing_comment() {
  local case_dir="$work_dir/case1"
  mkdir -p "$case_dir/bin"
  install_fake_gh "$case_dir/bin"
  local body_file="$case_dir/body.md"
  printf '<!-- ai-code-review -->\nhello\n' >"$body_file"
  local call_log="$case_dir/calls.log"
  : >"$call_log"

  PATH="$case_dir/bin:$PATH" \
    GH_CALL_LOG="$call_log" \
    FAKE_LIST_OUTPUT="" \
    FAKE_COMMENTS_JSON='[{"id":111,"body":"unrelated comment, no marker here"}]' \
    GITHUB_REPOSITORY="octo/repo" \
    "$sticky_comment" 42 "$body_file"

  local calls
  calls="$(cat "$call_log")"
  assert_contains "$calls" "--jq $EXPECTED_JQ_FILTER" "expected the exact marker-matching jq filter to be passed to gh api"
  assert_contains "$calls" "--method POST" "expected a POST call when no existing comment matches"
  assert_not_contains "$calls" "--method PATCH" "did not expect a PATCH call"
  assert_contains "$calls" "-F body=" "expected the create call to use -F (file-read), not -f (raw string)"
  assert_not_contains "$calls" "-f body=" "must not use -f/--raw-field for body=@file — it posts the literal path string instead of file contents"

  if have_jq; then
    pass_count=$((pass_count + 1))
  else
    skip "real jq execution for the no-match case (jq not on PATH in this environment)"
  fi
}

# --- Test 2: existing marker comment found -> updates (PATCH) the matched id ---
test_updates_when_existing_comment_found() {
  local case_dir="$work_dir/case2"
  mkdir -p "$case_dir/bin"
  install_fake_gh "$case_dir/bin"
  local body_file="$case_dir/body.md"
  printf '<!-- ai-code-review -->\nupdated\n' >"$body_file"
  local call_log="$case_dir/calls.log"
  : >"$call_log"

  if have_jq; then
    # Two comments: an unrelated one, and the marker comment to be matched —
    # exercises that the filter picks the marker comment specifically, not
    # just "any" comment.
    PATH="$case_dir/bin:$PATH" \
      GH_CALL_LOG="$call_log" \
      FAKE_LIST_OUTPUT="999888777" \
      FAKE_COMMENTS_JSON='[{"id":111,"body":"unrelated comment"},{"id":999888777,"body":"<!-- ai-code-review -->\nold content"}]' \
      GITHUB_REPOSITORY="octo/repo" \
      "$sticky_comment" 42 "$body_file"
  else
    skip "real jq execution for the matched case (jq not on PATH in this environment)"
    PATH="$case_dir/bin:$PATH" \
      GH_CALL_LOG="$call_log" \
      FAKE_LIST_OUTPUT="999888777" \
      FAKE_COMMENTS_JSON='[]' \
      GITHUB_REPOSITORY="octo/repo" \
      "$sticky_comment" 42 "$body_file"
  fi

  local calls
  calls="$(cat "$call_log")"
  assert_contains "$calls" "issues/comments/999888777" "expected PATCH against the matched comment id"
  assert_contains "$calls" "--method PATCH" "expected a PATCH call when an existing comment matches"
  assert_contains "$calls" "-F body=" "expected the update call to use -F (file-read), not -f (raw string)"
  assert_not_contains "$calls" "-f body=" "must not use -f/--raw-field for body=@file — it posts the literal path string instead of file contents"
}

# --- Test 3: missing body file -> exits non-zero, never calls gh ---
test_missing_body_file_fails_fast() {
  local case_dir="$work_dir/case3"
  mkdir -p "$case_dir/bin"
  install_fake_gh "$case_dir/bin"
  local call_log="$case_dir/calls.log"
  : >"$call_log"

  local rc=0
  PATH="$case_dir/bin:$PATH" \
    GH_CALL_LOG="$call_log" \
    FAKE_LIST_OUTPUT="" \
    FAKE_COMMENTS_JSON='[]' \
    GITHUB_REPOSITORY="octo/repo" \
    "$sticky_comment" 42 "$case_dir/does-not-exist.md" || rc=$?

  assert_equal "1" "$rc" "expected exit 1 for a missing body file"
  assert_equal "" "$(cat "$call_log")" "expected no gh invocation when the body file is missing"
}

# --- Test 4: missing arguments -> usage error ---
test_missing_arguments_fails_fast() {
  local rc=0
  "$sticky_comment" || rc=$?
  assert_equal "1" "$rc" "expected exit 1 when called with no arguments"
}

test_creates_when_no_existing_comment
test_updates_when_existing_comment_found
test_missing_body_file_fails_fast
test_missing_arguments_fails_fast

echo "sticky-comment tests: $pass_count passed, $fail_count failed, $skip_count skipped"
[ "$fail_count" -eq 0 ]
