from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.comments import Comment

F = "Arial"
BLUE = Font(name=F, color="0000FF")
BLACK = Font(name=F, color="000000")
GREEN = Font(name=F, color="008000")
BOLD = Font(name=F, bold=True)
HDR = Font(name=F, bold=True, color="FFFFFF")
TITLE = Font(name=F, bold=True, size=14)
HFILL = PatternFill("solid", fgColor="1F3864")
YEL = PatternFill("solid", fgColor="FFFF00")
GREY = PatternFill("solid", fgColor="F2F2F2")
WRAP = Alignment(wrap_text=True, vertical="top")
thin = Side(style="thin", color="BFBFBF")
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)

wb = Workbook()


def title(ws, text, sub=None):
    ws["A1"] = text
    ws["A1"].font = TITLE
    if sub:
        ws["A2"] = sub
        ws["A2"].font = Font(name=F, italic=True, color="595959")


def header(ws, row, labels, widths=None):
    for i, l in enumerate(labels, 1):
        c = ws.cell(row=row, column=i, value=l)
        c.font = HDR
        c.fill = HFILL
        c.alignment = Alignment(wrap_text=True, vertical="center")
        c.border = BOX
    ws.row_dimensions[row].height = 45
    if widths:
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w


def put(ws, ref, val, font=BLACK, fmt=None, fill=None):
    c = ws[ref]
    c.value = val
    c.font = font
    c.border = BOX
    if fmt:
        c.number_format = fmt
    if fill:
        c.fill = fill
    return c


NUM = "#,##0;(#,##0);-"
NUM1 = "#,##0.0;(#,##0.0);-"
NUM2 = "#,##0.00;(#,##0.00);-"
PCT = "0.0%;(0.0%);-"
USD = "$#,##0;($#,##0);-"
USD2 = "$#,##0.00;($#,##0.00);-"
MULT = "0.00x"

# ---------------------------------------------------------------- README
ws = wb.active
ws.title = "README"
title(ws, "Sovereign AI Compute Planner v0.1 (draft)",
      "From government AI use cases to tokens, GPUs, MW, placement and 10-year TCO. Planning-grade, not engineering design.")
lines = [
    ("PURPOSE", ""),
    ("", "Give a country a first, defensible order of magnitude for AI compute: how much, where it may run (by data class), and the cheapest eligible way to buy it. A conversation starter, not a procurement spec."),
    ("FLOW", ""),
    ("Layer 0", "L0_UseCases: pick use cases, mode (Pilot/Production), scaling driver and adoption. Produces users. + NonToken for biometrics, OCR, speech, vision, fine-tuning."),
    ("Layers 1-3", "Demand_L1_L3: users -> sessions -> input / cached / output tokens (incl. reasoning, agent steps, retries) -> daily tokens -> peak tokens/s. Method: NVIDIA AI Tokenomics worksheet [S01], corrected to keep input and output separate [S07]."),
    ("Placement", "Placement: data class (World Bank data classification approach [S14]) -> tier T1-T4 -> eligible buying modes. Hybrid by default, in line with World Bank guidance [S13]."),
    ("Layer 4", "Sizing_L4: peak tokens/s per tier / (tokens/s per GPU x production derating) -> GPUs -> IT kW -> facility MW (PUE) -> racks, energy. Throughput per GPU from Hardware_L4, calibrated with AIConfigurator [S04] (see Online_Tools)."),
    ("Layer 5", "TCO_L5: 10-year cost of API/managed, GPU-as-a-service, Owned, per tier, only where eligible. Structure: NVIDIA inference cost method [S03], FinOps AI cost estimation [S12]."),
    ("Output", "Ladder: one row per tier with GPUs, MW, cheapest eligible mode and the recommended step (0 cloud now / 1 small sovereign node / 2 dedicated via private operator)."),
    ("COLOUR LEGEND", ""),
    ("Blue text", "Input or assumption you may change."),
    ("Yellow fill", "Key assumption: replace with country data or calibration before using results."),
    ("Black text", "Formula. Do not overwrite."),
    ("Green text", "Formula pulling from another sheet."),
    ("HOW TO USE", ""),
    ("1", "Country: fill the yellow cells (sources and links in column D/E; step-by-step in Online_Tools)."),
    ("2", "L0_UseCases: set Include (1/0), Mode, and check adoption and token defaults. Example values are illustrative."),
    ("3", "Hardware_L4: replace tokens/s per GPU with AIConfigurator or InferenceX/MLPerf results for your model and latency target."),
    ("4", "Placement: confirm the data class -> tier mapping against the country's own classification law."),
    ("5", "TCO_L5: fill prices (OpenRouter for API, provider quotes for GPU-hours and capex)."),
    ("6", "Read Ladder. Switch Country!B10 between Low / Base / High to see the range."),
    ("SCOPE", ""),
    ("In scope", "GPU compute for generative AI (token-based) and non-LLM deep learning (biometrics, OCR, speech, vision), plus fine-tuning as batch."),
    ("Out of scope", "DPI core systems (ID, payments, data exchange) and classical ML scoring: CPU workloads, size them with the conventional data centre capacity tool."),
    ("CAVEATS", ""),
    ("1", "Benchmarks overstate production throughput; a derating factor is applied (Country!B16) and must be calibrated with GenAI-Perf [S06]."),
    ("2", "Hardware choice changes MW by up to ~50x for the same demand [S02]. Treat the hardware profile as a policy choice tied to grid and cooling."),
    ("3", "Adoption rates are scenario assumptions, not data. Replace with pilot telemetry as soon as available."),
    ("4", "Demand is held flat over the horizon in v0.1; no growth curve, no discounting."),
]
r = 4
for a, b in lines:
    ws.cell(row=r, column=1, value=a).font = BOLD if b == "" or a.isupper() else Font(name=F, bold=True, color="1F3864")
    c = ws.cell(row=r, column=2, value=b)
    c.font = Font(name=F)
    c.alignment = WRAP
    r += 1
ws.column_dimensions["A"].width = 18
ws.column_dimensions["B"].width = 140

