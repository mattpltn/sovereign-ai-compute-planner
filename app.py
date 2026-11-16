"""Sovereign AI Compute Planner: Shiny for Python front end.

Run locally:   shiny run app.py
Posit Connect: rsconnect deploy shiny . --entrypoint app:app
"""
from __future__ import annotations

import json
from copy import deepcopy

import pandas as pd
from shiny import App, reactive, render, ui

from engine import (Profile, TIERS, load_api_prices, load_catalogue, load_countries,
                    load_defaults, run)

CAT = load_catalogue()
D = load_defaults()
COUNTRIES = load_countries()
API_PRICES, API_PROV = load_api_prices(D)
HW_IDS = {"auto": "Auto (from grid and size)", **{h["id"]: f'{h["id"]}: {h["name"]}' for h in CAT["hardware"]}}
SRC = {s["id"]: s for s in CAT["sources"]}

# Fallbacks when the synced snapshot lacks a value. Always shown to the user.
FALLBACK = {
    "internet_share": (0.5, "fallback: 50%"),
    "civil_servants": (None, "fallback: 2% of population"),
    "outages_per_month": (0, "fallback: 0 (unknown, grid treated as reliable)"),
    "egdi": (None, "missing: no EGDI adjustment"),
}


def country_record(iso: str, overrides: dict) -> tuple[dict, list[str]]:
    c = dict(COUNTRIES[iso])
    notes = []
    for k, (v, msg) in FALLBACK.items():
        if c.get(k) is None:
            if k == "civil_servants":
                c[k] = 0.02 * c.get("population", 0)
            elif v is not None:
                c[k] = v
            notes.append(f"{k}: {msg}")
    for k, v in overrides.items():
        if v is not None:
            c[k] = v
            c.setdefault("_sources", {})[k] = "user override"
    return c, notes


def fmt(x, d=0):
    return "-" if x is None else f"{x:,.{d}f}"


def usd(x):
    return "-" if x is None else f"${x:,.0f}"


APP_COLS = ["id", "name", "include", "stage", "data_class", "model_class", "users_override", "traffic_split"]
NT_COLS = ["id", "name", "include", "mode", "units_per_day", "unit", "data_class"]


def apps_df():
    rows = []
    for a in CAT["use_cases"]:
        rows.append({**{k: a.get(k) for k in APP_COLS}, "users_override": "", "traffic_split": ""})
    return pd.DataFrame(rows, columns=APP_COLS)


def nt_df():
    return pd.DataFrame([{k: w.get(k) for k in NT_COLS} for w in CAT["nontoken"]], columns=NT_COLS)


def parse_split(s: str) -> dict | None:
    s = (s or "").strip()
    if not s:
        return None
    out = {}
    for part in s.split(","):
        k, v = part.split(":")
        out[int(k)] = float(v)
    return out


def num(x):
    try:
        if x is None or (isinstance(x, str) and not x.strip()):
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


iso_choices = {k: v.get("name", k) for k, v in sorted(COUNTRIES.items(), key=lambda kv: kv[1].get("name", ""))}

