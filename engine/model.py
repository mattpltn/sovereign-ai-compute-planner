"""Sovereign AI Compute Planner engine.

Pure functions, no UI. Mirrors Sovereign_AI_Compute_Planner_v0.1.xlsx formula by formula.
Flow: profile -> users -> tokens (L1-L3) -> peak tok/s -> placement (tier) -> GPUs -> MW -> TCO -> ladder.
"""
from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass, field

TIERS = ["T1", "T2", "T3", "T4"]
CLASSES = ["S", "M", "L"]
SCENARIOS = ("low", "base", "high")


def _roundup(x: float) -> int:
    return int(math.ceil(x - 1e-9)) if x > 0 else 0


@dataclass
class Profile:
    """What the user provides. Everything else is fetched or defaulted."""
    country: dict                       # one record from data/snapshots/countries.json
    ambition: str = "Base"              # Low / Base / High (adoption scenario)
    apps: list = field(default_factory=list)          # use case dicts (catalogue entries, edited)
    nontoken: list = field(default_factory=list)      # non-token workload dicts
    class_to_tier: dict = field(default_factory=dict) # {1:"T1",...}
    quotes: dict = field(default_factory=dict)        # client quotes overriding cost ranges
    hardware_choice: str = "auto"       # "auto" or a hardware id applied to all tiers
    speed: str = "base"                 # response speed target -> throughput point: low (fast) / base / high (relaxed)
    finance: dict = field(default_factory=dict)       # discount_rate, demand_growth, price_decline (fractions)
    local_gpu_provider: bool = True     # is there an in-country GPU-as-a-service provider (needed to rent in T3)?
    shared_sovereign_site: bool = True  # Confidential (T3) and Restricted (T4) share one secure site


# ----------------------------------------------------------------- Layers 0-3
def users(app: dict, country: dict, ambition: str, d: dict) -> float:
    if not app.get("include", 1):
        return 0.0
    if app.get("users_override"):
        return float(app["users_override"])
    if app["stage"] == "Pilot":
        return float(app["pilot_users"])
    drv = app["driver"]
    if drv == "Population":
        base = country["population"] * country["internet_share"]
    elif drv == "Civil servants":
        base = country["civil_servants"]
    else:
        base = app["fixed_base"]
    adopt = {"Low": app["adoption_low"], "High": app["adoption_high"]}.get(ambition, app["adoption_base"])
    adj = 1.0
    if app.get("citizen_facing") and country.get("egdi"):
        adj = min(1.5, country["egdi"] / d["global_egdi_average"]["value"])
    return base * app["eligible_share"] * adopt * adj


def app_demand(app: dict, country: dict, ambition: str, d: dict) -> dict:
    u = users(app, country, ambition, d)
    sessions = u * app["tasks_per_user_day"]
    k = app["agent_steps"] * app["retry"]
    in_task = (app["isl"] + app["system_prompt_tokens"]) * k
    cached_task = app["system_prompt_tokens"] * app["cache_hit"] * k
    out_task = (app["osl"] + app["reasoning_tokens"]) * k
    d_in, d_cached, d_out = sessions * in_task, sessions * cached_task, sessions * out_task
    eq = d_out + (d_in - d_cached) * d["prefill_weight"]["value"]
    days = float(app.get("active_days_per_year") or 365)   # rates are per active (working / school) day
    peak = eq * app["peak_share"] / (app["peak_window_h"] * 3600) * app["burst"] * app["sla_headroom"] * app["seasonal"]
    tpud = (d_in + d_out) / u if u else 0.0
    return dict(
        id=app["id"], name=app["name"], users=u, sessions=sessions,
        daily_input=d_in, daily_cached=d_cached, daily_output=d_out, daily_eq=eq,
        tokens_per_user_day=tpud,
        above_ceiling=tpud > d["tokens_per_user_day_ceiling"]["value"],
        avg_eq_tps=eq * days / 365 / 86400, peak_eq_tps=peak, model_class=app["model_class"], active_days=days,
        annual_uncached_input_m=(d_in - d_cached) * days / 1e6,
        annual_cached_input_m=d_cached * days / 1e6,
        annual_output_m=d_out * days / 1e6, annual_eq_m=eq * days / 1e6,
    )


