# Copilot weekly limit precise percentage

## Goal

Recover the precise GitHub Copilot CLI weekly limit percentage, not the rounded warning threshold and not an estimate derived from the monthly premium quota.

## Confirmed path

Copilot CLI receives the weekly quota in model API response headers:

```text
x-usage-ratelimit-weekly
x-usage-ratelimit-session
x-quota-snapshot-chat
x-quota-snapshot-completions
x-quota-snapshot-premium_interactions
```

The weekly value is not present in `https://github.com/github-copilot/chat/entitlement`; that endpoint only exposes monthly/premium quota fields.

The active probe must use the Copilot API endpoint returned by:

```text
https://api.github.com/copilot_internal/user
```

For this account, the returned model API base is:

```text
https://api.individual.githubcopilot.com
```

## Header format

The bundle parser (`Mcr`) decodes headers as URL query params:

```text
ent=<entitlement>&ov=<overage>&ovPerm=<bool>&rem=<remaining_percent>&rst=<reset_iso>
```

The precise usage percentage is:

```text
weekly_used_percent = 100 - rem
```

Example observed on May 8, 2026:

```text
x-usage-ratelimit-weekly: ent=0&ov=0.0&ovPerm=false&rem=1.3&rst=2026-05-11T00%3A00%3A00Z
```

So:

```text
weekly_remaining_percent = 1.3
weekly_used_percent = 98.7
weekly_reset_date = 2026-05-11T00:00:00Z
```

## Implemented

- `get_weekly_quota.py`: prints the precise weekly used percentage by default.
- `get_weekly_quota.py --remaining`: prints the precise weekly remaining percentage.
- `copilot_local_audit.py`: now includes weekly/session quota fields in the `[Live quota]` section.

The active probe sends a minimal `claude-haiku-4.5` chat completion request with `max_tokens=1`, then parses `x-usage-ratelimit-weekly`.

This is intentionally active, so each run can count as a small Copilot request.
