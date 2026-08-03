#!/usr/bin/env bash
# Unit tests for sticky-comment.sh, driven against a fake `gh` on PATH so no
# network or real GitHub state is needed. Run: .github/scripts/tests/test_sticky-comment.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sticky_comment="$script_dir/../sticky-comment.sh"

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

pass_count=0
fail_count=0

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

# Installs a fake `gh` on PATH that logs every invocation (one line per call,
# args space-joined) to $GH_CALL_LOG and answers the --paginate list call with
# $FAKE_LIST_OUTPUT.
install_fake_gh() {
  local bin_dir="$1"
  cat >"$bin_dir/gh" <<'FAKE_GH'
#!/usr/bin/env bash
echo "$*" >> "$GH_CALL_LOG"
if [ "$1" = "api" ] && [ "$2" = "--paginate" ]; then
  printf '%s' "$FAKE_LIST_OUTPUT"
  exit 0
fi
exit 0
FAKE_GH
  chmod +x "$bin_dir/gh"
}

# --- Test 1: no existing marker comment -> creates (POST) ---
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
    GITHUB_REPOSITORY="octo/repo" \
    "$sticky_comment" 42 "$body_file"

  local calls
  calls="$(cat "$call_log")"
  assert_contains "$calls" "--method POST" "expected a POST call when no existing comment matches"
  if [[ "$calls" == *"--method PATCH"* ]]; then
    fail_count=$((fail_count + 1))
    echo "FAIL: did not expect a PATCH call" >&2
  else
    pass_count=$((pass_count + 1))
  fi
}

# --- Test 2: existing marker comment found -> updates (PATCH) ---
test_updates_when_existing_comment_found() {
  local case_dir="$work_dir/case2"
  mkdir -p "$case_dir/bin"
  install_fake_gh "$case_dir/bin"
  local body_file="$case_dir/body.md"
  printf '<!-- ai-code-review -->\nupdated\n' >"$body_file"
  local call_log="$case_dir/calls.log"
  : >"$call_log"

  PATH="$case_dir/bin:$PATH" \
    GH_CALL_LOG="$call_log" \
    FAKE_LIST_OUTPUT="999888777" \
    GITHUB_REPOSITORY="octo/repo" \
    "$sticky_comment" 42 "$body_file"

  local calls
  calls="$(cat "$call_log")"
  assert_contains "$calls" "issues/comments/999888777" "expected PATCH against the matched comment id"
  assert_contains "$calls" "--method PATCH" "expected a PATCH call when an existing comment matches"
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

echo "sticky-comment tests: $pass_count passed, $fail_count failed"
[ "$fail_count" -eq 0 ]
