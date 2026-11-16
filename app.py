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
from engine.archetypes import (EXAMPLE_PORTFOLIO, build_profile, is_llm, load_archetypes, reference_sizes,
                               volume_warning)

CAT = load_catalogue()
D = load_defaults()
ARCH = load_archetypes()
COUNTRIES = load_countries()
API_PRICES, API_PROV = load_api_prices(D)
SRC = {s["id"]: s for s in CAT["sources"]}

CLASS_LABELS = {1: "1 · Public", 2: "2 · Internal", 3: "3 · Confidential", 4: "4 · Restricted"}
SCEN = {"Low": "Cautious", "Base": "Expected", "High": "Aggressive"}

type_choices = {}
for a in ARCH.values():
    type_choices.setdefault(a["group"], {})[a["id"]] = a["label"]
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
.empty { padding:28px; text-align:center; color:var(--muted); }
.warn { background:#fffbeb; border:1px solid #fde68a; border-radius:8px; padding:10px 14px; font-size:.88rem; margin-bottom:12px; }
"""


def fmt(x, d=0):
    return "-" if x is None else f"{x:,.{d}f}"


def money(x):
    if x is None:
        return "-"
    if abs(x) >= 1e6:
        return f"${x / 1e6:,.1f}M"
    if abs(x) >= 1e3:
        return f"${x / 1e3:,.0f}k"
    return f"${x:,.0f}"


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
    ui.output_ui("kpis"),
    ui.card(ui.card_header("Where the compute should run"), ui.output_table("ladder")),
    ui.card(ui.card_header("10-year cost by buying option: present value, Low – Base – High (USD)"), ui.output_ui("tco_flag"),
            ui.output_table("tco")),
    ui.card(ui.card_header("Demand by application"), ui.output_table("demand")),
    ui.layout_columns(ui.download_button("dl_results", "Export results (CSV)"),
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

app_ui = ui.page_navbar(
    setup_panel, apps_panel, results_panel, evidence_panel,
    title="Sovereign AI Compute Planner",
    header=ui.tags.style(CSS),
    footer=ui.div("v0.3 draft · planning-grade estimates · every default is sourced in the Evidence tab",
                  class_="hint", style="text-align:center;padding:16px"),
    fillable=False,
)


# ------------------------------------------------------------------ server
def server(input, output, session):
    apps = reactive.value([])

    # ---- add / remove

    @render.ui
    def a_type_hint():
        t = ARCH[input.a_type()]
        ev = t["evidence"].get("rate") or t["evidence"].get("gpu", "")
        ref = reference_sizes(country()[0])
        bits = []
        if ref["population"]:
            bits.append(f'population {ref["population"]:,.0f}')
        if ref["civil_servants"]:
            bits.append(f'civil servants {ref["civil_servants"]:,.0f}' + (" (rough estimate)" if ref["civil_servants_estimated"] else ""))
        return ui.div(ui.p(ev, class_="hint", style="margin-top:8px"),
                      ui.p("Country reference: " + " · ".join(bits), class_="hint") if bits else None)

    @reactive.effect
    @reactive.event(input.a_type)
    def _default_class():
        t = ARCH[input.a_type()]
        ui.update_select("a_class", selected=str(t["data_class"]))
        ui.update_numeric("a_volume", label=t["unit_label"])
        if is_llm(t) and t["unit"] == "users":
            ui.update_numeric("a_rate", label=f'Requests per person per day (default {t["rate"]["base"]:g} in Base)')
        else:
            ui.update_numeric("a_rate", label="Requests per person per day (not used for this type)", value=None)

    @reactive.effect
    @reactive.event(input.add)
    def _add():
        t = ARCH[input.a_type()]
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
                   traffic_split=split)
        w = volume_warning(new, country()[0], ARCH)
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
            t = ARCH[a["type"]]
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
                             if (w := volume_warning(a, country()[0], ARCH)) else [])),
                ui.tags.td(f'{fmt(a["volume"])}', ui.br(), ui.span(t["unit_label"], class_="hint")),
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
        notes = []
        g = input.grid()
        if g == "reliable":
            c["outages_per_month"] = 0
        elif g == "weak":
            c["outages_per_month"] = 10
        else:
            src = c.get("_sources", {}).get("outages_per_month", "")
            yr = re.findall(r"(19|20)(\d\d)", src)
            year = int("".join(yr[-1])) if yr else None
            if c.get("outages_per_month") is None:
                c["outages_per_month"] = None
                notes.append("No outage data for this country: grid shown as unknown and air-cooled hardware assumed. Set it in Setup.")
            elif year and year < 2020:
                c["outages_per_month"] = None
                notes.append(f"Outage data is from {year}: treated as unknown. Set grid reliability in Setup.")
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
        o = COUNTRIES[input.iso()].get("outages_per_month")
        bits.append(f"outages {o:g}/month" if o is not None else "outages: no data")
        return ui.p(" · ".join(bits), class_="hint")

    def quotes():
        q = {}
        for key, inp in [("gpu_hour_usd", "q_gpu_hour"), ("gpu_capex_usd", "q_gpu_capex"),
                         ("facility_capex_usd_per_mw_it", "q_fac")]:
            v = num(input[inp]())
            if v:
                q[key] = v
        return q

    @reactive.calc
    def result():
        c, _ = country()
        p = build_profile(c, input.ambition(), apps.get(), ARCH,
                          {cl: input[f"map{cl}"]() for cl in (1, 2, 3, 4)}, quotes(), input.hw())
        p.speed = input.speed()
        pct = lambda v: (num(v) or 0) / 100
        p.finance = {"discount_rate": pct(input.disc()), "demand_growth": pct(input.growth()),
                     "price_decline": pct(input.decline())}
        return run(p, CAT, D, API_PRICES)

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
        lows = sorted({ARCH[a["type"]]["label"] for a in apps.get() if ARCH[a["type"]]["confidence"]["volume"] == "Low"
                       and not a.get("rate_override") and ARCH[a["type"]]["unit"] == "users"})
        if lows:
            msgs.append("Usage rate is a weak assumption for: " + "; ".join(lows) +
                        ". Set requests per person per day under Advanced if the client knows it.")
        if quotes():
            msgs.append("Client quotes in use: " + ", ".join(quotes()))
        return ui.div(ui.tags.ul(*[ui.tags.li(m) for m in msgs], style="margin:0"), class_="warn") if msgs else None

    @render.ui
    def kpis():
        r = result()
        t = r["totals"]
        lo = sum((v["cost_range"]["low"] or 0) for v in r["tiers"].values())
        hi = sum((v["cost_range"]["high"] or 0) for v in r["tiers"].values())
        local = sum(v["sizing"]["facility_mw"] for k, v in r["tiers"].items() if k in ("T3", "T4"))
        return ui.layout_columns(
            kpi("GPUs (all tiers)", fmt(t["gpus"]), f'{SCEN[input.ambition()]} scenario'),
            kpi("Facility power", f'{t["facility_mw"]:.2f} MW', f"of which in-country sovereign: {local:.2f} MW"),
            kpi("10-year cost (present value)", money(t["cost"]), f"range {money(lo)} – {money(hi)} · discount {num(input.disc()) or 0:g}%"),
            col_widths=[4, 4, 4])

    @render.table
    def ladder():
        r = result()
        return pd.DataFrame([{
            "Tier": f'{t} · {D["tiers"][t]["name"]}', "GPUs": fmt(v["sizing"]["gpus"]),
            "Facility (MW)": f'{v["sizing"]["facility_mw"]:.2f}', "Utilisation": f'{v["sizing"]["utilisation"]:.0%}',
            "Apps / pooling": f'{v["sizing"]["n_apps"]} / D {v["sizing"]["diversity"]:.2f}' if v["sizing"]["n_apps"] else "-",
            "Hardware": v["hardware"] if v["sizing"]["gpus"] else "-",
            "Cheapest option": v["cheapest_mode"], "Grid": v["grid"], "Recommended step": v["step"],
        } for t, v in r["tiers"].items()])

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
                 "Requests/day": fmt(x["sessions"]), "Tokens/day (in+out)": fmt(x["daily_input"] + x["daily_output"]),
                 "Peak tokens/s": fmt(x["peak_eq_tps"], 0), "Model": x["model_class"]} for x in r["demand"]]
        rows += [{"Application": names.get(x["id"], x["id"]), "Tier": x["tier"], "Share": "100%",
                  "Requests/day": "-", "Tokens/day (in+out)": f'{fmt(x["gpu_hours_day"], 1)} GPU-h/day',
                  "Peak tokens/s": f'{x["peak_gpus"]:.2f} GPUs at peak' if x["mode"] == "Interactive" else "batch",
                  "Model": "non-LLM"} for x in r["nontoken"]]
        return pd.DataFrame(rows) if rows else None

    @render.download(filename="sovereign_ai_compute_results.csv")
    def dl_results():
        r = result()
        df = pd.DataFrame([{"tier": t, "step": v["step"], "mode": v["cheapest_mode"], "grid": v["grid"],
                            "hardware": v["hardware"],
                            **{k: v["sizing"][k] for k in ("gpus", "it_kw", "facility_mw", "racks", "energy_mwh", "utilisation")},
                            **{f"cost_{s}": v["cost_range"][s] for s in ("low", "base", "high")}}
                           for t, v in r["tiers"].items()])
        yield df.to_csv(index=False)

    @render.download(filename="scenario.json")
    def dl_scenario():
        yield json.dumps({"iso": input.iso(), "ambition": input.ambition(), "grid": input.grid(), "hw": input.hw(),
                          "speed": input.speed(), "finance": {"disc": input.disc(), "growth": input.growth(),
                                                              "decline": input.decline()},
                          "class_to_tier": {c: input[f"map{c}"]() for c in (1, 2, 3, 4)},
                          "quotes": quotes(), "apps": apps.get()}, indent=1)

    @reactive.effect
    @reactive.event(input.ul_scenario)
    def _load():
        f = input.ul_scenario()
        if not f:
            return
        sc = json.loads(open(f[0]["datapath"]).read())
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
        apps.set(sc.get("apps", []))

    # ---- evidence
    @render.ui
    def evidence():
        blocks = []
        for t in ARCH.values():
            if is_llm(t):
                facts = (f'{t["unit_label"]} × {t["rate"]["low"]:g} / {t["rate"]["base"]:g} / {t["rate"]["high"]:g} requests per day '
                         f'(Low / Base / High) · per call {t["isl"]:,} in + {t["system_prompt_tokens"]:,} system, '
                         f'{t["osl"]:,} out, {t["reasoning_tokens"]:,} reasoning · {t["agent_steps"]} call(s) per task · '
                         f'model {t["model_class"]}')
            else:
                facts = f'{t["gpu_seconds_per_unit"]:g} GPU-seconds per unit · {t["mode"]}'
            blocks.append(ui.div(
                ui.tags.b(t["label"]), " ",
                ui.span(f'volume {t["confidence"]["volume"]}', class_=f'hint conf-{t["confidence"]["volume"]}'), " · ",
                ui.span(f'size {t["confidence"]["tokens"]}', class_=f'hint conf-{t["confidence"]["tokens"]}'),
                ui.p(facts, class_="hint", style="margin:2px 0"),
                ui.tags.ul(*[ui.tags.li(ui.tags.i(k), ": ", v) for k, v in t["evidence"].items()], class_="hint"),
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
                                       class_="hint") for s in CAT["sources"]])


app = App(app_ui, server)
