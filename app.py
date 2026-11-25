"""Sovereign AI Compute Planner: Shiny for Python front end.

Run locally:   shiny run app.py
Posit Connect: rsconnect deploy shiny . --entrypoint app:app
"""
from __future__ import annotations

import json
import re
import uuid
from copy import deepcopy

import pandas as pd
from shiny import App, reactive, render, ui

from engine import TIERS, load_api_prices, load_catalogue, load_countries, load_defaults, run
from engine.model import cost_params
from engine.options import OPTIONS, colo_price, compare, with_no_placement
from engine.archetypes import (processing_for, processing_key, EXAMPLE_PORTFOLIO, POPULATION_BASIS, example_portfolio, basis_label, build_profile, is_llm,
                               load_archetypes, low_usage_note, normalize_app, parse_custom_types, rate_for,
                               reference_sizes, volume_warning, CUSTOM_TEMPLATE)
import base64
import math
import datetime as _dt
import zlib

CAT = load_catalogue()
D = load_defaults()
ARCH = load_archetypes()
COUNTRIES = load_countries()
API_PRICES, API_PROV = load_api_prices(D)
SRC = {s["id"]: s for s in CAT["sources"]}
D_GPS = {h["id"]: h.get("gpus_per_server", 1) for h in CAT["hardware"]}


def cite(text: str) -> list:
    """Turn source IDs (S36) in evidence text into internal links to the Sources list on the Evidence tab."""
    out = []
    for i, part in enumerate(re.split(r"\b(S\d{2,3})\b", str(text))):
        if i % 2 and part in SRC:
            out.append(ui.tags.a(part, href=f"#src-{part}", title=SRC[part]["title"]))
        elif part:
            out.append(part)
    return out


def cited_ids(t: dict) -> list:
    ids = sorted({x for v in t["evidence"].values() for x in re.findall(r"\b(S\d{2,3})\b", str(v)) if x in SRC},
                 key=lambda x: int(x[1:]))
    return ids

TIER_COLORS = {"T1": "#2a78d6", "T2": "#eb6834", "T3": "#1baf7a", "T4": "#eda100"}
CLASS_LABELS = {1: "1 · Public", 2: "2 · Internal", 3: "3 · Confidential", 4: "4 · Restricted"}
SCEN = {"Low": "Cautious", "Base": "Expected", "High": "Aggressive"}

def type_choices_for(arch: dict) -> dict:
    """Dropdown entries grouped, with the evidence confidence in parentheses (usage rate / size)."""
    out = {}
    for a in arch.values():
        c = a["confidence"]
        conf = (f'confidence: usage {c["volume"]}, size {c["tokens"]}' if "isl" in a else f'confidence: {c["tokens"]}')
        out.setdefault(a["group"], {})[a["id"]] = f'{a["label"]} ({conf})'
    return out


type_choices = type_choices_for(ARCH)


def encode_state(sc: dict) -> str:
    """Scenario -> compact URL-safe text (zlib + base64). The link carries the whole scenario; nothing is stored on a server."""
    return base64.urlsafe_b64encode(zlib.compress(json.dumps(sc, separators=(",", ":")).encode(), 9)).decode().rstrip("=")


def decode_state(txt: str) -> dict:
    return json.loads(zlib.decompress(base64.urlsafe_b64decode(txt + "=" * (-len(txt) % 4))).decode())


SAVE_JS = """
(function () {
  const KEY = 'saicp_saved_v1';
  const W = (function () { try { return window.top.location.href && window.top; } catch (e) { return window; } })();
  function list() { try { return JSON.parse(localStorage.getItem(KEY) || '[]'); } catch (e) { return []; } }
  function put(l) { try { localStorage.setItem(KEY, JSON.stringify(l.slice(0, 100))); } catch (e) {} }
  function push() { Shiny.setInputValue('saved_list', list(), {priority: 'event'}); }
  $(document).one('shiny:connected', function () {
    Shiny.addCustomMessageHandler('save_link', function (m) {
      const url = W.location.origin + W.location.pathname + '#v=' + m.id + '&s=' + m.state;
      try { W.history.replaceState(null, '', url); } catch (e) {}
      const l = list(); l.unshift({id: m.id, name: m.name, date: m.date, state: m.state, url: url}); put(l);
      if (navigator.clipboard) { navigator.clipboard.writeText(url).catch(function () {}); }
      Shiny.setInputValue('share_url', url, {priority: 'event'}); push();
    });
    Shiny.addCustomMessageHandler('saved_remove', function (id) { put(list().filter(function (x) { return x.id !== id; })); push(); });
  });
  $(document).one('shiny:sessioninitialized', function () {
    push();
    const h = (W.location.hash || '').match(/[#&]s=([^&]+)/);
    if (h) { Shiny.setInputValue('url_state', h[1], {priority: 'event'}); }
  });
})();
"""
iso_choices = {k: v.get("name", k) for k, v in sorted(COUNTRIES.items(), key=lambda kv: kv[1].get("name", ""))}

CSS = """
:root { --accent:#1f3864; --muted:#6b7280; --line:#e5e7eb; }
body { font-family: 'Inter', 'Segoe UI', Arial, sans-serif; background:#f7f8fa; }
.navbar { background: var(--accent) !important; }
.navbar .navbar-brand, .navbar .nav-link { color:#fff !important; }
.navbar .nav-link.active { border-bottom: 2px solid #fff; }
.card { border:1px solid var(--line); border-radius:10px; box-shadow:none; }
.card-header { background:#fff; font-weight:600; border-bottom:1px solid var(--line); }
.hint { color: var(--muted); font-size: .88rem; }
.applist { width:100%; border-collapse:collapse; font-size:.92rem; }
.applist th { text-align:left; color:var(--muted); font-weight:500; border-bottom:1px solid var(--line); padding:6px 8px; }
.applist td { border-bottom:1px solid var(--line); padding:8px; vertical-align:middle; }
.badge-c { display:inline-block; padding:2px 8px; border-radius:10px; font-size:.78rem; background:#eef2ff; color:#1f3864; }
.badge-1 { background:#ecfdf5; color:#065f46; } .badge-2 { background:#eff6ff; color:#1e40af; }
.badge-3 { background:#fffbeb; color:#92400e; } .badge-4 { background:#fef2f2; color:#991b1b; }
.conf-High { color:#065f46; } .conf-Medium { color:#92400e; } .conf-Low { color:#991b1b; }
.btn-x { border:none; background:none; color:#991b1b; font-size:1.1rem; cursor:pointer; }
.kpi { background:#fff; border:1px solid var(--line); border-radius:10px; padding:16px 18px; }
.kpi .v { font-size:1.7rem; font-weight:600; color: var(--accent); }
.kpi .l { color: var(--muted); font-size:.85rem; }
.kpi .s { color: var(--muted); font-size:.8rem; }
.shiny-html-output table, table.dataframe { font-size:.9rem; width:100%; }
.shiny-html-output table th, table.dataframe th { text-align:left !important; color:var(--muted); font-weight:500; }
.shiny-html-output table td { text-align:left; }
.shiny-input-container:not(.shiny-input-container-inline) { width:100%; }
.sec { margin: 22px 0 10px; font-weight: 600; color: var(--accent); font-size: 1.15rem; }
.answer { background: var(--accent); color: #fff; border-radius: 12px; padding: 18px 22px; margin-bottom: 8px; }
.answer .big { font-size: 1.6rem; font-weight: 600; }
.answer .line { font-size: 1rem; opacity: .92; margin-top: 4px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 14px; }
.ccard { background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 16px 18px; border-top: 5px solid var(--c); }
.ccard h5 { margin: 0 0 2px; font-size: 1.02rem; font-weight: 600; }
.ccard .sub { color: var(--muted); font-size: .84rem; margin-bottom: 10px; }
.ccard .row2 { display: flex; gap: 18px; flex-wrap: wrap; margin: 6px 0; }
.ccard .m .v { font-size: 1.25rem; font-weight: 600; color: #0b0b0b; }
.ccard .m .l { color: var(--muted); font-size: .78rem; }
.ccard .step { margin-top: 10px; font-size: .88rem; background: #f3f4f6; border-radius: 8px; padding: 8px 10px; }
.empty { padding:28px; text-align:center; color:var(--muted); }
.warn { background:#fffbeb; border:1px solid #fde68a; border-radius:8px; padding:10px 14px; font-size:.88rem; margin-bottom:12px; }
"""


def sig2(x):
    """Round to 2 significant figures: planning-grade, not false precision."""
    if not x:
        return 0
    from math import floor, log10
    return round(x, -int(floor(log10(abs(x)))) + 1)


def fmt(x, d=0):
    if x is None:
        return "-"
    if abs(x) >= 100:
        return f"{sig2(x):,.0f}"
    return f"{x:,.{d}f}"


def money(x):
    if x is None:
        return "-"
    x = sig2(x)
    if abs(x) >= 1e9:
        return f"${x / 1e9:,.1f}B"
    if abs(x) >= 1e6:
        return f"${x / 1e6:,.1f}M" if x < 1e7 else f"${x / 1e6:,.0f}M"
    if abs(x) >= 1e3:
        return f"${x / 1e3:,.0f}k"
    return f"${x:,.0f}"


def power(mw):
    if not mw:
        return "0 kW"
    return f"{sig2(mw * 1000):,.0f} kW" if mw < 1 else f"{sig2(mw):g} MW"


def usd(v):
    """Exact figure, rounded to the dollar (results page)."""
    return f"-${-v:,.0f}" if v < 0 else f"${v:,.0f}"


def money_range(lo, hi):
    """'$75–115M' style range."""
    if lo is None or hi is None:
        return "-"
    a, b = money(lo), money(hi)
    for suf in ("B", "M", "k"):
        if a.endswith(suf) and b.endswith(suf):
            return f"{a[:-1]}–{b[1:]}"
    return f"{a}–{b}"


def num(x):
    try:
        return None if x in (None, "") else float(x)
    except (TypeError, ValueError):
        return None


def kpi(label, value, sub=""):
    return ui.div(ui.div(label, class_="l"), ui.div(value, class_="v"), ui.div(sub, class_="s"), class_="kpi")