# ---------------------------------------------------------------- Country
ws = wb.create_sheet("Country")
title(ws, "Country profile and global parameters", "Yellow = replace with country data. Example values describe a fictional mid-size lower-middle-income country.")
header(ws, 3, ["Parameter", "Value", "Unit", "Source ID", "How to obtain / note"], [44, 16, 22, 12, 100])
rows = [
    ("Country name", "Example country", "text", "-", "Replace."),
    ("Population", 20000000, "people", "S29", "World Bank WDI SP.POP.TOTL, latest year."),
    ("Internet users", 0.45, "% of population", "S15, S16", "World Bank IT.NET.USER.ZS (ITU data). Applied only to 'Population' driver use cases."),
    ("Civil servants", 400000, "people", "S18", "World Bank Worldwide Bureaucracy Indicators: public sector employment. Multiply share by employed population if only a share is given."),
    ("UN E-Government Development Index (EGDI)", 0.50, "index 0-1", "S17", "UN E-Government Survey data centre, latest edition."),
    ("Global average EGDI", 0.638, "index 0-1", "S17", "UN E-Government Survey 2024 world average. Used to scale citizen-facing adoption (capped at 1.5x)."),
    ("Scenario", "Base", "Low / Base / High", "-", "Selects the adoption column in L0_UseCases."),
    ("Electricity price (business)", 0.15, "USD/kWh", "S20", "GlobalPetrolPrices electricity, business tariff, USD. Or utility tariff sheet."),
    ("Electrical outages in a typical month (firms)", 5, "outages/month", "S19", "World Bank Enterprise Surveys, Infrastructure indicators."),
    ("Weak-grid threshold", 1, "outages/month", "Analyst", "Above this, liquid-cooled dense profiles are flagged and backup is required."),
    ("PUE", 1.6, "ratio", "S22", "Uptime Institute global survey average is ~1.56; hot climates and small sites run higher."),
    ("Portfolio diversity factor D", 0.7, "ratio 0-1", "Method", "D = coincident peak / sum of standalone peaks. Applied within a tier only. 1.0 = no pooling benefit (conservative)."),
    ("Production derating vs benchmark", 0.6, "ratio 0-1", "S11, S06", "Benchmarks are tuned lab runs. Calibrate with GenAI-Perf on a real endpoint."),
    ("Prefill weight (input token vs output token cost)", 0.15, "ratio", "S03, S07", "Uncached input tokens are cheaper to process than output tokens. Calibrate: run AIConfigurator at your ISL/OSL; the profile's tokens/s/GPU then already includes prefill and this can be set lower."),
    ("Idle power fraction", 0.3, "ratio of peak IT power", "S09, S10", "Share of rated IT power drawn when idle. Calibrate with MLCommons Power methodology or DCGM telemetry."),
    ("Analysis horizon", 10, "years", "-", "Demand held flat in v0.1."),
    ("Sanity ceiling: tokens per user per day", 240000, "tokens/user/day", "S24", "Epoch AI: a human thinking 8h/day processes ~240k tokens/day. Use cases above this are flagged (agents can exceed it legitimately)."),
    ("Step 1 / Step 2 threshold", 1, "MW facility", "Analyst", "Below this, a sovereign tier fits in an existing facility (Ladder)."),
]
key_inputs = {5, 6, 7, 8, 11, 12, 14, 15, 16, 17, 18}
for i, (p, v, u, s, n) in enumerate(rows):
    rr = 4 + i
    put(ws, f"A{rr}", p, BLACK)
    fmt = None
    if isinstance(v, float) and v < 1 and u.startswith("%"):
        fmt = PCT
    elif isinstance(v, (int, float)) and v >= 1000:
        fmt = NUM
    elif u == "USD/kWh":
        fmt = "$0.000"
    put(ws, f"B{rr}", v, BLUE, fmt, YEL if rr in key_inputs else None)
    put(ws, f"C{rr}", u)
    put(ws, f"D{rr}", s)
    c = put(ws, f"E{rr}", n)
    c.alignment = WRAP
dv = DataValidation(type="list", formula1='"Low,Base,High"', allow_blank=False)
ws.add_data_validation(dv)
dv.add("B10")
# Named-cell map
C = dict(pop="Country!$B$5", inet="Country!$B$6", cs="Country!$B$7", egdi="Country!$B$8", egdiw="Country!$B$9",
         scn="Country!$B$10", kwh="Country!$B$11", outages="Country!$B$12", weak="Country!$B$13", pue="Country!$B$14",
         D="Country!$B$15", der="Country!$B$16", pre="Country!$B$17", idle="Country!$B$18", hor="Country!$B$19",
         ceil="Country!$B$20", thr="Country!$B$21")

# ---------------------------------------------------------------- Placement
ws = wb.create_sheet("Placement")
title(ws, "Placement: data class -> tier -> eligible buying modes",
      "Map to the country's own classification law. Default follows the World Bank data classification approach [S14] and hybrid guidance [S13].")
header(ws, 3, ["Data class", "Label", "Tier", "Note"], [14, 30, 12, 90])
classes = [
    (1, "Public", "T1", "Open data, public information. Offshore processing acceptable."),
    (2, "Internal / official use", "T2", "Non-sensitive government data. Cloud with in-country or regional residency and customer-managed keys."),
    (3, "Confidential", "T3", "Personal and confidential data. Processed in-country, on capacity run by a licensed (private) operator."),
    (4, "Restricted / secret", "T4", "Health records, social protection, tax, security. State-controlled enclave."),
]
for i, (k, l, t, n) in enumerate(classes):
    rr = 4 + i
    put(ws, f"A{rr}", k, BLUE)
    put(ws, f"B{rr}", l)
    put(ws, f"C{rr}", t, BLUE, fill=YEL)
    c = put(ws, f"D{rr}", n)
    c.alignment = WRAP
ws["A9"] = "Tiers and eligible modes (1 = eligible)"
ws["A9"].font = BOLD
header(ws, 10, ["Tier", "Description", "API / managed", "GPU-as-a-service", "Owned", "Hardware profile", "Sovereignty / rationale"])
ws.column_dimensions["E"].width = 10
ws.column_dimensions["F"].width = 16
ws.column_dimensions["G"].width = 80
tiers = [
    ("T1", "Public cloud / API, offshore permitted", 1, 1, 1, "P1", "Lowest cost, no local capex. World Bank default for non-sensitive data [S13]."),
    ("T2", "Cloud with in-country or regional residency", 1, 1, 1, "P1", "Contractual and technical residency controls; hybrid model [S13]."),
    ("T3", "Sovereign local, privately operated (colocation / GPUaaS)", 0, 1, 1, "P1", "In-country capacity run by a private operator: IFC-investable."),
    ("T4", "Government enclave, state-operated", 0, 0, 1, "P1", "Full state control; highest cost per token."),
]
for i, row in enumerate(tiers):
    rr = 11 + i
    for j, v in enumerate(row):
        col = "ABCDEFG"[j]
        c = put(ws, f"{col}{rr}", v, BLUE if j in (2, 3, 4, 5) else BLACK)
        if j in (1, 6):
            c.alignment = WRAP
dvp = DataValidation(type="list", formula1='"P1,P2,P3"')
ws.add_data_validation(dvp)
dvp.add("F11:F14")

# ---------------------------------------------------------------- Hardware
ws = wb.create_sheet("Hardware_L4")
title(ws, "Hardware profiles: throughput, power, price",
      "Yellow = calibrate. Throughput = sustained output tokens/s per GPU at your latency target, for each model class. Fill P3 from AIConfigurator (Online_Tools).")
header(ws, 3, ["ID", "Profile", "Cooling", "Rack power (kW)", "IT power per GPU, all-in (kW)",
               "Tokens/s per GPU: S model (~8B)", "Tokens/s per GPU: M model (~70B)", "Tokens/s per GPU: L reasoning model (~600B MoE)",
               "Cloud price ($/GPU-hour)", "Capex per GPU, server share ($)", "Software ($/GPU/year)", "Suitable for weak grid",
               "Tokens/s per MW IT: M model", "Tokens/s per MW IT: L model", "Source IDs", "Calibration / basis"],
       [6, 34, 12, 11, 12, 13, 13, 15, 12, 13, 12, 11, 15, 15, 12, 90])
hw = [
    ("P1", "HGX H100/H200 8-GPU, air-cooled", "Air", 41, 1.7, 3000, 800, 90, 2.60, 40000, 4500, "Yes", "S02, S10, S11",
     "L: NVIDIA 90 tok/s/GPU (H200, DeepSeek-R1) [S02]. kW/GPU implied by NVIDIA 54k tok/s per MW [S02]; DGX H100/H200 = 10.2 kW per 8-GPU server [S10]; rack = 4 servers. Price: GMI H200 list [S11]. S and M: PLACEHOLDERS, replace with AIConfigurator output. Capex/GPU: placeholder, replace with vendor quote."),
    ("P2", "GB300 NVL72, liquid-cooled", "Liquid", 130, 2.1, 12000, 4000, 6000, 2.65, 65000, 4500, "No", "S02",
     "L: NVIDIA 6,000 tok/s/GPU and 2.8M tok/s per MW (DeepSeek-R1, vendor analysis, conditions not published) [S02]. Price: NVIDIA [S02]. Rack kW, S, M, capex: PLACEHOLDERS."),
    ("P3", "Calibrated profile (fill from AIConfigurator)", "Air", 41, 1.7, 3000, 800, 90, 2.60, 40000, 4500, "Yes", "S04, S05, S06",
     "Copy of P1 until calibrated. Run AIConfigurator for the chosen GPU, model, ISL/OSL and TTFT/TPOT targets; enter the tokens/s per GPU of the best SLA-compliant configuration. Validate with GenAI-Perf."),
]
for i, row in enumerate(hw):
    rr = 4 + i
    (pid, name, cool, rk, kw, s, m, l, pr, cap, sw, wg, src, note) = row
    vals = [pid, name, cool, rk, kw, s, m, l, pr, cap, sw, wg]
    fmts = [None, None, None, NUM, "0.00", NUM, NUM, NUM, USD2, USD, USD, None]
    for j, v in enumerate(vals):
        col = "ABCDEFGHIJKL"[j]
        put(ws, f"{col}{rr}", v, BLUE if j >= 2 else BLACK, fmts[j], YEL if j in (4, 5, 6, 7, 9) else None)
    put(ws, f"M{rr}", f"=IF(E{rr}=0,0,G{rr}/E{rr}*1000)", BLACK, NUM)
    put(ws, f"N{rr}", f"=IF(E{rr}=0,0,H{rr}/E{rr}*1000)", BLACK, NUM)
    put(ws, f"O{rr}", src)
    c = put(ws, f"P{rr}", note)
    c.alignment = WRAP
    ws.row_dimensions[rr].height = 75
