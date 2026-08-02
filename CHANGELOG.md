# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0](https://github.com/Thomas97460/quota-tracker/compare/quota-tracker-v0.1.42...quota-tracker-v0.2.0) (2026-08-02)


### Added

* add --host and --port to daemon and serve commands ([4e41fd5](https://github.com/Thomas97460/quota-tracker/commit/4e41fd5e58dd36788dde4f9bfd9bde38f65a1a69))
* add Claude Fable 5 and Mythos 5 pricing ([3f0a546](https://github.com/Thomas97460/quota-tracker/commit/3f0a54617a30f90382cd12e67fa9b42c4717aa7e))
* add NixOS install section and adapt upgrade popup for Nix installs ([7ab9fec](https://github.com/Thomas97460/quota-tracker/commit/7ab9fec139e1e2bbae82549f6174a4d81cd83a05))
* add uninstall script ([fdabf6d](https://github.com/Thomas97460/quota-tracker/commit/fdabf6daadea4f5ec2e4cd51b04cb955e8841420))
* antigravity backend fixes and latest quotas route ([#32](https://github.com/Thomas97460/quota-tracker/issues/32)) ([24750c6](https://github.com/Thomas97460/quota-tracker/commit/24750c6e88aeec58b0eecfa5ab7ef048eb03f97c))
* antigravity frontend quotas and logo updates ([#33](https://github.com/Thomas97460/quota-tracker/issues/33)) ([99a1416](https://github.com/Thomas97460/quota-tracker/commit/99a14160135d74483c319471bca75454e51f0a33))
* **ci:** add autonomous git workflow with release-please and branch protection ([#37](https://github.com/Thomas97460/quota-tracker/issues/37)) ([5a7efe9](https://github.com/Thomas97460/quota-tracker/commit/5a7efe9d91671075c4e2c096c49a49687780f9d2))
* **claude-code:** add opus 4.8 ([8f5d29c](https://github.com/Thomas97460/quota-tracker/commit/8f5d29cf061c5a6575595d2bf5584497837d6b31))
* **copilot:** add support for credit/allotment quotas and float entitlements ([1ab7d78](https://github.com/Thomas97460/quota-tracker/commit/1ab7d78fbce806e2e8866a4e661a7c07901c2f1d))
* **copilot:** add support for credit/allotment quotas and float entitlements ([e4158e4](https://github.com/Thomas97460/quota-tracker/commit/e4158e4dbf4dd462c59d40b4c688ac75152cdf7e))
* implement database archival and token deduplication migrations ([4a9b959](https://github.com/Thomas97460/quota-tracker/commit/4a9b959b1362c224e915b9148eca6b7d3b614133))
* implement server-side downsampling and transparent archival view ([0c6bdda](https://github.com/Thomas97460/quota-tracker/commit/0c6bddaebe0411e8abf21e222013cd2be42c2c93))
* improve charts visual in light mode ([fb2c94e](https://github.com/Thomas97460/quota-tracker/commit/fb2c94e1a2c44de687818becd850389030dd0c29))
* make screenshot task port configurable ([8c44825](https://github.com/Thomas97460/quota-tracker/commit/8c44825574d558e72680e7746939e0b4dc73df14))
* nixos packaging conformity ([881b552](https://github.com/Thomas97460/quota-tracker/commit/881b55213b5f4be860214ef6e57cfb8c817748c9))
* remove all configuration on uninstall ([eff76ec](https://github.com/Thomas97460/quota-tracker/commit/eff76ec74a3bec5c9b28ee3f6177017be1ed28b2))
* remove auto update by copy update command ([e4a1819](https://github.com/Thomas97460/quota-tracker/commit/e4a18190b76d25f8f346d9616f70741047314994))
* support more codex models on pricing ([33a9873](https://github.com/Thomas97460/quota-tracker/commit/33a98733b4726f3decd9550fbe2b183954b9c6cb))
* use python3.14 ([4ea5f41](https://github.com/Thomas97460/quota-tracker/commit/4ea5f41b615902e67021fbfb64a2f965b53b3faa))


### Fixed

* actually include CLI host/port logic and Python fixes in 0.1.27 ([e5f0564](https://github.com/Thomas97460/quota-tracker/commit/e5f0564f905e110160b0c0f3cf73983a7a46945d))
* auto probe ([c8ae19e](https://github.com/Thomas97460/quota-tracker/commit/c8ae19e4412120f4effc93280dcd76fe60fff241))
* clarify uninstallation script questions ([222a0dd](https://github.com/Thomas97460/quota-tracker/commit/222a0ddb9164734d80e08b00224b06073ea446d8))
* claude quota probe ([a5a2794](https://github.com/Thomas97460/quota-tracker/commit/a5a2794ad4ed6f4fd2f73994133f0df85d38c418))
* claude sub sessions scan ([deadb6e](https://github.com/Thomas97460/quota-tracker/commit/deadb6e642dbee7e45a6f221797a3d2356961fa2))
* **claude:** correct token reporting and add reasoning support ([120e43c](https://github.com/Thomas97460/quota-tracker/commit/120e43cf3956b5db6cb9ad53fd525d39b41d8095))
* **config:** backfill default pricing for models missing from a saved config ([cc75d3e](https://github.com/Thomas97460/quota-tracker/commit/cc75d3ef6c49644407d5e1c57ec5bc0707446fbc))
* **copilot:** tighten auth resolution and probe failure handling ([92a6741](https://github.com/Thomas97460/quota-tracker/commit/92a6741b1f1943bc0b5ab8a12a86f6920e3a18e0))
* deduct cached tokens from input automatically for all providers ([bd4ecf7](https://github.com/Thomas97460/quota-tracker/commit/bd4ecf7a87304645d0983ee8a6484381dc4ef884))
* double codex token counting ([d2d6461](https://github.com/Thomas97460/quota-tracker/commit/d2d6461b2ac5e3f1b11db38168f2d7d085b76f79))
* explicit quota bucket fetch ([da8d274](https://github.com/Thomas97460/quota-tracker/commit/da8d274b420b283b66924011745345ba42d30ffc))
* frontend error ([bdd907c](https://github.com/Thomas97460/quota-tracker/commit/bdd907c9599bc107b9c1debbbb4c73d8019d0d78))
* gemini double tokens count ([e14c719](https://github.com/Thomas97460/quota-tracker/commit/e14c719707b5d6c26efe45572b232ede26ab44c8))
* lint and format ([108db0a](https://github.com/Thomas97460/quota-tracker/commit/108db0a73fe8c49098a1d994cb3bfe7e197f3c36))
* prevent claude probe failed ([06ea52b](https://github.com/Thomas97460/quota-tracker/commit/06ea52b67f679efb479915d983e05aa8190ed101))
* restore Python 3.13 compatibility ([76a2fe9](https://github.com/Thomas97460/quota-tracker/commit/76a2fe95a8d8c4b22bc137df4bf8f17a23835f56))
* startup script ([644e4ae](https://github.com/Thomas97460/quota-tracker/commit/644e4ae269aa47bae18369e37847ae8951808d01))
* trust only live quota probe from code providers ([8d2ad89](https://github.com/Thomas97460/quota-tracker/commit/8d2ad89e7aad02145424f6e40d90fd6e532ea7d4))
* update by front ([be10b8a](https://github.com/Thomas97460/quota-tracker/commit/be10b8ac54e7d88200018e6f16f5e722c8a53d5d))
* update popu^ ([abdcd93](https://github.com/Thomas97460/quota-tracker/commit/abdcd9314ed06dff44d20ff10c73b400f4e2d9f9))
* update popup ([895854d](https://github.com/Thomas97460/quota-tracker/commit/895854d0639433adac44c314eb946a19e666bddb))
* update popup ([309beff](https://github.com/Thomas97460/quota-tracker/commit/309beff279ecded4ab3946c8a6b25f311850809d))
* update via UI ([d782f03](https://github.com/Thomas97460/quota-tracker/commit/d782f03caed9528e22d8f4e54ac7c5087dce3e26))

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