# ------------------------------------------------------------------ UI
setup_panel = ui.nav_panel(
    "1 · Setup",
    ui.layout_columns(
        ui.card(
            ui.card_header("Country"),
            ui.input_selectize("iso", None, iso_choices, selected="XEX"),
            ui.output_ui("country_facts"),
            ui.input_radio_buttons("grid", "Grid reliability",
                                   {"auto": "From data", "reliable": "Reliable", "weak": "Weak (frequent outages)"},
                                   selected="auto", inline=True),
            ui.input_numeric("kwh", "Electricity tariff for data centres ($/kWh)", value=None, step=0.01),
            ui.input_numeric("pue", "Site PUE for air cooling (optional)", value=None, min=1.0, max=3.0, step=0.05),
            ui.p("Leave empty to use the regional value. For a specific site, run the Schneider Electric "
                 "Data center efficiency and PUE calculator [S48] and enter its PUE here.", class_="hint"),
            ui.p("Leave empty to use the country value, or the default range if none.", class_="hint"),
        ),
        ui.card(
            ui.card_header("Owning the servers"),
            ui.p("Two owned options are compared: servers in a commercial colocation data centre (price per kW, by "
                 "country), and servers in a data centre the government builds or already has.", class_="hint"),
            ui.input_checkbox("redundancy", "Owned options: add one spare server (N+1) for redundancy", value=False),
            ui.input_checkbox("own_dc_existing", "Own data centre: an existing facility has spare power and cooling "
                              "(no build cost; energy, staff and maintenance still counted)", value=False),
            ui.output_ui("colo_facts"),
        ),
        ui.card(
            ui.card_header("Adoption scenario"),
            ui.input_radio_buttons("ambition", None, SCEN, selected="Base", inline=True),
            ui.p("Changes how often people use each application (Low / Base / High rates in the Evidence tab). "
                 "Volumes you enter are never changed.", class_="hint"),
            ui.card_header("Hardware"),
            ui.input_select("hw", None, {"auto": "Automatic (cheapest allowed; air-cooled only on weak or unknown grids and sites under 1 MW)",
                                         **{h["id"]: f'{h["id"]} · {h["name"]}' for h in CAT["hardware"]}}),
            ui.input_radio_buttons("speed", "Response speed per user",
                                   {"low": "Fast (~130 tok/s)", "base": "Standard (~95 tok/s)", "high": "Relaxed (~55 tok/s)"},
                                   selected="base", inline=True),
            ui.p("Faster responses mean fewer users per GPU. Figures from SemiAnalysis InferenceX [S44].", class_="hint"),
        ),
        col_widths=[6, 6],
    ),
    ui.card(
        ui.card_header("Finance"),
        ui.layout_columns(
            ui.input_numeric("disc", "Discount rate (%/year)", value=round(D["discount_rate"]["value"] * 100, 1), min=0, max=20, step=0.5),
            ui.input_numeric("decline", "API price decline (%/year)", value=round(D["api_price_decline"]["value"] * 100, 1), min=0, max=80, step=5),
            ui.input_numeric("decline_hw", "GPU rental and hardware price decline (%/year)", value=round(D["hw_price_decline"]["value"] * 100, 1), min=-20, max=50, step=5),
            ui.input_numeric("gain", "Newer hardware: more work per GPU (%/year)", value=round(D["compute_gain_per_year"]["value"] * 100, 1), min=0, max=60, step=5),
            col_widths=[6, 6]),
        ui.p("Costs are shown as present value over 10 years. Growth is set per application. Price decline applies to API "
             "tokens, GPU rental and GPU purchases. Newer hardware: servers bought or refreshed in later years, and rented GPUs, "
             "do more work per GPU at the same price (Epoch AI: +40% per year in FLOP/s per dollar, +18% in memory bandwidth).",
             class_="hint"),
    ),
    ui.card(
        ui.card_header("Price references and ownership choices"),
        ui.layout_columns(
            ui.input_select("api_ref", "API prices", {
                "hyperscaler": "Hyperscaler in region (open models on AWS / Azure)",
                "open_market": "Open market (cheapest providers, OpenRouter median)",
                "frontier": "Proprietary frontier models (GPT-5.4 family, regional processing)"},
                selected=D["api_reference"]["value"]),
            ui.input_numeric("api_disc", "Negotiated API discount, multi-year commitment (%)",
                             value=round(D["api_commit_discount"]["value"] * 100, 1), min=0, max=80, step=5),
            ui.input_select("rent_ref", "GPU rental provider", {
                "hyperscaler": "Hyperscaler (AWS / Azure)", "neocloud": "Specialised GPU cloud (neocloud)"},
                selected=D["gpu_rental_reference"]["value"]),
            ui.input_radio_buttons("rent_mode", "GPU rental contract", {
                "reserved": "Reserved all year (24/7)", "on_demand": "On demand, switched off when not needed"},
                selected=D["gpu_rental_mode"]["value"]),
            ui.input_select("sw", "Serving software on owned GPUs", {
                "nvidia": "NVIDIA AI Enterprise licence ($4,500 per GPU per year)",
                "open_source": "Open source (vLLM, Kubernetes): no licence"},
                selected=D["software_stack"]["value"]),
            ui.input_numeric("life", "Owned servers kept in service (years)", value=D["server_life_years"]["value"],
                             min=5, max=10, step=1),
            ui.input_checkbox("night", "Open idle GPU hours (nights, weekends) to universities and research", False),
            ui.panel_conditional("input.night",
                ui.input_numeric("night_share", "Share of idle hours used (%)", value=30, min=0, max=100, step=10)),
            col_widths=[6, 6]),
        ui.p("Defaults reflect what a government usually buys: a hyperscaler in its region, reserved GPUs and the NVIDIA "
             "software licence. Servers are not sold: after the 5-year refresh period they stay in service, out of warranty "
             "(maintenance x2), until the end of their life; new servers are bought only when the need exceeds what is installed. "
             "Shared idle hours are valued at half the neocloud rental price and add their electricity.", class_="hint"),
    ),
    ui.accordion(
        ui.accordion_panel(
            "Client quotes (optional)",
            ui.p("Leave empty to use the default cost range. A quote replaces the range.", class_="hint"),
            ui.layout_columns(
                ui.input_numeric("q_gpu_hour", "GPU rental ($/GPU-hour)", None),
                ui.input_numeric("q_gpu_capex", "GPU server cost ($/GPU)", None),
                ui.input_numeric("q_fac", "Data centre build ($/MW IT)", None),
                ui.input_numeric("q_colo", "Colocation ($/kW IT/month)", None),
                col_widths=[3, 3, 3, 3]),
        ),
        open=False,
    ),
)

apps_panel = ui.nav_panel(
    "2 · Applications",
    ui.layout_columns(
        ui.card(
            ui.card_header("Add an application"),
            ui.input_select("a_type", "Type", type_choices, selected="staff_copilot"),
            ui.input_text("a_name", "Name", placeholder="e.g. Ministry of Finance copilot"),
            ui.input_numeric("a_volume", ARCH["staff_copilot"]["unit_label"], value=None, min=0),
            ui.panel_conditional(
                "['agriculture_advisory', 'citizen_assistant'].includes(input.a_type)",
                ui.input_radio_buttons("a_basis", "Who is counted in the volume?", {
                    "eligible": "Everyone eligible (all citizens or farmers in the target population, or all beneficiaries "
                                "of a scheme; most will not use the AI service)",
                    "users": "Service users (people registered or onboarded to the service: app users, or farmers "
                             "reached through extension or cooperatives)"},
                    selected="eligible"),
                ui.panel_conditional(
                    "input.a_type == 'agriculture_advisory' && input.a_basis == 'users'",
                    ui.p("Not yet validated and probably high: FarmerChat's open data gives far fewer questions per "
                         "farmer reached. Treat the result as an upper bound (see the methodology).", class_="hint")),
            ),
            ui.panel_conditional(
                "input.a_type == 'speech_to_text'",
                ui.input_radio_buttons("a_proc", "How is the audio processed?", {
                    "batch": ARCH["speech_to_text"]["processing"]["batch"]["label"],
                    "realtime": ARCH["speech_to_text"]["processing"]["realtime"]["label"]},
                    selected=ARCH["speech_to_text"]["processing"]["default"]),
            ),
            ui.layout_columns(
                ui.input_select("a_start", "Start year", {str(y): f"Year {y}" for y in range(1, 11)}, selected="1"),
                ui.input_numeric("a_growth", "Growth per year (%)", value=0, min=-50, max=200, step=5),
                col_widths=[6, 6]),
            ui.accordion(ui.accordion_panel(
                "Advanced",
                ui.input_numeric("a_rate", "Requests per person per day (leave empty for type default)", value=None, min=0),
                ui.input_select("a_model", "Model size", {"": "Type default", "S": "Small (~8B)",
                                                           "M": "Medium (~70B)", "L": "Large reasoning (~600B MoE)"}),
            ), open=False),
            ui.output_ui("a_type_hint"),
            ui.input_action_button("add", "Add application", class_="btn-primary w-100"),
            ui.accordion(ui.accordion_panel(
                "Custom application types (upload)",
                ui.p("For an application that no type fits: fill one row per type in the CSV template, then upload it. "
                     "Custom types appear in the Type list under \"Custom (uploaded)\" and are saved with the scenario.",
                     class_="hint"),
                ui.download_button("dl_template", "Download template (CSV)", class_="btn-sm"),
                ui.input_file("ul_custom", None, accept=[".csv"], button_label="Upload custom types",
                              placeholder="custom_application_types.csv"),
                ui.output_ui("custom_status"),
            ), open=False, style="margin-top:12px"),
        ),
        ui.card(
            ui.card_header(ui.div(ui.span("Application portfolio"),
                                  ui.span(ui.input_action_link("example", "Load example"), ui.span(" · "),
                                          ui.input_action_link("clear", "Clear all"), style="font-weight:400"),
                                  style="display:flex;justify-content:space-between;align-items:center")),
            ui.output_ui("example_note"),
            ui.output_ui("app_list"),
        ),
        col_widths=[4, 8],
    ),
)