ws["A8"] = "Check: P1 tokens/s per MW for L should be close to NVIDIA's 54,000 and P2 close to 2.8M [S02]."
ws["A8"].font = Font(name=F, italic=True)
HWR = "Hardware_L4!$A$4:$A$6"


def hw(col):
    return f"Hardware_L4!${col}$4:${col}$6"


# ---------------------------------------------------------------- L0 Use cases
ws = wb.create_sheet("L0_UseCases")
title(ws, "Layer 0: government use case catalogue (LLM / token-based)",
      "Blue = editable defaults. Token and adoption values are illustrative starting points: replace with pilot logs (GenAI-Perf / gateway telemetry) as soon as available.")
L0H = ["ID", "Use case", "Workload category [S01]", "Include (1/0)", "Mode", "Scaling driver", "Eligible share of driver",
       "Fixed base (if driver = Fixed)", "Pilot users", "Adoption: Low", "Adoption: Base", "Adoption: High", "Citizen-facing (1/0)",
       "Tasks per user per day", "Input tokens per step (ISL)", "Output tokens per step (OSL)", "Reasoning tokens per step",
       "Agent steps per task", "Retry multiplier", "System prompt tokens per step", "Cache hit rate (system prompt)",
       "Peak-window share of daily traffic", "Peak window (hours)", "Burst ratio", "Latency SLA headroom", "Seasonal spike factor",
       "Model class (S/M/L)", "Data class (1-4)", "Source IDs", "Basis / note"]
header(ws, 3, L0H, [7, 36, 16, 9, 12, 14, 10, 12, 9, 9, 9, 9, 9, 9, 10, 10, 10, 9, 9, 10, 9, 9, 9, 8, 9, 9, 9, 9, 14, 70])
uc = [
    ("UC01", "Citizen services assistant (multilingual chat)", "Chatbot", 1, "Production", "Population", 1, 0, 500, 0.02, 0.05, 0.10, 1, 0.1, 1500, 400, 0, 1, 1.1, 800, 0.5, 0.6, 10, 2, 1.2, 1.5, "M", 2, "S01, S07",
     "Sporadic use (~3 queries/month per adopter). ISL includes retrieved context (RAG)."),
    ("UC02", "Civil servant copilot (drafting, summarising)", "Copilot", 1, "Production", "Civil servants", 0.3, 0, 200, 0.1, 0.3, 0.6, 0, 8, 3000, 600, 0, 1, 1.1, 1000, 0.5, 0.8, 8, 2, 1.2, 1.2, "M", 3, "S01, S26",
     "Eligible share = desk-based staff. Check against US Army allowance of 200k tokens/user/month [S26]."),
    ("UC03", "Document intake and extraction (permits, land, registries)", "Content / extraction", 1, "Production", "Fixed", 1, 20000, 1000, 0.2, 0.5, 0.8, 0, 1, 4000, 500, 0, 1, 1.05, 500, 0.5, 0.8, 10, 1.5, 1.1, 1.3, "S", 3, "S01",
     "Fixed base = documents per day; 1 task per document. Assumes text already digitised (OCR in NonToken)."),
    ("UC04", "Translation into national and local languages", "Translation", 1, "Production", "Population", 1, 0, 500, 0.01, 0.03, 0.06, 1, 0.2, 500, 500, 0, 1, 1.05, 200, 0.5, 0.6, 10, 2, 1.2, 1.2, "S", 2, "S01", ""),
    ("UC05", "Community health worker triage assistant", "Chatbot", 1, "Production", "Fixed", 1, 20000, 300, 0.2, 0.5, 0.8, 0, 10, 2000, 500, 1000, 1, 1.1, 1000, 0.5, 0.7, 10, 1.5, 1.2, 1.5, "M", 4, "S01",
     "Fixed base = health workers. Seasonal factor covers epidemic peaks."),
    ("UC06", "Education tutor (secondary students)", "Chatbot", 1, "Pilot", "Fixed", 1, 500000, 2000, 0.05, 0.15, 0.3, 1, 2, 1500, 500, 0, 1, 1.1, 800, 0.5, 0.7, 8, 2, 1.2, 1.3, "M", 2, "S01", "Fixed base = students."),
    ("UC07", "Agriculture advisory (voice / SMS)", "Chatbot", 1, "Production", "Fixed", 1, 2000000, 1000, 0.01, 0.03, 0.08, 1, 0.1, 800, 300, 0, 1, 1.05, 500, 0.5, 0.6, 10, 2, 1.2, 2, "S", 1, "S01",
     "Fixed base = farming households. Speech handled in NonToken. Seasonal factor = planting season."),
    ("UC08", "Tax and customs risk agent", "Agent", 1, "Pilot", "Fixed", 1, 10000, 500, 0.2, 0.5, 1, 0, 1, 6000, 800, 2000, 6, 1.2, 1500, 0.5, 0.8, 10, 1.5, 1.1, 1.3, "L", 4, "S01, S25",
     "Fixed base = declarations per day. Agentic workloads use 4-15x more tokens than chat [S25]."),
    ("UC09", "Legal and regulatory research", "Agent / reasoning", 1, "Production", "Civil servants", 0.02, 0, 50, 0.2, 0.5, 0.8, 0, 3, 8000, 1000, 3000, 3, 1.1, 1000, 0.5, 0.8, 8, 2, 1.2, 1, "L", 2, "S01, S25", ""),
    ("UC10", "Government software engineering assistant", "Copilot", 1, "Production", "Fixed", 1, 2000, 100, 0.3, 0.6, 0.9, 0, 30, 4000, 400, 0, 1, 1.1, 1000, 0.6, 0.8, 8, 2, 1.2, 1, "M", 3, "S01", "Fixed base = government developers."),
    ("UC11", "Call centre and court transcript summaries", "Content / extraction", 1, "Production", "Fixed", 1, 30000, 1000, 0.2, 0.5, 0.8, 0, 1, 3000, 400, 0, 1, 1.05, 500, 0.5, 0.8, 10, 1.5, 1.2, 1.2, "S", 3, "S01",
     "Fixed base = calls/hearings per day. Speech-to-text itself is in NonToken."),
    ("UC12", "Policy analysis agent", "Agent", 1, "Pilot", "Fixed", 1, 300, 30, 0.3, 0.6, 0.9, 0, 4, 10000, 1500, 4000, 8, 1.2, 2000, 0.5, 0.8, 8, 1.5, 1.2, 1, "L", 3, "S01, S25", "Fixed base = analysts."),
    ("UC13", "Security and intelligence analysis", "Agent", 0, "Pilot", "Fixed", 1, 200, 20, 0.3, 0.6, 0.9, 0, 5, 8000, 1000, 3000, 6, 1.2, 1500, 0.5, 0.8, 8, 1.5, 1.2, 1, "L", 4, "S01",
     "Excluded by default (Include = 0): usually outside World Bank engagement."),
    ("UC14", "Open data and statistics Q&A", "Chatbot", 1, "Production", "Population", 1, 0, 200, 0.002, 0.005, 0.01, 1, 0.3, 2500, 400, 0, 1, 1.1, 800, 0.5, 0.6, 10, 2, 1.2, 1.2, "M", 1, "S01", ""),
    ("UC15", "Social protection case management", "Copilot", 1, "Production", "Fixed", 1, 5000, 200, 0.2, 0.5, 0.8, 0, 15, 3000, 500, 0, 1, 1.1, 1000, 0.5, 0.8, 8, 2, 1.2, 1.3, "M", 4, "S01", "Fixed base = caseworkers."),
]
UC0, UCN = 4, 4 + len(uc) - 1
cols = [chr(c) for c in range(ord("A"), ord("Z") + 1)] + ["AA", "AB", "AC", "AD"]
pctcols = {"G", "J", "K", "L", "U", "V"}
for i, row in enumerate(uc):
    rr = UC0 + i
    for j, v in enumerate(row):
        col = cols[j]
        fmt = PCT if col in pctcols else (NUM if isinstance(v, int) and v >= 1000 else None)
        if col in {"S", "X", "Y", "Z"}:
            fmt = MULT
        c = put(ws, f"{col}{rr}", v, BLUE if 2 < j < 28 else BLACK, fmt, YEL if col in {"J", "K", "L"} else None)
        if col == "AD":
            c.alignment = WRAP
