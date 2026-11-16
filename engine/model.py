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
    peak = eq * app["peak_share"] / (app["peak_window_h"] * 3600) * app["burst"] * app["sla_headroom"] * app["seasonal"]
    tpud = (d_in + d_out) / u if u else 0.0
    return dict(
        id=app["id"], name=app["name"], users=u, sessions=sessions,
        daily_input=d_in, daily_cached=d_cached, daily_output=d_out, daily_eq=eq,
        tokens_per_user_day=tpud,
        above_ceiling=tpud > d["tokens_per_user_day_ceiling"]["value"],
        avg_eq_tps=eq / 86400, peak_eq_tps=peak, model_class=app["model_class"],
        annual_uncached_input_m=(d_in - d_cached) * 365 / 1e6,
        annual_output_m=d_out * 365 / 1e6, annual_eq_m=eq * 365 / 1e6,
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
def size_tier(tier: str, dem: list, nt: list, hw: dict, d: dict) -> dict:
    D = d["diversity_factor"]["value"]
    der = d["production_derating"]["value"]
    pue = d["pue"]["value"]
    idle = d["idle_power_fraction"]["value"]
    tps = hw["tokens_per_s_per_gpu"]
    rows = [r for r in dem if r["tier"] == tier]
    peak = {c: sum(r["peak_eq_tps"] for r in rows if r["model_class"] == c) * D for c in CLASSES}
    avg = {c: sum(r["avg_eq_tps"] for r in rows if r["model_class"] == c) for c in CLASSES}
    gpus_llm = _roundup(sum(peak[c] / tps[c] for c in CLASSES) / der)
    ntr = [w for w in nt if w["tier"] == tier]
    gpus_nt = _roundup(sum(w["peak_gpus"] for w in ntr) * D)
    busy = (sum(avg[c] / tps[c] for c in CLASSES) / der * 24
            + sum(w["gpu_hours_day"] for w in ntr if w["mode"] == "Interactive"))
    batch = sum(w["gpu_hours_day"] for w in ntr if w["mode"] == "Batch")
    base = gpus_llm + gpus_nt
    idle_h = max(0.0, base * 24 - busy)
    extra = _roundup(max(0.0, batch - idle_h) / 24)
    total = base + extra
    util = min(1.0, (busy + batch) / (total * 24)) if total else 0.0
    it_kw = total * hw["kw_per_gpu"]
    return dict(
        tier=tier, hardware=hw["id"], peak_eq_tps=peak, gpus_llm=gpus_llm, gpus_nontoken=gpus_nt,
        gpus_batch_extra=extra, gpus=total, utilisation=util, it_kw=it_kw,
        facility_mw=it_kw * pue / 1000,
        racks=_roundup(it_kw / hw["rack_kw"]) if it_kw else 0,
        energy_mwh=it_kw * (idle + (1 - idle) * util) * pue * 8760 / 1000,
        annual_eq_m=sum(r["annual_eq_m"] for r in rows),
    )


def pick_hardware(p: Profile, hardware: list, it_mw_if_air: float, d: dict) -> dict:
    hw_by_id = {h["id"]: h for h in hardware}
    if p.hardware_choice != "auto":
        return hw_by_id[p.hardware_choice]
    weak = p.country.get("outages_per_month", 0) > d["weak_grid_outages_threshold"]["value"]
    air = next(h for h in hardware if h["weak_grid_ok"])
    if weak or it_mw_if_air < d["dense_profile_min_it_mw"]["value"]:
        return air
    dense = [h for h in hardware if not h["weak_grid_ok"]]
    return dense[0] if dense else air


# ----------------------------------------------------------------- Layer 5
def cost_params(p: Profile, d: dict, scenario: str) -> dict:
    c = d["costs"]
    q = p.quotes or {}
    kwh = q.get("electricity_usd_kwh") or p.country.get("electricity_usd_kwh")
    out = dict(
        kwh=kwh if kwh else c["electricity_usd_kwh"][scenario],
        fac=q.get("facility_capex_usd_per_mw_it") or c["facility_capex_usd_per_mw_it"][scenario],
        capex_mult=1.0 if q.get("gpu_capex_usd") else c["gpu_capex_multiplier"][scenario],
        hour_mult=1.0 if q.get("gpu_hour_usd") else c["gpu_hour_multiplier"][scenario],
        api_mult=1.0 if q.get("api_prices") else c["api_price_multiplier"][scenario],
    )
    return out


def tco_tier(sz: dict, dem: list, hw: dict, api_prices: dict, p: Profile, d: dict, scenario: str) -> dict:
    tier = sz["tier"]
    t = d["tiers"][tier]
    cp = cost_params(p, d, scenario)
    q = p.quotes or {}
    hor = d["horizon_years"]["value"]
    rate = (q.get("gpu_hour_usd") or hw["gpu_hour_usd"]) * cp["hour_mult"]
    capex_gpu = (q.get("gpu_capex_usd") or hw["capex_per_gpu_usd"]) * cp["capex_mult"]
    prices = q.get("api_prices") or api_prices
    n, it_mw = sz["gpus"], sz["it_kw"] / 1000
    rows = [r for r in dem if r["tier"] == tier]
    api_llm = sum(r["annual_uncached_input_m"] * prices[r["model_class"]]["input"]
                  + r["annual_output_m"] * prices[r["model_class"]]["output"] for r in rows) * cp["api_mult"]
    out = {}
    if t["api"]:
        out["API / managed"] = (api_llm + (sz["gpus_nontoken"] + sz["gpus_batch_extra"]) * 8760 * rate) * hor
    if t["gpuaas"]:
        out["GPU-as-a-service"] = n * 8760 * rate * hor
    if t["owned"]:
        capex = n * capex_gpu * _roundup(hor / d["gpu_refresh_years"]["value"]) + it_mw * cp["fac"]
        opex = (sz["energy_mwh"] * 1000 * cp["kwh"] + n * hw["software_per_gpu_year_usd"]
                + (d["fte_per_owned_tier"]["value"] * d["cost_per_fte_usd"]["value"] if n else 0)
                + d["maintenance_share"]["value"] * (n * capex_gpu + it_mw * cp["fac"]))
        out["Owned"] = capex + opex * hor
    return out


# ----------------------------------------------------------------- Run
def run(p: Profile, catalogue: dict, d: dict, api_prices: dict | None = None) -> dict:
    api_prices = api_prices or d["api_prices_fallback"]
    dem = demand_rows(p, d)
    nt = nontoken_rows(p, d)
    hardware = catalogue["hardware"]
    tiers = {}
    for t in TIERS:
        air = next(h for h in hardware if h["weak_grid_ok"])
        first = size_tier(t, dem, nt, air, d)
        hw = pick_hardware(p, hardware, first["it_kw"] / 1000, d)
        sz = first if hw["id"] == air["id"] else size_tier(t, dem, nt, hw, d)
        tco = {s: tco_tier(sz, dem, hw, api_prices, p, d, s) for s in SCENARIOS}
        base = tco["base"]
        if sz["gpus"] == 0 or not base:
            mode, best = "No demand", 0.0
        else:
            mode = min(base, key=base.get)
            best = base[mode]
        weak = p.country.get("outages_per_month", 0) > d["weak_grid_outages_threshold"]["value"]
        if sz["gpus"] == 0:
            grid = "-"
        elif t == "T1":
            grid = "Offshore: not applicable"
        elif weak and not hw["weak_grid_ok"]:
            grid = "WARNING: profile unsuitable for weak grid"
        elif weak:
            grid = "Weak grid: budget backup and storage"
        else:
            grid = "OK"
        if sz["gpus"] == 0:
            step = "No demand in this tier"
        elif t in ("T1", "T2"):
            step = "Step 0: use cloud / API under residency terms now"
        elif sz["facility_mw"] < d["step1_max_facility_mw"]["value"]:
            step = "Step 1: small sovereign inference node in an existing facility"
        else:
            step = "Step 2: dedicated capacity via private operator or PPP (IFC-investable)"
        cost_range = {s: (tco[s].get(mode) if mode in tco[s] else None) for s in SCENARIOS}
        per_m = best / (sz["annual_eq_m"] * d["horizon_years"]["value"]) if sz["annual_eq_m"] else None
        tiers[t] = dict(sizing=sz, tco=tco, cheapest_mode=mode, cheapest_cost=best,
                        cost_range=cost_range, usd_per_m_eq_tokens=per_m, grid=grid, step=step,
                        hardware=hw["id"])
    return dict(demand=dem, nontoken=nt, tiers=tiers,
                totals=dict(gpus=sum(v["sizing"]["gpus"] for v in tiers.values()),
                            facility_mw=sum(v["sizing"]["facility_mw"] for v in tiers.values()),
                            cost=sum(v["cheapest_cost"] for v in tiers.values())))
