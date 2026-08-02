# Contributing to Quota Tracker

First off, thank you for considering contributing to Quota Tracker! We welcome contributions to make local AI observability better for everyone.

This document outlines the development environment, technology stack, and the process for contributing to the project.

## Development Environment

We strive to make the development environment as reproducible and frictionless as possible. To achieve this, the project relies on **Nix**.

### Prerequisites

1.  **[Nix](https://nixos.org/download/)**: The package manager used to define our isolated development environment.
2.  **[Flakes](https://nixos.wiki/wiki/Flakes)**: Ensure Nix Flakes are enabled in your Nix configuration.
3.  **[direnv](https://direnv.net/)**: Used to automatically load the Nix environment when you enter the project directory.

### Getting Started

Once you have the prerequisites installed:

1.  Clone the repository:
    ```bash
    git clone https://github.com/Thomas97460/quota-tracker.git
    cd quota-tracker
    ```

2.  Allow `direnv` to setup the environment (this will invoke Nix and download necessary dependencies):
    ```bash
    direnv allow
    ```

3.  The project uses `task` (go-task) as the primary task runner. You can view available commands by running:
    ```bash
    task --list
    ```

## Technology Stack & Architecture Choices

Quota Tracker is built with a clear separation of concerns, keeping the backend lightweight and local-first, while providing a rich, modern user interface.

### Backend: Python
- **Why Python?** Python is excellent for parsing logs, handling file system events efficiently, and rapid development.
- **Key Technologies**:
  - `FastAPI`: For serving the local API and static frontend assets.
  - `SQLite`: For robust, local, zero-config data persistence.
  - `Pydantic`: For data validation and settings management.
  - `uv`: For fast Python dependency management.

### Frontend: React
- **Why React?** We wanted a highly interactive, responsive, and beautiful dashboard. React, combined with an ecosystem of charting libraries, makes this possible.
- **Key Technologies**:
  - `React` & `TypeScript`: For a type-safe, component-based UI.
  - `Vite`: For lightning-fast frontend tooling and building.
  - `Recharts`: For drawing the token and quota graphs.
  - Custom CSS: We prefer lean, custom CSS using CSS variables over heavy utility frameworks for this specific project to maintain absolute control over the styling and footprint.

## How to Contribute

We follow a standard Git Pull Request (PR) workflow, with `main` protected: no direct pushes, no force-push, no branch deletion. Everything lands via a PR.

1.  **Create a Branch**:
    Create a new branch from `main` for your feature or bug fix. Use a descriptive prefix.
    ```bash
    git checkout -b feat/add-new-provider
    # or
    git checkout -b fix/chart-y-axis-clipping
    ```

2.  **Make Your Changes**:
    Write your code, following the existing style and conventions.

3.  **Validate Your Changes**:
    Before pushing, ensure your code passes all linting, formatting, and tests. We have a strict validation pipeline.
    ```bash
    # Run the full, quiet validation suite
    task validate:quiet
    ```
    If this command fails, you can run individual tasks like `task format`, `task lint`, or `task test` to identify and fix the specific issues.

4.  **Open a Pull Request** with a [Conventional Commits](https://www.conventionalcommits.org/) title, e.g. `feat(api): add new provider`, `fix(frontend): correct y-axis clipping`, `chore(deps): bump fastapi`.
    The repo **squash-merges only** — your PR title becomes the single commit message on `main`, and [release-please](https://github.com/googleapis/release-please) parses that history to compute the next version and changelog entry. A required check lints the PR title against Conventional Commits, so a malformed title blocks merge.

5.  **Required checks before merge**: `ruff` (lint + format), `mypy` (strict), `interrogate` (docstring coverage ≥ 90%), `pytest` (coverage ≥ 90%), frontend build, PR title lint, and an **integration smoke test** that builds the real PyInstaller binary and hits `GET /api/health` — this catches packaging issues before they ever reach a tag. All are required status checks on `main`; none can be bypassed.

6.  **Governance files require a human review.** PRs touching `.github/`, `nix/`, `flake.nix`, `release-please-config.json`, `.release-please-manifest.json`, or `SECURITY.md` need a code-owner approval (see `.github/CODEOWNERS`) regardless of CI status — these control the workflow itself and are never auto-merged.

### Release process

- `release-please` maintains a standing **release PR** on `main` (title `chore(release): X.Y.Z`) that bumps `pyproject.toml`'s version and updates `CHANGELOG.md` from the Conventional Commits merged since the last release.
- **Merging that PR is the production-approval step.** There is no separate deploy click: once merged, `release-please` pushes the `vX.Y.Z` tag and creates the GitHub Release; `release.yml` then builds and attaches the Linux amd64/arm64 binaries. Only review that PR (version + changelog) like you would any release sign-off.
- The `v*` tags are protected: only the release automation can create them, so nobody (human or agent) can hand-push a release tag directly.
- "Rollback" here means **repointing what `releases/latest` resolves to**, since `install.sh` and Nix installs both pull by tag rather than through a server you control: mark the previous good release as latest again (or `git tag` a new patch release) rather than trying to push a change to users' machines.

### Code Style & Guidelines
- **Backend**: We use `ruff` for formatting and linting, and `mypy` for static type checking. Ensure all Python code is typed.
- **Frontend**: Follow React best practices. Keep components small and focused.

Thank you for your interest in improving Quota Tracker!