def split_by_class(app: dict) -> dict:
    """High-water mark by default; optional traffic split {data_class: share}."""
    split = app.get("traffic_split")
    if not split:
        return {int(app["data_class"]): 1.0}
    tot = sum(split.values())
    return {int(k): v / tot for k, v in split.items() if v > 0}


def demand_rows(p: Profile, d: dict) -> list[dict]:
    """One row per (app, data class) after the optional split, with its tier."""
    rows = []
    for app in p.apps:
        base = app_demand(app, p.country, p.ambition, d)
        for cls, share in split_by_class(app).items():
            r = {k: (v * share if isinstance(v, (int, float)) and not isinstance(v, bool)
                     and k not in ("tokens_per_user_day",) else v) for k, v in base.items()}
            r["data_class"] = cls
            r["share"] = share
            r["tier"] = p.class_to_tier[cls]
            rows.append(r)
    return rows


def nontoken_rows(p: Profile, d: dict) -> list[dict]:
    der = d["production_derating"]["value"]
    out = []
    for w in p.nontoken:
        inc = w.get("include", 1)
        gpu_h = w["units_per_day"] * w["gpu_seconds_per_unit"] / 3600 / der if inc else 0.0
        peak = 0.0
        if inc and w["mode"] == "Interactive":
            peak = (w["units_per_day"] * w["gpu_seconds_per_unit"] * w["peak_share"]
                    / (w["peak_window_h"] * 3600) * w["burst"] / der)
        out.append(dict(id=w["id"], name=w["name"], mode=w["mode"], gpu_hours_day=gpu_h,
                        peak_gpus=peak, tier=p.class_to_tier[int(w["data_class"])]))
    return out


# ----------------------------------------------------------------- Layer 4
def diversity(n: int, d: dict) -> float:
    """Pooling factor for n applications sharing a tier.

    'fixed' mode (v0.1): constant factor. 'scaled' mode: 1 for a single application, then
    D(n) = D_min + (1 - D_min) / sqrt(n): independent peaks add up roughly with the square root of n.
    """
    if d.get("diversity_mode", {}).get("value", "scaled") == "fixed":
        return d["diversity_factor"]["value"]
    if n <= 1:
        return 1.0
    dmin = d["diversity_factor_min"]["value"]
    return dmin + (1 - dmin) / math.sqrt(n)


def facility_for(country: dict, hw: dict, d: dict, scenario: str = "base") -> dict:
    """PUE and facility capex per MW of IT for this country and cooling type, with provenance."""
    if d.get("facility_mode", {}).get("value", "country") == "flat" or "facility" not in d:
        return dict(pue=d["pue"]["value"], capex_per_mw=d["costs"]["facility_capex_usd_per_mw_it"][scenario],
                    pue_src="flat default", capex_src="flat default")
    f = d["facility"]
    region = (country.get("region") or "").strip()
    pr = f["pue_air_by_region"].get(region)
    pue_air = (country.get("pue_override") or (pr["value"] if pr else f["pue_air_default"]["value"]))
    pue_src = ("user override" if country.get("pue_override")
               else f"{region}: {pr['note']}" if pr else "global average (no region)")
    liquid = hw.get("cooling", "Air").lower().startswith("liquid")
    pue = 1 + (pue_air - 1) * f["liquid_overhead_factor"]["value"] if liquid and not country.get("pue_override") else pue_air
    iso = country.get("iso3")
    mk = f["capex_usd_per_w_by_country"].get(iso) if iso else None
    rg = f["capex_usd_per_w_by_region"].get(region)
    if mk:
        per_w, capex_src = mk["value"], f'{mk["market"]} {mk["year"]} (Turner & Townsend)'
    elif rg:
        per_w, capex_src = rg["value"], f"{region} proxy: {rg['note']}"
    else:
        per_w, capex_src = f["capex_usd_per_w_default"]["value"], "global default"
    mult = f["capex_range"][scenario] * (f["liquid_capex_multiplier"][scenario] if liquid else 1.0)
    return dict(pue=pue, pue_air=pue_air, capex_per_mw=per_w * 1e6 * mult, pue_src=pue_src, capex_src=capex_src,
                liquid=liquid)


def throughput(hw: dict, cls: str, speed: str) -> tuple[float, bool]:
    """Tokens/s per GPU for a model class at the response-speed point, and whether it is a measured figure."""
    v = hw["tokens_per_s_per_gpu"][cls]
    measured = cls in hw.get("measured", [])
    if isinstance(v, dict):
        return float(v[speed]), measured
    return float(v), measured


