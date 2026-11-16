# Sovereign AI Compute Planner: Methodology

Version 0.2 (draft). Planning-grade estimates for early discussions with governments. It does not replace an engineering design or a procurement specification.

## 1. Purpose and scope

The tool answers four questions for a government:

1. How much AI compute will our planned applications need?
2. Where may each application run, given its data sensitivity?
3. What is the cheapest allowed way to buy that compute over 10 years?
4. What should we do first?

**In scope:** GPU compute for generative AI (language models, measured in tokens), other deep-learning workloads (speech-to-text, OCR, biometrics, image analysis), and model fine-tuning.

**Out of scope:** core digital public infrastructure (ID, payments, data exchange) and classical machine learning scoring. These run on CPUs and are sized with conventional data centre capacity tools.

The approach follows the World Bank's hybrid guidance for government cloud: use commercial cloud where the data allows it, and build local capacity only where sovereignty requires it [S13, S14].

## 2. Overview of the calculation

```
Applications (type + volume + data class)
   │  Layer 0: requests per day
   ▼
Tokens per request (input, cached input, output, reasoning)          Layer 1-2
   │
Daily tokens → peak tokens per second                                 Layer 3
   │
Placement: data class → tier (T1 public cloud ... T4 government enclave)
   │
GPUs per tier → IT kW → facility MW → energy                         Layer 4
   │
10-year cost per allowed buying mode → cheapest option                Layer 5
   │
Recommended step (0 cloud now, 1 small sovereign node, 2 dedicated capacity)
```

The token layers follow the structure of the NVIDIA AI Tokenomics worksheet [S01], with two corrections: input and output tokens are kept separate, because they load the hardware differently [S07], and the system prompt is added to input before cache savings are removed.

## 3. Inputs

### 3.1 What the user enters

| Input | Where | Notes |
|---|---|---|
| Country | Setup | Sets grid reliability and electricity tariff (both can be overridden). |
| Adoption scenario | Setup | Low / Base / High usage rate for each application type. |
| Placement rules | Setup | Which tier each data class may use. Set once per country from its data protection law. |
| Client quotes (optional) | Setup | GPU rental price, GPU server cost, data centre build cost. A quote replaces the default range. |
| Applications | Applications | One by one: type, name, volume, data class. Optional: usage rate, model size, traffic split. |

The volume is always something a client can give: staff with access, people in the target population, documents per day, audio hours per day. The tool never derives it from population statistics.

### 3.2 What the tool provides

Each application type carries defaults for usage rate, request size, peak pattern and model size, each with its evidence and a confidence level (Section 9). Country data (population, internet use, outages) is synced weekly from the World Bank API; API prices are synced weekly from OpenRouter [S21]. Electricity tariffs and EGDI are curated tables because no free API exists.

## 4. Layer 0: requests per day

For each application:

```
requests per day = volume × rate(scenario)
```

- For types measured in **people** (staff copilot, citizen assistant, tutor, health, coding, research agent), `rate` is requests per person with access per day. It already includes the fact that most people with access are not active every day.
- For types measured in **items** (documents, texts, calls, cases), `rate` = 1: each item is one request.
- The user can override `rate` per application under Advanced.

Example: the staff copilot rate of 1.8 comes from the UK cross-government trial, where 39% of 20,000 civil servants used Copilot several times a day and 43% several times a week [S36]: 0.39 × 4 + 0.43 × 0.5 ≈ 1.8.

## 5. Layers 1-2: tokens per request

A request is one task. A task may need several model calls (agents) and some retries.

```
k              = calls per task × retry multiplier
input          = (input tokens per call + system prompt tokens) × k
cached input   = system prompt tokens × cache hit rate × k
output         = (output tokens per call + reasoning tokens per call) × k
```

Reasoning tokens are generated tokens and cost the same as output [S32].

Daily totals are requests per day × each of the three values.

Because generating an output token costs much more GPU time than reading an input token, the tool converts everything to **equivalent output tokens**:

```
daily equivalent tokens = daily output + (daily input − daily cached input) × prefill weight
```

Prefill weight default: 0.15 [S03, S07]. If throughput per GPU is calibrated with AIConfigurator at the real input and output lengths, prefill is already inside the measured figure and the weight can be lowered.

**Sanity check:** tokens per user per day above ~240,000 (the volume a person processes in a working day, Epoch AI [S24]) are flagged. Agents may exceed it legitimately.

## 6. Layer 3: peak load

GPUs are sized for the busiest moment, not the daily average.

```
average tokens/s = daily equivalent tokens / 86,400
peak tokens/s    = daily equivalent tokens × peak share / (peak window hours × 3,600)
                   × burst × SLA headroom × seasonal factor
```

