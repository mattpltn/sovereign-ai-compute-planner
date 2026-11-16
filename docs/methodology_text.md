# Sovereign AI Compute Planner: Methodology

Version 0.5 (draft). Planning-grade estimates for early discussions with governments. It does not replace an engineering design or a procurement specification.

## Summary for presenters (one page)

**What the tool estimates.** For a government's planned AI applications: the 10-year cost (present value, with a range), the capacity to build or buy, and how that cost splits by application. It is a planning-grade estimate to open a conversation, not an engineering design or a procurement specification. The price range shown is typically ±30–40%; it covers prices and GPU efficiency only. Adoption uncertainty is shown separately, as three scenarios, and is often larger.

**The four inputs that matter.**
1. *The applications and their volume*: who uses each one and how many (staff with access, documents per day, citizens served). This is the single biggest driver.
2. *The data class of each application*: it decides where the application may run (public cloud, in-country cloud, sovereign site).
3. *The country*: grid reliability, electricity price, construction cost, and whether an in-country GPU provider exists.
4. *The adoption scenario*: cautious, expected or aggressive use.

**How to read the results page.**
- *The banner* gives the answer in two lines: the 10-year cost and what to build in-country.
- *1 · How much will it cost?* compares the three adoption scenarios. Each bar is split by data class, and the whisker shows the price range (hardware, cloud and API prices, GPU efficiency).
- *2 · What needs to be built or bought?* shows one card per destination. A cloud or API card shows the annual bill and nothing to build. A sovereign-site card shows servers, GPUs, power, the upfront capex next to the annual running cost, and renting as the alternative where an in-country provider exists.
- *3 · Where does the cost come from?* splits the cost by application.

**What the figures can be used for.** Comparing options, sizing the order of magnitude of an investment, and showing which applications drive the cost.

**What they cannot be used for.** Procurement quantities, budget lines, or quotes. Before any commitment, replace the defaults with the client's own data: pilot logs, vendor quotes, and a site assessment (Annex A explains how).

**Key caveats.** Usage rates for several application types are assumptions (marked Low confidence). Demand is held flat over 10 years unless a growth rate is entered. Backup fuel on weak grids is not costed.

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
Recommended step, worded after the option chosen:
  below GPU threshold · Step 0 buy as a service · Step 1 rent in-country or own servers in an existing room
  · Step 2 own servers in a colocation data centre · Step 3 dedicated facility via PPP
```

The token layers follow the structure of the NVIDIA AI Tokenomics worksheet [S01], with two corrections: input and output tokens are kept separate, because they load the hardware differently [S07], and the system prompt is added to input before cache savings are removed.

## 3. Inputs

### 3.1 What the user enters

| Input | Where | Notes |
|---|---|---|
| Country | Setup | Sets grid reliability and electricity tariff (both can be overridden). |
| Adoption scenario | Setup | Low / Base / High usage rate for each application type. |
| Response speed | Setup | Fast / Standard / Relaxed tokens per second per user; selects the throughput point. |
| Finance | Setup | Discount rate (default 8%), demand growth and market price decline (default 0%). |
| Placement rules | Setup | Which tier each data class may use. Set once per country from its data protection law. |
| Client quotes (optional) | Setup | GPU rental price, GPU server cost, data centre build cost. A quote replaces the default range. |
| Applications | Applications | One by one: type, name, volume, data class. Optional: usage rate, model size, traffic split. |

The volume is always something a client can give: staff with access, people in the target population, documents per day, audio hours per day. The tool never derives it from population statistics.

**Volume check at entry.** The tool compares each volume with a country reference and warns when it is implausible: staff copilot above the number of civil servants; coding assistant above 2% and research agent above 1% of civil servants; frontline health above 0.5% of population; tutor above 30% and citizen assistant above 100% of population. Civil servants come from the World Bank Worldwide Bureaucracy Indicators [S18]; if missing, a rough 2% of population is used and labelled as an estimate. The limits are assumptions meant to catch input errors (e.g. 20,000 analysts in a country of 400,000 civil servants).

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

Example: the staff copilot rate of 1.4 comes from the UK cross-government trial [S36]. Among survey respondents, 39% used Copilot several times a day and 43% several times a week: 0.39 × 4 + 0.43 × 0.5 = 1.78 requests per respondent per day. Respondents over-represent active users, so the figure is scaled by the 80% of licence holders who were active in the last 30 days: 1.78 × 0.8 ≈ 1.4 per person with access.

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

**Pooling (diversity factor D).** Applications sharing a tier rarely peak at the same moment, so the tier needs less than the sum of their individual peaks. The benefit grows with the number of applications n in the tier:

```
D(n) = 1                                   for a single application (no pooling)
D(n) = D_min + (1 − D_min) / √n            for n ≥ 2                 (D_min = 0.6, assumption)
```

The square root follows the usual behaviour of independent fluctuations: their sum grows with √n, not n. Examples: D(2) = 0.88, D(4) = 0.80, D(9) = 0.73, D(16) = 0.70. n counts language-model applications and interactive non-LLM applications in the tier.

**Language-model GPUs.**

```
diversified peak(size) = Σ peak tokens/s of applications of that size × D(n)
effective tokens/s per GPU(size) = measured figure                       if measured
                                 = figure × production derating (0.6)    if derived or placeholder
