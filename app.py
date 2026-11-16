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
from engine.archetypes import (EXAMPLE_PORTFOLIO, POPULATION_BASIS, basis_label, build_profile, is_llm,
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
            ui.input_radio_buttons("provider", "Is there an in-country GPU cloud provider?",
                                   {"no": "No / not sure", "yes": "Yes"}, selected="no", inline=True),
            ui.input_checkbox("shared", "Confidential and Restricted data share one secure site", value=True),
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
            ui.input_numeric("growth", "Demand growth (%/year)", value=round(D["demand_growth"]["value"] * 100, 1), min=-50, max=200, step=5),
            ui.input_numeric("decline", "Market price decline (%/year)", value=round(D["price_decline"]["value"] * 100, 1), min=0, max=80, step=5),
            col_widths=[4, 4, 4]),
        ui.p("Costs are shown as present value over 10 years. Price decline applies to API tokens, GPU rental and GPU purchases at refresh.",
             class_="hint"),
    ),
    ui.accordion(
        ui.accordion_panel(
            "Placement rules: data class → where it may run",
            ui.p("Set once per country from its data protection law. Each application runs in the tier of its data class. "
                 "Default follows the World Bank data classification approach [S14].", class_="hint"),
            ui.layout_columns(*[ui.input_select(f"map{c}", CLASS_LABELS[c],
                                                {t: f'{t} · {D["tiers"][t]["name"]}' for t in TIERS},
                                                selected=D["class_to_tier"][c]) for c in (1, 2, 3, 4)],
                              col_widths=[3, 3, 3, 3]),
        ),
        ui.accordion_panel(
            "Client quotes (optional)",
            ui.p("Leave empty to use the default cost range. A quote replaces the range.", class_="hint"),
            ui.layout_columns(
                ui.input_numeric("q_gpu_hour", "GPU rental ($/GPU-hour)", None),
                ui.input_numeric("q_gpu_capex", "GPU server cost ($/GPU)", None),
                ui.input_numeric("q_fac", "Data centre build ($/MW IT)", None),
                col_widths=[4, 4, 4]),
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
                "input.a_type === 'agriculture_advisory'",
                ui.input_radio_buttons("a_basis", "Who are these farmers?", {
                    "eligible": "Everyone eligible (all farmers, or all beneficiaries of a scheme; most will not use the AI service)",
                    "users": "Farmers using the advisory service (onboarded through extension, cooperatives, or app users)"},
                    selected="eligible"),
            ),
            ui.input_select("a_class", "Data class", {str(k): v for k, v in CLASS_LABELS.items()}, selected="3"),
            ui.accordion(ui.accordion_panel(
                "Advanced",
                ui.input_numeric("a_rate", "Requests per person per day (leave empty for type default)", value=None, min=0),
                ui.input_select("a_model", "Model size", {"": "Type default", "S": "Small (~8B)",
                                                           "M": "Medium (~70B)", "L": "Large reasoning (~600B MoE)"}),
                ui.input_text("a_split", "Split traffic by data class (optional)", placeholder="e.g. 2:0.9, 3:0.1"),
                ui.p("Use a split when sensitive requests are routed separately. Default: everything goes to the "
                     "application's data class.", class_="hint"),
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
            ui.output_ui("app_list"),
        ),
        col_widths=[4, 8],
    ),
)