def size_tier(tier: str, dem: list, nt: list, hw: dict, d: dict, speed: str = "base", country: dict | None = None,
              tps_mult: float = 1.0) -> dict:
    der = d["production_derating"]["value"]
    pue = facility_for(country or {}, hw, d)["pue"]
    idle = d["idle_power_fraction"]["value"]
    rows = [r for r in dem if r["tier"] == tier and r["sessions"] > 0]
    ntr = [w for w in nt if w["tier"] == tier and w["gpu_hours_day"] > 0]
    n_apps = len({r["id"] for r in rows} | {w["id"] for w in ntr if w["mode"] == "Interactive"})
    D = diversity(n_apps, d)
    # Effective throughput: measured figures are used as is; derived or placeholder figures are derated.
    eff = {}
    for c in CLASSES:
        tps, measured = throughput(hw, c, speed)
        eff[c] = (tps if measured else tps * der) * tps_mult
    peak = {c: sum(r["peak_eq_tps"] for r in rows if r["model_class"] == c) * D for c in CLASSES}
    avg = {c: sum(r["avg_eq_tps"] for r in rows if r["model_class"] == c) for c in CLASSES}
    llm_need = sum(peak[c] / eff[c] for c in CLASSES)
    nt_need = sum(w["peak_gpus"] for w in ntr) * D
    gpus_llm, gpus_nt = _roundup(llm_need), _roundup(nt_need)
    busy = (sum(avg[c] / eff[c] for c in CLASSES) * 24
            + sum(w["gpu_hours_day"] for w in ntr if w["mode"] == "Interactive"))
    batch = sum(w["gpu_hours_day"] for w in ntr if w["mode"] == "Batch")
    base = gpus_llm + gpus_nt
    idle_h = max(0.0, base * 24 - busy)
    extra_need = max(0.0, batch - idle_h) / 24
    extra = _roundup(extra_need)
    need = llm_need + nt_need + extra_need          # fractional GPUs actually needed
    below = (not rows) and 0 < need < d["gpu_threshold"]["value"] if "gpu_threshold" in d else False
    if below:                                      # tiny non-LLM load: no dedicated GPU
        gpus_llm = gpus_nt = extra = 0
    total = gpus_llm + gpus_nt + extra
    util = min(1.0, (busy + batch) / (total * 24)) if total else 0.0
    it_kw = total * hw["kw_per_gpu"]
    return dict(
        tier=tier, hardware=hw["id"], n_apps=n_apps, diversity=D, eff_tps=eff, peak_eq_tps=peak, gpus_llm=gpus_llm,
        gpus_nontoken=gpus_nt, gpus_batch_extra=extra, gpus=total, gpu_need=need, below_threshold=below,
        utilisation=util, it_kw=it_kw, pue=pue, facility_mw=it_kw * pue / 1000,
        racks=_roundup(it_kw / hw["rack_kw"]) if it_kw else 0,
        energy_mwh=it_kw * (idle + (1 - idle) * util) * pue * 8760 / 1000,
        annual_eq_m=sum(r["annual_eq_m"] for r in rows),
    )


def grid_weak(country: dict, d: dict):
    """True / False, or None when unknown.

    Outages per month (Enterprise Surveys) decide when available. Otherwise the share of firms that
    experienced outages is used as a fallback signal.
    """
    o = country.get("outages_per_month")
    if o is not None:
        return o > d["weak_grid_outages_threshold"]["value"]
    s = country.get("firms_with_outages_share")
    if s is not None:
        return s >= d["weak_grid_firm_share_threshold"]["value"]
    return None


def candidate_hardware(p: Profile, hardware: list, it_mw_if_air: float, d: dict) -> list:
    """Profiles allowed for a tier. Weak grid or small load: air-cooled only."""
    if p.hardware_choice != "auto":
        return [h for h in hardware if h["id"] == p.hardware_choice]
    weak = grid_weak(p.country, d)
    if weak is not False or it_mw_if_air < d["dense_profile_min_it_mw"]["value"]:
        return [h for h in hardware if h["weak_grid_ok"]]
    return list(hardware)


