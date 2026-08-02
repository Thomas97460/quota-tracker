#!/usr/bin/env bash
# Applies this repo's GitHub-as-code governance config: merge button settings,
# and the branch/tag rulesets checked into .github/rulesets/.
#
# Prerequisites:
#   - `gh auth login` as an account with admin rights on this repo.
#   - The RELEASE_PLEASE_TOKEN secret (a fine-grained PAT: Contents rw,
#     Pull requests rw, Metadata ro) must already be set on the repo — see
#     CONTRIBUTING.md. That PAT's owner needs the "admin" role bypass baked
#     into tags.json (actor_id 5) to be able to push the release tags that
#     release-please creates.
#
# Idempotent: re-running updates existing rulesets in place instead of
# creating duplicates.
set -euo pipefail

REPO="${REPO:-Thomas97460/quota-tracker}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "== repo merge settings =="
gh api -X PATCH "repos/${REPO}" \
  -F allow_squash_merge=true \
  -F allow_merge_commit=false \
  -F allow_rebase_merge=false \
  -F delete_branch_on_merge=true \
  -f squash_merge_commit_title=PR_TITLE \
  -f squash_merge_commit_message=BLANK \
  -F allow_auto_merge=true \
  >/dev/null
echo "ok"

apply_ruleset() {
  local file="$1"
  local name
  name="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['name'])" "$file")"

  local existing_id
  existing_id="$(gh api "repos/${REPO}/rulesets" --jq ".[] | select(.name==\"${name}\") | .id" 2>/dev/null || true)"

  if [[ -n "${existing_id}" ]]; then
    echo "== updating ruleset '${name}' (id ${existing_id}) =="
    gh api -X PUT "repos/${REPO}/rulesets/${existing_id}" --input "$file" >/dev/null
  else
    echo "== creating ruleset '${name}' =="
    gh api -X POST "repos/${REPO}/rulesets" --input "$file" >/dev/null
  fi
  echo "ok"
}

apply_ruleset "${DIR}/.github/rulesets/main.json"
apply_ruleset "${DIR}/.github/rulesets/tags.json"

echo "done."
