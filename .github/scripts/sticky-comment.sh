#!/usr/bin/env bash
# Upsert a single PR comment identified by the leading `<!-- ai-code-review -->`
# marker (see packages/code_reviewer/src/code_reviewer/render.py). Identifying by
# marker rather than comment author survives a token/app change; author matching
# breaks silently the moment that changes (claude-code-action#960).
#
# Usage: sticky-comment.sh <pr-number> <body-file>
# Requires: gh authenticated (GH_TOKEN/GITHUB_TOKEN), GITHUB_REPOSITORY set
# (both are ambient in GitHub Actions).
set -euo pipefail

pr_number="${1:?usage: sticky-comment.sh <pr-number> <body-file>}"
body_file="${2:?usage: sticky-comment.sh <pr-number> <body-file>}"

if [ ! -f "$body_file" ]; then
  echo "sticky-comment: body file not found: $body_file" >&2
  exit 1
fi

comment_id=$(gh api --paginate \
  "repos/${GITHUB_REPOSITORY}/issues/${pr_number}/comments" \
  --jq '[.[] | select(.body | startswith("<!-- ai-code-review -->"))][0].id // empty')

if [ -n "$comment_id" ]; then
  gh api --method PATCH \
    "repos/${GITHUB_REPOSITORY}/issues/comments/${comment_id}" \
    -F body=@"${body_file}" \
    --silent
else
  gh api --method POST \
    "repos/${GITHUB_REPOSITORY}/issues/${pr_number}/comments" \
    -F body=@"${body_file}" \
    --silent
fi
