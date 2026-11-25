# Sovereign AI Compute Planner: Methodology

Version 0.5 (draft). Planning-grade estimates for early discussions with governments. It does not replace an engineering design or a procurement specification.

## Summary for presenters (one page)

**What the tool estimates.** For a government's planned AI applications: the 10-year cost (present value, with a range) of delivering them four ways, for each application and for the whole portfolio. The four options are: **API** (pay per token), **GPU rental** (GPU-as-a-service), **owning servers in a commercial colocation data centre**, and **owning servers in the government's own data centre**. It is a planning-grade estimate to open a conversation, not an engineering design or a procurement specification. Figures are shown at Base prices, in US dollars, rounded to the dollar; the precision of the display is not the precision of the estimate. Adoption uncertainty is a separate setting (cautious, expected, aggressive).

**The inputs that matter.**
1. *The applications*: type, volume (staff with access, documents per day, citizens served), the year each one starts and its growth per year. Volume is the single biggest driver.
2. *The country*: grid reliability, electricity price, construction cost and colocation price per kW.
3. *The adoption scenario*: cautious, expected or aggressive use.

**What the tool does not decide.** Data classification and hosting rules are not modelled in the results (since v0.9). The results carry a note: the client must check its data protection and sector rules to know which options are allowed for each application. The cheapest option may not be allowed.

**How to read the results page.**
- *The banner* names the cheapest option for the portfolio, its 10-year cost and range, the other three options, and the servers needed if owning.
- *1 · 10-year cost of the portfolio, four ways* compares the options for all applications together. Capacity is sized each year on the combined, pooled load: spare capacity of one application serves the others.
- *2 · Cost per application* prices each application on its own under each option, then shows the portfolio together and the sum of the standalone costs. The gap is what sharing saves.
- *3 · What owning means* shows the servers installed by year (bought as the combined need grows, replaced after five years) and where the money goes for each owned option.
- *2 · Cost per application*: an application that needs less than 0.25 GPU on its own reads "spare capacity" in the GPU columns, marked ‡. Bought alone, only the API has a price, so the API is shown as the cheapest; if GPUs are bought for other applications, the work runs on their spare capacity at no extra cost.
- *Download* gives two files. Applications below 0.25 GPU on their own show $0 with a note (they run on existing servers); types with no cloud API carry a note in the API column.
- The two files: The **summary** (CSV) has the 10-year cost of each application and of the portfolio under the four options. The **full calculation** (ZIP of CSV files with a README) has every step: inputs and type defaults, requests and tokens per application, demand by application and year, GPUs, servers, kW, utilisation and energy by year, yearly cost by option and item with discount factors, and every price, factor and default used with its source.
- *For specialists: tokens and sizing factors* (closed by default) shows, per application, the model size, requests per day, tokens per request (input and output, cached share), tokens per day at start and per year in year 10, peak equivalent tokens per second and active days; for other AI applications, GPU-seconds per unit and GPU-hours per day. It also lists the factors applied: retries and agent steps, the prefill weight, peak factors, pooling, throughput per GPU and API prices.

**What the figures can be used for.** Comparing options, sizing the order of magnitude of an investment, and showing which applications drive the cost.

**What they cannot be used for.** Procurement quantities, budget lines, or quotes. Before any commitment, replace the defaults with the client's own data: pilot logs, vendor quotes, and a site assessment (Annex A explains how).

**Key caveats.** Usage rates for several application types are assumptions (marked Low confidence). Colocation prices outside North America, Europe, Latin America and the main Asia-Pacific markets are regional assumptions (Low confidence): replace them with a local quote. Backup fuel on weak grids is not costed.

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
Placement: data class → tier (T1 offshore cloud or API ... T4 government data centre), adjusted by in-country capability
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
| In-country capability | Setup | GPU provider, residency cloud, government data centre readiness, colocation (Section 7). |
| Placement rules | Setup | Which tier each data class may use. Set once per country from its data protection law. |
| Client quotes (optional) | Setup | GPU rental price, GPU server cost, data centre build cost. A quote replaces the default range. |
| Applications | Applications | One by one: type, name, volume, start year, growth per year (data class is kept internally from the type but not asked since v0.9). Optional: usage rate, model size, traffic split. For agriculture advisory, also who the farmers are (everyone eligible, or service users). The type list shows the evidence confidence of each type in parentheses. |
| Custom application types (optional) | Applications | Uploaded from a CSV template when no type fits (Section 9). |

The volume is always something a client can give: staff with access, people in the target population, documents per day, audio hours per day. The tool never derives it from population statistics.

**Volume check at entry.** The tool compares each volume with a country reference and warns when it is implausible: staff copilot above the number of civil servants; coding assistant above 2% and research agent above 1% of civil servants; frontline health above 0.5% of population; tutor above 30% and citizen assistant above 100% of population. Civil servants come from the World Bank Worldwide Bureaucracy Indicators [S18]: employed labour force × public sector share of employment. This counts all public sector employees, including teachers and health workers, so it is an upper bound for office staff; it is shown on the Setup country line; if missing, a rough 2% of population is used and labelled as an estimate. The limits are assumptions meant to catch input errors (e.g. 20,000 analysts in a country of 400,000 civil servants).

**Agriculture advisory check.** The volume is compared with the estimated number of agricultural workers: employed labour force × ILO modeled share of employment in agriculture [S68], synced from the World Bank API with its indicator code and year. The tool warns when the volume exceeds 1.5 times that estimate (`agri_volume_tolerance`, assumption, in the global defaults). Agricultural employment counts **workers, not holdings or households**; in smallholder countries several household members may use one service, hence the tolerance. If the share is missing or older than 2015, the estimate is treated as unknown and no check is run. The ILO share is a share of employment, so it is applied to the employed labour force (labour force × (1 − unemployment)), not to the whole labour force.