for col, f1 in [("E", '"Pilot,Production"'), ("F", '"Population,Civil servants,Fixed"'), ("AA", '"S,M,L"'), ("AB", '"1,2,3,4"'), ("D", '"0,1"')]:
    d = DataValidation(type="list", formula1=f1)
    ws.add_data_validation(d)
    d.add(f"{col}{UC0}:{col}{UCN}")
ws.freeze_panes = "C4"
note_r = UCN + 2
ws[f"A{note_r}"] = ("Formulas downstream (Demand_L1_L3): Users = Pilot users if Mode = Pilot; else base x eligible share x adoption(scenario) x EGDI adjustment (citizen-facing only). "
                    "Base: Population x internet users | Civil servants | Fixed base. Do not stack internet share on a base that is already digital (double counting).")
ws[f"A{note_r}"].font = Font(name=F, italic=True)

# ---------------------------------------------------------------- NonToken
ws = wb.create_sheet("NonToken")
title(ws, "Non-token GPU workloads (biometrics, OCR, speech, vision) and batch fine-tuning",
      "Units are not tokens. GPU-seconds per unit = benchmark throughput inverted; calibrate with MLPerf Inference results or a vendor test. Batch work fills idle GPU hours before adding GPUs.")
header(ws, 3, ["ID", "Workload", "Include (1/0)", "Unit", "Units per day", "GPU-seconds per unit", "Interactive / Batch",
               "Peak-window share", "Peak window (hours)", "Burst ratio", "Data class (1-4)", "Tier", "GPU-hours per day (derated)",
               "Peak GPUs (interactive, derated)", "Source IDs", "Basis / note"],
       [7, 40, 9, 22, 13, 11, 12, 10, 10, 9, 9, 7, 13, 13, 12, 80])
nt = [
    ("NT01", "Biometric 1:N deduplication at enrolment", 1, "enrolments", 5000, 2.0, "Batch", 0.6, 10, 1.5, 4, "S08",
     "PLACEHOLDER GPU-seconds (depends on gallery size and vendor ABIS). Obtain from ABIS vendor benchmark."),
    ("NT02", "Face 1:1 verification (authentication)", 1, "authentications", 100000, 0.02, "Interactive", 0.6, 10, 2, 4, "S08", "PLACEHOLDER. Many deployments run 1:1 on CPU; set Include = 0 if so."),
    ("NT03", "Document OCR and layout extraction", 1, "pages", 50000, 0.3, "Batch", 0.6, 10, 1.5, 3, "S08", "PLACEHOLDER. Calibrate with MLPerf vision results or a vendor OCR test."),
    ("NT04", "Speech-to-text (call centres, courts, voice channels)", 1, "audio hours", 2000, 60, "Interactive", 0.7, 10, 1.5, 3, "S08",
     "PLACEHOLDER ~60 GPU-seconds per audio hour (~60x real time). MLPerf Inference includes Whisper: use its result."),
    ("NT05", "Satellite / aerial image analysis", 1, "image tiles", 20000, 0.1, "Batch", 0.5, 12, 1, 1, "S08", "PLACEHOLDER."),
    ("NT06", "Model fine-tuning and evaluation", 1, "GPU-hours (annual / 365)", "=20000/365", 3600, "Batch", 0.5, 12, 1, 3, "S03",
     "Input annual GPU-hours (20,000 placeholder) divided by 365. 1 unit = 1 GPU-hour = 3,600 GPU-seconds."),
    ("NT07", "Classical ML scoring (fraud, risk, forecasting)", 0, "transactions", 0, 0, "Batch", 0.5, 12, 1, 3, "S30",
     "OUT OF GPU SCOPE: runs on CPU (US Census example [S30]). Size in the conventional data centre tool."),
]
NT0, NTN = 4, 4 + len(nt) - 1
for i, row in enumerate(nt):
    rr = NT0 + i
    (nid, name, inc, unit, upd, gs, mode, ps, wh, br, dc, src, note) = row
    vals = [nid, name, inc, unit, upd, gs, mode, ps, wh, br, dc]
    fmts = [None, None, None, None, NUM, NUM2, None, PCT, None, MULT, None]
    for j, v in enumerate(vals):
        col = "ABCDEFGHIJK"[j]
        put(ws, f"{col}{rr}", v, BLUE if j >= 2 else BLACK, fmts[j], YEL if col in {"E", "F"} else None)
    put(ws, f"L{rr}", f"=INDEX(Placement!$C$4:$C$7,MATCH(K{rr},Placement!$A$4:$A$7,0))", GREEN)
    put(ws, f"M{rr}", f"=IF(C{rr}=0,0,E{rr}*F{rr}/3600/{C['der']})", BLACK, NUM1)
    put(ws, f"N{rr}", f'=IF(OR(C{rr}=0,G{rr}="Batch"),0,E{rr}*F{rr}*H{rr}/(I{rr}*3600)*J{rr}/{C["der"]})', BLACK, NUM2)
    put(ws, f"O{rr}", src)
    c = put(ws, f"P{rr}", note)
    c.alignment = WRAP
d = DataValidation(type="list", formula1='"Interactive,Batch"')
ws.add_data_validation(d)
d.add(f"G{NT0}:G{NTN}")

# ---------------------------------------------------------------- Demand
ws = wb.create_sheet("Demand_L1_L3")
title(ws, "Layers 1-3: users -> tokens -> peak tokens per second",
      "Method: NVIDIA AI Tokenomics worksheet [S01]. Corrections: input, cached input and output kept separate [S07]; system prompt tokens added before cache savings are subtracted.")
DH = ["ID", "Use case", "L0: Users", "L1: Sessions per day", "L2: Input tokens per task", "L2: Cached input tokens per task",
      "L2: Output tokens per task (incl. reasoning)", "Daily input tokens", "Daily cached input tokens", "Daily output tokens",
      "Daily equivalent tokens (output + uncached input x prefill weight)", "Tokens per user per day", "Sanity check",
      "Average equivalent tokens/s", "L3: Peak equivalent tokens/s", "Model class", "Data class", "Tier",
      "Annual uncached input tokens (M)", "Annual output tokens (M)", "Annual equivalent tokens (M)", "API cost per year ($)"]
