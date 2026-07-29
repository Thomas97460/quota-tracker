# Changelog

All notable changes to this project will be documented in this file.

## [0.1.42] - 2026-07-29

### Added
- Added documented pricing for the GPT-5.6 Sol, Terra, and Luna model family.
- Added Claude Opus 5 pricing for Claude and Antigravity usage.
- Added Gemini 3.6 Flash, Gemini 3.5 Flash-Lite, and stable Gemini 3.1 Flash-Lite pricing.

### Fixed
- Corrected Gemini 3.5 Flash pricing and Antigravity model-label normalization.

## [0.1.39] - 2026-06-09

### Added
- Added support for non-Gemini models (Claude & GPT-OSS) via Antigravity provider.
- Added `/api/quotas/latest` endpoint for more efficient quota retrieval.
- Updated frontend to display accurate quota names and usage percentages for Antigravity.
- Added official Antigravity logo to the UI.

### Fixed
- Fixed backend parsing of Antigravity token usage to correctly capture cached and reasoning tokens.
- Fixed rollup display logic to appropriately group and sort Antigravity quotas.