LLM GPUs = roundup( Σ over sizes [ diversified peak(size) / effective tokens/s per GPU(size) ] )
```

- **Tokens/s per GPU** comes from the hardware profile at the **response speed** chosen in Setup (Section 10): Fast (~130 tokens/s per user), Standard (~95) or Relaxed (~55). Faster responses leave fewer users per GPU.
- **Production derating** (0.6) applies only to figures that are not measured at a fixed response speed (small-model figures, the GB300 medium figure) and to non-LLM GPU-seconds, which are placeholders [S11]. Measured benchmark figures [S44] are used as they are. Calibrate both with GenAI-Perf on a real endpoint [S06].

**Non-LLM GPUs.**

```
GPU-hours per day = units per day × GPU-seconds per unit / 3,600 / derating
peak GPUs (interactive only) = units per day × GPU-seconds per unit × peak share / (window × 3,600) × burst / derating
non-LLM GPUs = roundup( Σ peak GPUs × D(n) )
```

**Below the GPU threshold.** If a tier has no language-model application and its non-LLM workloads need less than 0.25 GPU in total (e.g. a few face verifications per second), the tool does not size a GPU. The result reads "Below GPU threshold: run on existing servers (CPU or a shared GPU)".

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
facility power (MW)   = IT load × PUE / 1,000                          (PUE by region and cooling, Section 8.1)
racks                 = roundup(IT load / rack kW)
annual energy (MWh)   = IT load × (idle fraction + (1 − idle fraction) × utilisation) × PUE × 8,760 / 1,000
```

**Throughput uncertainty.** Serving software, batching and model mix move tokens/s per GPU by more than the hardware choice in many cases. The Low / Base / High cases multiply tokens/s per GPU by 1.3 / 1.0 / 0.75, so GPUs, MW and cost all carry a range [S44].

### 8.1 Facility: PUE and construction cost by country and cooling

The facility (building, power distribution, backup, cooling) matters for the Owned option and for the air-versus-liquid decision. API and GPU-as-a-service prices already include the provider's facility.

```
PUE (air)        = site PUE entered by the user, else the regional value below, else the global average 1.56 [S22]
PUE (liquid)     = 1 + (PUE air − 1) × 0.82          (liquid cooling cut non-IT facility power by 18.1% [S51])
facility capex   = $ per W of IT × 1,000,000 × IT MW × cooling multiplier × range (0.85 / 1.0 / 1.2)
$ per W of IT    = the country's market in the Turner & Townsend cost index [S52, S53],
                   else the average of indexed markets in its region (labelled as a proxy), else $11/W [S23]
cooling multiplier (liquid vs air) = 0.90 / 1.085 / 1.10 (Low / Base / High)
```

Why a range for the liquid multiplier: Turner & Townsend measured liquid-cooled AI facilities in the US at 7-10% more than air-cooled facilities of the same IT capacity [S53]. Schneider Electric's cost model found the two equal at the same rack density, and 10-14% cheaper for liquid when it allows 2-4 times denser racks [S54]. Construction costs normally include UPS and generators; diesel and fuel logistics on weak grids are not costed (Section 16).