header(ws, 3, DH, [7, 36, 12, 12, 11, 11, 11, 15, 15, 15, 16, 12, 22, 12, 13, 8, 8, 7, 14, 14, 14, 14])
L = "L0_UseCases!"
for i in range(len(uc)):
    rr = UC0 + i
    base = f'IF({L}F{rr}="Population",{C["pop"]}*{C["inet"]},IF({L}F{rr}="Civil servants",{C["cs"]},{L}H{rr}))'
    adopt = f'IF({C["scn"]}="Low",{L}J{rr},IF({C["scn"]}="High",{L}L{rr},{L}K{rr}))'
    adj = f'IF({L}M{rr}=1,MIN(1.5,{C["egdi"]}/{C["egdiw"]}),1)'
    put(ws, f"A{rr}", f"={L}A{rr}", GREEN)
    put(ws, f"B{rr}", f"={L}B{rr}", GREEN)
    put(ws, f"C{rr}", f'=IF({L}D{rr}=0,0,IF({L}E{rr}="Pilot",{L}I{rr},{base}*{L}G{rr}*{adopt}*{adj}))', GREEN, NUM)
    put(ws, f"D{rr}", f"=C{rr}*{L}N{rr}", GREEN, NUM)
    put(ws, f"E{rr}", f"=({L}O{rr}+{L}T{rr})*{L}R{rr}*{L}S{rr}", GREEN, NUM)
    put(ws, f"F{rr}", f"={L}T{rr}*{L}U{rr}*{L}R{rr}*{L}S{rr}", GREEN, NUM)
    put(ws, f"G{rr}", f"=({L}P{rr}+{L}Q{rr})*{L}R{rr}*{L}S{rr}", GREEN, NUM)
    put(ws, f"H{rr}", f"=D{rr}*E{rr}", BLACK, NUM)
    put(ws, f"I{rr}", f"=D{rr}*F{rr}", BLACK, NUM)
    put(ws, f"J{rr}", f"=D{rr}*G{rr}", BLACK, NUM)
    put(ws, f"K{rr}", f"=J{rr}+(H{rr}-I{rr})*{C['pre']}", GREEN, NUM)
    put(ws, f"L{rr}", f"=IF(C{rr}=0,0,(H{rr}+J{rr})/C{rr})", BLACK, NUM)
    put(ws, f"M{rr}", f'=IF(L{rr}>{C["ceil"]},"CHECK: above human ceiling","OK")', GREEN)
    put(ws, f"N{rr}", f"=K{rr}/86400", BLACK, NUM1)
    put(ws, f"O{rr}", f"=K{rr}*{L}V{rr}/({L}W{rr}*3600)*{L}X{rr}*{L}Y{rr}*{L}Z{rr}", GREEN, NUM1)
    put(ws, f"P{rr}", f"={L}AA{rr}", GREEN)
    put(ws, f"Q{rr}", f"={L}AB{rr}", GREEN)
    put(ws, f"R{rr}", f"=INDEX(Placement!$C$4:$C$7,MATCH(Q{rr},Placement!$A$4:$A$7,0))", GREEN)
    put(ws, f"S{rr}", f"=(H{rr}-I{rr})*365/1000000", BLACK, NUM1)
    put(ws, f"T{rr}", f"=J{rr}*365/1000000", BLACK, NUM1)
    put(ws, f"U{rr}", f"=K{rr}*365/1000000", BLACK, NUM1)
    put(ws, f"V{rr}", f"=S{rr}*INDEX(TCO_L5!$B$5:$B$7,MATCH(P{rr},TCO_L5!$A$5:$A$7,0))+T{rr}*INDEX(TCO_L5!$C$5:$C$7,MATCH(P{rr},TCO_L5!$A$5:$A$7,0))", GREEN, USD)
TR = UCN + 1
put(ws, f"A{TR}", "Total", BOLD)
for col in ["C", "D", "H", "I", "J", "K", "N", "O", "S", "T", "U", "V"]:
    put(ws, f"{col}{TR}", f"=SUM({col}{UC0}:{col}{UCN})", BOLD, USD if col == "V" else NUM)
ws[f"A{TR+2}"] = ("Formulas: E = (ISL + system prompt) x steps x retries | F = system prompt x cache hit x steps x retries | G = (OSL + reasoning) x steps x retries | "
                  "O = daily equivalent x peak share / (window h x 3600) x burst x SLA headroom x seasonal [S01]. "
                  "Headroom raises capacity, not consumption: annual tokens and API cost use daily volumes only.")
ws[f"A{TR+2}"].font = Font(name=F, italic=True)
ws.freeze_panes = "C4"

DR = (UC0, UCN)


def drng(col):
    return f"Demand_L1_L3!${col}${DR[0]}:${col}${DR[1]}"


def nrng(col):
    return f"NonToken!${col}${NT0}:${col}${NTN}"


# ---------------------------------------------------------------- Sizing
ws = wb.create_sheet("Sizing_L4")
title(ws, "Layer 4: peak tokens/s -> GPUs -> IT kW -> facility MW, by tier",
      "GPUs = peak tokens/s x diversity D / (tokens/s per GPU x production derating) [S03 instance formula]. Facility = IT x PUE. Batch work first uses idle GPU-hours.")
SH = ["Tier", "Hardware profile", "Peak eq. tok/s: S (diversified)", "Peak eq. tok/s: M (diversified)", "Peak eq. tok/s: L (diversified)",
      "GPUs for LLM peak", "GPUs for non-token interactive peak", "Avg eq. tok/s: S", "Avg eq. tok/s: M", "Avg eq. tok/s: L",
      "Busy GPU-hours/day (interactive)", "Batch GPU-hours/day", "Base GPUs", "Idle GPU-hours/day", "Extra GPUs for batch",
      "Total GPUs", "Average utilisation", "IT load (kW)", "Facility power (MW)", "Racks", "Annual energy (MWh)", "Grid check"]
header(ws, 3, SH, [7, 9, 13, 13, 13, 10, 11, 11, 11, 11, 12, 11, 9, 11, 10, 9, 10, 11, 11, 8, 12, 40])


def hwv(prof, col):
    return f"INDEX({hw(col)},MATCH({prof},{HWR},0))"


for i, t in enumerate(["T1", "T2", "T3", "T4"]):
    rr = 4 + i
    pr = f"B{rr}"
    put(ws, f"A{rr}", t)
    put(ws, f"B{rr}", f"=INDEX(Placement!$F$11:$F$14,MATCH(A{rr},Placement!$A$11:$A$14,0))", GREEN)
    for col, cls in [("C", "S"), ("D", "M"), ("E", "L")]:
        put(ws, f"{col}{rr}", f'=SUMIFS({drng("O")},{drng("R")},A{rr},{drng("P")},"{cls}")*{C["D"]}', GREEN, NUM)
    gpu_llm = f"C{rr}/{hwv(pr,'F')}+D{rr}/{hwv(pr,'G')}+E{rr}/{hwv(pr,'H')}"
    put(ws, f"F{rr}", f"=ROUNDUP(({gpu_llm})/{C['der']},0)", GREEN, NUM)
    put(ws, f"G{rr}", f'=ROUNDUP(SUMIFS({nrng("N")},{nrng("L")},A{rr})*{C["D"]},0)', GREEN, NUM)
    for col, cls in [("H", "S"), ("I", "M"), ("J", "L")]:
        put(ws, f"{col}{rr}", f'=SUMIFS({drng("N")},{drng("R")},A{rr},{drng("P")},"{cls}")', GREEN, NUM)
    busy = f"(H{rr}/{hwv(pr,'F')}+I{rr}/{hwv(pr,'G')}+J{rr}/{hwv(pr,'H')})/{C['der']}*24"
    put(ws, f"K{rr}", f'={busy}+SUMIFS({nrng("M")},{nrng("L")},A{rr},{nrng("G")},"Interactive")', GREEN, NUM)
    put(ws, f"L{rr}", f'=SUMIFS({nrng("M")},{nrng("L")},A{rr},{nrng("G")},"Batch")', GREEN, NUM)
    put(ws, f"M{rr}", f"=F{rr}+G{rr}", BLACK, NUM)
    put(ws, f"N{rr}", f"=MAX(0,M{rr}*24-K{rr})", BLACK, NUM)
    put(ws, f"O{rr}", f"=ROUNDUP(MAX(0,L{rr}-N{rr})/24,0)", BLACK, NUM)
    put(ws, f"P{rr}", f"=M{rr}+O{rr}", BOLD, NUM)
    put(ws, f"Q{rr}", f"=IF(P{rr}=0,0,MIN(1,(K{rr}+L{rr})/(P{rr}*24)))", BLACK, PCT)
    put(ws, f"R{rr}", f"=P{rr}*{hwv(pr,'E')}", GREEN, NUM)
    put(ws, f"S{rr}", f"=R{rr}*{C['pue']}/1000", GREEN, "0.00")
    put(ws, f"T{rr}", f"=IF(R{rr}=0,0,ROUNDUP(R{rr}/{hwv(pr,'D')},0))", GREEN, NUM)
    put(ws, f"U{rr}", f"=R{rr}*({C['idle']}+(1-{C['idle']})*Q{rr})*{C['pue']}*8760/1000", GREEN, NUM)
    put(ws, f"V{rr}", f'=IF(P{rr}=0,"-",IF(A{rr}="T1","Offshore: not applicable",IF({C["outages"]}>{C["weak"]},IF({hwv(pr,"L")}="No","WARNING: profile unsuitable for weak grid","Weak grid: budget backup and storage"),"OK")))', GREEN)