app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.input_select("iso", "Country", iso_choices, selected="XEX"),
        ui.input_radio_buttons("ambition", "Ambition (adoption scenario)",
                               {"Low": "Cautious", "Base": "Expected", "High": "Aggressive"}, selected="Base"),
        ui.input_select("hw", "Hardware profile", HW_IDS, selected="auto"),
        ui.hr(),
        ui.download_button("dl_scenario", "Save scenario (JSON)"),
        ui.input_file("ul_scenario", "Load scenario", accept=[".json"]),
        ui.download_button("dl_results", "Export results (CSV)"),
        width=300,
    ),
    ui.navset_tab(
        ui.nav_panel(
            "1. Applications",
            ui.markdown(
                "Tick the applications in scope and set **stage** (Pilot / Production) and **data class** (1 public, "
                "2 internal, 3 confidential, 4 restricted). Placement follows the highest data class of each application. "
                "Optional **traffic_split** routes part of an application's traffic to another class, e.g. `1:0.9,3:0.1`. "
                "Optional **users_override** replaces the estimated user count. Token shapes and adoption curves are "
                "catalogue defaults (analyst assumptions, see Sources)."),
            ui.output_data_frame("apps"),
            ui.h5("Non-token GPU workloads (biometrics, OCR, speech, vision, fine-tuning)"),
            ui.output_data_frame("nts"),
        ),
        ui.nav_panel(
            "2. Data class → tier",
            ui.markdown("Set once per country from its data protection and classification rules. "
                        "Default follows the World Bank data classification approach [S14]."),
            *[ui.input_select(f"map{c}", f"Data class {c}",
                              {t: f'{t}: {D["tiers"][t]["name"]}' for t in TIERS}, selected=D["class_to_tier"][c])
              for c in (1, 2, 3, 4)],
            ui.output_table("tier_rules"),
        ),
        ui.nav_panel(
            "3. Client quotes (optional)",
            ui.markdown("Leave blank to use the default cost **range**. A quoted value replaces the range and is "
                        "labelled *client quote* in the results."),
            ui.layout_columns(
                ui.input_text("q_gpu_hour", "GPU-as-a-service ($/GPU-hour)"),
                ui.input_text("q_gpu_capex", "GPU capex, server share ($/GPU)"),
                ui.input_text("q_fac", "Facility capex ($ per MW IT)"),
                ui.input_text("q_kwh", "Electricity tariff ($/kWh)"),
                col_widths=[3, 3, 3, 3]),
            ui.layout_columns(
                *[ui.input_text(f"q_api_{c}_{io}", f"API {c} {io} ($/M tokens)")
                  for c in "SML" for io in ("input", "output")],
                col_widths=[2] * 6),
        ),
        ui.nav_panel(
            "Results",
            ui.output_ui("warnings"),
            ui.output_ui("headline"),
            ui.h5("Compute ladder"),
            ui.output_table("ladder"),
            ui.h5("10-year cost range of the cheapest eligible mode (undiscounted, USD)"),
            ui.output_table("tco"),
            ui.h5("Demand by application"),
            ui.output_table("demand"),
        ),
        ui.nav_panel(
            "Sources & assumptions",
            ui.h5("Country inputs and provenance"),
            ui.output_table("country_tbl"),
            ui.h5("Global defaults"),
            ui.output_table("defaults_tbl"),
            ui.p(f"API prices: {API_PROV}"),
            ui.h5("Sources"),
            ui.output_ui("sources"),
        ),
    ),
    title="Sovereign AI Compute Planner (v0.1, draft)",
)