**Who is counted in the volume?** Agriculture advisory and the citizen assistant have two usage rates, chosen per application. For the citizen assistant, *everyone eligible* keeps the Kisan e-Mitra rates and *service users* (people registered or onboarded to the service) uses 0.05 / 0.1 / 0.3 queries per user per day, a Low-confidence assumption. For agriculture advisory: *Everyone eligible* (all farmers, or all beneficiaries of a scheme; most will not use the AI service) keeps the Kisan e-Mitra rates, 0.00015 / 0.0005 / 0.002 queries per farmer per day [S40]. *Farmers using the advisory service* (onboarded through extension, cooperatives or an app) uses 0.05 / 0.1 / 0.3, a Low-confidence assumption: Base assumes about 1 in 6 onboarded farmers is active on a given day at about 0.6 queries per active user per day. The choice is saved with the scenario (`population_basis`); older scenarios load as *everyone eligible* and give the same results. 

**Agriculture service-user rate: not validated, likely high.** The open FarmerChat dataset has 1,446,866 questions from August 2024 to June 2026 for a service that reaches 1.2 million farmers or more [S107]: about 0.0017 questions per farmer reached per day, 60 times below the service-user Base of 0.1. Farmers reached includes farmers served through extension agents, and the dataset has no user ID, so it cannot give a rate per active user. Until Digital Green or a pilot gives monthly active users, treat agriculture results on the service-user basis as an upper bound.

**Very low usage note.** For citizen assistant, agriculture advisory and tutor, the tool shows an information note (not a warning, no effect on results) when an application makes fewer than 100 requests per day: the volume may be the whole eligible population rather than service users.

### 3.2 What the tool provides

