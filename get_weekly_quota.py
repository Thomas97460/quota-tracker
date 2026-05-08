#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from copilot_local_audit import probe_capi_usage_ratelimit_quota


def _format_percent(value: Any) -> str:
    if value is None:
        return "n/a"
    number = float(value)
    text = f"{number:.3f}".rstrip("0").rstrip(".")
    return f"{text}%"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print the precise Copilot weekly usage percentage from live quota headers."
    )
    parser.add_argument(
        "--copilot-home",
        type=Path,
        default=Path.home() / ".copilot",
        help="Path to Copilot home directory (default: ~/.copilot)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="Timeout in seconds for the live Copilot API probe (default: 20)",
    )
    parser.add_argument(
        "--remaining",
        action="store_true",
        help="Print remaining weekly percentage instead of used weekly percentage",
    )
    parser.add_argument("--json", action="store_true", help="Render the full probe as JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    probe = probe_capi_usage_ratelimit_quota(
        copilot_home=args.copilot_home.expanduser().resolve(),
        timeout_seconds=max(5, args.timeout),
    )

    if args.json:
        print(json.dumps(probe, indent=2, ensure_ascii=False))
        return 0 if probe.get("available") else 1

    if not probe.get("available"):
        print(probe.get("error") or "weekly quota unavailable", file=sys.stderr)
        return 1

    key = "weekly_remaining_percent" if args.remaining else "weekly_used_percent"
    print(_format_percent(probe.get(key)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