results_panel = ui.nav_panel(
    "3 · Results",
    ui.output_ui("warnings"),
    ui.output_ui("answer"),
    ui.h4("1 · 10-year cost of the portfolio, four ways", class_="sec"),
    ui.layout_columns(
        ui.card(ui.card_header("10-year cost by option (present value)"),
                ui.output_plot("chart_opts", height="300px")),
        ui.card(ui.card_header("The same numbers"), ui.output_ui("opt_table"),
                ui.p("All applications together, with their start years and growth. Capacity is sized each year on the "
                     "combined load, so spare capacity of one application serves the others. Base prices; figures in US "
                     "dollars, present value, rounded to the dollar.",
                     class_="hint")),
        col_widths=[7, 5]),
    ui.h4("2 · Cost per application", class_="sec"),
    ui.card(ui.card_header("10-year cost of each application if bought on its own, by option (present value)"),
            ui.output_ui("app_opts"),
            ui.p("Each row prices the application alone, so owned options carry their own servers, staff and facility. "
                 "The last two rows show the portfolio bought together and the sum of the rows: the gap is what sharing saves. "
                 "† Not available as a cloud API (e.g. national biometric deduplication): the API column prices it as rented GPUs. "
                 "Other non-language-model work uses per-unit cloud API prices (per audio hour, page, verification or chunk). "
                 "‡ Too small to need a GPU of its own (below 0.25 GPU): bought alone, the API is the only option with a price. "
                 "If the government owns or rents GPUs for other applications, this work runs on their spare capacity at no "
                 "extra cost.",
                 class_="hint")),
    ui.h4("3 · What owning means", class_="sec"),
    ui.layout_columns(
        ui.card(ui.card_header("Servers installed by year (owned options, shared by all applications)"),
                ui.output_plot("chart_fleet", height="280px"), ui.output_ui("fleet_note")),
        ui.card(ui.card_header("Where the money goes when owning (10-year present value)"), ui.output_ui("owned_parts")),
        col_widths=[6, 6]),
    ui.output_ui("footnote"),
    ui.accordion(
        ui.accordion_panel("For specialists: tokens and sizing factors behind the figures", ui.output_ui("tokens_panel")),
        ui.accordion_panel("Details: assumptions used", ui.output_table("assumptions")),
        ui.accordion_panel("Details: year by year (portfolio, not discounted)", ui.output_table("yearly")),
        open=False),
    ui.card(
        ui.card_header("Download"),
        ui.layout_columns(
            ui.div(ui.download_button("dl_results", "Summary (CSV)", class_="w-100"),
                   ui.p("The 10-year cost of each application and of the portfolio under the four options.", class_="hint")),
            ui.div(ui.download_button("dl_detail", "Full calculation (ZIP)", class_="w-100"),
                   ui.p("Every step: inputs, requests and tokens by year, GPUs, servers, kW and energy by year, "
                        "yearly costs by item, and every assumption used, with a README.", class_="hint")),
            ui.div(ui.download_button("dl_scenario", "Save scenario (JSON)", class_="w-100"),
                   ui.input_file("ul_scenario", None, accept=[".json"], button_label="Load scenario",
                                 placeholder="scenario.json")),
            col_widths=[4, 4, 4])),
)

evidence_panel = ui.nav_panel(
    "Evidence",
    ui.card(ui.card_header("Application types: default values and their sources"), ui.output_ui("evidence")),
    ui.card(ui.card_header("Country inputs"), ui.output_table("country_tbl")),
    ui.card(ui.card_header("Global defaults"), ui.output_table("defaults_tbl")),
    ui.card(ui.card_header("Sources"), ui.output_ui("sources")),
)

saved_panel = ui.nav_panel(
    "Saved work",
    ui.card(
        ui.card_header("Save and resume"),
        ui.p("Each save creates a new link with a timestamp, so you can keep several versions. The link contains the "
             "whole scenario (setup, applications, custom types, quotes); nothing is stored on a server. Saved links are "
             "listed below in this browser only: keep the link (bookmark, email) to open it elsewhere. "
             "Anyone with a link can see that scenario.", class_="hint"),
        ui.layout_columns(ui.input_text("save_name", None, placeholder="Version name (optional), e.g. Ghana, cautious"),
                          ui.input_action_button("save_link", "Save and get link", class_="btn-primary"),
                          col_widths=[8, 4]),
        ui.output_ui("share_out"),
    ),
    ui.card(ui.card_header("Saved versions (this browser)"), ui.output_ui("saved_list_ui")),
)

app_ui = ui.page_navbar(
    setup_panel, apps_panel, results_panel, evidence_panel, saved_panel,
    title="Sovereign AI Compute Planner",
    header=ui.TagList(ui.tags.style(CSS), ui.tags.script(SAVE_JS)),
    footer=ui.div("v0.9.11 draft · planning-grade estimates · every default is sourced in the Evidence tab",
                  class_="hint", style="text-align:center;padding:16px"),
    fillable=False,
)


