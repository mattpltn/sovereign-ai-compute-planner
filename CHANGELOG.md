# Changelog

All notable changes to the Sovereign AI Compute Planner. Format: [Keep a Changelog](https://keepachangelog.com/). Dates are UTC.
Every change to the model, defaults or sources must also update `docs/METHODOLOGY.md` (see `CLAUDE.md`).

## [Unreleased]

## [0.9.3] - 2026-11-17
### Added
- Two downloads on the results page: a summary CSV (each application and the portfolio under the four options) and the full calculation as a ZIP of CSV files with a README (inputs, tokens per application, demand by year, capacity, kW and energy by year, yearly costs by item with discount factors, every assumption with its source).
- Per-unit cloud API prices for other AI work in the API option: speech-to-text per audio hour, text-to-speech per audio hour, OCR per page, face verification per call, retrieval indexing per chunk (sources S76-S81).
### Changed
- The API option no longer prices other AI work as rented GPU-hours. Biometric deduplication, image and satellite analysis and fine-tuning are marked as not available as an API (†) and priced as rented GPUs; below 0.25 GPU they run on existing servers.

## [0.9.2] - 2026-11-17
### Added
- Results: a collapsed "For specialists: tokens and sizing factors" section. Per application: model size, requests per day, tokens per request (input, output, cached share), tokens per day at start, tokens per year in year 10, peak equivalent tokens per second, active days. Other AI applications: GPU-seconds per unit and GPU-hours per day. Plus the factors applied (retries and agent steps, prefill weight, peak factors, pooling, throughput per GPU, API prices).

## [0.9.1] - 2026-11-17
### Changed
- Own data centre is built with 30% spare capacity above the peak installed IT load (`facility_buffer`); facility maintenance stays at 5% of the build cost per year.
- Own data centre build cost now follows a size curve ($40M per MW at 0.1 MW down to $12M per MW at 50 MW, analyst assumption), scaled to each country by its Turner & Townsend cost relative to the global default. Small rooms are no longer priced at large-facility rates.
- Results page shows Base figures in US dollars rounded to the dollar, without price ranges; the CSV export gives one 10-year figure per option.
### Fixed
- Middle East, North Africa, Afghanistan & Pakistan countries used the global default PUE and construction cost because the region name did not match the World Bank data; they now use the regional values.
- GitHub Pages: the app failed to start because the Shiny version loaded in the browser needs pydantic; added to requirements.txt.

## [0.9.0] - 2026-11-17
### Added
- Each application has a start year (1-10) and a growth rate per year. Demand is zero before the start year and grows from it.
- Results compare four delivery options over 10 years: API, GPU rental (GPU-as-a-service), owning servers in a commercial colocation data centre, and owning servers in the government's own data centre. Shown for each application (priced on its own) and for the whole portfolio.
- Portfolio capacity is sized year by year on the combined, pooled load: servers are bought as the combined need grows, replaced after five years and never sold, so spare capacity is shared and not added up. The table shows the saving against buying each application alone.
- Colocation price per kW of IT per month by country or region (CBRE 2026 wholesale benchmarks, regional assumptions where none exist, x1.8 below 250 kW), with sources S69-S73 and a client-quote override.
- Owned options: servers by year chart and a breakdown of where the money goes (GPU servers, software, maintenance, staff, energy, colocation fee or facility build).
- Note on every results page: hosting and data regulation are not assessed; the client must check which options its rules allow for each application.
- Setup: "existing facility has spare power and cooling" removes the build cost from the own-data-centre option.
### Changed
- Data class, traffic split, placement rules and the in-country capability questions are no longer asked; placement remains in the engine (and Excel parity tests) but not in the results.
- The global demand growth setting is replaced by per-application growth; older saved scenarios apply their global rate to every application.
- Results CSV now lists each application and the portfolio under each option, Low / Base / High.

## [0.8.0] - 2026-11-16
### Added
- Setup: "In-country capability" questions. GPU provider (moved here); cloud with acceptable data residency (in-country, regional, none: with none, Internal data stays in-country); can a government data centre host GPU servers (ready: no facility build cost; fit-out or none: cost included); commercial colocation in-country (Confidential servers in colocation, Step 2 wording). Saved with the scenario; defaults keep earlier results.
### Changed
- One vocabulary for locations everywhere: Offshore cloud (API), Cloud with data residency (API or rented), In-country GPU provider (rented), Government data centre, Government-owned servers in private colocation. "Sovereign site" is no longer used. Site cards are titled by location and the data classes they serve.
- Tier names: T1 Offshore cloud or API; T2 Cloud with data residency; T3 In-country, private provider (government data centre if none); T4 Government data centre.
- Warnings explain when there is no in-country GPU provider (Confidential data on government-owned servers) and when Internal data is kept in-country.
- Step 1 and Step 2 wording follow the government data centre and colocation answers.
- Raw CSV adds the location.

## [0.7.1] - 2026-11-16
### Fixed
- Data sync failed at its test step: two agriculture tests read the freshly synced Estonia share instead of their own fixture. The sync itself had worked (all three agriculture indicator codes confirmed against API metadata; outages per month found for 145 countries).
- GitHub Actions moved to checkout v5 and setup-python v6 (Node.js 20 deprecation).

## [0.7.0] - 2026-11-16
### Added
- Agriculture advisory: "Who are these farmers?" choice. Everyone eligible keeps the Kisan e-Mitra rates (0.00015 / 0.0005 / 0.002); farmers using the advisory service use 0.05 / 0.1 / 0.3 per farmer per day (assumption, Low confidence). Saved as `population_basis`; older scenarios load as "everyone eligible" with identical results. Shown next to the volume in the results.
- Agriculture advisory volume check against estimated agricultural workers (employed labour force x ILO modeled agriculture share, World Bank WDI, S68). Warns above 1.5x (`agri_volume_tolerance`, global default). No check when the data is missing or older than 2015.
- Sync: SL.AGR.EMPL.ZS, SL.TLF.TOTL.IN and SP.RUR.TOTL are confirmed against live API metadata before use; code, name and source are recorded in the snapshot. Run the sync once to fill the new values.
- Information note when a citizen assistant, agriculture advisory or tutor makes fewer than 100 requests per day.
- Owned capacity: 10-year cost split into GPU servers, GPU software and maintenance, facility, energy and staff, so a client using colocation or an existing room can read the GPU part alone. Also in the raw CSV.
- Custom application types: CSV template to download, fill and upload; rows are validated and saved with the scenario.
- Save and resume: each save creates a timestamped link carrying the whole scenario; saved versions are listed in the browser with open, copy and remove.
- Evidence tab: source IDs in the evidence link to the Sources list; each type lists its sources. Same internal links in the methodology.
- The application type list shows the evidence confidence of each type.
- Cost by application shown two ways: share of the site (as before) and extra cost if added last, with a note that shares spread fixed costs and are not savings.
- Placement warning states the effect of moving applications above their default tier versus the default placement: servers added and change in 10-year cost.
- Owned site cards show the headroom at the busiest hour; the scenario table notes when the high end of the price range adds a server.
### Fixed
- Setup country line failed for countries without a public employment share (e.g. the example country).

## [0.6.1] - 2026-11-16
### Fixed
- Outage data: the sync had stored the share of firms experiencing outages (% of firms, IC.ELC.OUTG.ZS) as outages per month, so Ghana showed 74 "outages per month". The two measures are now separate fields. Outages per month decide when available; otherwise the grid is weak if at least 50% of firms report outages (assumption, Low confidence).
- Public employment share (WWBI) was divided by 100 twice, so civil servant reference sizes were 100x too small (Ghana ~8,000 instead of ~815,000). Current snapshot corrected; the sync no longer divides.
- The site now redeploys after each data sync (bot commits did not trigger the Pages workflow).
### Changed
- Setup country line shows which outage measure is used and its year, and the estimated number of civil servants.

## [0.6.0] - 2026-11-16
### Changed
- Usage rates are now per **active day** (working day 250, school day 190, clinic day 300, calendar day 365 for always-on services). Peak sizing uses the active-day rate; annual tokens and API cost use active days per year instead of 365. Office tools and per-item office workloads now cost about 30% less per year in API mode; GPU sizing is unchanged.
- Clinical decision support: 3 / 10 / 20 → 0.3 / 1 / 3 queries per worker with access per day, anchored on OpenEvidence (37.1 queries per active physician-month, JAMA 2026, S62). One query per consultation is kept as an override scenario.
- Teacher assistant: 0.7 / 1.4 / 3.6 → 0.34 / 1 / 2 per school day, from the EEF/NFER trial (about a third of lessons prepared with AI, S63); volume confidence Low → Medium.
- Student tutor restated per school day: 0.07 / 0.19 / 1.08 per calendar day → 0.1 / 0.27 / 1.5 per school day (same annual order of magnitude).
- OCR: 0.3 → 0.75 GPU-seconds per page, from the PP-OCRv5 A10 benchmark (S64).
- Units made explicit: retrieval indexing per 500-token chunk after overlap; image analysis per model-specific image chip; item volumes per working or clinic day.
- Staff copilot evidence: Base 1.4 described as a scenario estimate; the 0.8 factor is a scenario adjustment, not a validated bias correction.
### Added
- Each application type states the basis of its figures (observed, derived, assumption, uncalibrated, client), shown in the Evidence tab and the methodology.
- Coding assistant, research agent, biometric deduplication and image analysis marked uncalibrated, with calibration routes.
- Face verification and text-to-speech evidence (InsightFace-REST S65, Kokoro benchmarks S66); DWP Copilot evaluation (S67).
- Methodology: agent token totals stated with and without the ×1.1 retry (3,740 / 18,150 / 55,000 with it).

## [0.5.1] - 2026-11-16
### Fixed
- Server rounding now reaches the physical figures: for owned capacity, GPUs are rounded to whole servers before IT load, facility power, racks, energy and utilisation are calculated (previously only the cost used the rounded count).
- Raw CSV export: adds servers and facility kW; GPUs, kW and racks are blank for API tiers, with a separate "notional_gpus_if_api" column; file renamed and labelled as raw.
- Details table shows "service" instead of GPUs for API tiers, and "N (S servers)" for owned capacity.
- Outage data sync: the Enterprise Surveys indicator left WDI, so the sync now finds it by name across all World Bank databases. Until the sync is re-run, every country shows the grid as "Unknown".
### Added
- Results flag applications placed above their default tier by the placement rules.
### Changed
- Presenter summary: the price range is "typically ±30–40%, prices and GPU efficiency only"; adoption uncertainty is separate and often larger.
- Methodology: staff formula worded per owned site (Confidential and Restricted share one by default); shared-site rule states pooling, server rounding and the single 2-FTE minimum after the merge; duplicate table header in Section 12 removed.

## [0.5.0] - 2026-11-16
### Added
- Results page rebuilt around the client's three questions: a two-line answer banner; "How much will it cost?" with the three adoption scenarios stacked by data class and a price-range whisker; "What needs to be built or bought?" with one card per destination (servers, GPUs, power, upfront capex, annual running cost, rent alternative); "Where does the cost come from?" by application. Detailed tables collapsed below.
- Setup: "Is there an in-country GPU cloud provider?" (default no / not sure) and "Confidential and Restricted data share one secure site" (default on).
- Methodology: one-page summary for presenters; facility tables and site calibration moved to Annex A, hardware evidence and vendor claims to Annex B.
### Changed
- Owned capacity is rounded to whole servers (8 GPUs per HGX server, 72 per NVL72 rack); power and cost follow.
- Confidential work moves into the Restricted site when both would be owned: one facility, one team, pooled servers.
- The recommended step is worded after the buying option chosen (e.g. "rent GPUs from an in-country provider", "own 2 servers in an existing secure server room"); cloud and API tiers show no GPUs or racks.
- Hardware is chosen by the cost of the cheapest allowed option, so owned-only tiers compare ownership cost, not rental price.
- B200 power 1.7 → 2.0 kW per GPU (DGX B200 14.3 kW per 8 GPUs, S60); H200 large-model points taken from the same InferenceX comparison as B200 (625 / 819 / 1,591).
- Tutor rate 0.27 → 0.19 (Khanmigo weekday figure x 5/7); speech-to-text 6 → 12 GPU-seconds per audio hour (Baseten figure read per 8-GPU node).
- Agriculture advisory now uses per-farmer rates anchored on Kisan e-Mitra; the Farmer.Chat "61% meaningful users" is an impact measure, not usage (S61).
- Unverified examples removed from the evidence (Peru teacher pilot, emergency line); the voice agent example is now a government service line, with a note that 24/7 lines need a flatter peak.
### Fixed
- Changelog 0.3.0 had two "Changed" headings: the second block is now version 0.2.2.
- Methodology: Section 2 diagram lists the current steps; Section 10 no longer says derating applies to measured figures; worked example is rounded; CSV export labelled as raw.

## [0.4.0] - 2026-11-16
### Added
- Facility model by country and cooling: PUE by World Bank region (Uptime Institute) with a site PUE override; liquid cooling cuts non-IT power by 18% (NVIDIA/Vertiv); construction cost per watt from the Turner & Townsend index for 13 markets, regional proxies otherwise; liquid-cooled facility multiplier 0.90 / 1.085 / 1.10. Instructions to calibrate a site with the Schneider Electric TradeOff Tools.
- Rent-or-own table: API and GPU rental per year next to owned upfront capex, annual running cost and GPU refresh.
- Charts: 10-year cost by data class (with range) and by application.
- Six application types: clinical safety net (Penda Health model), teacher assistant, agriculture advisory, voice agent, text-to-speech, retrieval indexing.
- Throughput uncertainty (x1.3 / 1.0 / 0.75) inside the Low / Base / High range; GPU and MW ranges shown.
### Changed
- Results rounded to two significant figures and shown as "about X, range A–B"; power shown in kW below 1 MW.
- Owned staff: 2 FTE per site + 1 per 100 GPUs.
- Speech-to-text 60 → 6 GPU-seconds per audio hour (batched Whisper, Baseten); tutor rate from Khanmigo usage (0.27 per student with access per day, 15% engage); Pair added as a third copilot reference.

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

## [0.2.2] - 2026-11-16
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
