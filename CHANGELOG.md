# Changelog

All notable changes to the Sovereign AI Compute Planner. Format: [Keep a Changelog](https://keepachangelog.com/). Dates are UTC.
Every change to the model, defaults or sources must also update `docs/METHODOLOGY.md` (see `CLAUDE.md`).

## [Unreleased]

## [0.2.1] - 2026-11-16
### Added
- `docs/METHODOLOGY.md`: full method, formulas, evidence per application type, defaults, hardware, worked example and sources. Tables are generated from the catalogue by `docs/build_methodology.py`; CI fails if the document is out of date.
- `CHANGELOG.md` and `CLAUDE.md` (maintenance rules).

## [0.2.0] - 2026-11-16
### Added
- Application builder: applications are added one by one (type, name, volume, data class). Volumes are client inputs, no longer derived from population.
- 16 application types in `data/catalogue/archetypes.yaml` (10 generative AI, 6 non-LLM), each with sourced defaults, evidence and confidence (volume / size).
- Per-application overrides: usage rate, model size, traffic split by data class.
- Setup: grid reliability override, electricity tariff override.
- Evidence tab listing every default and its source.
### Changed
- New interface (Setup, Applications, Results, Evidence). Results show GPUs, MW and a 10-year cost range.
- Price sync matches model id prefixes; missing model sizes fall back per size instead of all-or-nothing.
### Fixed
- Edits not changing results (editable table replaced by form inputs).

## [0.1.2] - 2026-11-16
### Added
- Sources S31-S43: Azure production traces, OpenRouter State of AI, BurstGPT, Mooncake, Anthropic multi-agent, UK GDS, Australia DTA, Singapore Pair, NBER ChatGPT usage, Kisan e-Mitra, Anthropic Economic Index, TraceLab, EpiQAL.
### Changed
- Use-case defaults recalibrated to those sources. Example country: 273 → 176 GPUs, 0.74 → 0.48 MW. Largest corrections: citizen assistant (~3.5x lower) and agriculture advisory (~8x lower).
### Fixed
- CI: shinylive version pin; World Bank sync retries, longer timeout, fallback outage indicators.

## [0.1.1] - 2026-11-16
### Added
- Static deployment to GitHub Pages (Shinylive, runs in the browser).

## [0.1.0] - 2026-11-16
### Added
- Python engine reproducing `reference/Sovereign_AI_Compute_Planner_v0.1.xlsx` (tests).
- World Bank and OpenRouter weekly sync (GitHub Actions).
- Shiny for Python app, Posit Connect ready.