def server(input, output, session):
    loaded = reactive.value(None)

    @render.data_frame
    def apps():
        df = apps_df()
        sc = loaded.get()
        if sc:
            df = pd.DataFrame(sc["apps"], columns=APP_COLS)
        return render.DataGrid(df, editable=True, height="420px")

    @render.data_frame
    def nts():
        df = nt_df()
        sc = loaded.get()
        if sc:
            df = pd.DataFrame(sc["nontoken"], columns=NT_COLS)
        return render.DataGrid(df, editable=True)

    def quotes():
        q = {}
        for key, inp in [("gpu_hour_usd", "q_gpu_hour"), ("gpu_capex_usd", "q_gpu_capex"),
                         ("facility_capex_usd_per_mw_it", "q_fac"), ("electricity_usd_kwh", "q_kwh")]:
            v = num(input[inp]())
            if v:
                q[key] = v
        api = {c: {io: num(input[f"q_api_{c}_{io}"]()) for io in ("input", "output")} for c in "SML"}
        if all(api[c][io] for c in "SML" for io in ("input", "output")):
            q["api_prices"] = api
        return q

    @reactive.calc
    def profile():
        country, notes = country_record(input.iso(), {})
        edited = apps.data_view()
        apps_list = []
        by_id = {a["id"]: a for a in CAT["use_cases"]}
        for _, r in edited.iterrows():
            a = deepcopy(by_id[r["id"]])
            a["include"] = int(num(r["include"]) or 0)
            a["stage"] = "Pilot" if str(r["stage"]).strip().lower().startswith("p") and \
                str(r["stage"]).strip().lower() != "production" else "Production"
            a["data_class"] = int(num(r["data_class"]) or a["data_class"])
            a["model_class"] = str(r["model_class"]).strip().upper() or a["model_class"]
            a["users_override"] = num(r["users_override"])
            try:
                a["traffic_split"] = parse_split(str(r["traffic_split"]))
            except ValueError:
                notes.append(f'{a["id"]}: traffic_split not understood, ignored')
            apps_list.append(a)
        nt_by = {w["id"]: w for w in CAT["nontoken"]}
        nt_list = []
        for _, r in nts.data_view().iterrows():
            w = deepcopy(nt_by[r["id"]])
            w["include"] = int(num(r["include"]) or 0)
            w["mode"] = "Batch" if str(r["mode"]).strip().lower().startswith("b") else "Interactive"
            w["units_per_day"] = num(r["units_per_day"]) or 0
            w["data_class"] = int(num(r["data_class"]) or w["data_class"])
            nt_list.append(w)
        p = Profile(country=country, ambition=input.ambition(), apps=apps_list, nontoken=nt_list,
                    class_to_tier={c: input[f"map{c}"]() for c in (1, 2, 3, 4)},
                    quotes=quotes(), hardware_choice=input.hw())
        return p, notes

    @reactive.calc
    def result():
        p, _ = profile()
        return run(p, CAT, D, API_PRICES)

    @render.ui
    def warnings():
        p, notes = profile()
        r = result()
        msgs = list(notes)
        if p.country.get("_sources", {}).get("all", "").startswith("fictional"):
            msgs.append("Example country (fictional). Pick a real country after the first data sync.")
        if API_PROV.startswith("fallback"):
            msgs.append("API prices are fallback placeholders until the OpenRouter sync runs.")
        for x in r["demand"]:
            if x["above_ceiling"] and x["share"] == 1:
                msgs.append(f'{x["id"]}: tokens per user per day above the human ceiling [S24]. Fine for agents; check otherwise.')
        if p.quotes:
            msgs.append("Client quotes in use: " + ", ".join(p.quotes))
        if not msgs:
            return None
        return ui.div(ui.tags.ul(*[ui.tags.li(m) for m in msgs]), class_="alert alert-warning")

    @render.ui
    def headline():
        t = result()["totals"]
        return ui.layout_columns(
            ui.value_box("Total GPUs", fmt(t["gpus"])),
            ui.value_box("Facility power", f'{t["facility_mw"]:.2f} MW'),
            ui.value_box("10-year cost, cheapest eligible", usd(t["cost"])),
        )

    @render.table
    def ladder():
        r = result()
        return pd.DataFrame([{
            "Tier": t, "Description": D["tiers"][t]["name"], "Hardware": v["hardware"],
            "GPUs": fmt(v["sizing"]["gpus"]), "IT load (kW)": fmt(v["sizing"]["it_kw"], 1),
            "Facility (MW)": f'{v["sizing"]["facility_mw"]:.2f}', "Utilisation": f'{v["sizing"]["utilisation"]:.0%}',
            "Cheapest eligible mode": v["cheapest_mode"], "Grid check": v["grid"], "Recommended step": v["step"],
        } for t, v in r["tiers"].items()])

    @render.table
    def tco():
        r = result()
        rows = []
        for t, v in r["tiers"].items():
            row = {"Tier": t, "Cheapest mode": v["cheapest_mode"],
                   "Low": usd(v["cost_range"]["low"]), "Base": usd(v["cost_range"]["base"]),
                   "High": usd(v["cost_range"]["high"]),
                   "$ per M eq. tokens (base)": "-" if v["usd_per_m_eq_tokens"] is None else f'${v["usd_per_m_eq_tokens"]:.2f}'}
            for m in ("API / managed", "GPU-as-a-service", "Owned"):
                row[f"{m} (base)"] = usd(v["tco"]["base"].get(m)) if m in v["tco"]["base"] else "Not eligible"
            rows.append(row)
        return pd.DataFrame(rows)

    @render.table
    def demand():
        r = result()
        return pd.DataFrame([{
            "ID": x["id"], "Application": x["name"], "Class": x["data_class"], "Tier": x["tier"],
            "Share": f'{x["share"]:.0%}', "Users": fmt(x["users"]), "Model": x["model_class"],
            "Daily tokens (in+out)": fmt(x["daily_input"] + x["daily_output"]),
            "Peak eq. tok/s": fmt(x["peak_eq_tps"], 1),
        } for x in r["demand"] if x["users"] > 0])

    @render.table
    def tier_rules():
        return pd.DataFrame([{"Tier": t, "Description": v["name"], "API": "yes" if v["api"] else "no",
                              "GPU-as-a-service": "yes" if v["gpuaas"] else "no", "Owned": "yes" if v["owned"] else "no"}
                             for t, v in D["tiers"].items()])

    @render.table
    def country_tbl():
        p, _ = profile()
        c = p.country
        src = c.get("_sources", {})
        keys = ["population", "internet_share", "civil_servants", "egdi", "outages_per_month", "electricity_usd_kwh"]
        return pd.DataFrame([{"Input": k, "Value": c.get(k), "Source": src.get(k, src.get("all", "fallback / default"))}
                             for k in keys])

    @render.table
    def defaults_tbl():
        rows = []
        for k, v in D.items():
            if isinstance(v, dict) and "value" in v:
                rows.append({"Parameter": k, "Value": v["value"], "Source": v.get("source"), "Note": v.get("note", "")})
        for k, v in D["costs"].items():
            rows.append({"Parameter": k, "Value": f'{v["low"]} / {v["base"]} / {v["high"]}', "Source": v.get("source"),
                         "Note": "low / base / high. " + v.get("note", "")})
        return pd.DataFrame(rows)

    @render.ui
    def sources():
        return ui.tags.ol(*[ui.tags.li(ui.tags.b(s["id"]), f' {s["title"]}, {s["publisher"]}. ',
                                       ui.tags.a(s["url"], href=s["url"], target="_blank"), f' Used for: {s["used_for"]}')
                            for s in CAT["sources"]])

    @render.download(filename="scenario.json")
    def dl_scenario():
        sc = {"iso": input.iso(), "ambition": input.ambition(), "hw": input.hw(),
              "apps": apps.data_view().to_dict("records"), "nontoken": nts.data_view().to_dict("records"),
              "class_to_tier": {c: input[f"map{c}"]() for c in (1, 2, 3, 4)}, "quotes": quotes()}
        yield json.dumps(sc, indent=1, default=str)

    @reactive.effect
    @reactive.event(input.ul_scenario)
    def _load():
        f = input.ul_scenario()
        if not f:
            return
        sc = json.loads(open(f[0]["datapath"]).read())
        ui.update_select("iso", selected=sc.get("iso", "XEX"))
        ui.update_radio_buttons("ambition", selected=sc.get("ambition", "Base"))
        ui.update_select("hw", selected=sc.get("hw", "auto"))
        for c, t in sc.get("class_to_tier", {}).items():
            ui.update_select(f"map{c}", selected=t)
        loaded.set(sc)

    @render.download(filename="sovereign_ai_compute_results.csv")
    def dl_results():
        r = result()
        df = pd.DataFrame([{**{"tier": t, "step": v["step"], "mode": v["cheapest_mode"], "grid": v["grid"],
                               "hardware": v["hardware"]},
                            **{k: v["sizing"][k] for k in ("gpus", "it_kw", "facility_mw", "racks", "energy_mwh", "utilisation")},
                            **{f"cost_{s}": v["cost_range"][s] for s in ("low", "base", "high")}}
                           for t, v in r["tiers"].items()])
        yield df.to_csv(index=False)

app = App(app_ui, server)