Country and regional values, and how to calibrate a specific site with the Schneider Electric calculators: Annex A.

**Owned capacity comes in whole servers.** GPUs are sold in servers, not one by one: 8 GPUs per HGX server (H200, B200) and 72 per GB300 NVL72 rack. For owned capacity, GPUs are rounded up to whole servers first; IT load, facility power, racks, energy, utilisation and cost are then all calculated from the rounded number. Rented GPUs are counted one by one.

**One shared sovereign site (default).** In a small country, Confidential (T3) and Restricted (T4) data would realistically share one secure site. When both tiers would otherwise be owned, the tool moves the Confidential work into the Restricted site: data can always move to a more secure tier. After the merge, the site is sized as one tier: pooling uses the number of applications on the site (e.g. 3 applications give D = 0.83), servers are rounded once for the combined load, there is one facility, and one 2-FTE staff minimum instead of two. The option can be switched off in Setup.

**Is there an in-country GPU provider?** Renting GPUs for Confidential data assumes an in-country provider exists. Setup asks the question (default: no or not sure). Without one, owning is the only option for Confidential data.

**Hardware choice (automatic).** For each tier the tool first decides which profiles are allowed, then picks the cheapest:

1. If the grid is weak (more than 1 outage per month, World Bank Enterprise Surveys [S19], or set by the user in Setup), **unknown**, or the tier's IT load on air-cooled hardware is below 1 MW, only air-cooled profiles are allowed. Dense liquid-cooled racks (above 100 kW per rack) need a reliable grid and a specialised facility.
2. Among allowed profiles, the tool sizes the tier with each and keeps the one with the lowest cost for the cheapest allowed buying option. An owned-only tier is therefore compared on ownership cost (servers, energy, facility), not on rental price.

The user can force a profile in Setup.

**Unknown grid.** If the country has no outage data, or the data is older than 2020, the grid is shown as "Unknown: check grid reliability" and air-cooled hardware is assumed. It is never shown as OK without data.

**What the grid setting changes, and what it does not.** It changes which hardware is allowed and the grid warning in the results. It does not yet add the cost of backup power (UPS, generators, batteries) or diesel, which on a weak grid is material. This is a known gap (Section 16).

## 9. Application types and their evidence

Each default below has a source or is marked as an assumption. Confidence: **High** = direct measurement or client data, **Medium** = indirect evidence or a derivation, **Low** = assumption to replace with client data.

{{TYPES}}

### How the agent sizes were checked

Anthropic reports that a single agent uses about 4 times the tokens of a chat interaction, and a multi-agent system about 15 times [S35]. The process agent is sized at 4.9 times a copilot request (≈18.2k vs ≈3.7k tokens) and the research agent at 14.7 times (≈55k). The test suite enforces both ranges.

### How the citizen assistant rate was checked

India's Kisan e-Mitra chatbot answers 8,000-20,000 queries per day for about 93 million PM-KISAN beneficiaries [S40], i.e. 0.9-2.2 queries per 10,000 people per day. The citizen assistant Low rate (0.00015) is the midpoint of that range; Base is about 3 times higher and High about 13 times higher, for assistants that cover several services (assumption).

### Units used for usage rates