put(ws, "A8", "Total", BOLD)
for col in ["F", "G", "L", "M", "O", "P", "R", "T", "U"]:
    put(ws, f"{col}8", f"=SUM({col}4:{col}7)", BOLD, NUM)
put(ws, "S8", "=SUM(S4:S7)", BOLD, "0.00")
ws["A10"] = "T1 capacity sits in a hyperscaler: its MW is shown for information, not to be built locally."
ws["A10"].font = Font(name=F, italic=True)
ws["A11"] = "Validation path: send the T3/T4 workload (ISL, OSL, peak request rate, TTFT/TPOT targets) to AIConfigurator [S04] for a minimum GPU count; compare with column P."
ws["A11"].font = Font(name=F, italic=True)

# ---------------------------------------------------------------- TCO
ws = wb.create_sheet("TCO_L5")
title(ws, "Layer 5: 10-year cost by tier and buying mode (eligible modes only)",
      "Structure: NVIDIA inference TCO method [S03] and FinOps AI cost estimation [S12]. Undiscounted, flat demand, USD.")
header(ws, 4, ["Model class", "API price: input ($ per M tokens)", "API price: output ($ per M tokens)", "Source / how to obtain"], None)
for col, w in zip("ABCDEFGHIJKLM", [12, 18, 18, 16, 16, 16, 16, 16, 16, 16, 14, 16, 22]):
    ws.column_dimensions[col].width = w
prices = [("S", 0.10, 0.40), ("M", 0.50, 1.50), ("L", 1.00, 4.00)]
for i, (k, a, b) in enumerate(prices):
    rr = 5 + i
    put(ws, f"A{rr}", k)
    put(ws, f"B{rr}", a, BLUE, USD2, YEL)
    put(ws, f"C{rr}", b, BLUE, USD2, YEL)
    put(ws, f"D{rr}", "S21: PLACEHOLDER. OpenRouter median price for an open-weight model of this size (see Online_Tools).")
ws["A9"] = "Owned and service parameters"
ws["A9"].font = BOLD
params = [
    ("Facility capex ($ per MW IT)", 11000000, USD, "S23: PLACEHOLDER. Use the current Cushman & Wakefield Data Center Development Cost Guide or local quotes."),
    ("Maintenance (% of capex per year)", 0.05, PCT, "Analyst assumption."),
    ("Operations staff per owned tier (FTE)", 4, NUM, "Analyst assumption."),
    ("Cost per FTE ($ per year)", 60000, USD, "Analyst assumption: local market."),
    ("GPU refresh cycle (years)", 5, NUM, "Common 4-5 year depreciation [S03]."),
]
for i, (p, v, f, s) in enumerate(params):
    rr = 10 + i
    put(ws, f"A{rr}", p)
    put(ws, f"B{rr}", v, BLUE, f, YEL)
    put(ws, f"D{rr}", s)
ws.column_dimensions["A"].width = 34
P = dict(fac="TCO_L5!$B$10", mnt="TCO_L5!$B$11", fte="TCO_L5!$B$12", ftec="TCO_L5!$B$13", ref="TCO_L5!$B$14")
header(ws, 17, ["Tier", "Total GPUs", "IT load (MW)", "API / managed: per year ($)", "GPU-as-a-service: per year ($)",
                "Owned: capex over horizon ($)", "Owned: opex per year ($)", "API / managed: horizon total ($)",
                "GPU-as-a-service: horizon total ($)", "Owned: horizon total ($)", "Annual equivalent tokens (M)",
                "Cheapest eligible: $ per M eq. tokens", "Cheapest eligible mode"])
for i, t in enumerate(["T1", "T2", "T3", "T4"]):
    rr = 18 + i
    sr = 4 + i
    el = lambda col: f"INDEX(Placement!${col}$11:${col}$14,MATCH(A{rr},Placement!$A$11:$A$14,0))"
    prof = f"Sizing_L4!$B${sr}"
    rate = f"INDEX({hw('I')},MATCH({prof},{HWR},0))"
    capg = f"INDEX({hw('J')},MATCH({prof},{HWR},0))"
    swg = f"INDEX({hw('K')},MATCH({prof},{HWR},0))"
    put(ws, f"A{rr}", t)
    put(ws, f"B{rr}", f"=Sizing_L4!P{sr}", GREEN, NUM)
    put(ws, f"C{rr}", f"=Sizing_L4!R{sr}/1000", GREEN, "0.00")
    nontok_gpus = f"(Sizing_L4!G{sr}+Sizing_L4!O{sr})"
    put(ws, f"D{rr}", f'=IF({el("C")}=1,SUMIFS({drng("V")},{drng("R")},A{rr})+{nontok_gpus}*8760*{rate},"Not eligible")', GREEN, USD)
    put(ws, f"E{rr}", f'=IF({el("D")}=1,B{rr}*8760*{rate},"Not eligible")', GREEN, USD)
    put(ws, f"F{rr}", f"=IF({el('E')}=1,B{rr}*{capg}*ROUNDUP({C['hor']}/{P['ref']},0)+C{rr}*{P['fac']},\"Not eligible\")", GREEN, USD)
    opex = (f"Sizing_L4!U{sr}*1000*{C['kwh']}+B{rr}*{swg}+IF(B{rr}>0,{P['fte']}*{P['ftec']},0)"
            f"+{P['mnt']}*(B{rr}*{capg}+C{rr}*{P['fac']})")
    put(ws, f"G{rr}", f'=IF({el("E")}=1,{opex},"Not eligible")', GREEN, USD)
    put(ws, f"H{rr}", f'=IF(ISNUMBER(D{rr}),D{rr}*{C["hor"]},"Not eligible")', GREEN, USD)
    put(ws, f"I{rr}", f'=IF(ISNUMBER(E{rr}),E{rr}*{C["hor"]},"Not eligible")', GREEN, USD)
    put(ws, f"J{rr}", f'=IF(ISNUMBER(F{rr}),F{rr}+G{rr}*{C["hor"]},"Not eligible")', GREEN, USD)
    put(ws, f"K{rr}", f'=SUMIFS({drng("U")},{drng("R")},A{rr})', GREEN, NUM)
    put(ws, f"L{rr}", f'=IF(OR(B{rr}=0,K{rr}=0),"-",MIN(H{rr}:J{rr})/(K{rr}*{C["hor"]}))', GREEN, USD2)
    put(ws, f"M{rr}", f'=IF(B{rr}=0,"No demand",IF(H{rr}=MIN(H{rr}:J{rr}),"API / managed",IF(I{rr}=MIN(H{rr}:J{rr}),"GPU-as-a-service","Owned")))', BLACK)
