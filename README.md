# Sovereign AI Compute Planner (v0.2, draft)

Planning tool for governments: from AI use cases to tokens, GPUs, megawatts, placement by data class, and a 10-year cost range. Planning-grade, not engineering design.

**Status:** private draft. Not cleared for publication. Do not share outside the core team until clearance.

## Flow

1. **Layer 0, use cases.** The user picks applications from a catalogue, sets stage (Pilot/Production) and data class.
2. **Layers 1-3, tokens.** Users → sessions → input / cached / output tokens (reasoning, agent steps, retries) → peak tokens/s. Method: NVIDIA AI Tokenomics worksheet [S01], input and output kept separate [S07].
3. **Placement.** Each application goes to the tier of its highest data class (high-water mark). An optional traffic split routes part of an application to another class. Class → tier mapping is set once per country [S13, S14].
4. **Layer 4, sizing.** Peak tokens/s ÷ (tokens/s per GPU × production derating) → GPUs → IT kW → facility MW (PUE) [S02, S03]. Batch work fills idle GPU-hours first. Hardware is picked automatically: air-cooled on weak grids or small loads.
5. **Layer 5, TCO.** API, GPU-as-a-service and Owned, each only where the tier allows it. Shown as a low / base / high range; client quotes replace the range [S03, S12].
6. **Ladder.** Step 0 cloud now, Step 1 small sovereign node, Step 2 dedicated capacity via a private operator or PPP.

## What the user provides

1. **Setup:** country (grid and tariff), adoption scenario, placement rules (data class → tier), optional client quotes.
2. **Applications, one by one:** pick a type (staff copilot, citizen assistant, document extraction, process agent, research agent, speech-to-text, OCR, biometrics...), enter the volume the client knows (staff with access, documents per day, audio hours per day...) and the data class.
3. **Results:** GPUs, MW and 10-year cost by tier, with the recommended step.

Usage rates, token sizes, peaks and GPU-seconds come from the type (`data/catalogue/archetypes.yaml`), each with its evidence and a confidence level, shown in the Evidence tab. Any of them can be overridden per application under Advanced.

## What the tool gets itself

| Input | Source | How |
|---|---|---|
| Population, internet use, outages, labour force, unemployment | World Bank API (WDI) | `sync/worldbank.py`, weekly |
| Public employment share | World Bank Worldwide Bureaucracy Indicators | same, API source 64 (code to verify on first run) |
| API prices per model class | OpenRouter `/api/v1/models` | `sync/openrouter.py`, weekly, median of reference models |
| EGDI | UN E-Government Survey | curated `data/egdi.csv` (no API, biennial) |
| Electricity tariff | utility / GlobalPetrolPrices | curated `data/electricity.csv` (no free API) |
| PUE, derating, facility cost, refresh | cited defaults | `data/catalogue/defaults.yaml`, reviewed yearly |

The sync runs in GitHub Actions (`.github/workflows/sync.yml`) and commits a dated snapshot. The app reads snapshots only, so it works on servers without outbound internet (Posit Connect).

## Known gaps (v0.1)

- **Use-case token shapes and adoption are analyst defaults**, not data. Next: upload of pilot gateway logs to replace them.
- **GPU throughput** for S and M model classes and GPU capex are placeholders. Next: sync from public benchmark data (InferenceMAX, MLPerf) once formats and licences are confirmed.
- Demand is flat over the horizon; no growth curve, no discounting.

## Run

```bash
pip install -r requirements.txt
python -m pytest -q          # engine must reproduce reference/Sovereign_AI_Compute_Planner_v0.1.xlsx
shiny run app.py             # http://127.0.0.1:8000
```

Deploy to Posit Connect: `rsconnect deploy shiny . --entrypoint app:app`.

**GitHub Pages (no server).** `.github/workflows/pages.yml` exports the app with Shinylive on every push to `main`: Python runs in the visitor's browser (WebAssembly), nothing is sent to a server. Enable it once in Settings → Pages → Source: GitHub Actions. First load takes 20-40 seconds.
Note: on GitHub Free/Pro, a Pages site is public even when the repo is private.

Local static test: `shinylive export . site && python -m http.server --directory site 8008`.

## Layout

```
engine/        pure-Python model (no UI), mirrors the Excel formula by formula
data/catalogue use cases, non-token workloads, hardware, defaults, sources (YAML, every value sourced or flagged)
data/snapshots synced country data and API prices (JSON, written by sync/)
sync/          World Bank and OpenRouter sync scripts
app.py         Shiny for Python interface
reference/     the Excel v0.1 and its generator, the audited reference
tests/         engine vs Excel, split, weak grid, quotes
```
