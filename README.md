# quota-tracker

Track token usage and quotas for [Claude](https://claude.ai), [Copilot](https://github.com/features/copilot), [Codex](https://openai.com/codex) and [Gemini](https://gemini.google.com) — locally, with no telemetry.

**Zero configuration required.** Quota Tracker automatically leverages your existing local CLI credentials to fetch real-time quotas. It parses and backfills your conversation history into a local database, ensuring your usage data is persisted and searchable even after a local environment cleanup.

<p align="center">
  <a href="https://github.com/Thomas97460/quota-tracker/actions/workflows/ci.yml">
    <img src="https://github.com/Thomas97460/quota-tracker/actions/workflows/ci.yml/badge.svg" alt="CI">
  </a>
  <a href="https://github.com/Thomas97460/quota-tracker/releases/latest">
    <img src="https://img.shields.io/github/v/release/Thomas97460/quota-tracker?style=flat-square&color=00d7d7&label=latest" alt="latest">
  </a>
  <a href="https://github.com/Thomas97460/quota-tracker/actions/workflows/ci.yml">
    <img src="https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2FThomas97460%2Fquota-tracker%2Fmain%2Fassets%2Fcoverage.json&style=flat-square" alt="coverage">
  </a>
  <a href="https://github.com/Thomas97460/quota-tracker/actions/workflows/ci.yml">
    <img src="https://img.shields.io/github/actions/workflow/status/Thomas97460/quota-tracker/ci.yml?job=lint&label=ruff&style=flat-square" alt="ruff">
  </a>
  <a href="https://github.com/Thomas97460/quota-tracker/actions/workflows/ci.yml">
    <img src="https://img.shields.io/github/actions/workflow/status/Thomas97460/quota-tracker/ci.yml?job=typecheck&label=mypy&style=flat-square" alt="mypy">
  </a>
  <a href="https://github.com/Thomas97460/quota-tracker/actions/workflows/ci.yml">
    <img src="https://img.shields.io/github/actions/workflow/status/Thomas97460/quota-tracker/ci.yml?job=tests&label=tests&style=flat-square" alt="tests">
  </a>
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/python-3.14%2B-00d7d7?style=flat-square" alt="python">
  </a>
</p>

## Quick start (Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/Thomas97460/quota-tracker/main/install.sh | bash
```

Installs the binary, runs migrations, backfills history and starts a systemd user service. Open the printed URL when done.

<div align="center">
<img src="assets/screenshots/overview.png" alt="quota-tracker overview" width="100%">
</div>

## NixOS

> [!WARNING]
> If you previously installed via the curl method above, run the [uninstall script](#uninstall) first to avoid systemd service conflicts.

Add to your `configuration.nix`:

```nix
{ config, pkgs, ... }:
let
  # ...your other let bindings...
  quotaTrackerFlake = builtins.getFlake "github:Thomas97460/quota-tracker/v0.1.35"; # ← update tag to upgrade
  quotaTrackerPackage = quotaTrackerFlake.packages.${pkgs.system}.default;
in {
  imports = [
    # ...your other imports...
    quotaTrackerFlake.nixosModules.default
  ];

  # ...rest of your configuration...

  services.quota-tracker = {
    enable  = true;
    package = quotaTrackerPackage;
    host    = "127.0.0.1";
    port    = 8787;
  };
}
```

Then apply with `sudo nixos-rebuild switch`. To upgrade, change the version tag and rebuild.

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/Thomas97460/quota-tracker/main/uninstall.sh | bash
```

The uninstall helper asks before removing the systemd user service, then asks separately before deleting app files. It has a separate database prompt so you can uninstall quota-tracker while keeping the local SQLite history.
