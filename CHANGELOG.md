# Changelog

All notable changes to the Sovereign AI Compute Planner. Format: [Keep a Changelog](https://keepachangelog.com/). Dates are UTC.
Every change to the model, defaults or sources must also update `docs/METHODOLOGY.md` (see `CLAUDE.md`).

## [Unreleased]

## [0.3.0] - 2026-11-16
### Changed
- Pooling factor D now depends on the number of applications in the tier: 1 for a single application, D(n) = 0.6 + 0.4/√n otherwise (was a flat 0.7 everywhere).
- Throughput per GPU is a Low / Base / High range tied to a response-speed target (Fast ~130, Standard ~95, Relaxed ~55 tok/s per user), from InferenceX [S44]. The 0.6 production derating no longer applies to measured figures; it remains for derived figures and non-LLM placeholders.
- Costs are present values over 10 years, with discount rate (default 8%), demand growth and market price decline (default 0%) as Setup inputs. GPUs are re-bought at each refresh for the demand at the end of the cycle.
- Owned staff sized to the deployment: 1 FTE + 1 per 100 GPUs (was a flat 4 FTE per tier).
- Cached input tokens are priced at 10% / 25% / 50% of the input price (Low / Base / High) instead of free [S46, S47].
- Ladder: Step 1 below 1 MW; new Step 2 colocation in an existing commercial data centre for 1-10 MW; PPP / IFC dedicated facility only from 10 MW (Step 3).
### Added
- Results show every allowed buying option across Low – Base – High, mark the cheapest, and flag tiers where the cheapest option changes within the range.
- "Below GPU threshold" outcome for tiers with only tiny non-LLM workloads (< 0.25 GPU).
- Volume check at entry against civil servants or population, with a warning in the portfolio list.
- Results show the number of applications and the pooling factor per tier.
### Fixed
- Missing or pre-2020 outage data now shows the grid as "Unknown" (air-cooled assumed), never "OK".
### Changed
- Hardware throughput recalibrated to independent benchmarks (SemiAnalysis InferenceX [S44], MLPerf v5.1 [S45]) at a fixed interactivity (~90-95 tok/s per user for large reasoning models, ~75 for 70B). Liquid (GB300 NVL72) vs air (H200) gap on the large model: 65x (NVIDIA claim) → 7.3x per GPU. P1 H200: L 90 → 779, M 800 → 1,930 tok/s per GPU; kW per GPU 1.7 → 1.4. P2 rental price scaled to the ownership cost ratio ($4.92/GPU-hour).
- Automatic hardware choice: among allowed profiles (air-cooled only on weak grids or below 1 MW), picks the lowest GPU-hour cost for each tier.
- Review corrections: staff copilot Base rate 1.8 → 1.4 (UK survey shares scaled by the 80% of licence holders active monthly), Low 0.85 → 0.7; citizen assistant Low 0.0002 → 0.00015 (Kisan e-Mitra midpoint); agent multipliers stated exactly (4.9x, 14.7x); tutor and rate units defined; P1 rental vs ownership cost clarified; kW per GPU explained (1.275 kW server only vs 1.4 kW all-in).
- Methodology application table now shows burst, SLA headroom and seasonal factors.
### Added
- Profile P3: HGX B200, air-cooled (newer silicon without liquid cooling).
- Methodology section "Vendor claims versus independent benchmarks"; per-profile evidence.
- `tests/fixtures/hardware_v01.yaml` keeps Excel parity.

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