All rates are **requests per person with access per day**, averaged over every day of the week. When a source gives messages per *active* user, the rate is that figure multiplied by the share of people with access who are active (stated in each type's evidence). ChatGPT's 3.6 is messages per *weekly* active user per day [S39].

## 10. Hardware profiles

{{HARDWARE}}

Throughput figures come from independent, open benchmarks run at a fixed **interactivity** (output speed seen by each user): about 90-95 tokens/s per user for the large reasoning model and about 75 for the medium model, from SemiAnalysis InferenceX [S44]; small-model figures from MLPerf Inference v5.1 [S45] or derived (marked). Power per GPU is implied by the benchmark's tokens per MW or taken from the vendor's system rating. Measured figures are used as they are; the production derating (0.6) applies only to derived figures (Section 8).

Evidence for each figure, and the comparison of vendor claims with independent benchmarks: Annex B.

## 11. Layer 5: 10-year cost (present value)

For each tier, the tool computes the cost of every buying mode the tier allows (Section 7 table), year by year, discounts it to present value, and picks the cheapest. In USD. Structure follows NVIDIA's inference cost method [S03] and the FinOps Foundation AI cost estimation guidance [S12].

**Year factors** (year y = 1 … 10, costs counted at the start of each year):

```
growth(y)   = (1 + demand growth)^(y−1)          user input, default 0%
price(y)    = (1 − market price decline)^(y−1)   user input, default 0%; applies to API tokens, GPU rental, GPU purchases
discount(y) = 1 / (1 + discount rate)^(y−1)      user input, default 8% (6-10% is a common range for public infrastructure)
GPUs(y)     = roundup( GPUs in year 1 × growth(y) )
```

**Buying modes:**

```
API / managed(y)    = price(y) × [ growth(y) × Σ ( uncached input (M) × input price
                                                   + cached input (M) × input price × cached share
                                                   + output (M) × output price ) × API multiplier
                                   + non-LLM and batch GPUs(y) × 8,760 × $/GPU-hour ]
GPU-as-a-service(y) = price(y) × GPUs(y) × 8,760 × $/GPU-hour
Owned:
  facility capex (year 1)      = IT MW in the last year × facility cost per MW
  GPU purchase (each refresh)  = GPUs needed at the end of the cycle × capex per GPU × price(first year of cycle)
  opex(y)                      = energy × tariff + GPUs × software per GPU + staff(GPUs) × cost per FTE
                                 + 5% × (GPU capex + facility capex)
  staff(GPUs)                  = 2 FTE per site + GPUs / 100        (assumption: one site per owned destination, and
                                                                     Confidential + Restricted share one site by default;
                                                                     1 FTE per ~100 GPUs)
present value                  = Σ discount(y) × cost(y)
$ per million tokens           = present value / Σ discount(y) × annual equivalent tokens × growth(y)
```

**Cached input is priced, not free.** Providers charge cached input tokens at a discount: 10% of the normal input price at Anthropic [S46], up to 50% at OpenAI [S47]. The tool uses 10% / 25% / 50% (Low / Base / High). On owned or rented GPUs cached tokens skip the prefill computation, so they do not add GPU load.

**Rent or own, side by side.** The results show, per tier, what the client would actually pay: API cost per year, GPU rental per year, and for owning the upfront capex (facility + first GPUs), the annual running cost (energy, staff, software, maintenance) and the GPU refresh. The cheapest option is marked, but the decision is the client's: renting has no upfront cost and can scale down; owning needs sustained utilisation.

**The results page** is organised around three client questions (see the summary at the top): the 10-year cost under three adoption scenarios, the capacity to build or buy per destination, and the cost per application. Detailed tables (every option Low – Base – High, tiers and hardware, rent or own per tier, demand) are collapsed below. The raw CSV export is unrounded, for analysts.

**Charts.** The tool plots the 10-year present value by data class (with the Low – High range) and by application. Application costs share each tier's cost in proportion to the application's GPU need (peak tokens/s ÷ tokens/s per GPU for language models; GPUs at peak or GPU-hours per day ÷ 24 for other workloads).

**Rounding.** Results are rounded to two significant figures and shown as "about X" with a Low – High range (e.g. "about $1.6M, range $1.4–2.1M"). The tool does not have more precision than that.

**Ranges and the cheapest option.** Every cost item has a Low / Base / High value (Section 14). The results table shows **every allowed option** across Low – Base – High, marks the cheapest at Base with ★, and flags any tier where the cheapest option changes within the range. In that case the choice depends on prices and the client should obtain quotes. A client quote replaces the range for that item.

## 12. Recommended step (the ladder)

The step is worded after the buying option the tool actually chose, so the two never contradict each other.

| Condition | Step |
|---|---|
| Only tiny non-LLM workloads (below 0.25 GPU) | **Below GPU threshold:** run on existing servers (CPU or a shared GPU). |
| Cheapest option is API | **Step 0:** buy as an API service (with data residency for internal data). |
| Cheapest option is GPU rental | **Step 0:** rent cloud GPUs (public or internal data), or **Step 1:** rent GPUs from an in-country provider (confidential data). |
| Owned, facility power below 1 MW | **Step 1:** own N servers in an existing secure server room. |
| Owned, 1 to 10 MW | **Step 2:** own N servers in a colocation data centre run by a private operator. |
| Owned, 10 MW or more | **Step 3:** dedicated facility through a PPP or private operator (IFC-investable). |

Cloud and API tiers show no GPUs, racks or power in the results: nothing is built for them. The raw CSV export keeps their notional GPU count in a separate, labelled column for analysts.

If the placement rules put an application above its default tier (e.g. internal data mapped to the sovereign site), the results flag it, so a presenter can explain why the sovereign site is larger than expected.

A PPP or IFC transaction for a facility of one or two megawatts is not realistic: transaction costs and minimum ticket sizes call for roughly 10 MW or more (assumption, adjustable). Between 1 and 10 MW, hosting in an existing colocation site is the practical route.

Triggers to move up a step: a confidential or restricted application reaches production; measured utilisation of a node stays above ~60% for two quarters; the grid check shows a warning or "unknown" (budget backup and storage before committing capex).

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
- **Hardware throughput** for small models, the GB300 medium-model figure and **GPU-seconds for non-LLM workloads** are derived or placeholders until calibrated (AIConfigurator, MLPerf [S08]). Benchmarks run one model per GPU pool; real deployments mixing several models will do somewhat worse, which the derating partly covers.
- **Backup fuel on weak grids**: facility construction costs include UPS and generators, but diesel and fuel logistics are not costed; the tool flags weak or unknown grids.
- **PUE by region** uses fleet averages from surveys (2020 regional, 2024 global), which overstate a new, well-designed site. Use the site PUE input when known.
- **Demand is flat by default.** Growth and price decline are single optional annual rates (default 0%); there is no adoption curve per application.
- **Deliberately not modelled** (planning grade): hourly load curves, per-model-copy and GPU memory checks, Monte Carlo simulation, AIConfigurator lookup tables, spillover between tiers.
- **Vendor figures** (NVIDIA) are used for structure and calibration ranges, not as final values.
- **Placement** is a policy decision. The tool applies the rules the user sets; it does not interpret the law.

## Annex A. Facility values by country and site calibration

{{FACILITY}}

**Calibrating a specific site.** The Schneider Electric TradeOff Tools [S48] give a site-level estimate (±20%):
1. *Data center capital cost calculator*: enter IT load (kW), rack density, cooling architecture (air or liquid), redundancy and build or prefabricated. Read the $/W; enter it in Setup → Client quotes as data centre build cost per MW IT (× 1,000,000).
2. *Data center efficiency and PUE calculator*: enter the location (climate), cooling type and load. Read the annual PUE; enter it in Setup → Site PUE.


## Annex B. Hardware evidence and vendor claims

Evidence per profile:

{{HARDWARE_EVIDENCE}}

### Vendor claims versus independent benchmarks

NVIDIA states that GB300 NVL72 delivers 65 times the tokens per GPU of HGX H200 (6,000 vs 90) and 50 times the tokens per MW on DeepSeek-R1 [S02]. Version 0.1 of this tool used those figures, which produced a 10x difference in GPUs between liquid-cooled and air-cooled hardware.

Independent measurements give a smaller gap. At 94 tokens/s per user, InferenceX measures 5,667 tokens/s per GPU on GB300 NVL72 and 779 on H200: 7.3 times per GPU, and about 3.8 times lower cost per token [S44]. Across 65-130 tokens/s per user the per-GPU gap is 4.6-7.3 times. MLPerf v5.1 reports about 5 times Hopper per GPU for GB300 on DeepSeek-R1 [S45]. NVIDIA's 65x corresponds to an operating point where H200 barely produces tokens.

The gap also depends on the model. It is largest for large mixture-of-experts reasoning models, which benefit from the 72-GPU NVLink domain, and much smaller for dense 70B models (about 2x between B200 and H200 [S44]).

For a mixed government portfolio the tool now gives a liquid-versus-air gap of roughly 2-4 times in GPUs and 1.3-3.5 times in cost. The higher end applies to portfolios dominated by large reasoning models. The hardware choice remains a policy decision tied to the grid. The air-cooled B200 profile (P3) is the middle option: newer silicon without liquid cooling.


## 17. Sources

{{SOURCES}}

Additional sanity-check tools (not used as sources): AI-DC calculator, Netray, GPUAdvisor.
