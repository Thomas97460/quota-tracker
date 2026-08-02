#!/usr/bin/env bash
# Applies this repo's GitHub-as-code governance config: merge button settings,
# and the branch/tag rulesets checked into .github/rulesets/.
#
# Prerequisites:
#   - `gh auth login` as an account with admin rights on this repo. That
#     account needs the "admin" role bypass baked into tags.json (actor_id 5)
#     to be able to manually push release tags (see AGENTS.md: pushing a
#     vX.Y.Z tag is the production-approval act itself).
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

echo "== removing legacy classic branch protection on main =="
# Superseded by main.json's ruleset above; left in place it stacks an
# unsatisfiable "1 approving review" requirement on top (an account can never
# approve its own PR, and every PR here is authored as the sole owner).
gh api -X DELETE "repos/${REPO}/branches/main/protection" >/dev/null 2>&1 || true
echo "ok"

echo "done."