Each application type carries defaults for usage rate, request size, peak pattern and model size, each with its evidence and a confidence level (Section 9). Country data (population, internet use, outages, labour force, agricultural employment, rural population, merchandise imports and exports) is synced weekly from the World Bank API; when the API limits requests (HTTP 429) or times out, the sync waits and retries (honouring the API's Retry-After, otherwise 15 s doubling to 5 min, up to about 13 minutes) and pauses 1 s between calls; indicator codes used for the agriculture check are confirmed against the API's own metadata at each sync, and the code, name and source are recorded in the snapshot. A code whose name no longer matches is not stored and the sync log says so; API prices are synced weekly from OpenRouter [S21]. Electricity tariffs and EGDI are curated tables because no free API exists.

## 4. Layer 0: requests per day

For each application:

```
requests per active day = volume × rate(scenario)
annual requests         = requests per active day × active days per year
```

- Every rate is per **active day**: a working day for office tools (250 per year), a school day for education (190), a clinic day for patient visits (300), and a calendar day for always-on services (365). Each type states its active days.
- **Peak sizing uses the active-day rate**, because the busiest day is an active day. **Annual tokens and API cost use active days per year.** A working-day rate is never multiplied by 365.
- For types measured in **people** (staff copilot, citizen assistant, tutor, health, coding, research agent, teacher, farmer), `rate` is requests per person with access per active day. It already includes the fact that most people with access are not active every day.
- For types measured in **items** (documents, texts, calls, cases, visits), `rate` = 1: each item is one request, and the client gives the volume per active day.
- The user can override `rate` per application under Advanced.

Example: the staff copilot rate of 1.4 per working day is a **scenario estimate**, not an observed requests-per-licence rate. It is derived from the UK cross-government trial [S36]: among survey respondents, 39% used Copilot several times a day and 43% several times a week, so 0.39 × 4 + 0.43 × 0.5 = 1.78 requests per respondent per day. Respondents over-represent active users, so the figure is multiplied by 0.8, the share of licence holders active in the last 30 days: 1.78 × 0.8 ≈ 1.4. The 0.8 is a scenario adjustment, not a validated correction for respondent bias.

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

*Since v0.9 the results page does not use placement: all applications are priced under all four options and the client checks which options its rules allow (Section 11a). Placement remains in the engine and in the Excel parity tests, and is documented here for reference.*

Each application runs in the tier of its data class (the "high-water mark": the most sensitive data it touches decides). The default mapping follows the World Bank data classification approach [S14]:

| Data class | Example | Default tier |
|---|---|---|
| 1 Public | open data, public information | T1 public cloud or API, offshore allowed |
| 2 Internal | non-sensitive government data | T2 cloud with data residency (in-country or regional) |
| 3 Confidential | personal and confidential data | T3 in-country, private provider (government data centre if there is none) |
| 4 Restricted | health, social protection, tax, security | T4 government data centre |

**One vocabulary for locations.** Results name where work actually runs, after the cheapest buying option is chosen: *Offshore cloud (API)*; *Cloud with in-country / regional data residency (API)*; *Cloud GPUs with data residency (rented)*; *In-country GPU provider (rented)*; *Government data centre* (government-owned servers in a government facility); *Government-owned servers in private colocation*. The tier codes T1-T4 are kept in the detail tables only.

**In-country capability (Setup).** Four questions decide what is possible in the country:

| Question | Answers | Effect |
|---|---|---|
| In-country GPU cloud provider (GPU-as-a-service)? | No / not sure (default), Yes | Without a provider, Confidential work cannot be rented in-country: it runs on government-owned servers (capex). |
| Cloud with acceptable data residency for Internal data? | In-country region, Regional (default), No | With No, Internal data is kept in-country: it is placed with Confidential data (T3) and follows the same rules. |
| Can a government data centre host GPU servers? | Ready (power and cooling available), Fit-out needed (default), No | Ready: no facility build cost for government-run sites (energy, staff and maintenance remain). Otherwise the facility cost by country applies. Also words Step 1. |
| Commercial colocation data centre in-country? | No / not sure (default), Yes | With Yes, Confidential work on owned servers is placed in private colocation (facility cost applies as a proxy for colocation charges). Words Step 2. |

So when there is no in-country GPU provider, everything that must stay in-country is government capex in the government data centre, unless a colocation site exists for Confidential data.

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

**One government data centre for Confidential and Restricted data (default).** In a small country, Confidential (T3) and Restricted (T4) data would realistically share one secure site. When both tiers would otherwise be owned, the tool moves the Confidential work into the Restricted site: data can always move to a more secure tier. After the merge, the site is sized as one tier: pooling uses the number of applications on the site (e.g. 3 applications give D = 0.83), servers are rounded once for the combined load, there is one facility, and one 2-FTE staff minimum instead of two. The option can be switched off in Setup.

**Is there an in-country GPU provider?** Renting GPUs for Confidential data assumes an in-country provider exists. Setup asks the question (default: no or not sure). Without one, owning is the only option for Confidential data.

**Hardware choice (automatic).** For each tier the tool first decides which profiles are allowed, then picks the cheapest:

1. If the grid is weak (more than 1 outage per month, World Bank Enterprise Surveys [S19]; where outages per month are not published, at least 50% of firms reporting outages, a Low-confidence assumption; or set by the user in Setup), **unknown**, or the tier's IT load on air-cooled hardware is below 1 MW, only air-cooled profiles are allowed. Dense liquid-cooled racks (above 100 kW per rack) need a reliable grid and a specialised facility.
2. Among allowed profiles, the tool sizes the tier with each and keeps the one with the lowest cost for the cheapest allowed buying option. An owned-only tier is therefore compared on ownership cost (servers, energy, facility), not on rental price.

The user can force a profile in Setup.

**Two outage measures, never mixed.** Enterprise Surveys publish the number of outages in a typical month and, separately, the percentage of firms that experienced outages. The tool uses the first when available and the second only as a fallback, each with its own threshold. The country line in Setup shows which one is used and its year.

**Unknown grid.** If the country has neither measure, or the data is older than 2020, the grid is shown as "Unknown: check grid reliability" and air-cooled hardware is assumed. It is never shown as OK without data.

**What the grid setting changes, and what it does not.** It changes which hardware is allowed and the grid warning in the results. It does not yet add the cost of backup power (UPS, generators, batteries) or diesel, which on a weak grid is material. This is a known gap (Section 16).

## 9. Application types and their evidence

Each default below has a source or is marked as an assumption. Confidence: **High** = direct measurement or client data, **Medium** = indirect evidence or a derivation, **Low** = assumption to replace with client data.

Each type also states the **basis** of its rate and size, so a reader can tell measurement from estimate:

- **observed**: a measured usage figure or benchmark, used with its stated denominator and hardware.
- **derived**: computed from observed data with stated assumptions (for example a survey frequency turned into a daily rate, or a benchmark on one GPU applied to another).
- **assumption**: a planning value with no direct measurement.
- **uncalibrated**: a placeholder that must be replaced with client, pilot or vendor data before results are relied on (coding assistant, research agent, satellite and image analysis).
- **client**: the volume comes from the client and the rate is 1 per item.

{{TYPES}}

### Example portfolio, sized from the country

*Load example* (Applications page) builds eight applications sized from the selected country's synced data. The rules are rough planning assumptions (Low confidence), meant to show the tool, not to forecast; every figure can be edited after loading, and a collapsed note lists the rule behind each one.

| Application | Volume rule | Driver (source) | Start | Growth |
|---|---|---|---|---|
| Civil servant copilot | 50% of civil servants get access | Civil servants [S18] | Year 1 | 2% |
| National services assistant (service users) | 2% of internet users register | Population × internet use [S16] | Year 2 | 25% |
| Agriculture advisory (service users) | 5% of agricultural workers onboarded | Agricultural workers, ILO modeled [S68] | Year 2 | 20% |
| Land registry intake | 1 document per working day per 3,000 people | Population [S108 check] | Year 1 | 0% |
| Customs risk agent | 16 declarations per $1 million of merchandise trade a year, over 250 working days | Merchandise imports + exports [S16, S101, S102]; population rule if trade is missing | Year 2 | 5% |
| Legal research | 0.05% of civil servants | Civil servants | Year 3 | 10% |
| Court transcription | 1 hour of hearings a day per 70,000 people | Population | Year 1 | 0% |
| ID enrolment deduplication | 2.5% of the population enrols each year | Population | Year 1 | 0% |

Volumes are rounded to two significant figures. An application whose driver is unknown for the country is left out, and the note says so.

**Checks against measured volumes (v0.9.9).**

- *Customs.* The risk agent screens every declaration. Declarations follow trade, not population: the WCO counted 610 million declarations a year (excluding postal and express) [S101] when world merchandise exports were $18.95 trillion [S102], with imports about the same. That is 16 declarations per $1 million of trade, applied to the country's merchandise imports plus exports (World Bank TM.VAL.MRCH.CD.WT and TX.VAL.MRCH.CD.WT, synced). Where trade data is missing, the earlier population rule is used and the note says so.
- *Land registry.* The rule gives 83 documents per 1,000 people a year. England and Wales processed 4.6 million register change applications in a year [S108], about 75 per 1,000 people. The rule matches a mature registry, so it is an upper end where less land is formally registered. The rules are in `data/catalogue/example_portfolio.yaml`.

### Custom application types

When no type fits, the user downloads a CSV template (one row per type), fills it and uploads it on the Applications page. `kind` = `llm` for language-model applications (usage rates, active days, token sizes, calls per task, retry, cache hit, model size, peak pattern) or `other` for other AI (GPU-seconds per unit, batch or interactive, peak pattern). Each row also states its data class, confidence (High / Medium / Low), basis (observed, derived, assumption, uncalibrated, client) and evidence. Rows with a missing or out-of-range value are skipped and listed; nothing is guessed. Custom types are marked "(custom)", appear under "Custom (uploaded)", and are saved with the scenario.

### Saving and resuming work

Each save creates a new link with a timestamp, so several versions can be kept. The link carries the whole scenario (setup, applications, custom types, quotes) in compressed form after the `#` of the address; nothing is stored on a server, and anyone with the link can open that scenario. Saved versions are listed in the browser where they were saved, with open, copy and remove. The JSON file save and load remain available.

### How the agent sizes were checked

Anthropic reports that a single agent uses about 4 times the tokens of a chat interaction, and a multi-agent system about 15 times [S35]. The process agent is sized at 4.1 times a copilot request and the research agent at 12.3 times. Per task, the copilot uses ≈4,455 tokens, the process agent ≈18,150 and the research agent ≈55,000. These totals **include the ×1.1 retry multiplier**; without it they are ≈4,050, ≈16,500 and ≈50,000. The copilot rose from ≈3,740 in v0.9.9, when meeting summaries were added to its input mix; the agents did not change. A measured agent benchmark confirms the research agent: 48,000 input and 6,900 output tokens per medium-difficulty task (GAIA Level 2) [S105]. The ratios are the same either way. The test suite enforces both ranges.

### How the citizen assistant rate was checked

India's Kisan e-Mitra chatbot answers 8,000-20,000 queries per day for about 93 million PM-KISAN beneficiaries [S40], i.e. 0.9-2.2 queries per 10,000 people per day. The citizen assistant Low rate (0.00015) is the midpoint of that range; Base is about 3 times higher and High about 13 times higher, for assistants that cover several services (assumption).

### Units used for usage rates

All rates are **requests per person with access per active day**, with the active days per year stated for each type (Section 4). When a source gives messages per *active* user, the rate is that figure multiplied by the share of people with access who are active (stated in each type's evidence). When a source gives a calendar-day rate for a working-day tool, it is converted to the active day (× 365 / active days), never the reverse. ChatGPT's 3.6 is messages per *weekly* active user per calendar day [S39].

Non-LLM units are stated explicitly: OCR per page; face verification per verification (detection plus one embedding, liveness excluded); retrieval indexing per 500-token chunk counted after overlap; image analysis per model-specific image chip (for example 512 × 512 pixels), so scenes must be converted to chips first.

### How the newer rates were checked

- **Clinical decision support** [S62]: on OpenEvidence, US physicians averaged 37.1 queries per active user-month, and nurse practitioners and physician assistants 44.5. That is about 1.2-1.5 per calendar day for an active user. The default is 0.3 / 1 / 3 per worker with access per calendar day. One query per consultation (3-20 per day) is an intensive scenario, entered as an override. Caveat: US clinicians, voluntary use, and the data came from the platform operator.
- **Teacher assistant** [S63]: in the EEF/NFER trial, teachers prepared about a third of their lessons with ChatGPT, about 1.7 preparations per week, or 0.34 per school day. With 1 / 3 / 6 requests per preparation (assumption) the rate is 0.34 / 1 / 2 per school day, equivalent to 0.24 / 0.73 / 1.46 per calendar day.
- **OCR** [S64]: PP-OCRv5 server pipeline, 0.74 s per image on an A10 (wall time, including image reading). Default 0.75 GPU-seconds per page, provisional; layout and table models need separate calibration.

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
  breakdown (shown per site)   = GPU servers incl. refresh · GPU software + maintenance · facility build + maintenance
                                 · energy · staff
$ per million tokens           = present value / Σ discount(y) × annual equivalent tokens × growth(y)
```

**GPU part versus facility.** For owned capacity the results split the 10-year present value into GPU servers (including refresh), GPU software and maintenance, facility build and its maintenance, energy and staff. A client using colocation or an existing server room can drop the facility line and add its colocation rent or room costs, which the tool does not model; energy and staff usually remain unless the colocation fee bundles power. The same breakdown is in the raw CSV export.

**Cached input is priced, not free.** Providers charge cached input tokens at a discount: 10% of the normal input price at Anthropic [S46], up to 50% at OpenAI [S47]. The tool uses 10% / 25% / 50% (Low / Base / High). On owned or rented GPUs cached tokens skip the prefill computation, so they do not add GPU load.

**Rent or own, side by side.** The results show, per tier, what the client would actually pay: API cost per year, GPU rental per year, and for owning the upfront capex (facility + first GPUs), the annual running cost (energy, staff, software, maintenance) and the GPU refresh. The cheapest option is marked, but the decision is the client's: renting has no upfront cost and can scale down; owning needs sustained utilisation.

**The results page** is organised around three client questions (see the summary at the top): the 10-year cost under three adoption scenarios, the capacity to build or buy per destination, and the cost per application. Detailed tables (every option Low – Base – High, tiers and hardware, rent or own per tier, demand) are collapsed below. The raw CSV export is unrounded, for analysts.

**Why moving a small application to the government data centre barely changes its cost.** The site is sized by the largest workloads, usually the staff copilot. A small application placed on the same site uses spare capacity on servers that are bought anyway, so its share of the cost is small, and it may be close to its API cost. Its cost only jumps if it is the only workload on a site, or if it pushes the site to another server. The results therefore show cost per application two ways: **share of site** (fixed costs spread by GPU need, as in the charts; removing the application would not save this amount) and **extra cost if added last** (10-year total with all applications minus the total without this one). When placement rules move applications above their default tier, the warning states what the move changes versus the default placement: servers added and the change in 10-year cost, which can be negative when API spending is replaced by spare capacity. Each owned site card also shows the **headroom at the busiest hour** (1 − GPU need at peak ÷ GPUs bought), and the scenario table notes when the high end of the price range needs an extra server, which explains a lopsided range.

**Charts.** The tool plots the 10-year present value by data class (with the Low – High range) and by application. Application costs share each tier's cost in proportion to the application's GPU need (peak tokens/s ÷ tokens/s per GPU for language models; GPUs at peak or GPU-hours per day ÷ 24 for other workloads).

**Rounding.** Results are rounded to two significant figures and shown as "about X" with a Low – High range (e.g. "about $1.6M, range $1.4–2.1M"). The tool does not have more precision than that.

**Ranges and the cheapest option.** Every cost item has a Low / Base / High value (Section 14). The results table shows **every allowed option** across Low – Base – High, marks the cheapest at Base with ★, and flags any tier where the cheapest option changes within the range. In that case the choice depends on prices and the client should obtain quotes. A client quote replaces the range for that item.

## 11a. Four delivery options, start year and growth (v0.9)

**Start year and growth.** Each application has a start year (1 to 10) and a growth rate per year. Its demand in year y is:

```
demand(y) = 0                                         before the start year
demand(y) = demand at start × (1 + growth)^(y − start) from the start year
```

The global demand growth setting is replaced by these per-application rates (older saved scenarios apply their global rate to every application).

**Sizing each year, pooled.** For each year, the tool sizes one pool with the demand of every application active that year (Section 8, with pooling across all of them). So a server bought for one application serves the others' spare needs: excess capacity is never added up across applications.

**The four options**, each priced year by year and discounted to present value:

| Option | Cost each year |
|---|---|
| API | Language-model tokens × API prices (cached input at a discount, Section 11). Other AI work at per-unit cloud API prices (table below). Work with no cloud API is priced as rented GPUs (marked † in the results); below 0.25 GPU it runs on existing servers. |
| GPU rental (GPU-as-a-service) | Reserved (default): GPUs needed that year (newer GPUs do more each, below) × 8,760 hours × reserved price. On demand: hours of work ÷ 0.6 × on-demand price, never more than renting all year. Rented capacity follows demand year by year. |
| Own + colocation | Server purchases (whole 8-GPU servers, bought when the pooled need exceeds what is installed, replaced after 5 years, never sold; optionally one spare server, N+1) + network, storage and security equipment (15% of each server purchase) + software + GPU maintenance + staff + energy (IT energy × PUE × tariff, paid to the operator) + colocation fee (installed IT kW × price per kW per month × 12). |
| Own + own data centre | The same server, software, maintenance, staff and energy lines + facility build in the first year with demand + facility maintenance every year from then on. If an existing facility has spare power and cooling (Setup), there is no build and no facility maintenance cost. |

Staff follow Section 11 (2 FTE minimum per site + 1 per 100 GPUs) and are the same in both owned options; a colocation operator runs the building, not the servers.

**Network, storage and security equipment.** Each server purchase carries 15% of its price for switches, storage, firewalls and security appliances, including key management (`owned_infra_share`, Medium confidence). Bills of materials for AI clusters put GPU servers at 60-70% of capital cost and networking at 10-25% [S85]; a small inference deployment needs little storage beyond the servers' own drives, so the lower end is used.

**Redundancy (optional).** Setup can add one spare server (N+1) whenever servers are needed, for workloads that must survive a server failure. It adds a server's purchase, equipment, software, maintenance, energy and colocation space. A second site for disaster recovery is not modelled.

**Price declines.** Two rates, set in Setup:

- *API prices* (tokens and per-unit API prices): 20% per year by default (`api_price_decline`, Low confidence). The price of a fixed level of performance has fallen 9x to 900x per year depending on the task [S82], about 10x per year for an LLM of equivalent performance [S83]. A government does not keep paying for last year's capability: it moves to newer models, so its bill per token for a chosen tier falls far less. 20% is a conservative planning value.
- *GPU rental and GPU server prices*: 0% by default (`hw_price_decline`). Rental prices fell more than 60% in 2025 and then rose about 40% between October 2025 and March 2026 [S84]: there is no stable trend to project.

**Newer hardware does more per GPU.** A GPU bought or rented in year y does `(1 + gain)^(y − 1)` times the work of a year-1 GPU, at the same price per GPU (`compute_gain_per_year`, 25% by default, Medium confidence). Sizing stays in year-1 GPUs; the conversion happens when capacity is bought or rented:

```
work per GPU bought in year y   = (1 + gain)^(y − 1)
GPUs rented in year y           = ceil(GPUs needed (year-1 GPUs) / work per GPU of year y)
installed capacity (year-1 GPUs)= Σ over cohorts still in service: servers × GPUs per server × work per GPU of their year
servers bought in year y        = ceil((need + spare − installed capacity) / (GPUs per server × work per GPU of year y))
energy                          = installed GPUs × kW per GPU × (idle + (1 − idle) × need / installed capacity) × 8,760 × PUE × tariff
```

So a refresh in year 6 replaces year-1 servers with fewer, newer ones, and growth later in the period needs fewer added servers. Power per GPU is kept constant, which is consistent with the profiles (H200 1.4 kW, B200 2.0 kW, GB300 2.1 kW all-in, Annex B). The API option is unaffected: its prices have their own decline.

Evidence: Epoch AI finds that FLOP/s per dollar of ML GPUs doubles every 2.07 years, about +40% per year [S86]. Memory bandwidth, which limits LLM decoding, doubles only every ~4.1 years, about +18% per year [S87]. 25% sits between the two; lower-precision formats (FP8, then FP4) push the real gain for inference above the bandwidth trend. Set 0% to reproduce version 0.9.6.

With 0% on both price declines, owning is favoured, because API and rental are paid every year while servers are bought upfront.

**Own data centre: build and maintenance.**

```
design IT load      = peak installed IT load over 10 years × (1 + 30% buffer)
facility build      = design IT load (MW) × build cost per MW (size curve × country factor)
facility maintenance = 5% of the build cost per year, from the first year of use
```

- *Buffer.* Facilities are built with spare capacity above the IT load installed: 30% is used as best practice (`facility_buffer`, adjustable).
- *Build cost by size.* Small sites cost more per MW because power intake, UPS, cooling plant, fire suppression and security are largely fixed. The tool uses this curve (analyst assumption from the World Bank team, Medium confidence), interpolated on the logarithm of capacity and flat outside its ends:

| Design IT capacity | 0.1 MW | 0.5 MW | 1 MW | 5 MW | 10 MW | 20 MW | 50 MW |
|---|---|---|---|---|---|---|---|
| Build cost, $M per MW | 40 | 30 | 25 | 22 | 20 | 15 | 12 |

- *Country factor.* The curve is the global level. Each country is scaled by its Turner & Townsend construction cost relative to the global default of $11.0 per W (Section 8.1): Ghana uses the Sub-Saharan Africa average, $10.51 per W, so × 0.955. Liquid cooling and the Low / High cases apply as in Section 8.1. A client quote in $ per MW replaces the curve.
- *Maintenance.* 5% of the build cost per year (`maintenance_share`, the same rate as GPU maintenance). Facility staff, security, insurance and generator fuel are not counted separately.
- *Energy* (IT × PUE) is counted separately in both owned options.

Example: a peak of 1 MW of IT in Ghana is built as 1.3 MW. Curve at 1.3 MW: $24.5M per MW, × 0.955 = $23.4M per MW, so the build costs $30.4M and maintenance $1.5M per year. One 8-GPU server (11 kW peak, 15 kW built) sits below the curve's first point: $38.2M per MW, a build of $0.56M.

**Per application and for the portfolio.** The per-application table prices each application alone, so each owned row carries its own servers, staff and facility. The portfolio row prices all applications together. The difference between the portfolio and the sum of the rows is the saving from sharing: large for owned options (one team, one facility, pooled servers), small for GPU rental (pooled peaks), nil for API (tokens add up).

**Hardware.** For each set of applications the tool picks the hardware with the lowest cost of its cheapest option, with the same grid and size rules as before (Section 8).

### Price references and ownership choices (v0.9.11)

The cost of each option depends on what the government actually buys. The defaults follow what a government usually buys, not the cheapest offer on the market; every choice is in Setup.

**API prices.** Three references, per model class (dollars per million tokens, input / output):

| Reference | Small (8B) | Medium (70B) | Large (DeepSeek class) | Source |
|---|---|---|---|---|
| Hyperscaler in region (default): the same open models on AWS or Azure | 0.15 / 0.15 (Ministral 8B) | 0.72 / 0.72 (Llama 3.3 70B) | 0.74 / 2.22 (DeepSeek v3.2, Mumbai, São Paulo, Jakarta) | [S109] |
| Open market: median of the cheapest providers | synced weekly | synced weekly | synced weekly | [S21] |
| Proprietary frontier models, regional processing (+10%) | 0.22 / 1.375 (GPT-5.4 nano) | 0.825 / 4.95 (GPT-5.4 mini) | 2.75 / 16.50 (GPT-5.4) | [S110] |

A government can also commit for several years and negotiate a discount. Published discounts apply to reserved capacity (Azure provisioned reservations: up to 64% for a month, 70% for a year, against the hourly provisioned rate [S111]), not to the per-token price, so the default is 0% and the discount is set from a real offer.

**GPU rental.** The hardware profiles carry a specialised-cloud (neocloud) price, $2.60 per H200 GPU-hour [S11]. Hyperscalers, which governments usually choose, cost more:

| H200, per GPU-hour | On demand | Reserved 1 year |
|---|---|---|
| Azure ND H200 v5 | $10.60 [S112] | -35% (ND H100 v5: $7.93 vs $12.29) [S112] |
| AWS p5en | $7.91 [S113] | up to -40% [S113] |
| Average used | $9.255 = 3.56 × neocloud | $5.76 = 2.216 × neocloud |

The same multiples are applied to B200 and GB300 (assumption). *Reserved* (default) rents the GPUs all year, 24/7. *On demand* bills only the hours of work, divided by 0.6 for autoscaling headroom (assumption, Low), at the on-demand price, and never more than renting all year. On demand suits work concentrated in office hours; large on-demand capacity is not always available at hyperscalers.

**Serving software on owned GPUs.** By default the NVIDIA AI Enterprise licence, $4,500 per GPU per year [S115], because serving skills are scarce in most low- and middle-income countries. The open-source option (vLLM or SGLang on Kubernetes) has no licence fee; staff is unchanged, which may understate the skills it needs.

**After the 5-year refresh period: keep or sell.** Two policies, and by default the tool takes the cheaper of the two for the portfolio (by the cost of owning with colocation), and says which one it chose:

- *Keep in service.* Servers stay in service until year 8 (assumption, Low; hyperscalers depreciate servers over 6 years and the hardware physically lasts longer [S114]). Out of warranty, their maintenance doubles (10% of capex per year, assumption), and new servers are bought only when the need exceeds the installed capacity.
- *Replace and sell at auction.* At the refresh period the servers are replaced by newer ones and sold at a public auction for 5% of their purchase price (assumption, Low). A 5-year-old HGX H100 server sits at 5-14% of its price new in American Compute's conservative band for 2028, and 2-6% a year later [S117]; a quick public sale gets the low end.

Keeping servers is often the dearer policy. Newer GPUs do much more work each (25% per year), while software, maintenance, colocation and energy are paid per GPU. For a copilot for 1 million civil servants with flat demand, keeping costs $5.40M and replacing and selling $4.77M over 10 years (own + colocation); the auction itself brings little ($0.04M in present value): the saving comes from running fewer, newer GPUs. Keeping wins when demand grows fast enough to use the old servers alongside the new ones.

**Idle hours opened to universities and research (option).** Owned or reserved GPUs sized for office-hour peaks are idle most of the night and at weekends: typical government use leaves 85-90% of GPU-hours idle. A share of those idle hours (Setup, 30% when ticked) can be opened to universities and research. The shared hours are valued at half the neocloud rental price (what they would otherwise pay, at an academic rate; assumption, Low) and shown as a negative cost; their electricity is added. This is the strongest economic case for owning: the same servers serve two communities.

**Effect on a large example** (copilot for 1 million civil servants, India, present value over 10 years):

| Settings | API | GPU rental | Own + colocation |
|---|---|---|---|
| Before v0.9.11 (open market, neocloud, servers replaced at 5 years) | $2.57M | $2.35M | $4.81M |
| v0.9.11 defaults (hyperscaler API and rental; servers replaced and sold, the cheaper policy here) | $3.04M | $5.21M | $4.77M |
| Defaults + open-source software + 30% of idle hours shared | $3.04M | $4.89M | $3.74M |
| Frontier API + open-source software + 30% of idle hours shared | $5.38M | $4.89M | $3.74M |

Independent studies that find owning cheaper compare it with frontier APIs or hyperscaler on-demand prices; against the cheapest open-model APIs, owning rarely wins [S116]. The tool shows both, by its choice of reference.

### Availability: export controls, sanctions and supply (context only)

Not every option is open to every country, whatever its cost. The tool does not model this, because the rules change several times a year and no maintained dataset exists; the results page reminds the user to check.

- **Buying GPUs** depends on export licences. Some countries need a licence for advanced GPUs, some get only older generations under quotas, and sanctioned countries are closed. New GPUs also have long delivery times when supply is short.
- **Renting GPUs** abroad is being brought under the same controls for customers from restricted countries; renting in-country means the provider imports the GPUs, with the same constraints.
- **APIs** from some providers are not offered in, or to entities owned from, some countries, and a provider can suspend access to a model at short notice. Open models served by several providers reduce that risk.

**Where API data is processed.** Every API price in the tool (language models, transcription, OCR, face verification, embeddings) is a public list price. These providers mostly process data outside the client's country, often in the United States, and may move it between regions; the price does not fix the location. In-region or in-country processing, where offered, can cost more and must be agreed in the contract. The results page says so in its footnote.

**Data regulation.** The tool does not check whether an option is allowed. The results page states that the client must assess, for each application, whether its data may be processed by an API provider or a cloud outside the country, hosted by a private operator in-country (colocation or GPU rental), or must stay in a government data centre.

### Which applications can be bought as an API

All language-model types can be bought from API providers. For other AI work the tool uses these per-unit prices (Low / Base / High):

| Type | Unit | Low | Base | High | Basis |
|---|---|---|---|---|---|
| Speech-to-text, batch (default) | audio hour | $0.04 | $0.185 | $0.36 | Average of eight list prices, below |
| Speech-to-text, real-time | audio hour | $0.15 | $0.705 | $1.44 | Average of six list prices, below |
| Text-to-speech | audio hour | $0.20 | $0.80 | $1.50 | $4 / $16 / $30 per million characters [S78] × ~50,000 characters per spoken hour (assumption) |
| OCR | page | $0.0006 | $0.0015 | $0.01 | $1.50 per 1,000 pages on AWS, Google and Azure, $0.60 above 5 million a month, ~$10 with layout [S79] |
| Face verification (1:1) | verification | $0.0004 | $0.001 | $0.002 | Amazon Rekognition, Face++ [S80]; liveness not included; some providers restrict identity use |
| Retrieval indexing | 500-token chunk | $0.000002 | $0.00001 | $0.000065 | $0.02 per million tokens, $0.13 for a large model [S81] |
| Biometric deduplication (1:N) | – | not available | | | Bought from an identity-system (ABIS) vendor and run in-country; priced as rented GPUs. Compute only: the ABIS licence and matching software, usually the larger cost, are not included |
| Image and satellite analysis | – | not available | | | Custom models; priced as rented GPUs |
| Fine-tuning | – | not available | | | Training an open model; priced as rented GPUs |

**Speech-to-text prices are a blend.** Transcription APIs differ by a factor of ten, so the Base price is the simple, unweighted average of the list prices of the main providers in November 2026, and Low and High are the cheapest and dearest of them. Each transcription application is either batch (recorded audio, transcribed within hours; the default) or real-time (live captions and voice services).

| Provider and model | Batch $/audio hour | Real-time $/audio hour | Source |
|---|---|---|---|
| Groq Whisper large-v3 turbo | 0.04 | – (files only) | [S95] |
| Groq Whisper large-v3 | 0.111 | – (files only) | [S95] |
| AssemblyAI Universal-2 / Universal-Streaming | 0.15 | 0.15 | [S76] |
| Azure AI Speech batch / real-time | 0.18 | 1.00 | [S97] |
| Google Cloud dynamic batch / standard | 0.18 | 0.96 | [S98] |
| ElevenLabs Scribe v3 / Scribe v3 Live | 0.20 | 0.22 | [S99] |
| Deepgram Nova-3 pre-recorded / streaming | 0.258 | 0.462 | [S100], [S96] |
| OpenAI Whisper | 0.36 | – | [S77], [S96] |
| AWS Transcribe | – | 1.44 | [S77] |
| **Average (Base)** | **0.185** | **0.705** | |

Batch is sized as steady work over 24 hours, real-time for the busy hours (70% of the audio in 10 hours, bursts of 1.5). Both use 12 GPU-seconds per audio hour: streaming servers batch concurrent streams.

**Confirmation of the GPU estimate.** Groq sells Whisper large-v3 turbo at $0.04 per audio hour at about 216 times real time [S95]. Our rented-GPU cost is about $0.04 per audio hour (12 GPU-seconds, derated, at $2.60 per GPU-hour, sized for peaks). The cheapest API is priced at about what the GPU work costs, which supports the throughput used.

At the Base batch price, 20,000 audio hours a day cost $1.35M a year through an API, against about $0.27M for the GPUs that do the same work. At Groq's price the two are level.

Beyond technical availability, an API may be ruled out by data rules (see the note on the results page), offline use in the field, latency for real-time voice, local-language coverage, rate limits at national scale, or payment in foreign currency.

### Colocation price per kW

Colocation is priced per kW of committed IT load per month, excluding energy, which is paid on top. Wholesale benchmarks are asking rates for 250–500 kW requirements in Tier III facilities [S69, S70]. Smaller deployments, which is most government AI starts (one to a few servers, 10–60 kW), pay retail rates: published US cabinet prices work out at a median of about $364 per kW per month [S71] against the $196 wholesale average, so the tool multiplies by 1.8 below 250 kW. For Sub-Saharan Africa, the Middle East and North Africa, South Asia and developing East Asia no public wholesale benchmark was found; the regional values are assumptions (Low confidence), checked against retail points: power above the rack allowance costs $500 per kW per month in Nairobi, Dar es Salaam and Lagos [S73], and Indian providers quote INR 12,000–25,000 per kW per month [S72]. A client quote replaces the value (Setup, Client quotes). The Low / Base / High cases use ×0.8 / 1 / 1.3 in the engine; since v0.9.1 the results page shows Base figures only.

{{COLOCATION}}

## 12. Recommended step (the ladder)

*Not shown on the results page since v0.9; kept for reference and for the engine's placement view.*

The step is worded after the buying option the tool actually chose, so the two never contradict each other.

| Condition | Step |
|---|---|
| Only tiny non-LLM workloads (below 0.25 GPU) | **Below GPU threshold:** run on existing servers (CPU or a shared GPU). |
| Cheapest option is API | **Step 0:** buy as an API service (with data residency for internal data). |
| Cheapest option is GPU rental | **Step 0:** rent cloud GPUs (public or internal data), or **Step 1:** rent GPUs from an in-country provider (confidential data). |
| Owned, facility power below 1 MW | **Step 1:** own N servers in the existing government data centre / the government data centre (fit-out needed) / a secure server room to be built or leased, following the Setup answer. In colocation if Confidential servers are placed there. |
| Owned, 1 to 10 MW | **Step 2:** own N servers in a colocation data centre run by a private operator, or in a new or expanded government data centre when there is no colocation in-country. |
| Owned, 10 MW or more | **Step 3:** dedicated facility through a PPP or private operator (IFC-investable). |

Cloud and API tiers show no GPUs, racks or power in the results: nothing is built for them. The raw CSV export keeps their notional GPU count in a separate, labelled column for analysts.

If the placement rules put an application above its default tier (e.g. internal data mapped to the government data centre), the results flag it with the servers and 10-year cost it adds versus the default placement.

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
| Electrical outages per month; share of firms with outages (fallback) | World Bank Enterprise Surveys [S19] | Weekly; the per-month indicator moved in 2026 and is found by name |
| Employment in agriculture (% of employment, ILO modeled), labour force, rural population | World Bank WDI [S68] | Weekly; codes confirmed against API metadata at each sync |
| API prices per model size | OpenRouter model list [S21] | Weekly (`sync/openrouter.py`), median of reference models |
| EGDI | UN E-Government Survey [S17] | Curated `data/egdi.csv`, every two years |
| Electricity tariff | Utility tariff sheets, GlobalPetrolPrices [S20] | Curated `data/electricity.csv` |

Each synced value keeps its indicator code and year. The app reads stored snapshots only, so it also works on servers without internet access.

## 16. Limitations

- **Usage rates for several types are assumptions** (marked Low, basis "assumption" or "uncalibrated"). They should be replaced with client data or pilot logs.
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

### Cross-checks against new sources (v0.9.7)

The hardware defaults were checked against chip prices from Epoch AI [S88], vendor list prices and independent power figures. Every check confirms the values already used; none was changed.

| Figure | Value used | Independent evidence | Result |
|---|---|---|---|
| H200 capex per GPU | $40,000 | Supermicro HGX H200 8-GPU server from $319,421.64, about $39,900 per GPU [S89]; Epoch chip price × server factor ~1.35 [S88] | Confirmed |
| B200 capex per GPU | $50,000 (was marked placeholder) | New HGX B200 8-GPU nodes $360K-$470K, midpoint about $51,900 per GPU [S90]; street prices $300K-$500K+, Aivres from about $340K [S91] | Confirmed; no longer a placeholder |
| GB300 capex per GPU | $65,000 | Epoch chip price $38-49k [S88] × rack-scale server factor ~1.35-1.5 | Consistent; Low confidence (no public rack price) |
| GB300 power per GPU | 2.1 kW all-in | 2.12 kW all-in per chip at 1,400 W TDP [S92]; HPE rack 132 kW nominal for 72 GPUs, 1.83 kW per GPU before network and storage [S93] | Confirmed |
| B200 power per GPU | 2.0 kW all-in | 1,000 W TDP per GPU [S94]; all-in is about 2x TDP, as for H200 (1.4 kW for 700 W) | Consistent |
| GB300 vs H200 throughput | 4.6-7.3x per GPU (large model) | InferenceX at fixed interactivity [S44]; MLPerf about 5x [S45] | Unchanged; vendor 65x rejected (below) |

Server factor = server price per GPU ÷ chip price: it covers CPUs, memory, NVLink switches, network cards, chassis and margin.

### Vendor claims versus independent benchmarks

NVIDIA states that GB300 NVL72 delivers 65 times the tokens per GPU of HGX H200 (6,000 vs 90) and 50 times the tokens per MW on DeepSeek-R1 [S02]. Version 0.1 of this tool used those figures, which produced a 10x difference in GPUs between liquid-cooled and air-cooled hardware.

Independent measurements give a smaller gap. At 94 tokens/s per user, InferenceX measures 5,667 tokens/s per GPU on GB300 NVL72 and 779 on H200: 7.3 times per GPU, and about 3.8 times lower cost per token [S44]. Across 65-130 tokens/s per user the per-GPU gap is 4.6-7.3 times. MLPerf v5.1 reports about 5 times Hopper per GPU for GB300 on DeepSeek-R1 [S45]. NVIDIA's 65x corresponds to an operating point where H200 barely produces tokens.

The gap also depends on the model. It is largest for large mixture-of-experts reasoning models, which benefit from the 72-GPU NVLink domain, and much smaller for dense 70B models (about 2x between B200 and H200 [S44]).

For a mixed government portfolio the tool now gives a liquid-versus-air gap of roughly 2-4 times in GPUs and 1.3-3.5 times in cost. The higher end applies to portfolios dominated by large reasoning models. The hardware choice remains a policy decision tied to the grid. The air-cooled B200 profile (P3) is the middle option: newer silicon without liquid cooling.


## 17. Sources

{{SOURCES}}

Additional sanity-check tools (not used as sources): AI-DC calculator, Netray, GPUAdvisor.
