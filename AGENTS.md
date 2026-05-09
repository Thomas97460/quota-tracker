# Quota Tracker — Agent Context

## Project Overview

**quota-tracker** is a local tool that monitors AI provider API quotas and usage (tokens, costs, rate limits). It supports multiple providers (Anthropic Claude, etc.) and exposes a REST API with a React dashboard frontend.

## Architecture

```
quota-tracker/
├── quota_tracker/          # Python backend (FastAPI)
│   ├── api/
│   │   ├── routes.py       # REST API endpoints
│   │   └── schemas.py      # Pydantic response models
│   ├── providers/          # Per-provider quota scrapers
│   ├── config.py           # App configuration
│   ├── cli.py              # CLI entry point
│   └── _ui.py              # Embedded frontend server
├── frontend/               # React + TypeScript dashboard
│   ├── src/
│   │   ├── pages/          # Overview, ProviderDetail, Settings
│   │   ├── components/     # Charts, UI panels
│   │   ├── hooks/          # useConfig, data fetching
│   │   ├── types.ts        # Shared TypeScript types
│   │   └── utils.ts        # Helpers
│   └── dist/               # Built assets (embedded in Python package)
├── tests/                  # pytest unit + snapshot tests
├── Taskfile.yml            # Task runner (dev, build, test)
└── pyproject.toml          # Python package config
```

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLite, uv (package manager)
- **Frontend**: React 18, TypeScript, Vite, custom CSS design system (no Tailwind in components)
- **Design**: Dark theme, Geist fonts, CSS variables — inspired by claude.ai/design
- **Tests**: pytest, snapshot testing for API shapes

## Key Commands

```bash
task dev          # Start backend + frontend dev servers
task build        # Build frontend and package
task test         # Run test suite
task lint         # Lint frontend (TypeScript)
```

Or with uv/npm directly:
```bash
uv run quota-tracker         # Start the app
cd frontend && npm run dev   # Frontend dev server
cd frontend && npm run build # Build frontend
uv run pytest                # Run tests
```

## Development Guidelines

- Keep backend logic in `quota_tracker/`; never import frontend code from Python
- API schemas live in `schemas.py`; keep them in sync with `frontend/src/types.ts`
- New providers go in `quota_tracker/providers/`
- CSS design tokens are in `frontend/src/index.css`; use existing variables, don't hardcode colors
- Snapshot tests in `tests/snapshots/` must be updated when API shapes change
- The `dist/` directory is gitignored; always run `task build` before packaging

## Conventions

- Python: follow existing code style, use type hints
- TypeScript: strict mode, no `any`
- Commits: `feat:`, `fix:`, `refactor:` prefixes