# ------------------------------------------------------------------ server
def server(input, output, session):
    custom = reactive.value({})

    def A():
        return {**ARCH, **custom.get()}

    apps = reactive.value([])

    # ---- add / remove

    @render.download(filename="custom_application_types.csv")
    def dl_template():
        yield CUSTOM_TEMPLATE.read_text()

    custom_msg = reactive.value(None)

    @reactive.effect
    @reactive.event(input.ul_custom)
    def _custom_upload():
        f = input.ul_custom()
        if not f:
            return
        types, errs = parse_custom_types(open(f[0]["datapath"], encoding="utf-8-sig").read(), ARCH)
        custom.set({**custom.get(), **types})
        custom_msg.set((types, errs))

    @reactive.effect
    def _refresh_types():
        arch = A()
        with reactive.isolate():
            cur = input.a_type()
        ui.update_select("a_type", choices=type_choices_for(arch), selected=cur if cur in arch else "staff_copilot")

    @render.ui
    def custom_status():
        m = custom_msg.get()
        items = [ui.tags.li(t["label"]) for t in custom.get().values()]
        out = []
        if items:
            out.append(ui.p(f"{len(items)} custom type{'s' if len(items) != 1 else ''} loaded:", class_="hint", style="margin:6px 0 0"))
            out.append(ui.tags.ul(*items, class_="hint"))
        if m and m[1]:
            out.append(ui.div(ui.tags.b("Rows skipped:"), ui.tags.ul(*[ui.tags.li(e) for e in m[1]]),
                              style="color:#92400e;font-size:.82rem"))
        return ui.div(*out) if out else None

    @render.ui
    def a_type_hint():
        t = A()[input.a_type()]
        ev = t["evidence"].get("rate") or t["evidence"].get("gpu", "")
        ref = reference_sizes(country()[0])
        bits = []
        if input.a_type() == "agriculture_advisory":
            bits.append(f'~{sig2(ref["agri_workers"]):,.0f} agricultural workers (ILO modeled estimate, {ref["agri_year"]})'
                        if ref["agri_workers"] else "agricultural workers unknown (no recent data): volume not checked")
        if ref["population"]:
            bits.append(f'population {ref["population"]:,.0f}')
        if ref["civil_servants"]:
            bits.append(f'civil servants {ref["civil_servants"]:,.0f}' + (" (rough estimate)" if ref["civil_servants_estimated"] else ""))
        return ui.div(ui.p(ev, class_="hint", style="margin-top:8px"),
                      ui.p("Country reference: " + " · ".join(bits), class_="hint") if bits else None)

    @reactive.effect
    @reactive.event(input.a_type)
    def _default_class():
        t = A()[input.a_type()]
        ui.update_numeric("a_volume", label=t["unit_label"])
        if is_llm(t) and t["unit"] == "users":
            ui.update_numeric("a_rate", label=f'Requests per person per day (default {t["rate"]["base"]:g} in Base)')
        else:
            ui.update_numeric("a_rate", label="Requests per person per day (not used for this type)", value=None)

    @reactive.effect
    @reactive.event(input.add)
    def _add():
        t = A()[input.a_type()]
        vol = num(input.a_volume())
        if not vol:
            ui.notification_show(f'Enter {t["unit_label"].lower()} first.', type="warning")
            return
        rate = num(input.a_rate()) if is_llm(t) and t["unit"] == "users" else None
        new = dict(uid=uuid.uuid4().hex[:8], name=input.a_name().strip() or t["label"], type=t["id"], volume=vol,
                   data_class=int(t.get("data_class", 1)), rate_override=rate, model_class=input.a_model() or None,
                   start_year=int(input.a_start()), growth=(num(input.a_growth()) or 0) / 100,
                   population_basis=input.a_basis() if t.get("rate_by_basis") else "eligible",
                   processing=input.a_proc() if t.get("processing") else None)
        w = volume_warning(new, country()[0], A(), D["agri_volume_tolerance"]["value"])
        if w:
            ui.notification_show(w, type="warning", duration=10)
        apps.set(apps.get() + [new])
        ui.update_text("a_name", value="")
        ui.update_numeric("a_volume", value=None)

    @reactive.effect
    @reactive.event(input.remove_app)
    def _remove():
        apps.set([a for a in apps.get() if a["uid"] != input.remove_app()])

    @reactive.effect
    @reactive.event(input.example)
    def _example():
        c, _ = country()
        lst, notes = example_portfolio(c)
        apps.set([dict(a, uid=uuid.uuid4().hex[:8]) for a in lst])
        example_notes.set((c.get("name", input.iso()), notes))

    example_notes = reactive.value(None)

    @reactive.effect
    @reactive.event(input.clear)
    def _clear():
        apps.set([])
        example_notes.set(None)

    @render.ui
    def example_note():
        n = example_notes.get()
        if not n or not apps.get():
            return None
        name, notes = n
        return ui.accordion(ui.accordion_panel(
            f"How the example was sized for {name} (rough rules, edit any figure)",
            ui.tags.ul(*[ui.tags.li(x, class_="hint") for x in notes]),
            ui.p("Shares and ratios are planning assumptions (Low confidence), applied to the country's synced data. "
                 "Change the country in Setup and load the example again to resize it.", class_="hint")),
            open=False, style="margin-bottom:10px")

    @render.ui
    def app_list():
        lst = apps.get()
        if not lst:
            return ui.div("No applications yet. Add one on the left, or load the example portfolio.", class_="empty")
        res = {x["id"]: x for x in result()["demand"]} if lst else {}
        ntr = {x["id"]: x for x in result()["nontoken"]}
        rows = []
        for a in lst:
            t = A()[a["type"]]
            if a["uid"] in res:
                d = res[a["uid"]]
                load = f'{fmt(d["sessions"])} requests/day'
            elif a["uid"] in ntr:
                load = f'{fmt(ntr[a["uid"]]["gpu_hours_day"], 1)} GPU-h/day'
            else:
                load = "-"
            rows.append(ui.tags.tr(
                ui.tags.td(ui.tags.b(a["name"]), ui.br(), ui.span(t["label"], class_="hint"),
                           *([ui.br(), ui.span("⚠ " + w, style="color:#92400e;font-size:.82rem")]
                             if (w := volume_warning(a, country()[0], A(), D["agri_volume_tolerance"]["value"])) else []),
                           *([ui.br(), ui.span("ⓘ " + n, style="color:#1e40af;font-size:.82rem")]
                             if (n := low_usage_note(a, A(), input.ambition())) else [])),
                ui.tags.td(f'{fmt(a["volume"])}', ui.br(), ui.span(t["unit_label"], class_="hint"),
                           *([ui.br(), ui.span(f"({b})", class_="hint")] if (b := basis_label(a, A())) else [])),
                ui.tags.td(f'Year {a.get("start_year", 1)}', ui.br(),
                           ui.span(f'{a.get("growth", 0) * 100:+.0f}% per year', class_="hint")),
                ui.tags.td(load),
                ui.tags.td(ui.span("●", class_=f'conf-{t["confidence"]["volume"]}', title=f'Usage rate evidence: {t["confidence"]["volume"]}'),
                           ui.span("●", class_=f'conf-{t["confidence"]["tokens"]}', title=f'Size evidence: {t["confidence"]["tokens"]}'),
                           style="white-space:nowrap;font-size:1.1rem"),
                ui.tags.td(ui.tags.button("✕", class_="btn-x", title="Remove",
                                          onclick=f"Shiny.setInputValue('remove_app','{a['uid']}',{{priority:'event'}})")),
            ))
        return ui.tags.table(
            ui.tags.thead(ui.tags.tr(*[ui.tags.th(h) for h in ("Application", "Volume", "Start · growth",
                                                                "Load at start", "Evidence", "")])),
            ui.tags.tbody(*rows), class_="applist")

    # ---- country and profile
    @reactive.calc
    def country():
        c = dict(COUNTRIES[input.iso()])
        c["iso3"] = input.iso()
        if num(input.pue()):
            c["pue_override"] = num(input.pue())
        notes = []
        g = input.grid()
        if g == "reliable":
            c["outages_per_month"] = 0
        elif g == "weak":
            c["outages_per_month"] = 10
        else:
            def year_of(field):
                yr = re.findall(r"(19|20)(\d\d)", c.get("_sources", {}).get(field, ""))
                return int("".join(yr[-1])) if yr else None
            for field in ("outages_per_month", "firms_with_outages_share"):
                y = year_of(field)
                if c.get(field) is not None and y and y < 2020:
                    c[field] = None
                    notes.append(f"Outage data ({field.replace('_', ' ')}) is from {y}: not used. Set grid reliability in Setup.")
            if c.get("outages_per_month") is None and c.get("firms_with_outages_share") is None:
                notes.append("No outage data for this country: grid shown as unknown and air-cooled hardware assumed. Set it in Setup.")
            elif c.get("outages_per_month") is None:
                notes.append(f'Outages per month not available: grid judged from the share of firms with outages '
                             f'({c["firms_with_outages_share"]:.0%}). Set grid reliability in Setup if you know better.')
        k = num(input.kwh())
        if k:
            c["electricity_usd_kwh"] = k
        return c, notes

    @render.ui
    def country_facts():
        c, _ = country()
        bits = []
        if c.get("population"):
            bits.append(f'Population {c["population"] / 1e6:,.1f}M')
        if c.get("internet_share"):
            bits.append(f'internet use {c["internet_share"]:.0%}')
        if c.get("electricity_usd_kwh"):
            bits.append(f'tariff ${c["electricity_usd_kwh"]:.2f}/kWh')
        cs = c.get("civil_servants")
        if cs:
            yr = c.get("_sources", {}).get("public_employment_share", "")[-4:]
            bits.append(f"civil servants ~{sig2(cs):,.0f} (all public sector employees, {c.get('public_employment_share', 0):.0%} of jobs, {yr})" if c.get('public_employment_share') else f"civil servants ~{sig2(cs):,.0f}")
        ref = reference_sizes(c)
        if ref["agri_workers"]:
            bits.append(f'~{sig2(ref["agri_workers"]):,.0f} agricultural workers (ILO modeled estimate, {ref["agri_year"]})')
        cc = COUNTRIES[input.iso()]
        o, s = cc.get("outages_per_month"), cc.get("firms_with_outages_share")
        if o is not None:
            yr = cc.get("_sources", {}).get("outages_per_month", "")[-4:]
            bits.append(f"outages {o:.1f} per month" + (f" ({yr})" if yr.isdigit() else ""))
        if s is not None:
            bits.append(f"{s:.0%} of firms had outages ({cc['_sources'].get('firms_with_outages_share', '')[-4:]})")
        if o is None and s is None:
            bits.append("outages: no data")
        return ui.p(" · ".join(bits), class_="hint")

    def quotes():
        q = {}
        for key, inp in [("gpu_hour_usd", "q_gpu_hour"), ("gpu_capex_usd", "q_gpu_capex"),
                         ("facility_capex_usd_per_mw_it", "q_fac"), ("colo_usd_per_kw_month", "q_colo")]:
            v = num(input[inp]())
            if v:
                q[key] = v
        return q

    def _run(ambition, app_list=None, tiers=None):
        c, _ = country()
        p = build_profile(c, ambition, apps.get() if app_list is None else app_list, A(),
                          dict(D["class_to_tier"]), quotes(), input.hw())
        p.speed = input.speed()
        p.gov_dc = "ready" if input.own_dc_existing() else "fitout"
        pct = lambda v: (num(v) or 0) / 100
        p.finance = {"discount_rate": pct(input.disc()), "demand_growth": 0.0, "price_decline": 0.0,
                     "api_price_decline": pct(input.decline()), "hw_price_decline": pct(input.decline_hw()),
                     "compute_gain_per_year": pct(input.gain()),
                     "api_reference": input.api_ref(), "api_commit_discount": pct(input.api_disc()),
                     "gpu_rental_reference": input.rent_ref(), "gpu_rental_mode": input.rent_mode(),
                     "software_stack": input.sw(), "server_life_years": int(num(input.life()) or 5),
                     "idle_sharing_share": pct(input.night_share()) if input.night() else 0.0}
        p.redundancy = bool(input.redundancy())
        return p

    @reactive.calc
    def opt():
        """The four options, per application and for the portfolio."""
        p = with_no_placement(_run(input.ambition()))
        meta = {a["uid"]: {"start_year": a.get("start_year", 1), "growth": a.get("growth", 0.0)} for a in apps.get()}
        return compare(p, CAT, D, API_PRICES, meta)

    @reactive.calc
    def result():
        return run(_run(input.ambition()), CAT, D, API_PRICES)




    # ---- results
    @render.ui
    def warnings():
        _, notes = country()
        msgs = list(notes)
        if not apps.get():
            msgs.append("Add applications in step 2 to see results.")
        if input.iso() == "XEX":
            msgs.append("Example country (fictional) selected in Setup.")
        if "fallback" in API_PROV:
            msgs.append(f"API prices: {API_PROV}.")
        lows = sorted({A()[a["type"]]["label"] for a in apps.get() if A()[a["type"]]["confidence"]["volume"] == "Low"
                       and not a.get("rate_override") and A()[a["type"]]["unit"] == "users"})
        if lows:
            msgs.append("Usage rate is a weak assumption for: " + "; ".join(lows) +
                        ". Set requests per person per day under Advanced if the client knows it.")
        if quotes():
            msgs.append("Client quotes in use: " + ", ".join(quotes()))
        info = [n for a in apps.get() if (n := low_usage_note(a, A(), input.ambition()))]
        out = []
        if msgs:
            out.append(ui.div(ui.tags.ul(*[ui.tags.li(m) for m in msgs], style="margin:0"), class_="warn"))
        if info:
            out.append(ui.div(ui.tags.ul(*[ui.tags.li(m) for m in info], style="margin:0"),
                              style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;padding:8px 12px;margin:8px 0;font-size:.9rem"))
        return ui.div(*out) if out else None

    DEST = {"T1": "Public data", "T2": "Internal data", "T3": "Confidential data", "T4": "Restricted data"}
    SCEN_LABEL = {"Low": "Cautious", "Base": "Expected", "High": "Aggressive"}

    # ---- results (v0.9: four options per application and for the portfolio)
    OPT_SHORT = {"API": "API", "GPU-as-a-service": "GPU rental", "Owned + colocation": "Own + colocation",
                 "Owned + own data centre": "Own + own data centre"}

    def _names():
        return {a["uid"]: a for a in apps.get()}

    @render.ui
    def colo_facts():
        c, _ = country()
        cp = colo_price(dict(c, _quotes=quotes()), D, "base", 0)
        small = D["colocation"]["small_deployment_factor"]["value"]
        return ui.p(f'Colocation price used: ${cp["wholesale"]:,.0f} per kW of IT per month wholesale '
                    f'({cp["src"]}), x{small:g} for deployments under '
                    f'{D["colocation"]["small_deployment_kw"]["value"]:,.0f} kW. Energy is paid on top.', class_="hint")

    @render.ui
    def answer():
        if not apps.get():
            return None
        r = opt()["total"]
        pv, rg = r["base"]["pv"], r["range"]
        best = r["cheapest"]
        order = sorted(OPTIONS, key=pv.get)
        others = " · ".join(f"{OPT_SHORT[o]} {usd(pv[o])}" for o in order[1:])
        fl = r["base"]["fleet"]
        peak = max(fl.values(), key=lambda f: f["servers"])
        yr = next(y for y, f in fl.items() if f["servers"] == peak["servers"])
        own = (f'Owning needs up to {peak["servers"]} server{"s" if peak["servers"] != 1 else ""} '
               f'({peak["gpus"]} GPUs, {r["base"]["peak_it_kw"]:,.0f} kW of IT load) by year {yr}.'
               if peak["servers"] else "")
        return ui.div(
            ui.div(f"Cheapest over 10 years: {OPT_SHORT[best]}, {usd(pv[best])}", class_="big"),
            ui.div(f'10-year present value at {num(input.disc()) or 0:g}% · '
                   f'{len(apps.get())} application{"s" if len(apps.get()) != 1 else ""}, {SCEN[input.ambition()].lower()} adoption',
                   class_="line"),
            ui.div("Other options: " + others + ". " + own, class_="line"),
            class_="answer")

    @render.plot(alt="10-year cost by option")
    def chart_opts():
        import matplotlib.pyplot as plt
        if not apps.get():
            return None
        r = opt()["total"]
        pv, best = r["base"]["pv"], r["cheapest"]
        fig, ax = plt.subplots(figsize=(7, 3))
        xs = list(range(len(OPTIONS)))
        vals = [pv[o] / 1e6 for o in OPTIONS]
        ax.bar(xs, vals, width=0.55, color=["#1f5fa8" if o == best else "#9db8d9" for o in OPTIONS])
        for x, o in zip(xs, OPTIONS):
            ax.text(x, pv[o] / 1e6 * 1.02, usd(pv[o]), ha="center", va="bottom", fontsize=8,
                    fontweight="bold" if o == best else "normal")
        ax.set_xticks(xs, ["API", "GPU rental", "Own, colo", "Own, own DC"], fontsize=8)
        ax.tick_params(axis="y", labelsize=8)
        ax.yaxis.set_major_formatter(lambda v, _: f"${v:g}M")
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", color="#e5e7eb", lw=0.6)
        ax.set_axisbelow(True)
        ax.set_ylim(0, max(pv.values()) / 1e6 * 1.15)
        fig.subplots_adjust(left=0.1, right=0.98, top=0.95, bottom=0.12)
        return fig

    @render.ui
    def opt_table():
        if not apps.get():
            return None
        r = opt()["total"]
        b = r["base"]
        rows = []
        for o in OPTIONS:
            parts = b["pv_parts"].get(o, {})
            up = (parts.get("facility_build", 0) + b["fleet"][b["first_year"]]["buy"] * b["capex_gpu"]
                  * D_GPS.get(b["hardware"], 8)) if o.startswith("Owned") and b["first_year"] else 0
            rows.append(ui.tags.tr(
                ui.tags.td(ui.tags.b(OPT_SHORT[o]) if o == r["cheapest"] else OPT_SHORT[o]),
                ui.tags.td(usd(b["pv"][o]), style="font-weight:600" if o == r["cheapest"] else ""),
                ui.tags.td(usd(up) if up else "-")))
        return ui.tags.table(ui.tags.thead(ui.tags.tr(*[ui.tags.th(h) for h in ("Option", "10-year cost",
                                                                                  "Upfront, first year of use")])),
                             ui.tags.tbody(*rows), class_="table table-sm")

    @render.ui
    def app_opts():
        if not apps.get():
            return None
        o_ = opt()
        nm = _names()
        head = ui.tags.tr(ui.tags.th("Application"), ui.tags.th("Start · growth"),
                          *[ui.tags.th(OPT_SHORT[o]) for o in OPTIONS], ui.tags.th("Cheapest"))

        def row(label, sub, pv, best, style="", no_api=False):
            # Work below the GPU threshold costs nothing extra on GPUs: say so instead of showing $0 as a price.
            spare = pv["API"] > 0 and not any(pv[o] for o in OPTIONS if o != "API")
            cell = lambda o: ("spare capacity" if spare and o != "API" else usd(pv[o])) + (" †" if no_api and o == "API" else "")
            best_txt = OPT_SHORT[best] + (" ‡" if spare else "")
            return ui.tags.tr(ui.tags.td(label), ui.tags.td(sub, class_="hint"),
                              *[ui.tags.td(cell(o), style=("font-weight:700" if o == best else "")
                                           + (";color:#64748b" if spare and o != "API" else "")) for o in OPTIONS],
                              ui.tags.td(best_txt), style=style)
        rows = []
        for uid, res in o_["apps"].items():
            a = nm.get(uid)
            if not a:
                continue
            label = a["name"] + (f" ({b})" if (b := basis_label(a, A())) else "")
            sub = f'year {a.get("start_year", 1)}, {a.get("growth", 0) * 100:+.0f}%/yr'
            if not any(res["base"]["pv"].values()):
                rows.append(ui.tags.tr(ui.tags.td(label), ui.tags.td(sub, class_="hint"),
                                       ui.tags.td(f"Below {D['gpu_threshold']['value']:g} GPU on its own: runs on existing "
                                                  "servers (CPU or a shared GPU). In the portfolio it uses spare GPU time.",
                                                  colspan=len(OPTIONS) + 1, class_="hint")))
                continue
            ap = processing_for(a, A()[a["type"]])[1] or {}
            rows.append(row(label, sub, res["base"]["pv"], res["cheapest"], no_api=ap.get("available") is False))
        t = o_["total"]
        rows.append(row(ui.tags.b("All together (shared capacity)"), "", t["base"]["pv"], t["cheapest"],
                        "border-top:2px solid #94a3b8"))
        ss = o_["sum_standalone"]
        rows.append(row(ui.tags.i("Sum if each is bought alone"), "", ss, min(ss, key=ss.get), "color:#64748b"))
        return ui.tags.table(ui.tags.thead(head), ui.tags.tbody(*rows), class_="table table-sm")

    @render.plot(alt="Servers installed by year")
    def chart_fleet():
        import matplotlib.pyplot as plt
        if not apps.get():
            return None
        b = opt()["total"]["base"]
        yrs = list(b["fleet"])
        sv = [b["fleet"][y]["servers"] for y in yrs]
        kk = D_GPS.get(b["hardware"], 8)
        need = [b["sizing"][y]["gpu_need"] / kk for y in yrs]
        capy = [b["fleet"][y]["capacity"] / kk for y in yrs]
        fig, ax = plt.subplots(figsize=(7, 3))
        ax.bar(yrs, sv, width=0.6, color="#9db8d9", label="installed")
        ax.plot(yrs, need, color="#1f5fa8", lw=2, marker="o", ms=4, label="needed at the busiest hour")
        if b["compute_gain"]:
            ax.step(yrs, capy, where="mid", color="#64748b", lw=1.2, ls="--", label="capacity (in year-1 servers)")
        sv = [max(a, c) for a, c in zip(sv, capy)]
        for y in yrs:
            if b["fleet"][y]["buy"]:
                ax.text(y, b["fleet"][y]["servers"] + 0.03, f'+{b["fleet"][y]["buy"]}', ha="center", va="bottom", fontsize=7)
        ax.set_xticks(yrs, [f"Y{y}" for y in yrs], fontsize=7)
        ax.tick_params(axis="y", labelsize=7)
        ax.yaxis.get_major_locator().set_params(integer=True)

        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", color="#e5e7eb", lw=0.6)
        ax.set_axisbelow(True)
        ax.legend(fontsize=7, frameon=False, loc="upper left", ncol=1)
        ax.set_ylim(0, max(sv + [1]) * 1.6)
        fig.subplots_adjust(left=0.07, right=0.98, top=0.95, bottom=0.12)
        return fig

    @render.ui
    def fleet_note():
        if not apps.get():
            return None
        b = opt()["total"]["base"]
        hw = {h["id"]: h["name"] for h in CAT["hardware"]}[b["hardware"]]
        return ui.p(f"Hardware: {hw}. Servers are bought when the combined need exceeds what is installed (+N), "
                    f"replaced after {D['gpu_refresh_years']['value']} years, and never sold. Servers bought in later years do "
                    f"{b['compute_gain']:.0%} more work per GPU for each year of purchase, so fewer are needed. Peak IT load "
                    f"{b['peak_it_kw']:,.0f} kW ({b['peak_facility_kw']:,.0f} kW with cooling, PUE {b['pue']:.2f}). "
                    f"An own data centre is built for {b['design_it_kw']:,.0f} kW of IT: the peak plus "
                    f"{D['facility_buffer']['value']:.0%} spare capacity.",
                    class_="hint")

    @render.ui
    def owned_parts():
        if not apps.get():
            return None
        b = opt()["total"]["base"]
        pc, po = b["pv_parts"]["Owned + colocation"], b["pv_parts"]["Owned + own data centre"]
        items = [("GPU servers (purchases and refresh)", "gpu_servers"),
                 ("Network, storage and security equipment", "network_storage_security"), ("GPU software and support", "software"),
                 ("GPU maintenance", "maintenance_gpu"), ("Staff", "staff"), ("Energy", "energy"),
                 ("Colocation fee", "colocation"), ("Facility build (peak IT load + buffer)", "facility_build"),
                 ("Facility maintenance", "maintenance_facility"),
                 ("Idle hours shared with universities (value)", "shared_capacity_value")]
        rows = [ui.tags.tr(ui.tags.td(lbl), ui.tags.td(usd(pc[k]) if pc.get(k) else "-"),
                           ui.tags.td(usd(po[k]) if po.get(k) else "-")) for lbl, k in items]
        rows.append(ui.tags.tr(ui.tags.td(ui.tags.b("Total")), ui.tags.td(ui.tags.b(usd(sum(pc.values())))),
                               ui.tags.td(ui.tags.b(usd(sum(po.values()))))))
        gpu = sum(pc.get(k, 0) for k in ("gpu_servers", "network_storage_security", "software", "maintenance_gpu"))
        return ui.div(ui.tags.table(ui.tags.thead(ui.tags.tr(ui.tags.th(""), ui.tags.th("Own + colocation"),
                                                             ui.tags.th("Own + own data centre"))),
                                    ui.tags.tbody(*rows), class_="table table-sm"),
                      ui.p(f"The IT part alone (servers, network and security equipment, software, maintenance) is {usd(gpu)} in both. The difference "
                           "between the two is the colocation fee against building and maintaining a facility. "
                           + ("An existing facility is assumed: no build cost." if input.own_dc_existing() else ""),
                           class_="hint"))

    @render.ui
    def footnote():
        if not apps.get():
            return None
        return ui.div(
            ui.tags.b("Hosting and data regulation are not assessed here. "),
            "The cheapest option may not be allowed. Before choosing, the client needs to check its data protection and "
            "sector rules for each application: whether the data may be processed by an API provider or a cloud outside "
            "the country, hosted by a private operator in-country (colocation or GPU rental), or must stay in a "
            "government data centre.",
            ui.br(), ui.br(),
            ui.tags.b("API prices do not fix where the data is processed. "),
            "Every API price in this tool (language models, transcription, OCR and the others) is a public list price "
            "from providers that mostly process data outside the country, often in the United States, and may move it "
            "between regions. In-region or in-country processing, where a provider offers it, can cost more and must be "
            "agreed in the contract.",
            ui.br(), ui.br(),
            ui.tags.b("Some options may not be available. "),
            "Export controls, sanctions and GPU supply limits can rule out an option or delay it, whatever its cost. "
            "Buying GPUs needs an export licence for some countries and is closed to others; renting GPUs abroad and "
            "using APIs from some providers are restricted for the same countries; and new GPUs often have long "
            "delivery times. The rules change several times a year: check the current situation for the country "
            "before choosing.",
            class_="warn", style="margin-top:14px")

    @render.ui
    def tokens_panel():
        if not apps.get():
            return None
        r = result()
        H = int(D["horizon_years"]["value"])
        nm = _names()
        b = opt()["total"]["base"]
        big = lambda v: (f"{v / 1e9:,.1f}B" if v >= 1e9 else f"{v / 1e6:,.1f}M" if v >= 1e6
                         else f"{v / 1e3:,.0f}k" if v >= 1e3 else f"{v:,.0f}")
        size = {"S": "Small (~8B)", "M": "Medium (~70B)", "L": "Large reasoning (~600B MoE)"}
        rows = []
        for x in r["demand"]:
            a = nm.get(x["id"])
            if not a or not x["sessions"]:
                continue
            g10 = (1 + a.get("growth", 0)) ** max(0, H - a.get("start_year", 1))
            n = x["sessions"]
            rows.append(ui.tags.tr(
                ui.tags.td(a["name"]), ui.tags.td(size.get(x["model_class"], x["model_class"])),
                ui.tags.td(f'{n:,.0f}'),
                ui.tags.td(f'{x["daily_input"] / n:,.0f} · {x["daily_output"] / n:,.0f}'
                           + (f' ({x["daily_cached"] / x["daily_input"]:.0%} cached)' if x["daily_input"] else "")),
                ui.tags.td(big(x["daily_input"] + x["daily_output"])),
                ui.tags.td(big((x["daily_input"] + x["daily_output"]) * x["active_days"] * g10)),
                ui.tags.td(f'{x["peak_eq_tps"] * g10:,.0f}'),
                ui.tags.td(f'{x["active_days"]:.0f}')))
        llm = ui.tags.table(ui.tags.thead(ui.tags.tr(*[ui.tags.th(h) for h in (
            "Application", "Model size", "Requests/day at start", "Tokens per request (input · output)",
            "Tokens/day at start", f"Tokens/year in year {H}", f"Peak equivalent tokens/s, year {H}", "Active days/year")])),
            ui.tags.tbody(*rows), class_="table table-sm") if rows else ui.p("No language-model application.", class_="hint")
        nrows = [ui.tags.tr(ui.tags.td(nm[w["id"]]["name"]), ui.tags.td(f'{A()[nm[w["id"]]["type"]]["gpu_seconds_per_unit"]:g}'),
                            ui.tags.td(w["mode"]), ui.tags.td(f'{w["gpu_hours_day"]:,.1f}'))
                 for w in r["nontoken"] if w["id"] in nm and w["gpu_hours_day"]]
        nt = ui.tags.table(ui.tags.thead(ui.tags.tr(*[ui.tags.th(h) for h in (
            "Other AI application", "GPU-seconds per unit", "Mode", "GPU-hours/day at start (after derating)")])),
            ui.tags.tbody(*nrows), class_="table table-sm") if nrows else None
        sz = b["sizing"][H]
        eff = ", ".join(f'{size[c].split(" ")[0]} {sz["eff_tps"][c]:,.0f}' for c in ("S", "M", "L"))
        pr = ", ".join(f'{size[c].split(" ")[0]} ${API_PRICES[c]["input"]:g} in / ${API_PRICES[c]["output"]:g} out'
                       for c in ("S", "M", "L"))
        hw = {h["id"]: h["name"] for h in CAT["hardware"]}[b["hardware"]]
        fac = [
            f"Tokens per request include the system prompt, agent steps (calls per task) and a retry allowance (x{ARCH['staff_copilot']['retry']:g} for most types). "
            "Part of the system prompt is served from cache and priced at a discount.",
            f"GPU sizing uses equivalent tokens: output + uncached input x {D['prefill_weight']['value']:g} (reading input "
            "is cheaper than writing output).",
            "Peak load: share of daily traffic in the busy hours, x burst, x service headroom, x seasonal factor, set per type "
            "(Evidence tab).",
            f"Pooling: applications rarely peak together. In year {H} the {sz['n_apps']} active applications share the "
            f"capacity with a factor of {sz['diversity']:.2f} on their summed peaks.",
            f"Throughput per GPU on {hw} at the chosen response speed, tokens/s: {eff} (InferenceX measurements; "
            "derived figures derated).",
            f"API prices per million tokens: {pr} ({API_PROV}).",
            f"Portfolio in year {H}: {big(sz['annual_eq_m'] * 1e6)} equivalent tokens per year, {sz['gpus']} GPUs at the busiest hour.",
        ]
        return ui.div(
            ui.p("For readers who want to check the order of magnitude. Volumes are converted to requests, requests to "
                 "tokens, and tokens to GPUs or API spend. Year figures include each application's growth.", class_="hint"),
            llm, nt, ui.tags.ul(*[ui.tags.li(f, class_="hint") for f in fac]))

    @render.table
    def assumptions():
        if not apps.get():
            return pd.DataFrame()
        b = opt()["total"]["base"]
        c, _ = country()
        hw = next(h for h in CAT["hardware"] if h["id"] == b["hardware"])
        rows = [("Hardware", f'{hw["name"]}, {hw["kw_per_gpu"]:g} kW per GPU'),
                ("GPU server price", f'${b["capex_gpu"]:,.0f} per GPU'),
                ("GPU rental", f'${b["gpu_hour"]:.2f} per GPU-hour'),
                ("Colocation", f'${b["colo"]["value"]:,.0f} per kW of IT per month'
                               + (f' = ${b["colo"]["wholesale"]:,.0f} wholesale x {D["colocation"]["small_deployment_factor"]["value"]:g} '
                                  f'under {D["colocation"]["small_deployment_kw"]["value"]:,.0f} kW' if b["colo"]["small"] else "")
                               + f' ({b["colo"]["src"]})'),
                ("Facility build (own data centre)", "existing facility, not counted" if input.own_dc_existing()
                 else f'{usd(b["facility_capex"])} for {b["design_it_kw"]:,.0f} kW of IT (peak + {D["facility_buffer"]["value"]:.0%}), '
                      f'at ${b["build_per_mw"] / 1e6:,.1f}M per MW (size curve ${b["build_curve"]["curve_musd_per_mw"]:.1f}M x country '
                      f'factor {b["build_curve"]["country_factor"]:.2f}); '
                      f'maintenance {usd(b["facility_maint_year"])} per year ({D["maintenance_share"]["value"]:.0%} of build)'),
                ("PUE", f'{b["pue"]:.2f}'),
                ("Electricity", f'${cost_params(_run(input.ambition()), D, "base")["kwh"]:.3f} per kWh'),
                ("API prices", API_PROV),
                ("Discount rate", f'{num(input.disc()) or 0:g}% · API price decline {num(input.decline()) or 0:g}% per year · '
                                   f'GPU rental and hardware {num(input.decline_hw()) or 0:g}% per year'),
                ("Newer hardware", f'{num(input.gain()) or 0:g}% more work per GPU per year of purchase (Epoch AI)'),
                ("API price reference", {"hyperscaler": "Hyperscaler in region", "open_market": "Open market median",
                                         "frontier": "Proprietary frontier models (+10% regional processing)"}[b["api_reference"]]
                                        + (f' · negotiated discount {num(input.api_disc()):g}%' if num(input.api_disc()) else "")),
                ("GPU rental", f'{"Hyperscaler" if b["rental_reference"] == "hyperscaler" else "Neocloud"}, '
                               + (f'reserved all year at ${b["gpu_hour"]:.2f} per GPU-hour' if b["rental_mode"] == "reserved"
                                  else f'on demand at ${b["gpu_hour_on_demand"]:.2f} per GPU-hour, billed for the hours of work')),
                ("Owned servers", f'kept {b["server_life"]} years · software: '
                                  + ("NVIDIA AI Enterprise" if input.sw() == "nvidia" else "open source, no licence")
                                  + (f' · {b["night_share"]:.0%} of idle hours opened to universities at ${b["night_rate"]:.2f} per GPU-hour'
                                     if b["night_share"] else ""))]
        return pd.DataFrame(rows, columns=["Item", "Value used (Base)"])

    @render.table
    def yearly():
        if not apps.get():
            return pd.DataFrame()
        b = opt()["total"]["base"]
        rows = []
        for y in b["fleet"]:
            rows.append({"Year": y, "GPUs needed (busiest hour, year-1 GPUs)": b["sizing"][y]["gpus"],
                         "GPUs rented (newer GPUs)": b["sizing"][y]["gpus_rented"],
                         "Servers installed": b["fleet"][y]["servers"],
                         **{OPT_SHORT[o]: usd(b["yearly"][o][y]) for o in OPTIONS}})
        return pd.DataFrame(rows)

    def _note(uid, res):
        a = _names().get(uid)
        bits = []
        if not any(res["base"]["pv"].values()):
            bits.append(f"below {D['gpu_threshold']['value']:g} GPU on its own: runs on existing servers, no extra cost")
        if a and (A()[a["type"]].get("api_price") or {}).get("available") is False:
            bits.append("not available as a cloud API: the API column prices it as rented GPUs")
        if a and a["type"] == "biometric_dedup":
            bits.append("compute only; identity-system (ABIS) licence not included")
        return "; ".join(bits)

    @render.download(filename="ai_compute_full_calculation.zip")
    def dl_detail():
        import io
        import zipfile
        o_ = opt()
        nm = _names()
        r = result()
        b = o_["total"]["base"]
        H = int(D["horizon_years"]["value"])
        files = {}
        csv = lambda rows: pd.DataFrame(rows).to_csv(index=False)
        g = lambda a, y: 0.0 if y < a.get("start_year", 1) else (1 + a.get("growth", 0)) ** (y - a.get("start_year", 1))
        # 1. inputs
        rows = []
        for a in apps.get():
            t = A()[a["type"]]
            row_ = {"application": a["name"], "type": t["label"], "volume": a["volume"], "unit": t["unit_label"],
                    "start_year": a.get("start_year", 1), "growth_per_year": a.get("growth", 0),
                    "population_basis": a.get("population_basis", "")}
            if "isl" in t:
                rate = a.get("rate_override") or rate_for(a, t)[{"Low": "low", "Base": "base", "High": "high"}[input.ambition()]]
                row_.update(rate_per_unit_per_active_day=rate, active_days_per_year=t.get("active_days_per_year", 365),
                            model_size=a.get("model_class") or t["model_class"], input_tokens=t["isl"],
                            system_prompt_tokens=t["system_prompt_tokens"], output_tokens=t["osl"],
                            reasoning_tokens=t["reasoning_tokens"], calls_per_task=t["agent_steps"], retry=t["retry"],
                            cache_hit=t["cache_hit"], peak_share=t["peak_share"], peak_window_h=t["peak_window_h"],
                            burst=t["burst"], sla_headroom=t["sla_headroom"], seasonal=t["seasonal"])
            else:
                mode_, ap = processing_for(a, t)
                ap = ap or {}
                row_.update(gpu_seconds_per_unit=t["gpu_seconds_per_unit"], mode=mode_, processing=processing_key(a, t) or "", peak_share=t["peak_share"],
                            peak_window_h=t["peak_window_h"], burst=t["burst"],
                            api_price_base=ap.get("base", "not available"), api_price_unit=ap.get("unit", ""))
            rows.append(row_)
        files["1_inputs_applications.csv"] = csv(rows)
        # 2. tokens per application at start, 3. by year
        rows, yrows = [], []
        for x in r["demand"]:
            a = nm.get(x["id"])
            if not a:
                continue
            n = x["sessions"] or 1
            rows.append({"application": a["name"], "model_size": x["model_class"], "requests_per_day": x["sessions"],
                         "input_tokens_per_request": x["daily_input"] / n, "cached_input_tokens_per_request": x["daily_cached"] / n,
                         "output_tokens_per_request": x["daily_output"] / n, "tokens_per_day": x["daily_input"] + x["daily_output"],
                         "equivalent_tokens_per_day": x["daily_eq"], "peak_equivalent_tokens_per_s": x["peak_eq_tps"],
                         "active_days_per_year": x["active_days"]})
            for y in range(1, H + 1):
                f = g(a, y)
                yrows.append({"application": a["name"], "year": y, "growth_factor": f, "requests_per_day": x["sessions"] * f,
                              "tokens_per_year": (x["daily_input"] + x["daily_output"]) * x["active_days"] * f,
                              "uncached_input_tokens_per_year_m": x["annual_uncached_input_m"] * f,
                              "cached_input_tokens_per_year_m": x["annual_cached_input_m"] * f,
                              "output_tokens_per_year_m": x["annual_output_m"] * f,
                              "equivalent_tokens_per_year_m": x["annual_eq_m"] * f, "peak_equivalent_tokens_per_s": x["peak_eq_tps"] * f})
        for w in r["nontoken"]:
            a = nm.get(w["id"])
            if not a:
                continue
            for y in range(1, H + 1):
                f = g(a, y)
                yrows.append({"application": a["name"], "year": y, "growth_factor": f, "units_per_day": w["units_per_day"] * f,
                              "gpu_hours_per_day": w["gpu_hours_day"] * f, "peak_gpus": w["peak_gpus"] * f})
        files["2_tokens_per_application_at_start.csv"] = csv(rows)
        files["3_demand_by_application_and_year.csv"] = csv(yrows)
        # 4. sizing by year (portfolio)
        hw = next(h for h in CAT["hardware"] if h["id"] == b["hardware"])
        rows = []
        for y in range(1, H + 1):
            s_, f = b["sizing"][y], b["fleet"][y]
            rows.append({"year": y, "applications_pooled": s_["n_apps"], "pooling_factor": s_["diversity"],
                         "gpus_needed_fractional": s_["gpu_need"], "gpus_needed": s_["gpus"],
                         "gpus_for_llm": s_["gpus_llm"], "gpus_for_other_ai": s_["gpus_nontoken"] + s_["gpus_batch_extra"],
                         "servers_installed": f["servers"], "servers_bought": f["buy"], "gpus_installed": f["gpus"],
                         "capacity_installed_year1_gpus": f["capacity"], "work_per_gpu_bought_this_year": b["gain"][y],
                         "gpus_rented_gpu_as_a_service": s_["gpus_rented"],
                         "it_load_kw": f["gpus"] * hw["kw_per_gpu"], "facility_load_kw": f["gpus"] * hw["kw_per_gpu"] * b["pue"],
                         "utilisation_of_gpus_needed": s_["utilisation"],
                         "utilisation_of_gpus_installed": (s_["utilisation"] * s_["gpus"] / f["capacity"]) if f["gpus"] else 0.0,
                         "equivalent_tokens_per_year_m": s_["annual_eq_m"],
                         "api_tokens_cost_usd": s_["api_llm"], "api_other_ai_cost_usd": s_["api_nt"]})
        files["4_capacity_by_year.csv"] = csv(rows)
        # 5. yearly cost by option and item
        rows = []
        for y in range(1, H + 1):
            for o in OPTIONS:
                items = b["yearly_parts"][o].get(y) if o in b["yearly_parts"] and b["yearly_parts"][o] else None
                if items:
                    for k, v in items.items():
                        rows.append({"year": y, "option": o, "item": k, "cost_usd": v, "discount_factor": b["disc"][y],
                                     "present_value_usd": v * b["disc"][y]})
                else:
                    rows.append({"year": y, "option": o, "item": "total", "cost_usd": b["yearly"][o][y],
                                 "discount_factor": b["disc"][y], "present_value_usd": b["yearly"][o][y] * b["disc"][y]})
        files["5_costs_by_year_and_item.csv"] = csv(rows)
        # 6. options per application
        rows = []
        for uid, res in list(o_["apps"].items()) + [("ALL", o_["total"])]:
            for o in OPTIONS:
                rows.append({"application": nm[uid]["name"] if uid in nm else "All together (shared capacity)",
                             "option": o, "pv_10y_usd": res["base"]["pv"][o], "cheapest": o == res["cheapest"],
                             "note": _note(uid, res),
                             "hardware": res["base"]["hardware"],
                             "peak_servers": max(f["servers"] for f in res["base"]["fleet"].values())})
        files["6_options_per_application.csv"] = csv(rows)
        # 7. assumptions
        c, _ = country()
        cp_ = cost_params(_run(input.ambition()), D, "base")
        rows = [("country", c.get("name", input.iso()), ""), ("adoption_scenario", SCEN[input.ambition()], ""),
                ("hardware", hw["name"], hw.get("evidence", "")), ("kw_per_gpu", hw["kw_per_gpu"], "hardware.yaml"),
                ("gpus_per_server", hw.get("gpus_per_server", 1), "hardware.yaml"),
                ("gpu_server_price_per_gpu_usd", b["capex_gpu"], "hardware.yaml / quote"),
                ("gpu_rental_usd_per_hour", b["gpu_hour"], "hardware.yaml / quote"),
                *[(f"throughput_tokens_per_s_per_gpu_{k}", v, "S44 InferenceX, chosen speed") for k, v in b["sizing"][H]["eff_tps"].items()],
                *[(f"api_price_{k}_input_per_m", v["input"], API_PROV) for k, v in API_PRICES.items()],
                *[(f"api_price_{k}_output_per_m", v["output"], API_PROV) for k, v in API_PRICES.items()],
                ("electricity_usd_per_kwh", cp_["kwh"], "country / default"), ("pue", b["pue"], "facility.yaml"),
                ("colocation_usd_per_kw_month", b["colo"]["value"],
                 (f'{b["colo"]["wholesale"]:g} wholesale x {D["colocation"]["small_deployment_factor"]["value"]:g} '
                  f'(deployment under {D["colocation"]["small_deployment_kw"]["value"]:g} kW); ' if b["colo"]["small"] else "wholesale; ")
                 + b["colo"]["src"]),
                ("facility_buffer", D["facility_buffer"]["value"], D["facility_buffer"]["source"]),
                ("design_it_kw", b["design_it_kw"], "peak IT load x (1 + buffer)"),
                ("build_usd_per_mw", b["build_per_mw"], "size curve x country factor"),
                ("facility_build_usd", b["facility_capex"], ""), ("discount_rate_pct", num(input.disc()) or 0, "Setup"),
                ("api_price_decline_pct", num(input.decline()) or 0, "Setup (S82, S83)"),
                ("hw_price_decline_pct", num(input.decline_hw()) or 0, "Setup (S84)"),
                ("compute_gain_per_year_pct", num(input.gain()) or 0, "Setup (S86, S87)"),
                ("api_reference", b["api_reference"], "Setup (S109, S110, S21)"),
                ("api_commit_discount_pct", num(input.api_disc()) or 0, "Setup (S111)"),
                ("gpu_rental_reference", b["rental_reference"], "Setup (S112, S113, S11)"),
                ("gpu_rental_mode", b["rental_mode"], "Setup"),
                ("gpu_hour_usd_reserved", b["gpu_hour"], ""), ("gpu_hour_usd_on_demand", b["gpu_hour_on_demand"], ""),
                ("software_stack", input.sw(), "Setup (S115)"),
                ("server_life_years", b["server_life"], "Setup (S114)"),
                ("idle_sharing_share", b["night_share"], "Setup"),
                ("owned_infra_share", D["owned_infra_share"]["value"], D["owned_infra_share"]["source"]),
                ("redundancy_spare_server", bool(input.redundancy()), "Setup")]
        for k, v in D.items():
            if isinstance(v, dict) and "value" in v:
                rows.append((f"default.{k}", v["value"], v.get("source", "")))
        files["7_assumptions.csv"] = csv([{"item": k, "value": v, "source": s_} for k, v, s_ in rows])
        files["README.txt"] = """Sovereign AI Compute Planner - full calculation
Base prices, the adoption scenario chosen in Setup, US dollars, present value at the discount rate shown in 7_assumptions.csv.

1_inputs_applications.csv      What was entered, and the defaults used for each application type.
2_tokens_per_application_at_start.csv
                               requests/day = volume x rate; tokens per request = (input + system prompt) x calls x retry
                               for input, (output + reasoning) x calls x retry for output;
                               cached = system prompt x cache hit x calls x retry.
                               equivalent tokens = output + (input - cached) x prefill weight.
                               peak tokens/s = equivalent tokens/day x peak share / (window x 3600) x burst x headroom x seasonal.
3_demand_by_application_and_year.csv
                               growth factor = 0 before the start year, (1 + growth)^(year - start) after.
                               tokens/year use active days per year (working, school or calendar days).
4_capacity_by_year.csv         All applications pooled each year: GPUs = summed peaks x pooling factor / tokens/s per GPU,
                               plus other AI work. Servers are bought when the need exceeds what is installed, replaced
                               after the refresh period, never sold. kW = GPUs x kW per GPU (x PUE for the facility).
                               Energy uses the GPUs installed: (idle share + (1 - idle share) x utilisation of GPUs
                               installed) x kW x 8,760 h x PUE x tariff.
5_costs_by_year_and_item.csv   Yearly cost of each option by item, the discount factor and the present value.
                               API and GPU rental are shown as totals.
6_options_per_application.csv  Each application priced alone, and the portfolio priced together.
7_assumptions.csv              Every price, factor and default used, with its source ID (see the methodology).
"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for name, content in files.items():
                z.writestr(name, content)
        yield buf.getvalue()

    @render.download(filename="ai_compute_summary.csv")
    def dl_results():
        o_ = opt()
        nm = _names()
        rows = []
        for uid, res in list(o_["apps"].items()):
            a = nm.get(uid)
            if not a:
                continue
            rows.append({"application": a["name"], "start_year": a.get("start_year", 1),
                         "growth_per_year": a.get("growth", 0),
                         **{f"{OPT_SHORT[o]} (10-year, USD)": round(res["base"]["pv"][o]) for o in OPTIONS},
                         "cheapest": OPT_SHORT[res["cheapest"]] if any(res["base"]["pv"].values()) else "-",
                         "note": _note(uid, res)})
        t = o_["total"]
        rows.append({"application": "All together (shared capacity)",
                     **{f"{OPT_SHORT[o]} (10-year, USD)": round(t["base"]["pv"][o]) for o in OPTIONS},
                     "cheapest": OPT_SHORT[t["cheapest"]]})
        rows.append({"application": "Sum if each is bought alone",
                     **{f"{OPT_SHORT[o]} (10-year, USD)": round(v) for o, v in o_["sum_standalone"].items()}})
        df = pd.DataFrame(rows).astype({"start_year": "Int64"})
        yield df.to_csv(index=False)
















    import matplotlib
    import matplotlib.ticker
    matplotlib.rcParams.update({"font.size": 7.5, "font.family": "DejaVu Sans"})

    def _style(ax):
        for sp in ("top", "right", "left"):
            ax.spines[sp].set_visible(False)
        ax.spines["bottom"].set_color("#c9c8c3")
        ax.tick_params(colors="#52514e", labelsize=7.5, length=0)
        ax.xaxis.grid(True, color="#ecebe7", linewidth=0.8)
        ax.set_axisbelow(True)

    def _money_axis(ax):
        import matplotlib.ticker as mt
        ax.xaxis.set_major_formatter(mt.FuncFormatter(lambda v, _: money(v) if v else "0"))









    def scenario_dict():
        return {"version": "0.9", "own_dc_existing": bool(input.own_dc_existing()),
                "iso": input.iso(), "ambition": input.ambition(), "grid": input.grid(), "hw": input.hw(),
                "speed": input.speed(), "finance": {"disc": input.disc(), "decline": input.decline(), "decline_hw": input.decline_hw(), "gain": input.gain(),
                            "api_ref": input.api_ref(), "api_disc": input.api_disc(), "rent_ref": input.rent_ref(),
                            "rent_mode": input.rent_mode(), "sw": input.sw(), "life": input.life(),
                            "night": bool(input.night()), "night_share": input.night_share()},
                "redundancy": bool(input.redundancy()),
                "quotes": quotes(), "apps": apps.get(), "custom_types": custom.get()}

    @render.download(filename="scenario.json")
    def dl_scenario():
        yield json.dumps(scenario_dict(), indent=1)

    def apply_scenario(sc):
        custom.set(sc.get("custom_types") or {})
        known = {**ARCH, **custom.get()}
        ui.update_selectize("iso", selected=sc.get("iso", "XEX"))
        ui.update_radio_buttons("ambition", selected=sc.get("ambition", "Base"))
        ui.update_radio_buttons("grid", selected=sc.get("grid", "auto"))
        cap = sc.get("capability", {})
        ui.update_checkbox("own_dc_existing", value=bool(sc.get("own_dc_existing", cap.get("gov_dc") == "ready")))
        ui.update_select("hw", selected=sc.get("hw", "auto"))
        ui.update_radio_buttons("speed", selected=sc.get("speed", "base"))
        f = sc.get("finance", {})
        ui.update_checkbox("redundancy", value=bool(sc.get("redundancy", False)))
        for k in ("disc", "decline", "decline_hw", "gain", "api_disc", "life", "night_share"):
            if f.get(k) is not None:
                ui.update_numeric(k, value=f[k])
        for k in ("api_ref", "rent_ref", "sw"):
            if f.get(k):
                ui.update_select(k, selected=f[k])
        if f.get("rent_mode"):
            ui.update_radio_buttons("rent_mode", selected=f["rent_mode"])
        ui.update_checkbox("night", value=bool(f.get("night", False)))
        g_old = (num(f.get("growth")) or 0) / 100          # before v0.9 growth was one global rate
        lst = [dict(normalize_app(a), start_year=a.get("start_year", 1), growth=a.get("growth", g_old))
               for a in sc.get("apps", [])]
        missing = [a["name"] for a in lst if a["type"] not in known]
        if missing:
            ui.notification_show("Skipped applications with an unknown type: " + ", ".join(missing), type="warning")
        apps.set([a for a in lst if a["type"] in known])

    @reactive.effect
    @reactive.event(input.url_state)
    def _from_link():
        try:
            apply_scenario(decode_state(input.url_state()))
            ui.notification_show("Scenario loaded from the link.", duration=4)
        except Exception:  # noqa: BLE001
            ui.notification_show("This link could not be read: it may be truncated.", type="warning")

    @reactive.effect
    @reactive.event(input.save_link)
    async def _save_link():
        now = _dt.datetime.now()
        vid = now.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        name = (input.save_name() or "").strip() or f'{COUNTRIES.get(input.iso(), {}).get("name", input.iso())}, {len(apps.get())} applications'
        await session.send_custom_message("save_link", {"id": vid, "name": name, "date": now.strftime("%Y-%m-%d %H:%M"),
                                                  "state": encode_state(scenario_dict())})

    @render.ui
    def share_out():
        url = input.share_url() if "share_url" in input else None
        if not url:
            return None
        return ui.div(ui.p("Saved. Link copied to the clipboard (if the browser allows):", class_="hint", style="margin:8px 0 2px"),
                      ui.tags.textarea(url, readonly=True, rows=3, style="width:100%;font-size:.75rem",
                                       onclick="this.select()"))

    @render.ui
    def saved_list_ui():
        lst = input.saved_list() if "saved_list" in input else None
        if not lst:
            return ui.div("No saved versions in this browser yet.", class_="empty")
        rows = [ui.tags.tr(
            ui.tags.td(ui.tags.b(x.get("name", "")), ui.br(), ui.span(x.get("date", ""), class_="hint")),
            ui.tags.td(ui.tags.a("Open", href="#", onclick=f"Shiny.setInputValue('open_saved', '{x['id']}', {{priority: 'event'}}); return false;"),
                       " · ", ui.tags.a("Copy link", href="#", onclick=f"navigator.clipboard && navigator.clipboard.writeText('{x.get('url', '')}'); return false;"),
                       " · ", ui.tags.a("Remove", href="#", style="color:#b91c1c",
                                        onclick=f"Shiny.setInputValue('remove_saved', '{x['id']}', {{priority: 'event'}}); return false;")))
            for x in lst]
        return ui.tags.table(ui.tags.tbody(*rows), class_="table table-sm")

    @reactive.effect
    @reactive.event(input.open_saved)
    def _open_saved():
        x = next((x for x in (input.saved_list() or []) if x["id"] == input.open_saved()), None)
        if x:
            apply_scenario(decode_state(x["state"]))
            ui.notification_show(f'Opened "{x["name"]}" ({x["date"]}).', duration=4)

    @reactive.effect
    @reactive.event(input.remove_saved)
    async def _remove_saved():
        await session.send_custom_message("saved_remove", input.remove_saved())

    @reactive.effect
    @reactive.event(input.ul_scenario)
    def _load():
        f = input.ul_scenario()
        if not f:
            return
        apply_scenario(json.loads(open(f[0]["datapath"]).read()))

    # ---- evidence
    @render.ui
    def evidence():
        blocks = []
        for t in A().values():
            if is_llm(t):
                facts = (f'{t["unit_label"]} × {t["rate"]["low"]:g} / {t["rate"]["base"]:g} / {t["rate"]["high"]:g} requests per active day '
                         f'(Low / Base / High), {t.get("active_days_per_year", 365)} active days per year · per call {t["isl"]:,} in + {t["system_prompt_tokens"]:,} system, '
                         f'{t["osl"]:,} out, {t["reasoning_tokens"]:,} reasoning · {t["agent_steps"]} call(s) per task · '
                         f'model {t["model_class"]}')
            else:
                facts = f'{t["gpu_seconds_per_unit"]:g} GPU-seconds per unit · {t["mode"]}'
            blocks.append(ui.div(
                ui.tags.b(t["label"]), " ",
                ui.span(f'volume {t["confidence"]["volume"]}', class_=f'hint conf-{t["confidence"]["volume"]}'), " · ",
                ui.span(f'size {t["confidence"]["tokens"]}', class_=f'hint conf-{t["confidence"]["tokens"]}'), " · ",
                ui.span("basis: " + ", ".join(f"{k} {v}" for k, v in t.get("basis", {}).items()), class_="hint"),
                ui.p(facts, class_="hint", style="margin:2px 0"),
                ui.tags.ul(*[ui.tags.li(ui.tags.i(k), ": ", *cite(v)) for k, v in t["evidence"].items()], class_="hint"),
                ui.p("Sources: ", *[x for i in cited_ids(t) for x in (ui.tags.a(i, href=f"#src-{i}", title=SRC[i]["title"]), " ")]
                     if cited_ids(t) else "Sources: none (assumption)", class_="hint", style="margin:0"),
                style="padding:8px 0;border-bottom:1px solid #e5e7eb"))
        return ui.div(*blocks)

    @render.table
    def country_tbl():
        c, _ = country()
        src = c.get("_sources", {})
        keys = ["population", "internet_share", "outages_per_month", "electricity_usd_kwh"]
        return pd.DataFrame([{"Input": k, "Value": c.get(k), "Source": src.get(k, src.get("all", "default / user"))}
                             for k in keys])

    @render.table
    def defaults_tbl():
        rows = [{"Parameter": k, "Value": v["value"], "Source": v.get("source"), "Note": v.get("note", "")}
                for k, v in D.items() if isinstance(v, dict) and "value" in v]
        rows += [{"Parameter": k, "Value": f'{v["low"]} / {v["base"]} / {v["high"]}', "Source": v.get("source"),
                  "Note": "low / base / high. " + v.get("note", "")} for k, v in D["costs"].items()]
        rows.append({"Parameter": "API prices", "Value": "", "Source": API_PROV, "Note": ""})
        return pd.DataFrame(rows)

    @render.ui
    def sources():
        return ui.tags.ol(*[ui.tags.li(ui.tags.b(s["id"]), f' {s["title"]}, {s["publisher"]}. ',
                                       ui.tags.a(s["url"], href=s["url"], target="_blank"), f' · {s["used_for"]}',
                                       id=f'src-{s["id"]}', class_="hint", style="scroll-margin-top:70px")
                            for s in CAT["sources"]])


app = App(app_ui, server)