# ----------------------------------------------------------------- Layer 5
def cost_params(p: Profile, d: dict, scenario: str) -> dict:
    c = d["costs"]
    q = p.quotes or {}
    kwh = q.get("electricity_usd_kwh") or p.country.get("electricity_usd_kwh")
    return dict(
        kwh=kwh if kwh else c["electricity_usd_kwh"][scenario],
        fac=q.get("facility_capex_usd_per_mw_it") or c["facility_capex_usd_per_mw_it"][scenario],
        capex_mult=1.0 if q.get("gpu_capex_usd") else c["gpu_capex_multiplier"][scenario],
        hour_mult=1.0 if q.get("gpu_hour_usd") else c["gpu_hour_multiplier"][scenario],
        api_mult=1.0 if q.get("api_prices") else c["api_price_multiplier"][scenario],
        cache_share=c["cached_input_price_share"][scenario] if "cached_input_price_share" in c else 0.0,
    )


def finance(p: Profile, d: dict) -> tuple[float, float, float]:
    f = p.finance or {}
    pick = lambda k: f[k] if f.get(k) is not None else d[k]["value"]
    return pick("discount_rate"), pick("demand_growth"), pick("price_decline")


def staff_fte(n_gpus: float, d: dict) -> float:
    if not n_gpus:
        return 0.0
    if d.get("staff_mode", {}).get("value", "scaled") == "flat":
        return d["fte_per_owned_tier"]["value"]
    return d["fte_min"]["value"] + n_gpus / d["gpus_per_fte"]["value"]


def _server_round(n: int, hw: dict) -> int:
    """Owned GPUs come in whole servers (8-GPU HGX) or racks (72-GPU NVL72)."""
    k = hw.get("gpus_per_server", 1)
    return int(math.ceil(n / k) * k) if n > 0 else 0


