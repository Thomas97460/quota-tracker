# quota-tracker

Track token usage and quotas for [Claude](https://claude.ai), [Copilot](https://github.com/features/copilot), [Codex](https://openai.com/codex) and [Gemini](https://gemini.google.com) — locally, with no telemetry.

[![CI](https://github.com/Thomas97460/quota-tracker/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Thomas97460/quota-tracker/actions/workflows/ci.yml)
[![Release](https://github.com/Thomas97460/quota-tracker/actions/workflows/release.yml/badge.svg)](https://github.com/Thomas97460/quota-tracker/actions/workflows/release.yml)
[![version](https://img.shields.io/github/v/release/Thomas97460/quota-tracker?style=flat-square&color=00d7d7&label=latest)](https://github.com/Thomas97460/quota-tracker/releases/latest)
[![coverage](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2FThomas97460%2Fquota-tracker%2Fmain%2Fassets%2Fcoverage.json&style=flat-square)](https://github.com/Thomas97460/quota-tracker/actions/workflows/ci.yml)
[![ruff](https://img.shields.io/github/actions/workflow/status/Thomas97460/quota-tracker/ci.yml?job=ruff&label=ruff&style=flat-square)](https://github.com/Thomas97460/quota-tracker/actions/workflows/ci.yml)
[![mypy](https://img.shields.io/github/actions/workflow/status/Thomas97460/quota-tracker/ci.yml?job=mypy&label=mypy&style=flat-square)](https://github.com/Thomas97460/quota-tracker/actions/workflows/ci.yml)
[![tests](https://img.shields.io/github/actions/workflow/status/Thomas97460/quota-tracker/ci.yml?job=pytest&label=tests&style=flat-square)](https://github.com/Thomas97460/quota-tracker/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.12%2B-00d7d7?style=flat-square)](https://www.python.org/)

<div align="center">
<img src="assets/screenshots/overview.png" alt="quota-tracker overview" width="100%">
</div>

## Quick start

**Linux**

```bash
curl -fsSL https://raw.githubusercontent.com/Thomas97460/quota-tracker/main/install.sh | bash
```

Installs the binary, runs migrations, backfills history and starts a systemd user service. Open the printed URL when done.

**macOS**

```bash
git clone https://github.com/Thomas97460/quota-tracker
cd quota-tracker
uv sync
task run-api
```

Then open [http://localhost:8787](http://localhost:8787).
