# Agent Guidelines — quota-tracker

## Commits

Never add `Co-Authored-By` or any authorship trailer to commit messages.

## Hard stops

- Never merge the `release-please` PR (title `chore(release): X.Y.Z`) without
  explicit human opt-in in the current conversation. Merging it *is*
  production promotion: it pushes the `vX.Y.Z` tag and creates the GitHub
  Release, which `release.yml` then builds binaries for. This is the *only*
  guardrail on prod promotion — the tag ruleset stops a pushed tag from being
  moved or deleted, but not who can merge the PR that creates it, since the
  release-please token authenticates as the repo owner just like everything
  else here.
- Never merge a PR touching a path listed in `.github/CODEOWNERS`
  (`.github/`, `nix/`, `flake.nix`, `release-please-config.json`,
  `.release-please-manifest.json`, `SECURITY.md`) without the human
  explicitly saying so in the conversation — even though auto-merge into
  `main` is otherwise permitted. GitHub can't enforce this by itself here:
  the agent acts under the same GitHub identity as the human (see "Workflow"
  below), and GitHub blocks an account from approving its own PR, so a
  code-owner-review requirement would just permanently block every
  agent-opened PR. This is a procedural rule, not an ACL — see
  `CONTRIBUTING.md` for how this was resolved.
- Never hand-push, move, or delete a `v*` tag — the tag ruleset blocks
  everyone except the release-please automation from touching them.
- No secrets in versioned files.
- Unit test coverage ≥ 90% (`pytest --cov-fail-under=90`) and docstring
  coverage ≥ 90% (`interrogate`) are enforced by required CI checks; do not
  lower, bypass, or remove either gate.
- `mypy` runs in `strict` mode; do not relax it.
- Do not add quality-gate bypasses such as `# pragma: no cover`,
  `# type: ignore`, `# noqa`, or equivalent ruff/mypy/pytest exclusions unless
  a real constraint makes it unavoidable. Any exception must be narrow and
  documented next to the suppression.
- Never edit `.github/rulesets/*.json` or run
  `scripts/github/apply-governance.sh` without explicit human go-ahead — it
  mutates live GitHub branch/tag protection on the real repo.
- `quota_tracker/providers/` and `quota_tracker/db/` must never import from
  `quota_tracker/api/` or `quota_tracker/daemon.py` (see "Code rules").

## Code rules

1. DRY — no duplicated logic.
2. Keep functions small and modules focused. Follow the existing split:
   `providers/` (per-service parsers: Claude, Copilot, Codex, Gemini,
   Antigravity), `db/` (SQLite persistence), `api/` (FastAPI routes),
   `daemon.py` (scheduler/orchestration), `cli.py` (entry point).
3. **Package layering.** `providers/` and `db/` are lower-level and must
   never import from `api/` or `daemon.py`. `daemon.py` and `api/` sit above
   them and may import both — this direction is enforced by convention, not
   tooling, so don't introduce a reverse import.
4. **Backend**: `ruff` for lint + format, `mypy --strict`, everything typed.
   **Frontend**: TypeScript, small focused React components, custom CSS
   variables — no Tailwind or other heavy utility framework (see
   `CONTRIBUTING.md`).
5. Golden Path / fail-fast: validate strictly at the boundaries (CLI args,
   API request bodies), then trust the data. Don't wrap business logic deep
   in the daemon/provider code with defensive `try/except` for states that
   input validation already ruled out — let genuinely unexpected states fail
   loudly.
6. Use `assert` only to help `mypy` narrow types, never as runtime control
   flow.

## Workflow

quota-tracker uses a single trunk branch, `main`, protected: no direct
pushes, no force-push, no deletion, no bypass. Everything lands via a PR.

0. Enter the project's Nix devShell (`direnv allow`) for all required
   tooling (`uv`, `task`, `gh`, `node`). If a tool is missing, add it to
   `flake.nix`'s devShell packages.
1. Sync before starting: `git fetch origin && git rebase origin/main`.
2. Branch from `main`: `git checkout -b feat/my-feature` (or `fix/...`,
   `chore/...`).
3. Make changes, then keep validation green locally: `task validate:quiet`
   (or `task lint` / `task typecheck` / `task test` / `task build-frontend`
   individually to isolate a failure).
4. Commit, then push. **The PR title must be a Conventional Commit**
   (`feat(scope): ...`, `fix(scope): ...`, `chore(scope): ...`, etc.) — the
   repo squash-merges, so that title becomes the single commit message on
   `main`, and `release-please` parses that history to compute the next
   version and changelog entry.