- **Peak share / window:** share of daily traffic in the busy hours (e.g. 80% in 8 office hours).
- **Burst:** short spikes above the busy-hour average. Production LLM traffic is bursty [S33].
- **SLA headroom:** spare capacity to keep response times stable. Kept low (1.1) because burst already covers most spikes.
- **Seasonal:** planting season, tax deadlines, epidemics.

## 7. Placement

Each application runs in the tier of its data class (the "high-water mark": the most sensitive data it touches decides). The default mapping follows the World Bank data classification approach [S14]:

| Data class | Example | Default tier |
|---|---|---|
| 1 Public | open data, public information | T1 public cloud or API, offshore allowed |
| 2 Internal | non-sensitive government data | T2 cloud with in-country or regional residency |
| 3 Confidential | personal and confidential data | T3 sovereign local, privately operated |
| 4 Restricted | health, social protection, tax, security | T4 government enclave, state-operated |

**Traffic split (optional).** If an application routes sensitive requests separately (e.g. 90% public questions, 10% personal cases), the user enters a split such as `1:0.9, 3:0.1`. Each part is sized in its own tier. This often decides whether a local node is needed at all.

## 8. Layer 4: GPUs, power, energy

Calculated separately for each tier.

**Language-model GPUs.** Peaks of all applications in a tier are added per model size (S, M, L) and multiplied by the diversity factor D, because applications do not peak at the same moment:

```
diversified peak(size) = Σ peak tokens/s of applications of that size × D        (D = 0.7)
LLM GPUs = roundup( Σ over sizes [ diversified peak(size) / tokens/s per GPU(size) ] / production derating )
```

- **Tokens/s per GPU** comes from the hardware profile (Section 10). It must be calibrated with AIConfigurator for the real model, input and output lengths and latency target [S04, S05].
- **Production derating** (0.6): benchmark results overstate what a production service achieves [S11]. Calibrate with GenAI-Perf on a real endpoint [S06].

**Non-LLM GPUs.**

```
GPU-hours per day = units per day × GPU-seconds per unit / 3,600 / derating
peak GPUs (interactive only) = units per day × GPU-seconds per unit × peak share / (window × 3,600) × burst / derating
non-LLM GPUs = roundup( Σ peak GPUs × D )
```

**Batch work fills idle time first.** Batch workloads (OCR, deduplication, image analysis, fine-tuning) use idle GPU-hours of the interactive fleet before any extra GPU is added:

```
busy GPU-hours/day  = Σ average tokens/s / tokens/s per GPU / derating × 24 + interactive non-LLM GPU-hours
idle GPU-hours/day  = max(0, (LLM GPUs + non-LLM GPUs) × 24 − busy)
extra GPUs          = roundup( max(0, batch GPU-hours − idle) / 24 )
total GPUs          = LLM GPUs + non-LLM GPUs + extra GPUs
utilisation         = min(1, (busy + batch) / (total GPUs × 24))
```

**Power and energy.**

```
IT load (kW)          = total GPUs × kW per GPU (all-in, includes CPU, network, storage share)
facility power (MW)   = IT load × PUE / 1,000                          (PUE 1.6) [S22]
racks                 = roundup(IT load / rack kW)
annual energy (MWh)   = IT load × (idle fraction + (1 − idle fraction) × utilisation) × PUE × 8,760 / 1,000
```

**Hardware choice (automatic).** If the grid is weak (more than 1 outage per month, World Bank Enterprise Surveys [S19], or set by the user) or the tier's IT load is below 1 MW, the tool uses the air-cooled profile. Dense liquid-cooled racks (above 100 kW per rack) need a reliable grid and a specialised facility. The user can force a profile.

## 9. Application types and their evidence

Each default below has a source or is marked as an assumption. Confidence: **High** = direct measurement or client data, **Medium** = indirect evidence or a derivation, **Low** = assumption to replace with client data.

{{TYPES}}

### How the agent sizes were checked

Anthropic reports that a single agent uses about 4 times the tokens of a chat interaction, and a multi-agent system about 15 times [S35]. The process agent is sized at about 5 times a copilot request and the research agent at about 16 times. The test suite enforces both ranges.

### How the citizen assistant rate was checked

India's Kisan e-Mitra chatbot answers 8,000-20,000 queries per day for about 93 million PM-KISAN beneficiaries [S40], i.e. about 1-2 queries per 10,000 people per day. The citizen assistant Low rate equals Kisan e-Mitra; Base is 2.5 times higher and High 10 times higher, for assistants that cover several services.