ws["A23"] = ("Notes: API mode prices LLM tokens per use case (Demand_L1_L3 col V) and buys non-token GPUs as a service. GPU-as-a-service = all GPUs reserved 24/7. "
             "Owned = GPU capex x refresh cycles + facility capex + energy + software + staff + maintenance. Cost per token includes non-token workloads.")
ws["A23"].font = Font(name=F, italic=True)

# ---------------------------------------------------------------- Ladder
ws = wb.create_sheet("Ladder")
title(ws, "Output: compute ladder by tier",
      "Start hybrid, earn the local build. Read with the scenario selected in Country!B10.")
header(ws, 3, ["Tier", "Description", "Total GPUs", "IT load (MW)", "Facility power (MW)", "Annual energy (MWh)",
               "Cheapest eligible mode", "Horizon cost, cheapest ($)", "Grid check", "Recommended step"],
       [7, 44, 10, 10, 11, 12, 18, 16, 36, 70])
for i, t in enumerate(["T1", "T2", "T3", "T4"]):
    rr = 4 + i
    sr, tr = 4 + i, 18 + i
    put(ws, f"A{rr}", t)
    put(ws, f"B{rr}", f"=INDEX(Placement!$B$11:$B$14,MATCH(A{rr},Placement!$A$11:$A$14,0))", GREEN)
    put(ws, f"C{rr}", f"=Sizing_L4!P{sr}", GREEN, NUM)
    put(ws, f"D{rr}", f"=Sizing_L4!R{sr}/1000", GREEN, "0.00")
    put(ws, f"E{rr}", f"=Sizing_L4!S{sr}", GREEN, "0.00")
    put(ws, f"F{rr}", f"=Sizing_L4!U{sr}", GREEN, NUM)
    put(ws, f"G{rr}", f"=TCO_L5!M{tr}", GREEN)
    put(ws, f"H{rr}", f'=IF(C{rr}=0,0,MIN(TCO_L5!H{tr}:J{tr}))', GREEN, USD)
    put(ws, f"I{rr}", f"=Sizing_L4!V{sr}", GREEN)
    c = put(ws, f"J{rr}", f'=IF(C{rr}=0,"No demand in this tier",IF(OR(A{rr}="T1",A{rr}="T2"),"Step 0: use cloud / API under residency terms now",IF(E{rr}<{C["thr"]},"Step 1: small sovereign inference node in an existing facility","Step 2: dedicated capacity via private operator or PPP (IFC-investable)")))', GREEN)
    c.alignment = WRAP
put(ws, "A8", "Total", BOLD)
for col, f in [("C", NUM), ("D", "0.00"), ("E", "0.00"), ("F", NUM), ("H", USD)]:
    put(ws, f"{col}8", f"=SUM({col}4:{col}7)", BOLD, f)
ws["A10"] = "Triggers to move up a step (review annually)"
ws["A10"].font = BOLD
trig = [
    "Step 0 -> 1: a confidential or restricted use case reaches production, or the data protection law requires in-country processing.",
    "Step 1 -> 2: measured utilisation of the Step 1 node above ~60% for two quarters, and at least three use cases in production.",
    "Any step: grid check shows a warning -> budget backup and storage before committing capex.",
    "Any step: replace placeholders (yellow cells) with calibrated values before sharing results externally.",
]
for i, t in enumerate(trig):
    ws.cell(row=11 + i, column=1, value=f"- {t}").font = Font(name=F)

# ---------------------------------------------------------------- Online tools
ws = wb.create_sheet("Online_Tools")
title(ws, "Inputs that come from online tools: how to get them", "One row per input cell. Record the date and version you used in the Note column.")
header(ws, 3, ["Feeds cell", "Tool", "URL", "Steps", "Note"], [26, 26, 52, 110, 30])
tools = [
    ("Hardware_L4 F:H (tokens/s per GPU), profile P3", "AIConfigurator (NVIDIA Dynamo)", "https://github.com/ai-dynamo/aiconfigurator",
     "1) Install per the README quick start. 2) Choose the system (GPU type), backend (TensorRT-LLM, vLLM or SGLang) and model of each class (e.g. 8B, 70B, a large MoE). "
     "3) Set ISL and OSL to the dominant use case of that class (L0_UseCases O:P) and the latency targets (TTFT, time per output token). "
     "4) Run the default search; it reports SLA-compliant configurations and their throughput. 5) Enter tokens/s per GPU of the best compliant configuration. "
     "Treat as model-based estimates [S05]."),
    ("Country!B16 (production derating)", "GenAI-Perf", "https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/perf_benchmark/genai-perf-README.html",
     "1) Stand up a test endpoint (any cloud GPU) with the same model and backend. 2) Run GenAI-Perf with the use case ISL/OSL and rising concurrency. "
     "3) Take the highest throughput that still meets the latency target. 4) Derating = measured / AIConfigurator estimate."),
    ("NonToken F (GPU-seconds per unit)", "MLPerf Inference results", "https://mlcommons.org/benchmarks/inference-datacenter/",
     "1) Open the latest datacenter results. 2) Find the closest workload (vision models for OCR/images, Whisper for speech). "
     "3) Take the Server scenario throughput for your GPU, divide by number of GPUs. 4) GPU-seconds per unit = 1 / (units per second per GPU)."),
    ("TCO_L5 B5:C7 (API prices)", "OpenRouter model list", "https://openrouter.ai/models",
     "1) Filter by open-weight models of each size class. 2) Read input and output price per million tokens. 3) Enter the median of 3-5 providers."),
    ("Country!B11 (electricity price)", "GlobalPetrolPrices", "https://www.globalpetrolprices.com/electricity_prices/",
     "1) Select the country. 2) Use the business tariff in USD/kWh. 3) Prefer the utility's published large-customer tariff if available."),
    ("Country!B6 (internet users)", "World Bank data / ITU", "https://data.worldbank.org/indicator/IT.NET.USER.ZS",
     "1) Search the country. 2) Take the latest year. 3) Enter as a fraction (45% = 0.45)."),
    ("Country!B7 (civil servants)", "World Bank Worldwide Bureaucracy Indicators", "https://www.worldbank.org/en/data/interactive/2019/05/21/worldwide-bureaucracy-indicators-dashboard",
     "1) Select the country. 2) Read public sector employment (count, or share x employed population from WDI)."),
    ("Country!B8 (EGDI)", "UN E-Government Knowledgebase", "https://publicadministration.un.org/egovkb/en-us/Data-Center",
     "1) Select the country. 2) Read the latest EGDI value."),
    ("Country!B12 (outages per month)", "World Bank Enterprise Surveys", "https://www.enterprisesurveys.org/en/data/exploretopics/infrastructure",
     "1) Select the country. 2) Read 'number of electrical outages in a typical month'."),
    ("Hardware_L4 (cross-check of P1/P2)", "AI-DC Calculator / Netray (sanity check only)", "https://dmvevents.github.io/aidc-calculator/",
     "Enter the GPU count from Sizing_L4 and compare rack, power and capex outputs. Planning-grade tools: do not use as a source."),
]
for i, row in enumerate(tools):
    rr = 4 + i
    for j, v in enumerate(row):
        c = put(ws, f"{'ABCDE'[j]}{rr}", v)
        c.alignment = WRAP
    put(ws, f"E{rr}", "Date / version used:", BLUE)
    ws.row_dimensions[rr].height = 70