def tco_tier(sz: dict, dem: list, hw: dict, api_prices: dict, p: Profile, d: dict, scenario: str) -> dict:
    """Present value (discounted at year start) of each allowed buying mode over the horizon."""
    tier = sz["tier"]
    t = d["tiers"][tier]
    cp = cost_params(p, d, scenario)
    q = p.quotes or {}
    r, g, dec = finance(p, d)
    H, R = int(d["horizon_years"]["value"]), int(d["gpu_refresh_years"]["value"])
    idle = d["idle_power_fraction"]["value"]
    fac = facility_for(p.country, hw, d, scenario)
    pue = fac["pue"]
    if not q.get("facility_capex_usd_per_mw_it"):
        cp["fac"] = fac["capex_per_mw"]
    rate = (q.get("gpu_hour_usd") or hw["gpu_hour_usd"]) * cp["hour_mult"]
    capex_gpu = (q.get("gpu_capex_usd") or hw["capex_per_gpu_usd"]) * cp["capex_mult"]
    prices = q.get("api_prices") or api_prices
    rows = [x for x in dem if x["tier"] == tier]
    api_llm = sum(x["annual_uncached_input_m"] * prices[x["model_class"]]["input"]
                  + x.get("annual_cached_input_m", 0) * prices[x["model_class"]]["input"] * cp["cache_share"]
                  + x["annual_output_m"] * prices[x["model_class"]]["output"] for x in rows) * cp["api_mult"]
    years = range(1, H + 1)
    grow = {y: (1 + g) ** (y - 1) for y in years}
    price = {y: (1 - dec) ** (y - 1) for y in years}
    disc = {y: 1 / (1 + r) ** (y - 1) for y in years}
    gpus = {y: _roundup(sz["gpus"] * grow[y]) for y in years}
    nt_gpus = {y: _roundup((sz["gpus_nontoken"] + sz["gpus_batch_extra"]) * grow[y]) for y in years}
    out, detail = {}, {}
    if t["api"]:
        out["API / managed"] = sum(disc[y] * price[y] * (api_llm * grow[y] + nt_gpus[y] * 8760 * rate) for y in years)
        detail["API / managed"] = dict(annual_y1=api_llm + nt_gpus[1] * 8760 * rate)
    if t["gpuaas"] and (tier != "T3" or p.local_gpu_provider):
        out["GPU-as-a-service"] = sum(disc[y] * price[y] * gpus[y] * 8760 * rate for y in years)
        detail["GPU-as-a-service"] = dict(annual_y1=gpus[1] * 8760 * rate)
    if t["owned"]:
        it_mw_max = _server_round(max(gpus.values()), hw) * hw["kw_per_gpu"] / 1000
        fac_capex = it_mw_max * cp["fac"]
        total = fac_capex  # facility built in year 1, sized for the last year
        # Present-value breakdown, so a client using colocation or an existing room can see the GPU part alone.
        pv = {"gpu_servers": 0.0, "facility_build": fac_capex, "energy": 0.0, "staff": 0.0,
              "software": 0.0, "maintenance_gpu": 0.0, "maintenance_facility": 0.0}
        opex_y1 = None
        purchases = []
        for c in range(math.ceil(H / R)):
            start, end = 1 + c * R, min(H, (c + 1) * R)
            owned = _server_round(gpus[end], hw)                 # whole servers, for demand at the end of the cycle
            total += disc[start] * owned * capex_gpu * price[start]
            pv["gpu_servers"] += disc[start] * owned * capex_gpu * price[start]
            purchases.append((start, owned * capex_gpu * price[start]))
            for y in range(start, end + 1):
                util = min(1.0, sz["utilisation"] * sz["gpus"] * grow[y] / owned) if owned else 0.0
                energy_mwh = owned * hw["kw_per_gpu"] * (idle + (1 - idle) * util) * pue * 8760 / 1000
                opex = (energy_mwh * 1000 * cp["kwh"] + owned * hw["software_per_gpu_year_usd"]
                        + staff_fte(owned, d) * d["cost_per_fte_usd"]["value"]
                        + d["maintenance_share"]["value"] * (owned * capex_gpu + fac_capex))
                total += disc[y] * opex
                pv["energy"] += disc[y] * energy_mwh * 1000 * cp["kwh"]
                pv["software"] += disc[y] * owned * hw["software_per_gpu_year_usd"]
                pv["staff"] += disc[y] * staff_fte(owned, d) * d["cost_per_fte_usd"]["value"]
                pv["maintenance_gpu"] += disc[y] * d["maintenance_share"]["value"] * owned * capex_gpu
                pv["maintenance_facility"] += disc[y] * d["maintenance_share"]["value"] * fac_capex
                if opex_y1 is None:
                    opex_y1 = opex
        out["Owned"] = total
        n1 = _server_round(gpus[min(H, R)], hw)
        detail["Owned"] = dict(gpus=n1, servers=n1 // hw.get("gpus_per_server", 1) if n1 else 0,
                               it_kw=n1 * hw["kw_per_gpu"], facility_kw=n1 * hw["kw_per_gpu"] * pue,
                               racks=_roundup(n1 * hw["kw_per_gpu"] / hw["rack_kw"]) if n1 else 0,
                               upfront=fac_capex + purchases[0][1], facility_capex=fac_capex,
                               gpu_capex_y1=purchases[0][1], refresh=[(y, v) for y, v in purchases[1:]],
                               annual_opex_y1=opex_y1 or 0.0, pue=pue, capex_per_mw=cp["fac"], pv_breakdown=pv)
    tokens_pv = sum(disc[y] * sz["annual_eq_m"] * grow[y] for y in years)
    return {"modes": out, "detail": detail, "tokens_pv_m": tokens_pv}


def step_for(tier: str, sz: dict, d: dict, mode: str = "", owned: dict | None = None) -> str:
    """Recommended step, worded after the buying option actually chosen."""
    if sz["below_threshold"]:
        return "Below GPU threshold: run on existing servers (CPU or a shared GPU)"
    if sz["gpus"] == 0:
        return "No demand in this tier"
    if mode == "API / managed":
        return "Step 0: buy as an API service" + (" with in-country or regional data residency" if tier == "T2" else "")
    if mode == "GPU-as-a-service":
        return ("Step 1: rent GPUs from an in-country provider" if tier == "T3"
                else "Step 0: rent cloud GPUs" + (" with data residency" if tier == "T2" else ""))
    mw = (owned or {}).get("facility_kw", sz["facility_mw"] * 1000) / 1000
    srv = (owned or {}).get("servers")
    what = f"own {srv} server{'s' if srv != 1 else ''}" if srv else "own the servers"
    if mw < d["step1_max_facility_mw"]["value"]:
        return f"Step 1: {what} in an existing secure server room"
    if mw < d["step3_min_facility_mw"]["value"]:
        return f"Step 2: {what} in a colocation data centre run by a private operator"
    return "Step 3: dedicated facility via PPP or private operator (IFC-investable)"