results_panel = ui.nav_panel(
    "3 · Results",
    ui.output_ui("warnings"),
    ui.output_ui("answer"),
    ui.h4("1 · How much will it cost?", class_="sec"),
    ui.layout_columns(
        ui.card(ui.card_header("10-year cost by adoption scenario (present value, stacked by data class; whisker = price range)"),
                ui.output_plot("chart_scen", height="300px")),
        ui.card(ui.card_header("The same numbers"), ui.output_table("scen_table"), ui.output_ui("range_note"),
                ui.p("Adoption scenario: how much people use the applications. Price range: low and high costs for "
                     "hardware, cloud and API prices, and GPU efficiency. All figures rounded.", class_="hint")),
        col_widths=[7, 5]),
    ui.h4("2 · What needs to be built or bought?", class_="sec"),
    ui.output_ui("capacity_cards"),
    ui.h4("3 · Where does the cost come from?", class_="sec"),
    ui.layout_columns(
        ui.card(ui.card_header("10-year cost by application (present value)"), ui.output_plot("chart_app", height="360px")),
        ui.card(ui.card_header("By application"), ui.output_table("app_table"),
                ui.p("Share of site: each application carries part of the site's fixed costs (servers, facility, staff) in "
                     "proportion to its GPU need. Removing it would not save that amount. Extra cost if added last: what "
                     "this application adds on top of all the others (often close to zero when it fits in spare capacity).",
                     class_="hint")),
        col_widths=[6, 6]),
    ui.accordion(
        ui.accordion_panel("Details: every buying option, Low – Base – High",
                           ui.output_ui("tco_flag"), ui.output_table("tco")),
        ui.accordion_panel("Details: placement tiers and hardware", ui.output_table("ladder")),
        ui.accordion_panel("Details: rent or own per tier (year 1)", ui.output_table("rent_own"), ui.output_ui("rent_own_note")),
        ui.accordion_panel("Details: demand by application", ui.output_table("demand")),
        ui.accordion_panel("Details: cost by data class (Base, with range)", ui.output_plot("chart_class", height="300px")),
        open=False),
    ui.layout_columns(ui.download_button("dl_results", "Export raw results (CSV, unrounded)"),
                      ui.download_button("dl_scenario", "Save scenario"),
                      ui.input_file("ul_scenario", None, accept=[".json"], button_label="Load scenario",
                                    placeholder="scenario.json"),
                      col_widths=[3, 3, 6]),
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
    footer=ui.div("v0.7 draft · planning-grade estimates · every default is sourced in the Evidence tab",
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
        ui.update_select("a_class", selected=str(t["data_class"]))
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
        split = None
        s = (input.a_split() or "").strip()
        if s:
            try:
                split = {int(k): float(v) for k, v in (p.split(":") for p in s.split(","))}
            except ValueError:
                ui.notification_show("Traffic split not understood, ignored. Format: 2:0.9, 3:0.1", type="warning")
        rate = num(input.a_rate()) if is_llm(t) and t["unit"] == "users" else None
        new = dict(uid=uuid.uuid4().hex[:8], name=input.a_name().strip() or t["label"], type=t["id"], volume=vol,
                   data_class=int(input.a_class()), rate_override=rate, model_class=input.a_model() or None,
                   traffic_split=split,
                   population_basis=input.a_basis() if t.get("rate_by_basis") else "eligible")
        w = volume_warning(new, country()[0], A(), D["agri_volume_tolerance"]["value"])
        if w:
            ui.notification_show(w, type="warning", duration=10)
        apps.set(apps.get() + [new])
        ui.update_text("a_name", value="")
        ui.update_numeric("a_volume", value=None)
        ui.update_text("a_split", value="")

    @reactive.effect
    @reactive.event(input.remove_app)
    def _remove():
        apps.set([a for a in apps.get() if a["uid"] != input.remove_app()])

    @reactive.effect
    @reactive.event(input.example)
    def _example():
        apps.set([dict(a, uid=uuid.uuid4().hex[:8]) for a in EXAMPLE_PORTFOLIO])

    @reactive.effect
    @reactive.event(input.clear)
    def _clear():
        apps.set([])

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
            tier = input[f"map{a['data_class']}"]()
            rows.append(ui.tags.tr(
                ui.tags.td(ui.tags.b(a["name"]), ui.br(), ui.span(t["label"], class_="hint"),
                           *([ui.br(), ui.span("⚠ " + w, style="color:#92400e;font-size:.82rem")]
                             if (w := volume_warning(a, country()[0], A(), D["agri_volume_tolerance"]["value"])) else []),
                           *([ui.br(), ui.span("ⓘ " + n, style="color:#1e40af;font-size:.82rem")]
                             if (n := low_usage_note(a, A(), input.ambition())) else [])),
                ui.tags.td(f'{fmt(a["volume"])}', ui.br(), ui.span(t["unit_label"], class_="hint"),
                           *([ui.br(), ui.span(f"({b})", class_="hint")] if (b := basis_label(a, A())) else [])),
                ui.tags.td(ui.span(CLASS_LABELS[a["data_class"]], class_=f'badge-c badge-{a["data_class"]}'),
                           " → ", tier),
                ui.tags.td(load),
                ui.tags.td(ui.span("●", class_=f'conf-{t["confidence"]["volume"]}', title=f'Usage rate evidence: {t["confidence"]["volume"]}'),
                           ui.span("●", class_=f'conf-{t["confidence"]["tokens"]}', title=f'Size evidence: {t["confidence"]["tokens"]}'),
                           style="white-space:nowrap;font-size:1.1rem"),
                ui.tags.td(ui.tags.button("✕", class_="btn-x", title="Remove",
                                          onclick=f"Shiny.setInputValue('remove_app','{a['uid']}',{{priority:'event'}})")),
            ))
        return ui.tags.table(
            ui.tags.thead(ui.tags.tr(*[ui.tags.th(h) for h in ("Application", "Volume", "Data class → tier",
                                                                "Estimated load", "Evidence", "")])),
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
            bits.append(f"outages {o:.1f} per month ({cc['_sources'].get('outages_per_month', '')[-4:]})")
        if s is not None:
            bits.append(f"{s:.0%} of firms had outages ({cc['_sources'].get('firms_with_outages_share', '')[-4:]})")
        if o is None and s is None:
            bits.append("outages: no data")
        return ui.p(" · ".join(bits), class_="hint")

    def quotes():
        q = {}
        for key, inp in [("gpu_hour_usd", "q_gpu_hour"), ("gpu_capex_usd", "q_gpu_capex"),
                         ("facility_capex_usd_per_mw_it", "q_fac")]:
            v = num(input[inp]())
            if v:
                q[key] = v
        return q

    def _run(ambition, app_list=None, tiers=None):
        c, _ = country()
        p = build_profile(c, ambition, apps.get() if app_list is None else app_list, A(),
                          tiers or {cl: input[f"map{cl}"]() for cl in (1, 2, 3, 4)}, quotes(), input.hw())
        p.speed = input.speed()
        p.local_gpu_provider = input.provider() == "yes"
        p.shared_sovereign_site = bool(input.shared())
        pct = lambda v: (num(v) or 0) / 100
        p.finance = {"discount_rate": pct(input.disc()), "demand_growth": pct(input.growth()),
                     "price_decline": pct(input.decline())}
        return run(p, CAT, D, API_PRICES)

    @reactive.calc
    def result():
        return _run(input.ambition())

    @reactive.calc
    def added_last():
        """Extra 10-year cost of each application if added last: total minus the total without it."""
        lst = apps.get()
        tot = result()["totals"]["cost"]
        return {a["uid"]: tot - _run(input.ambition(), [x for x in lst if x["uid"] != a["uid"]])["totals"]["cost"]
                for a in lst} if len(lst) > 1 else {a["uid"]: tot for a in lst}

    @reactive.calc
    def placement_delta():
        """Versus the default placement: servers and 10-year cost added by the user's placement rules."""
        r0 = _run(input.ambition(), tiers=dict(D["class_to_tier"]))
        r1 = result()
        return dict(servers=_build_summary(r1)[0] - _build_summary(r0)[0], cost=r1["totals"]["cost"] - r0["totals"]["cost"])

    @reactive.calc
    def scenarios():
        return {a: (result() if a == input.ambition() else _run(a)) for a in ("Low", "Base", "High")}

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
        order = {"T1": 1, "T2": 2, "T3": 3, "T4": 4}
        moved = [a["name"] for a in apps.get()
                 if order[input[f'map{a["data_class"]}']()] > order[D["class_to_tier"][a["data_class"]]]]
        if moved:
            pdl = placement_delta()
            srv = (f'{pdl["servers"]:+d} server{"s" if abs(pdl["servers"]) != 1 else ""}' if pdl["servers"]
                   else "no extra servers (they use spare capacity)")
            msgs.append(f'{len(moved)} application{"s" if len(moved) != 1 else ""} placed above the default tier by your '
                        f'placement rules ({", ".join(moved)}). Versus the default placement: {srv}, '
                        f'10-year cost {"+" if pdl["cost"] >= 0 else "−"}{money(abs(pdl["cost"]))}.')
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

    SHORT = {"build": "sovereign site", "rent": "GPU rental", "service": "API"}

    def where(r, t):
        v = r["tiers"][t]
        k = v["capacity"]["kind"]
        if v.get("shared_site"):
            return "Sovereign site (shared)"
        if k == "build":
            return f"Sovereign site ({DEST[t].split()[0].lower()})"
        if k == "rent":
            return "In-country GPU rental"
        if k == "service":
            return "API service" + (" (residency)" if t == "T2" else "")
        return DEST[t]

    def _build_summary(r):
        builds = [(t, v) for t, v in r["tiers"].items() if v["capacity"]["kind"] == "build"]
        servers = sum(v["capacity"]["servers"] or 0 for _, v in builds)
        gpus = sum(v["capacity"]["gpus"] or 0 for _, v in builds)
        fkw = sum(v["capacity"]["facility_kw"] or 0 for _, v in builds)
        capex = sum(v["detail"]["base"]["Owned"]["upfront"] for _, v in builds)
        return servers, gpus, fkw, capex

    @render.ui
    def answer():
        if not apps.get():
            return None
        r = result()
        t = r["totals"]
        servers, gpus, fkw, capex = _build_summary(r)
        rent = [v for v in r["tiers"].values() if v["capacity"]["kind"] == "rent"]
        svc = [v for v in r["tiers"].values() if v["capacity"]["kind"] == "service"]
        parts = []
        if servers:
            parts.append(f"Build in-country: {servers} server{'s' if servers != 1 else ''} ({gpus} GPUs), "
                         f"about {power(fkw / 1000)} of facility power, {money(capex)} upfront.")
        if rent:
            parts.append(f"Rent about {sum(v['capacity']['gpus'] for v in rent)} GPUs from an in-country provider.")
        if svc:
            yr = sum(v["detail"]["base"]["API / managed"]["annual_y1"] for v in svc if "API / managed" in v["detail"]["base"])
            parts.append(f"Buy the rest as cloud or API services, about {money(yr)} per year.")
        return ui.div(
            ui.div(f'About {money(t["cost"])} over 10 years', class_="big"),
            ui.div(f'Range {money_range(t["cost_range"]["low"], t["cost_range"]["high"])} with '
                   f'{SCEN_LABEL[input.ambition()].lower()} adoption · present value at {num(input.disc()) or 0:g}% · '
                   f'{len(apps.get())} application{"s" if len(apps.get()) != 1 else ""}', class_="line"),
            ui.div(" ".join(parts), class_="line"),
            class_="answer")

    @render.plot(alt="10-year cost by adoption scenario")
    def chart_scen():
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch
        fig, ax = plt.subplots(figsize=(7.5, 3.3))
        if not apps.get():
            ax.axis("off")
            ax.text(0.5, 0.5, "Add applications to see costs", ha="center", color="#52514e")
            return fig
        sc = scenarios()
        keys = ["Low", "Base", "High"]
        x = range(3)
        bottom = [0.0, 0.0, 0.0]
        used = []
        for t in ("T1", "T2", "T3", "T4"):
            vals = [sc[k]["tiers"][t]["cost_range"]["base"] or 0 for k in keys]
            if any(vals):
                ax.bar(x, vals, bottom=bottom, color=TIER_COLORS[t], width=0.55, edgecolor="#fcfcfb", linewidth=2)
                bottom = [b + v for b, v in zip(bottom, vals)]
                used.append(t)
        lo = [sc[k]["totals"]["cost_range"]["low"] for k in keys]
        hi = [sc[k]["totals"]["cost_range"]["high"] for k in keys]
        ax.errorbar(x, bottom, yerr=[[b - l for b, l in zip(bottom, lo)], [h - b for b, h in zip(bottom, hi)]],
                    fmt="none", ecolor="#52514e", elinewidth=1.2, capsize=4)
        for xi, b, h in zip(x, bottom, hi):
            ax.text(xi, h * 1.03, f"about {money(b)}", ha="center", va="bottom", fontsize=8, color="#0b0b0b", fontweight="bold")
        ax.set_xticks(list(x), [f"{SCEN_LABEL[k]}\nadoption" + (" (selected)" if k == input.ambition() else "") for k in keys])
        ax.set_ylim(0, max(hi) * 1.2)
        ax.legend(handles=[Patch(color=TIER_COLORS[t], label=DEST[t]) for t in used], loc="upper center",
                  bbox_to_anchor=(0.5, -0.2), ncol=len(used), frameon=False, fontsize=7.5)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.spines["left"].set_color("#c9c8c3")
        ax.spines["bottom"].set_color("#c9c8c3")
        ax.tick_params(colors="#52514e", labelsize=7.5, length=0)
        ax.yaxis.grid(True, color="#ecebe7", linewidth=0.8)
        ax.set_axisbelow(True)
        import matplotlib.ticker as mt
        ax.yaxis.set_major_formatter(mt.FuncFormatter(lambda v, _: money(v) if v else "0"))
        ax.yaxis.set_major_locator(mt.MaxNLocator(4))
        fig.subplots_adjust(left=0.1, right=0.98, bottom=0.28, top=0.95)
        return fig

    @render.table
    def scen_table():
        if not apps.get():
            return None
        sc = scenarios()
        rows = []
        for k in ("Low", "Base", "High"):
            r = sc[k]
            servers, gpus, fkw, capex = _build_summary(r)
            rows.append({"Adoption": SCEN_LABEL[k] + (" ★" if k == input.ambition() else ""),
                         "10-year cost": f'about {money(r["totals"]["cost"])}',
                         "Price range": money_range(r["totals"]["cost_range"]["low"], r["totals"]["cost_range"]["high"]),
                         "Servers to build": f"{servers}" if servers else "none",
                         "Facility power": power(fkw / 1000) if fkw else "-"})
        return pd.DataFrame(rows)

    @render.ui
    def range_note():
        if not apps.get():
            return None
        r = result()
        per = {h["id"]: h.get("gpus_per_server", 1) for h in CAT["hardware"]}
        extra = []
        for t, v in r["tiers"].items():
            if v["capacity"]["kind"] != "build" or v.get("merged_into"):
                continue
            n = per.get(v["hardware"], 1)
            hi = math.ceil((v["sizing_range"]["high"]["gpus"] or 0) / n)
            if hi > (v["sizing"].get("servers") or 0):
                extra.append(hi - v["sizing"]["servers"])
        if not extra:
            return None
        k = sum(extra)
        return ui.p(f'The high end of the price range adds {k} server{"s" if k != 1 else ""}: with lower GPU efficiency the same '
                    'load no longer fits, which is why the range is lopsided.', class_="hint")

    def _m(v, l):
        return ui.div(ui.div(v, class_="v"), ui.div(l, class_="l"), class_="m")

    def _pv_breakdown(pv):
        """10-year present value of owning, split so a client with colocation or an existing room sees the GPU part."""
        gpu = pv["gpu_servers"] + pv["software"] + pv["maintenance_gpu"]
        fac = pv["facility_build"] + pv["maintenance_facility"]
        return ui.div(
            ui.p(ui.tags.b("10-year cost of owning, present value"), class_="hint", style="margin:6px 0 2px"),
            ui.div(_m(money(pv["gpu_servers"]), "GPU servers incl. refresh"),
                   _m(money(pv["software"] + pv["maintenance_gpu"]), "GPU software + maintenance"),
                   _m(money(fac), "facility build + maintenance"),
                   _m(money(pv["energy"]), "energy"), _m(money(pv["staff"]), "staff"), class_="row2"),
            ui.p(f"GPU part alone: {money(gpu)}. With colocation or an existing server room, the facility "
                 f"({money(fac)}) drops out and is replaced by colocation rent or the room's existing costs (not included); "
                 "energy and staff usually remain, unless the colocation fee bundles power.", class_="hint"))

    @render.ui
    def capacity_cards():
        if not apps.get():
            return None
        r = result()
        hwname = {h["id"]: h["name"] for h in CAT["hardware"]}
        cards = []
        for t, v in r["tiers"].items():
            cap, det = v["capacity"], v["detail"]["base"]
            if v.get("merged_into") or cap["kind"] == "none":
                continue
            color = TIER_COLORS[t]
            title = ("Shared sovereign site · Confidential + Restricted data" if v.get("shared_site")
                     else f'{DEST[t]} · {D["tiers"][t]["name"]}')
            if cap["kind"] == "service":
                api = det.get("API / managed", {}).get("annual_y1")
                body = [ui.div(_m(money(api) if api is not None else "-", "per year"),
                               _m(money(v["cost_range"]["base"]), "10-year present value"), class_="row2"),
                        ui.p("Nothing to build: bought as an API service.", class_="hint")]
            elif cap["kind"] == "rent":
                body = [ui.div(_m(f'{cap["gpus"]}', "GPUs rented"),
                               _m(money(det["GPU-as-a-service"]["annual_y1"]), "per year"),
                               _m(money(v["cost_range"]["base"]), "10-year present value"), class_="row2")]
            else:
                own = det["Owned"]
                rent = det.get("GPU-as-a-service", {}).get("annual_y1")
                body = [ui.div(_m(f'{cap["servers"]}', "servers" if (cap["servers"] or 0) != 1 else "server"),
                               _m(f'{cap["gpus"]}', "GPUs"), _m(power(cap["it_kw"] / 1000), "IT load"),
                               _m(power(cap["facility_kw"] / 1000), f'facility (PUE {v["facility"]["pue"]:.2f})'),
                               _m(f'{cap["racks"]}', "rack" if cap["racks"] == 1 else "racks"), class_="row2"),
                        ui.div(_m(money(own["upfront"]), "upfront (facility + GPUs)"),
                               _m(money(own["annual_opex_y1"]), "per year to run"),
                               _m(", ".join(f"{money(x)} in year {y}" for y, x in own["refresh"]) or "-", "GPU refresh"),
                               class_="row2"),
                        ui.p(f'Headroom at the busiest hour: about {max(0, 1 - v["sizing"].get("gpu_need", 0) / cap["gpus"]):.0%} '
                             'of the GPUs, room for more applications without new hardware.' if cap["gpus"] else "",
                             class_="hint", style="margin:4px 0"),
                        _pv_breakdown(own["pv_breakdown"]),
                        ui.p(f'Hardware: {hwname.get(v["hardware"], v["hardware"])} · utilisation {v["sizing"]["utilisation"]:.0%}'
                             + (f' · renting instead: {money(rent)} per year' if rent else
                                " · renting not available (no in-country provider)" if t == "T3" or v.get("shared_site") else ""),
                             class_="hint")]
            cards.append(ui.div(ui.tags.h5(title), ui.div(v["grid"] if v["grid"] not in ("-", "OK", "Offshore: not applicable") else "",
                                                           class_="sub"),
                                *body, ui.div(v["step"], class_="step"), class_="ccard", style=f"--c:{color}"))
        return ui.div(*cards, class_="cards")

    @render.table
    def app_table():
        r = result()
        if not apps.get():
            return None
        total = r["totals"]["cost"] or 1
        req = {}
        for x in r["demand"]:
            req[x["id"]] = req.get(x["id"], 0) + x["sessions"]
        rows = []
        for a in sorted(apps.get(), key=lambda a: -sum(r["by_app"].get(a["uid"], {}).values())):
            cost = sum(r["by_app"].get(a["uid"], {}).values())
            dest = [t for t in r["by_app"].get(a["uid"], {})]
            t = A()[a["type"]]
            rows.append({"Application": a["name"],
                         "Volume": f'{fmt(a["volume"])} {t["unit_label"].lower()}'
                                   + (f" ({b})" if (b := basis_label(a, A())) else ""),
                         "Requests/day": fmt(req[a["uid"]]) if a["uid"] in req else "GPU job",
                         "Data class": CLASS_LABELS[a["data_class"]].split(" · ")[1],
                         "Runs in": ", ".join(where(r, x) for x in dest) or "-",
                         "10-year cost (share of site)": money(cost) if cost else "-",
                         "Share": f"{cost / total:.0%}" if cost else "-",
                         "Extra cost if added last": money(max(0, al)) if (al := added_last().get(a["uid"])) is not None and al > 1 else "≈ 0"})
        return pd.DataFrame(rows)

    @render.ui
    def kpis():
        r = result()
        t = r["totals"]
        lo = sum((v["cost_range"]["low"] or 0) for v in r["tiers"].values())
        hi = sum((v["cost_range"]["high"] or 0) for v in r["tiers"].values())
        local = sum(v["sizing"]["facility_mw"] for k, v in r["tiers"].items() if k in ("T3", "T4"))
        g, mw = t["gpus_range"], t["mw_range"]
        return ui.layout_columns(
            kpi("GPUs (all tiers)", f'about {fmt(t["gpus"])}', f'range {fmt(g["low"])}–{fmt(g["high"])} · {SCEN[input.ambition()]} adoption'),
            kpi("Facility power", f'about {power(t["facility_mw"])}', f'range {power(mw["low"])}–{power(mw["high"])} · in-country sovereign: {power(local)}'),
            kpi("10-year cost (present value)", f'about {money(t["cost"])}', f"range {money_range(lo, hi)} · discount {num(input.disc()) or 0:g}%"),
            col_widths=[4, 4, 4])

    @render.table
    def ladder():
        r = result()
        return pd.DataFrame([{
            "Tier": f'{t} · {D["tiers"][t]["name"]}',
            "GPUs": ("service" if v["capacity"]["kind"] == "service" else
                     f'{v["sizing"]["gpus"]} ({v["sizing"].get("servers")} servers)' if v["capacity"]["kind"] == "build"
                     else fmt(v["sizing"]["gpus"])),
            "Facility power": power(v["sizing"]["facility_mw"]) if v["capacity"]["kind"] == "build" else "-",
            "Utilisation": f'{v["sizing"]["utilisation"]:.0%}',
            "Apps / pooling": f'{v["sizing"]["n_apps"]} / D {v["sizing"]["diversity"]:.2f}' if v["sizing"]["n_apps"] else "-",
            "Hardware": v["hardware"] if v["sizing"]["gpus"] else "-",
            "PUE": f'{v["facility"]["pue"]:.2f}' if v["sizing"]["gpus"] else "-",
            "Grid": v["grid"], "Recommended step": v["step"],
        } for t, v in r["tiers"].items()])


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

    @render.plot(alt="10-year cost by data class")
    def chart_class():
        import matplotlib.pyplot as plt
        r = result()
        rows = [(t, v) for t, v in r["tiers"].items() if v["cheapest_cost"]]
        fig, ax = plt.subplots(figsize=(7.5, 3.2))
        if not rows:
            ax.axis("off")
            ax.text(0.5, 0.5, "Add applications to see costs", ha="center", color="#52514e")
            return fig
        labels = [f'{t}\n{"Public" if t == "T1" else "Internal" if t == "T2" else "Confidential" if t == "T3" else "Restricted"}'
                  for t, _ in rows][::-1]
        base = [v["cost_range"]["base"] for _, v in rows][::-1]
        lo = [v["cost_range"]["low"] for _, v in rows][::-1]
        hi = [v["cost_range"]["high"] for _, v in rows][::-1]
        cols = [TIER_COLORS[t] for t, _ in rows][::-1]
        y = range(len(rows))
        ax.barh(y, base, color=cols, height=0.55)
        ax.errorbar(base, y, xerr=[[b - l for b, l in zip(base, lo)], [h - b for b, h in zip(base, hi)]],
                    fmt="none", ecolor="#52514e", elinewidth=1.2, capsize=3)
        for yi, b, h, (t, v) in zip(y, base, hi, rows[::-1]):
            ax.text(h * 1.02, yi, f'{money(b)} · {v["cheapest_mode"]}', va="center", fontsize=7.5, color="#0b0b0b")
        ax.set_yticks(list(y), labels)
        ax.set_xlim(0, max(hi) * 1.6)
        _style(ax)
        _money_axis(ax)
        ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(4))
        fig.subplots_adjust(left=0.2, right=0.97, bottom=0.12, top=0.96)
        return fig

    @render.plot(alt="10-year cost by application")
    def chart_app():
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch
        r = result()
        names = {a["uid"]: a["name"] + (f" ({b})" if (b := basis_label(a, A())) else "") for a in apps.get()}
        items = sorted(((names.get(k, k), sum(v.values()), max(v, key=v.get)) for k, v in r["by_app"].items()),
                       key=lambda x: x[1])
        fig, ax = plt.subplots(figsize=(7.5, max(3.2, 0.3 * len(items) + 0.9)))
        if not items:
            ax.axis("off")
            ax.text(0.5, 0.5, "Add applications to see costs", ha="center", color="#52514e")
            return fig
        y = range(len(items))
        ax.barh(y, [c for _, c, _ in items], color=[TIER_COLORS[t] for _, _, t in items], height=0.6)
        for yi, (_, c, t) in zip(y, items):
            ax.text(c * 1.02 + max(x for _, x, _ in items) * 0.01, yi, f"{money(c)} · {SHORT.get(r['tiers'][t]['capacity']['kind'], '')}",
                    va="center", fontsize=7.5, color="#0b0b0b")
        ax.set_yticks(list(y), [n if len(n) <= 40 else n[:38] + "…" for n, _, _ in items])
        ax.set_xlim(0, max(c for _, c, _ in items) * 2.5)
        tiers_used = sorted({t for _, _, t in items})
        _style(ax)
        _money_axis(ax)
        ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(4))
        ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(3))
        fig.subplots_adjust(left=0.44, right=0.97, bottom=0.1, top=0.97)
        return fig

    @render.table
    def rent_own():
        r = result()
        rows = []
        for t, v in r["tiers"].items():
            if not v["sizing"]["gpus"]:
                continue
            det = v["detail"]["base"]
            api = det.get("API / managed", {}).get("annual_y1")
            rent = det.get("GPU-as-a-service", {}).get("annual_y1")
            own = det.get("Owned")
            rows.append({
                "Tier": t,
                "API: per year": money(api) if api is not None else "not allowed",
                "Rent GPUs: per year": money(rent) if rent is not None else "not allowed",
                "Own: upfront (facility + GPUs)": money(own["upfront"]) if own else "-",
                "Own: per year (energy, staff, software, maintenance)": money(own["annual_opex_y1"]) if own else "-",
                "Own: GPU refresh": ", ".join(f'{money(val)} in year {y}' for y, val in own["refresh"]) if own and own["refresh"] else "-",
                "Facility basis": (f'PUE {v["facility"]["pue"]:.2f}; ${own["capex_per_mw"] / 1e6:.1f}M per MW IT '
                                   f'({v["facility"]["capex_src"]})') if own else "-",
            })
        return pd.DataFrame(rows) if rows else None

    @render.ui
    def rent_own_note():
        return ui.p("Renting has no upfront cost and scales down; owning concentrates cost upfront and needs utilisation to pay off. "
                    "Facility cost and PUE come from the country and the cooling type (Methodology, Section 8). "
                    "Year-1 values, rounded to two significant figures.", class_="hint")

    @render.ui
    def tco_flag():
        r = result()
        flips = [f'{t}: cheapest is {v["winners"]["low"]} (Low), {v["winners"]["base"]} (Base), {v["winners"]["high"]} (High)'
                 for t, v in r["tiers"].items() if v["winner_changes"]]
        if not flips:
            return ui.p("The cheapest option is the same across the Low – High range in every tier.", class_="hint")
        return ui.div(ui.tags.b("The cheapest option changes within the range: "), "; ".join(flips),
                      ". Get client quotes before choosing.", class_="warn")

    @render.table
    def tco():
        r = result()
        rows = []
        for t, v in r["tiers"].items():
            row = {"Tier": t}
            for m in ("API / managed", "GPU-as-a-service", "Owned"):
                if m not in v["tco"]["base"]:
                    row[m] = "not allowed"
                elif v["sizing"]["gpus"] == 0:
                    row[m] = "-"
                else:
                    cell = " – ".join(money(v["tco"][s][m]) for s in ("low", "base", "high"))
                    row[m] = ("★ " if m == v["cheapest_mode"] else "") + cell
            row["$ per M tokens (base)"] = "-" if v["usd_per_m_eq_tokens"] is None else f'${v["usd_per_m_eq_tokens"]:.2f}'
            rows.append(row)
        return pd.DataFrame(rows)

    @render.table
    def demand():
        r = result()
        names = {a["uid"]: a["name"] for a in apps.get()}
        rows = [{"Application": names.get(x["id"], x["id"]), "Tier": x["tier"], "Share": f'{x["share"]:.0%}',
                 "Requests/day": fmt(x["sessions"]), "Tokens/day (in+out)": f'{sig2((x["daily_input"] + x["daily_output"]) / 1e6):g}M',
                 "Peak tokens/s": fmt(x["peak_eq_tps"], 0), "Model": x["model_class"]} for x in r["demand"]]
        rows += [{"Application": names.get(x["id"], x["id"]), "Tier": x["tier"], "Share": "100%",
                  "Requests/day": "-", "Tokens/day (in+out)": f'{fmt(x["gpu_hours_day"], 1)} GPU-h/day',
                  "Peak tokens/s": f'{x["peak_gpus"]:.2f} GPUs at peak' if x["mode"] == "Interactive" else "batch",
                  "Model": "non-LLM"} for x in r["nontoken"]]
        return pd.DataFrame(rows) if rows else None

    @render.download(filename="sovereign_ai_compute_results_raw.csv")
    def dl_results():
        r = result()
        rows = []
        for t, v in r["tiers"].items():
            kind = v["capacity"]["kind"]
            phys = kind in ("build", "rent")
            sz = v["sizing"]
            rows.append({
                "tier": t, "buying_option": v["cheapest_mode"], "capacity": kind, "step": v["step"], "grid": v["grid"],
                "hardware": v["hardware"] if phys else "",
                "servers": sz.get("servers", "") if kind == "build" else "",
                "gpus": sz["gpus"] if phys else "", "it_kw": sz["it_kw"] if phys else "",
                "facility_kw": sz["facility_mw"] * 1000 if kind == "build" else "",
                "racks": sz["racks"] if kind == "build" else "", "energy_mwh_year": sz["energy_mwh"] if kind == "build" else "",
                "utilisation": sz["utilisation"] if phys else "",
                "notional_gpus_if_api": sz["gpus"] if kind == "service" else "",
                **{f"cost_pv_{s_}": v["cost_range"][s_] for s_ in ("low", "base", "high")},
                **{f"owned_pv_{k}": x for k, x in
                   (v["detail"]["base"].get("Owned", {}).get("pv_breakdown", {}) if kind == "build" else {}).items()},
            })
        yield ("# Raw, unrounded figures for analysts. Planning-grade estimates: present to clients rounded, as ranges.\n"
               + pd.DataFrame(rows).to_csv(index=False))

    def scenario_dict():
        return {"version": "0.7", "iso": input.iso(), "ambition": input.ambition(), "grid": input.grid(), "hw": input.hw(),
                "speed": input.speed(), "finance": {"disc": input.disc(), "growth": input.growth(),
                                                    "decline": input.decline()},
                "class_to_tier": {c: input[f"map{c}"]() for c in (1, 2, 3, 4)},
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
        ui.update_select("hw", selected=sc.get("hw", "auto"))
        ui.update_radio_buttons("speed", selected=sc.get("speed", "base"))
        f = sc.get("finance", {})
        for k in ("disc", "growth", "decline"):
            if f.get(k) is not None:
                ui.update_numeric(k, value=f[k])
        for c, t in sc.get("class_to_tier", {}).items():
            ui.update_select(f"map{c}", selected=t)
        lst = [normalize_app(a) for a in sc.get("apps", [])]
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