## 10. Hardware profiles

{{HARDWARE}}

Profile P1 throughput for large reasoning models (90 tokens/s per GPU) and the power per GPU come from NVIDIA's cost-per-token analysis (H200, DeepSeek-R1, 54,000 tokens/s per MW) [S02] and the DGX H100/H200 power rating of 10.2 kW per 8-GPU server [S10]. Profile P2 figures are NVIDIA vendor claims [S02]. Small and medium model throughput and capex per GPU are placeholders until calibrated with AIConfigurator and vendor quotes. The hardware choice changes the MW result by up to ~50 times for the same demand [S02], so it is treated as a policy decision tied to the grid.

## 11. Layer 5: 10-year cost

For each tier, the tool computes the cost of every buying mode the tier allows (Section 7 table), then picks the cheapest. Undiscounted, demand held flat over the horizon, in USD. Structure follows NVIDIA's inference cost method [S03] and the FinOps Foundation AI cost estimation guidance [S12].

```
API / managed (per year)   = Σ [ uncached input (M) × API input price + output (M) × API output price ] × API multiplier
                             + (non-LLM GPUs + extra batch GPUs) × 8,760 × $/GPU-hour
GPU-as-a-service (per year) = total GPUs × 8,760 × $/GPU-hour
Owned (capex over horizon)  = total GPUs × capex per GPU × roundup(horizon / refresh years) + IT MW × facility cost per MW
Owned (opex per year)       = energy MWh × 1,000 × tariff + GPUs × software per GPU
                             + staff (4 FTE × cost per FTE, if any GPU) + maintenance 5% × (GPU capex + facility capex)
10-year total               = per-year cost × 10   (Owned: capex + opex × 10)
$ per million tokens        = cheapest 10-year cost / (annual equivalent tokens × 10)
```

Every cost item has a Low / Base / High value. The tool shows the 10-year cost of the cheapest option in all three, as a range. A client quote replaces the range for that item.

## 12. Recommended step (the ladder)

| Condition | Step |
|---|---|
| Tier T1 or T2 | **Step 0:** use cloud or API now, under residency terms where required. |
| Tier T3 or T4, facility power below 1 MW | **Step 1:** small sovereign inference node in an existing facility. |
| Tier T3 or T4, facility power 1 MW or more | **Step 2:** dedicated capacity through a private operator or PPP (IFC-investable). |

Triggers to move up a step: a confidential or restricted application reaches production; measured utilisation of a Step 1 node stays above ~60% for two quarters; the grid check shows a warning (budget backup and storage before committing capex).

## 13. Worked example

{{EXAMPLE}}

## 14. Global defaults

{{DEFAULTS}}

## 15. Data sources and automatic updates

| Input | Source | Update |
|---|---|---|
| Population, internet use, labour force, unemployment | World Bank API (WDI) [S29, S15] | Weekly, GitHub Actions (`sync/worldbank.py`) |
| Public employment share | World Bank Worldwide Bureaucracy Indicators [S18] | Weekly (API source 64) |
| Electrical outages per month | World Bank Enterprise Surveys [S19] | Weekly; indicator moved in 2026, fallbacks tried |
| API prices per model size | OpenRouter model list [S21] | Weekly (`sync/openrouter.py`), median of reference models |
| EGDI | UN E-Government Survey [S17] | Curated `data/egdi.csv`, every two years |
| Electricity tariff | Utility tariff sheets, GlobalPetrolPrices [S20] | Curated `data/electricity.csv` |

Each synced value keeps its indicator code and year. The app reads stored snapshots only, so it also works on servers without internet access.

## 16. Limitations

- **Usage rates for several types are assumptions** (marked Low). They should be replaced with client data or pilot logs.
- **Pilot calibration is the next step.** Public data gives starting values, not a forecast for a specific client. A pilot's gateway or tracing export can replace measurable values: requests per day, model mix and token sizes from timestamps and token counts; active users from stable user IDs; calls per task from session or trace IDs. Adoption still needs the number of eligible users from the client, and task success needs outcome labels.
- **Hardware throughput** for small and medium models and **GPU-seconds for non-LLM workloads** are placeholders until calibrated (AIConfigurator, MLPerf [S08]).
- **Demand is flat** over 10 years: no growth curve, no discounting.
- **Vendor figures** (NVIDIA) are used for structure and calibration ranges, not as final values.
- **Placement** is a policy decision. The tool applies the rules the user sets; it does not interpret the law.

## 17. Sources

{{SOURCES}}

Additional sanity-check tools (not used as sources): AI-DC calculator, Netray, GPUAdvisor.