# ----------------------------------------------------------------- Run
def grid_status(p: Profile, hw: dict, sz: dict, tier: str, d: dict) -> str:
    if sz["gpus"] == 0:
        return "-"
    if tier == "T1":
        return "Offshore: not applicable"
    weak = grid_weak(p.country, d)
    if weak is None:
        return "Unknown: check grid reliability (air-cooled assumed)"
    if weak and not hw["weak_grid_ok"]:
        return "WARNING: profile unsuitable for weak grid"
    if weak:
        return "Weak grid: budget backup and storage"
    return "OK"


def _as_servers(sz: dict, hw: dict, d: dict) -> dict:
    """Physical figures for owned capacity: whole servers, then power, energy and utilisation from those GPUs."""
    n = _server_round(sz["gpus"], hw)
    if not n or n == sz["gpus"]:
        return dict(sz, servers=n // hw.get("gpus_per_server", 1) if n else 0)
    idle = d["idle_power_fraction"]["value"]
    util = min(1.0, sz["utilisation"] * sz["gpus"] / n)
    it_kw = n * hw["kw_per_gpu"]
    return dict(sz, gpus=n, servers=n // hw.get("gpus_per_server", 1), gpus_needed=sz["gpus"], utilisation=util,
                it_kw=it_kw, facility_mw=it_kw * sz["pue"] / 1000, racks=_roundup(it_kw / hw["rack_kw"]),
                energy_mwh=it_kw * (idle + (1 - idle) * util) * sz["pue"] * 8760 / 1000)


def _solve_tier(t, dem, nt, p, hardware, d, api_prices):
    air = next(h for h in hardware if h["weak_grid_ok"])
    first = size_tier(t, dem, nt, air, d, p.speed, p.country)
    um = d.get("throughput_uncertainty", {"low": 1.0, "base": 1.0, "high": 1.0})
    best = None
    for h in candidate_hardware(p, hardware, first["it_kw"] / 1000, d):
        sz = size_tier(t, dem, nt, h, d, p.speed, p.country)
        base = tco_tier(sz, dem, h, api_prices, p, d, "base")["modes"]
        key = (min(base.values()) if base and sz["gpus"] else 0.0, sz["it_kw"])
        if best is None or key < best[0]:          # hardware with the lowest cost of the cheapest allowed option
            best = (key, h, sz)
    _, hw, sz = best
    sizes = {sc: (sz if um[sc] == 1.0 else size_tier(t, dem, nt, hw, d, p.speed, p.country, um[sc])) for sc in SCENARIOS}
    res = {sc: tco_tier(sizes[sc], dem, hw, api_prices, p, d, sc) for sc in SCENARIOS}
    tco = {s: res[s]["modes"] for s in SCENARIOS}
    detail = {s: res[s]["detail"] for s in SCENARIOS}
    if sz["gpus"] == 0 or not tco["base"]:
        mode, cost, winners = ("Below GPU threshold" if sz["below_threshold"] else "No demand"), 0.0, {}
    else:
        winners = {s: min(tco[s], key=tco[s].get) for s in SCENARIOS}
        mode = winners["base"]
        cost = tco["base"][mode]
    cost_range = {s: (tco[s][winners[s]] if winners else None) for s in SCENARIOS}
    per_m = cost / res["base"]["tokens_pv_m"] if res["base"]["tokens_pv_m"] and cost else None
    owned = detail["base"].get("Owned") if mode == "Owned" else None
    # Owned capacity is physical: round GPUs to whole servers before reporting power, energy and utilisation.
    if winners:
        sizes = {sc: (_as_servers(sizes[sc], hw, d) if winners[sc] == "Owned" else sizes[sc]) for sc in SCENARIOS}
        sz = sizes["base"]
    # Capacity actually acquired: owned servers, rented GPUs, or nothing (API service).
    if mode == "Owned":
        cap = dict(kind="build", gpus=owned["gpus"], servers=owned["servers"], it_kw=owned["it_kw"],
                   facility_kw=owned["facility_kw"], racks=owned["racks"])
    elif mode == "GPU-as-a-service":
        cap = dict(kind="rent", gpus=sz["gpus"], servers=None, it_kw=sz["it_kw"], facility_kw=None, racks=None)
    else:
        cap = dict(kind="service" if sz["gpus"] else "none", gpus=None, servers=None, it_kw=None, facility_kw=None, racks=None)
    return dict(sizing=sz, sizing_range={sc: dict(gpus=sizes[sc]["gpus"], facility_mw=sizes[sc]["facility_mw"])
                                         for sc in SCENARIOS},
                tco=tco, detail=detail, facility=facility_for(p.country, hw, d), cheapest_mode=mode, cheapest_cost=cost,
                winners=winners, winner_changes=len(set(winners.values())) > 1, cost_range=cost_range,
                usd_per_m_eq_tokens=per_m, capacity=cap, grid=grid_status(p, hw, sz, t, d),
                step=step_for(t, sz, d, mode, owned), hardware=hw["id"], merged_into=None)


def run(p: Profile, catalogue: dict, d: dict, api_prices: dict | None = None) -> dict:
    api_prices = api_prices or d["api_prices_fallback"]
    dem = demand_rows(p, d)
    nt = nontoken_rows(p, d)
    hardware = catalogue["hardware"]
    tiers = {t: _solve_tier(t, dem, nt, p, hardware, d, api_prices) for t in TIERS}
    # Shared sovereign site: Confidential work moves into the Restricted site when it would otherwise be owned
    # separately (data can always move to a more secure tier). One site, one team, pooled GPUs.
    t3, t4 = tiers["T3"], tiers["T4"]
    if (p.shared_sovereign_site and t3["sizing"]["gpus"] and t4["sizing"]["gpus"]
            and t3["cheapest_mode"] == "Owned" and t4["cheapest_mode"] == "Owned"):
        dem = [dict(r, tier="T4") if r["tier"] == "T3" else r for r in dem]
        nt = [dict(x, tier="T4") if x["tier"] == "T3" else x for x in nt]
        tiers["T4"] = _solve_tier("T4", dem, nt, p, hardware, d, api_prices)
        tiers["T4"]["shared_site"] = True
        tiers["T3"] = _solve_tier("T3", dem, nt, p, hardware, d, api_prices)   # now empty
        tiers["T3"]["merged_into"] = "T4"
        tiers["T3"]["step"] = "Served by the shared sovereign site (with Restricted data)"
    alloc = allocate(dem, nt, tiers)
    return dict(demand=dem, nontoken=nt, tiers=tiers, by_app=alloc,
                totals=dict(gpus_range={sc: sum(v["sizing_range"][sc]["gpus"] for v in tiers.values()) for sc in SCENARIOS},
                            mw_range={sc: sum(v["sizing_range"][sc]["facility_mw"] for v in tiers.values()) for sc in SCENARIOS},
                            gpus=sum(v["sizing"]["gpus"] for v in tiers.values()),
                            facility_mw=sum(v["sizing"]["facility_mw"] for v in tiers.values()),
                            cost=sum(v["cheapest_cost"] for v in tiers.values()),
                            cost_range={sc: sum((v["cost_range"][sc] or 0) for v in tiers.values()) for sc in SCENARIOS}))


def allocate(dem: list, nt: list, tiers: dict) -> dict:
    """Share each tier's cheapest present-value cost among its applications, by their share of GPU need.

    Language-model application: peak tokens/s / effective tokens/s per GPU of its model size.
    Non-LLM: GPUs at peak (interactive) or GPU-hours per day / 24 (batch).
    Applications split across classes contribute to several tiers.
    """
    out: dict = {}
    for t, v in tiers.items():
        cost = v["cheapest_cost"] or 0.0
        if not cost:
            continue
        eff = v["sizing"]["eff_tps"]
        w = {}
        for r in dem:
            if r["tier"] == t and r["sessions"] > 0:
                w[r["id"]] = w.get(r["id"], 0) + r["peak_eq_tps"] / eff[r["model_class"]]
        for x in nt:
            if x["tier"] == t and x["gpu_hours_day"] > 0:
                w[x["id"]] = w.get(x["id"], 0) + (x["peak_gpus"] if x["mode"] == "Interactive" else x["gpu_hours_day"] / 24)
        tot = sum(w.values())
        for k, val in w.items():
            out.setdefault(k, {})
            out[k][t] = out[k].get(t, 0) + cost * val / tot if tot else 0
    return out