# ---------------------------------------------------------------- Sources
ws = wb.create_sheet("Sources")
title(ws, "Sources", "Every Source ID used in the workbook. Vendor sources are flagged: use their structure, calibrate their numbers.")
header(ws, 3, ["ID", "Title", "Publisher", "URL", "Used for", "Type"], [7, 60, 26, 70, 50, 14])
src = [
    ("S01", "AI Tokenomics: forecasting worksheet (base demand, workload multipliers, operational shaping)", "NVIDIA", "https://www.nvidia.com/en-us/solutions/ai/tokenomics-guide/", "Layers 1-3 structure", "Vendor"),
    ("S02", "Rethinking AI TCO: Why Cost per Token Is the Only Metric That Matters (Apr 2026)", "NVIDIA", "https://blogs.nvidia.com/blog/lowest-token-cost-ai-factories/", "Tokens/s per GPU and per MW, $/GPU-hour, cost per token formula", "Vendor"),
    ("S03", "LLM Inference Benchmarking: How Much Does Your LLM Inference Cost?", "NVIDIA", "https://developer.nvidia.com/blog/llm-inference-benchmarking-how-much-does-your-llm-inference-cost/", "Instances = peak / throughput at latency target; TCO structure, licensing, depreciation", "Vendor"),
    ("S04", "AIConfigurator", "NVIDIA ai-dynamo (open source)", "https://github.com/ai-dynamo/aiconfigurator", "Workload + SLA -> configuration and minimum GPUs", "Tool"),
    ("S05", "Lightning-Fast Configuration Optimization for Multi-Framework LLM Inference", "arXiv", "https://arxiv.org/html/2601.06288v1", "Method behind AIConfigurator", "Paper"),
    ("S06", "GenAI-Perf documentation", "NVIDIA", "https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/perf_benchmark/genai-perf-README.html", "Measured throughput and latency; derating calibration", "Tool"),
    ("S07", "Right-sizing and auto-scaling an inference system", "AWS Prescriptive Guidance", "https://docs.aws.amazon.com/prescriptive-guidance/latest/gen-ai-inference-architecture-and-best-practices-on-aws/right-sizing-and-auto-scaling.html", "Keep input and output lengths separate; benchmark real workload shapes", "Independent check"),
    ("S08", "MLPerf Inference (datacenter results)", "MLCommons", "https://mlcommons.org/benchmarks/inference-datacenter/", "Non-token throughput (vision, Whisper speech)", "Benchmark"),
    ("S09", "MLCommons Power working group", "MLCommons", "https://mlcommons.org/working-groups/benchmarks/power/", "Power measurement method; idle power", "Benchmark"),
    ("S10", "DGX H100/H200 User Guide: system power 10.2 kW max", "NVIDIA", "https://docs.nvidia.com/dgx/dgxh100-user-guide/introduction-to-dgxh100.html", "Server power for P1", "Vendor spec"),
    ("S11", "MLPerf Inference numbers vs production throughput; GPU rental rates", "GMI Cloud", "https://www.gmicloud.ai/en/blog/mlperf-inference-vs-production-throughput", "Production derating rationale; $/GPU-hour", "Provider"),
    ("S12", "Cost Estimation of AI Workloads", "FinOps Foundation", "https://www.finops.org/wg/cost-estimation-of-ai-workloads/", "TCO structure", "Independent"),
    ("S13", "Government Migration to Cloud Ecosystems: Multiple Options, Significant Benefits, Manageable Risks", "World Bank (2022)", "https://www.worldbank.org/en/topic/digital/publication/government-migration-to-cloud-ecosystems-multiple-options-significant-benefits-manageable-risks", "Hybrid as default; tier logic", "World Bank"),
    ("S14", "Data Classification Matrix and Cloud Assessment Framework", "World Bank (2023)", "https://openknowledge.worldbank.org/entities/publication/876f86a8-5ed0-4f44-8ea4-ab49695521e8/full", "Data class -> security requirements -> tier", "World Bank"),
    ("S15", "Individuals using the Internet (% of population), IT.NET.USER.ZS", "World Bank / ITU", "https://data.worldbank.org/indicator/IT.NET.USER.ZS", "Country!B6", "Data"),
    ("S16", "ITU ICT statistics", "ITU", "https://www.itu.int/en/ITU-D/Statistics/pages/stat/default.aspx", "Connectivity cross-check", "Data"),
    ("S17", "UN E-Government Survey, data centre (EGDI)", "UN DESA", "https://publicadministration.un.org/egovkb/en-us/Data-Center", "Country!B8:B9", "Data"),
    ("S18", "Worldwide Bureaucracy Indicators", "World Bank", "https://www.worldbank.org/en/data/interactive/2019/05/21/worldwide-bureaucracy-indicators-dashboard", "Country!B7", "Data"),
    ("S19", "Enterprise Surveys: infrastructure (electrical outages)", "World Bank", "https://www.enterprisesurveys.org/en/data/exploretopics/infrastructure", "Country!B12", "Data"),
    ("S20", "Electricity prices", "GlobalPetrolPrices", "https://www.globalpetrolprices.com/electricity_prices/", "Country!B11", "Data"),
    ("S21", "Model list and prices", "OpenRouter", "https://openrouter.ai/models", "API prices", "Market data"),
    ("S22", "Global Data Center Survey (PUE)", "Uptime Institute", "https://uptimeinstitute.com/resources/research-and-reports", "Country!B14", "Industry survey"),
    ("S23", "Data Center Development Cost Guide", "Cushman & Wakefield", "https://www.cushmanwakefield.com/en/united-states/insights/data-center-development-cost-guide", "Facility capex per MW", "Industry"),
    ("S24", "How many digital workers could OpenAI deploy?", "Epoch AI", "https://epochai.substack.com/p/how-many-digital-workers-could-openai", "~240k tokens per human per day sanity ceiling", "Research"),
    ("S25", "Agentic workloads use 4-15x more tokens than chat (Signal65 research)", "MeriTalk", "https://www.meritalk.com/?p=209235", "Agent multipliers", "Industry"),
    ("S26", "The Army promised unlimited AI tokens; it ran dry in weeks", "DEV Community", "https://dev.to/jahanzaibai/the-army-promised-unlimited-ai-tokens-it-ran-dry-in-weeks-50g", "Real public-sector consumption anchor (200k tokens/user/month)", "Press"),
    ("S27", "A blueprint for building national compute capacity for AI", "OECD (2023)", "https://www.oecd.org/en/publications/a-blueprint-for-building-national-compute-capacity-for-artificial-intelligence_876367e3-en.html", "Policy framing", "Policy"),
    ("S28", "7 learnings about compute strategy (KIRA Compute Report 2025)", "Philip Fox / KIRA Center", "https://foxphilip.substack.com/p/7-learnings-about-compute-strategy", "Bottom-up national demand method", "Research"),
    ("S29", "Population, total (SP.POP.TOTL)", "World Bank WDI", "https://data.worldbank.org/indicator/SP.POP.TOTL", "Country!B5", "Data"),
    ("S30", "Why federal leaders must reclaim the economics of AI (CPU inference at US Census)", "FedScoop", "https://fedscoop.com/ai-infrastructure-economics-public-sector/", "Classical ML on CPU; ~90% of government AI is inference", "Press"),
]
for i, row in enumerate(src):
    rr = 4 + i
    for j, v in enumerate(row):
        c = put(ws, f"{'ABCDEF'[j]}{rr}", v)
        c.alignment = WRAP
        if j == 3:
            c.hyperlink = v
            c.font = Font(name=F, color="0563C1", underline="single")

# order sheets
order = ["README", "Ladder", "Country", "L0_UseCases", "NonToken", "Demand_L1_L3", "Placement", "Hardware_L4", "Sizing_L4", "TCO_L5", "Online_Tools", "Sources"]
wb._sheets = [wb[n] for n in order]
for s in wb.worksheets:
    s.sheet_view.zoomScale = 90
wb.save("/home/claude/build/Sovereign_AI_Compute_Planner_v0.1.xlsx")
print("saved")