5. Open a PR targeting `main`: `gh pr create --base main ...`.
6. Watch CI and use `gh` actively to inspect failures before drawing
   conclusions: `gh pr checks <n>`, `gh run view <id> --log-failed`,
   `gh run list`. Required checks, all with zero bypass: `ruff`, `mypy`,
   `interrogate`, `pytest`, `frontend build`, `integration smoke`,
   `lint-pr-title`.
7. Once required checks are green, the agent may merge the PR itself
   (`gh pr merge --squash --auto`) — **except** PRs touching a
   `.github/CODEOWNERS` path, which need the human's explicit go-ahead first
   (see "Hard stops").
8. After merge: `git checkout main && git fetch origin && git reset --hard origin/main`.

Keep the branch rebased on `main` throughout: `git fetch origin && git rebase
origin/main`. Never merge `main` into the feature branch — rebase only.

Merging to `main` does not deploy anywhere by itself: there is no server the
maintainer controls. It only feeds `release-please`, which is what actually
prepares a release — see below.

## Release & promotion

quota-tracker ships as GitHub Release binaries (Linux amd64/arm64, built with
PyInstaller) and as a Nix flake pinned by tag. There is no `int`/`prod`
server environment — users pull updates themselves (`install.sh` resolves
`releases/latest`; NixOS configs pin an explicit tag).

1. `release-please` maintains a standing PR (`chore(release): X.Y.Z`) on
   `main`, computed from Conventional Commits merged since the last release.
   It bumps `pyproject.toml`'s version and updates `CHANGELOG.md`.
2. Merging that PR **is** production promotion — there is no separate deploy
   step. It pushes the `vX.Y.Z` tag and creates the GitHub Release;
   `release.yml` then builds and attaches the Linux binaries.
3. Never merge the release-please PR without explicit human opt-in in the
   conversation (see "Hard stops") — merging it *is* the approval.

### Rollback

There is no server to roll back — `install.sh` and Nix installs both resolve
a version by tag, so "rollback" means repointing what that resolution
returns, not pushing a change to anyone's machine:

- Curl/`install.sh` users pull `releases/latest` — mark a previous good
  release as "latest" again on GitHub, or cut a new patch release from the
  last known-good commit.
- Nix users pin an explicit tag in their `configuration.nix` — tell them to
  point at the previous tag and rebuild.

Never move or delete an existing `vX.Y.Z` tag (the tag ruleset blocks this
anyway) — always roll forward with a new tag/release rather than rewriting
history.

## Language

English everywhere written to the repo — code, comments, commit messages,
PR descriptions, and doc files (`AGENTS.md`, `README.md`, `CONTRIBUTING.md`,
`CHANGELOG.md`, etc.). No exceptions.

The developer communicates in French. When talking with the human in
conversation, respond in French — this applies to chat only, never to
anything written to the repo.

## Advice

- **Check the branch state on the remote before committing to it.** A local
  branch may already have been merged. Verify with `gh` (e.g.
  `gh pr view <branch> --json state,mergedAt`). If it's merged, don't add
  commits to it — resync (`git checkout main && git fetch origin && git
  reset --hard origin/main`) and branch fresh.
- **Prefer `gh` for everything GitHub.** Inspect PRs, checks, and failures
  directly (`gh pr checks`, `gh run view <id> --log-failed`, `gh pr view`)
  instead of guessing.
- **Missing permissions or a missing secret → tell the human, don't work
  around them.** If `gh auth status` is logged out, or `release-please.yml`
  fails for lack of the `RELEASE_PLEASE_TOKEN` secret, stop and ask the human
  to authenticate or create it rather than substituting `GITHUB_TOKEN` or
  weakening the workflow.

## Reference

- Commands: [`Taskfile.yml`](Taskfile.yml)
- Contributing guide (full workflow write-up): [`CONTRIBUTING.md`](CONTRIBUTING.md)
- GitHub governance (branch/tag rulesets, applied live as code):
  [`scripts/github/apply-governance.sh`](scripts/github/apply-governance.sh),
  [`.github/CODEOWNERS`](.github/CODEOWNERS),
  [`.github/rulesets/`](.github/rulesets/)
- Release automation: [`release-please-config.json`](release-please-config.json),
  [`.release-please-manifest.json`](.release-please-manifest.json)
- Security policy: [`SECURITY.md`](SECURITY.md)
