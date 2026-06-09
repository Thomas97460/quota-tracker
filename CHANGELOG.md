# Changelog

All notable changes to this project will be documented in this file.

## [0.1.39] - 2026-06-09

### Added
- Added support for non-Gemini models (Claude & GPT-OSS) via Antigravity provider.
- Added `/api/quotas/latest` endpoint for more efficient quota retrieval.
- Updated frontend to display accurate quota names and usage percentages for Antigravity.
- Added official Antigravity logo to the UI.

### Fixed
- Fixed backend parsing of Antigravity token usage to correctly capture cached and reasoning tokens.
- Fixed rollup display logic to appropriately group and sort Antigravity quotas.
