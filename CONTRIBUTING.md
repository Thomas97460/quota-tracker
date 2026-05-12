# Contributing to Quota Tracker

First off, thank you for considering contributing to Quota Tracker! We welcome contributions to make local AI observability better for everyone.

This document outlines the process for contributing to the project, as well as the development environment and technology stack.

## How to Create Pull Requests

We follow a structured **fork-and-pull request** workflow. The goal is to keep the project history clean and ensure each change is well-defined and validated.

### 1. Preparation & Sync
*   **Fork & Clone**: Fork the repository and clone it locally.
*   **Keep Synced**: Always keep your `main` branch up to date with the `upstream` repository to avoid merge conflicts.
*   **Feature Branch**: Create a dedicated branch for every fix or feature: `git checkout -b feature/my-change upstream/main`.

### 2. Implementation & Commits
*   **Atomic Changes**: Focus each PR on a single logical change. If you have multiple unrelated fixes, use multiple PRs.
*   **Commit Style**: Use small, frequent, and atomic commits. Write clear messages (e.g., `feat: ...` or `fix: ...`).
*   **Stay Idiomatic**: Follow the existing code style and naming conventions of the project.

### 3. Quality Control
*   **Validation**: Before submitting, ensure your code passes the full suite:
    ```bash
    task validate:quiet
    ```
*   **Self-Review**: Read through your own changes before pushing. Look for debug prints, commented-out code, or missing documentation.

### 4. Submission & Review
*   **Push & Open**: Push to your fork and open a PR against our `main` branch.
*   **Context**: Provide a concise description of the "What" and "Why". Reference any related issues.
*   **Iterate**: Be prepared to discuss your changes. If updates are requested, push new commits to the same branch.
*   **Finality**: Once approved, your changes will be merged (and squashed if necessary) by a maintainer.

---

## Development Environment

While not mandatory, we strive to make the development environment as reproducible and frictionless as possible using **Nix** and **direnv**. These tools are here to facilitate your work, but you can also set up your environment manually using the provided `pyproject.toml` and `package.json` files.

### Optional Prerequisites (Recommended)

1.  **[Nix](https://nixos.org/download/)**: The package manager used to define our isolated development environment.
2.  **[Flakes](https://nixos.wiki/wiki/Flakes)**: Ensure Nix Flakes are enabled in your Nix configuration.
3.  **[direnv](https://direnv.net/)**: To automatically load the Nix environment when you enter the project directory.

If you choose to use these:
```bash
# The environment is automatically setup.
# View available development tasks:
task --list
```

## Technology Stack & Architecture

### Backend: Python
- **Engine**: `FastAPI` for the API and static serving.
- **Data**: `SQLite` for local persistence.
- **Validation**: `Pydantic` for configuration and schemas.
- **Tooling**: `uv` for dependency management, `ruff` for linting/formatting, and `mypy` for typing.

### Frontend: React
- **Engine**: `React` with `TypeScript`.
- **Tooling**: `Vite` for builds.
- **Charts**: `Recharts` for data visualization.
- **Styling**: Pure CSS (using CSS variables) for a lean, custom-tailored footprint.

---

## Review Process

- **Necessity**: Does the change solve a real problem or add valuable functionality?
- **Code Quality**: Is the code readable, maintainable, and type-safe?
- **Artifact Quality**: Are there tests? Does it pass CI?

Maintainers are volunteers. Please be patient and polite during the review process. We appreciate your contributions!
