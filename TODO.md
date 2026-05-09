# Quota Tracker — TODO

Source-of-truth tracker for in-progress refactor. Update each item as it lands.
R&D references live in `copilot_local_audit.py`, `codex_local_audit.py`, `gemini_local_audit.py`.
If a request requires logic not present in those scripts, do **not** invent it — log it under "Needs R&D".

## User requests

### Pricing snapshot (2026-05-09)

One-shot snapshot of official token pricing (USD) to support "cost of tokens" estimation.
Prices change; treat this as a dated reference and keep the source URLs.

#### OpenAI (official)

Source: https://developers.openai.com/api/docs/pricing

Prices per 1M tokens (Standard, short context):

| Model | Input | Cached input | Output |
| --- | ---: | ---: | ---: |
| gpt-5.5 | 5.00 | 0.50 | 30.00 |
| gpt-5.5-pro | 30.00 | - | 180.00 |
| gpt-5.4 | 2.50 | 0.25 | 15.00 |
| gpt-5.4-mini | 0.75 | 0.075 | 4.50 |
| gpt-5.4-nano | 0.20 | 0.02 | 1.25 |
| gpt-5.4-pro | 30.00 | - | 180.00 |

Specialized (same source):

| Category | Model | Input | Cached input | Output |
| --- | --- | ---: | ---: | ---: |
| Codex | gpt-5.3-codex | 1.75 | 0.175 | 14.00 |

#### Anthropic (official)

Source: https://platform.claude.com/docs/en/about-claude/pricing

Anthropic prompt caching has distinct costs for cache write (5m / 1h) and cache read (hits & refreshes).

Prices per 1M tokens:

| Model | Input (base) | Cache read (hit) | Cache write (5m) | Cache write (1h) | Output |
| --- | ---: | ---: | ---: | ---: | ---: |
| Claude Opus 4.7 | 5.00 | 0.50 | 6.25 | 10.00 | 25.00 |
| Claude Opus 4.6 | 5.00 | 0.50 | 6.25 | 10.00 | 25.00 |
| Claude Opus 4.5 | 5.00 | 0.50 | 6.25 | 10.00 | 25.00 |
| Claude Opus 4.1 | 15.00 | 1.50 | 18.75 | 30.00 | 75.00 |
| Claude Sonnet 4.6 | 3.00 | 0.30 | 3.75 | 6.00 | 15.00 |
| Claude Sonnet 4.5 | 3.00 | 0.30 | 3.75 | 6.00 | 15.00 |
| Claude Sonnet 4 | 3.00 | 0.30 | 3.75 | 6.00 | 15.00 |
| Claude Haiku 4.5 | 1.00 | 0.10 | 1.25 | 2.00 | 5.00 |
| Claude Haiku 3.5 | 0.80 | 0.08 | 1.00 | 1.60 | 4.00 |
| Claude Haiku 3 | 0.25 | 0.03 | 0.30 | 0.50 | 1.25 |

#### Google Gemini (Vertex AI / Google Cloud) (official)

Source: https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing

Prices per 1M tokens (Priority, <= 200K input tokens, token-based):

| Model | Input | Cached input | Output |
| --- | ---: | ---: | ---: |
| Gemini 3.1 Pro Preview | 3.60 | 0.36 | 21.60 |
| Gemini 3 Pro Preview | 3.60 | 0.36 | 21.60 |
| Gemini 3 Flash Preview | 0.90 | 0.09 | 5.40 |
| Gemini 3.1 Flash-Lite | 0.45 | 0.045 | 2.70 |
| Gemini 2.5 Pro | 2.25 | 0.23 | 18.00 |
| Gemini 2.5 Flash | 0.54 | 0.05 | 4.50 |
| Gemini 2.5 Flash Lite | 0.18 | 0.02 | 0.72 |

Note: the Google pricing table includes other tiers (e.g. >200K input tokens) and modality-specific rates (audio/video/image).

#### GitHub Copilot (official)

Source: https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing

Prices per 1M tokens (usage-based billing rates effective June 1, 2026):

OpenAI:

| Model | Input | Cached input | Output |
| --- | ---: | ---: | ---: |
| GPT-4.1 | 2.00 | 0.50 | 8.00 |
| GPT-5 mini | 0.25 | 0.025 | 2.00 |
| GPT-5.2 | 1.75 | 0.175 | 14.00 |
| GPT-5.2-Codex | 1.75 | 0.175 | 14.00 |
| GPT-5.3-Codex | 1.75 | 0.175 | 14.00 |
| GPT-5.4 | 2.50 | 0.25 | 15.00 |
| GPT-5.4 mini | 0.75 | 0.075 | 4.50 |
| GPT-5.4 nano | 0.20 | 0.02 | 1.25 |
| GPT-5.5 | 5.00 | 0.50 | 30.00 |

Anthropic (note: Copilot table includes a "cache write" column for Anthropic models):

| Model | Input | Cached input | Output |
| --- | ---: | ---: | ---: |
| Claude Haiku 4.5 | 1.00 | 0.10 | 5.00 |
| Claude Sonnet 4 | 3.00 | 0.30 | 15.00 |
| Claude Sonnet 4.5 | 3.00 | 0.30 | 15.00 |
| Claude Sonnet 4.6 | 3.00 | 0.30 | 15.00 |
| Claude Opus 4.5 | 5.00 | 0.50 | 25.00 |
| Claude Opus 4.6 | 5.00 | 0.50 | 25.00 |
| Claude Opus 4.7 | 5.00 | 0.50 | 25.00 |

Google:

| Model | Input | Cached input | Output |
| --- | ---: | ---: | ---: |
| Gemini 2.5 Pro | 1.25 | 0.125 | 10.00 |
| Gemini 3 Flash | 0.50 | 0.05 | 3.00 |
| Gemini 3.1 Pro | 2.00 | 0.20 | 12.00 |

### Official structured endpoints (pricing / costs)

Goal: get pricing in a structured way (API), ideally with the same rates you would pay using each provider directly.

Reality check:
* OpenAI + Anthropic expose **structured usage/cost** endpoints, but do **not** expose an official "pricing table" endpoint per model.
* Google Cloud exposes **structured SKU pricing** (Catalog API / Pricing API), which can be used to derive Gemini/Vertex AI token pricing.
* GitHub exposes **structured billing/usage** endpoints, but the **per-token rate tables** live in docs (not a pricing API).

#### OpenAI (API key)

Structured spend (official):
* `GET https://api.openai.com/v1/organization/costs`
* `GET https://api.openai.com/v1/organization/usage/...` (e.g. `.../completions`, `.../moderations`, etc.)

Reference: https://platform.openai.com/docs/api-reference/usage

Note: OpenAI pricing tables are published on web pages (e.g. https://openai.com/api/pricing/), not via a stable pricing endpoint.

#### Anthropic (API key)

Structured usage + costs (official Admin API, org-level):
* `GET https://api.anthropic.com/v1/organizations/usage_report/messages`
* `GET https://api.anthropic.com/v1/organizations/cost_report`

Reference: https://platform.claude.com/docs/en/manage-claude/usage-cost-api

Note: Model pricing tables are published on web pages (e.g. https://platform.claude.com/docs/en/about-claude/pricing), not via a stable pricing endpoint.

#### Google Gemini (Vertex AI / Google Cloud) (API key)

Structured public SKU pricing (official):
* Cloud Billing Catalog API (v1): `GET https://cloudbilling.googleapis.com/v1/services?key=API_KEY`, then `GET https://cloudbilling.googleapis.com/v1/services/{SERVICE_ID}/skus?key=API_KEY`
* Cloud Billing Pricing API (v2beta): `GET https://cloudbilling.googleapis.com/v2beta/services?key=API_KEY` and `GET https://cloudbilling.googleapis.com/v2beta/services/{SERVICE_ID}/skus?key=API_KEY`

References:
* https://docs.cloud.google.com/billing/v1/how-tos/catalog-api
* https://docs.cloud.google.com/billing/docs/how-to/get-pricing-information-api

Note: you must map the relevant Vertex AI / Gemini SKUs (text input, cached input, output) to the models you want to price.

#### GitHub Copilot (GitHub token, not a provider "API key")

Structured billing/usage (official GitHub REST API):
* Premium request usage for orgs: `GET https://api.github.com/organizations/{org}/settings/billing/premium_request/usage`
* Copilot metrics: `GET https://api.github.com/orgs/{org}/copilot/metrics`

References:
* https://docs.github.com/en/rest/billing/usage
* https://docs.github.com/en/rest/copilot/copilot-metrics

Note: Copilot's per-token rates are published in docs: https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing


## Needs R&D (not in audit scripts)

N/A
