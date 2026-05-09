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

We follow a standard Git Pull Request (PR) workflow.

1.  **Create a Branch**: 
    Create a new branch from `main` for your feature or bug fix. Use a descriptive name.
    ```bash
    git checkout -b feature/add-new-provider
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

4.  **Commit Your Changes**:
    Write clear, concise commit messages. If your PR addresses an open issue, reference it in your commits or PR description.

5.  **Open a Pull Request**:
    Push your branch to your fork (or the main repository if you have access) and open a Pull Request against the `main` branch. 
    Describe your changes clearly in the PR description, including what problem it solves and how you solved it.

### Code Style & Guidelines
- **Backend**: We use `ruff` for formatting and linting, and `mypy` for static type checking. Ensure all Python code is typed.
- **Frontend**: Follow React best practices. Keep components small and focused.

Thank you for your interest in improving Quota Tracker!
