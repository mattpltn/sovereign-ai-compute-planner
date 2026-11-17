"""Four ways to deliver the same applications, year by year, over the horizon (v0.9).

For each application, and for all applications together:
  API              : pay per token (language models); non-LLM work on rented cloud GPUs
  GPU-as-a-service : rent the GPUs needed each year, by the hour
  Owned + colocation: buy whole servers when needed, host them in a commercial data centre (price per kW)
  Owned + own data centre: buy servers and build (or use) a facility sized for the peak year

Demand starts in each application's start year and grows at its own rate. Capacity for the portfolio is sized
on the combined, pooled load of each year: excess capacity of one application is not added to another's.
No data classification or hosting rule is applied here; the results carry a note that the client must check
data regulation.
"""
from __future__ import annotations

import dataclasses
import math

from engine.model import (SCENARIOS, candidate_hardware, cost_params, demand_rows, facility_for, finance,
                          nontoken_rows, size_tier, staff_fte, _roundup)

OPTIONS = ("API", "GPU-as-a-service", "Owned + colocation", "Owned + own data centre")
POOL = "P"
_SCALE = ("sessions", "peak_eq_tps", "avg_eq_tps", "annual_uncached_input_m", "annual_cached_input_m",
          "annual_output_m", "annual_eq_m", "daily_eq")
_SCALE_NT = ("gpu_hours_day", "peak_gpus", "units_per_day")


def colo_price(country: dict, d: dict, scenario: str = "base", it_kw: float = 0.0) -> dict:
    """USD per kW of committed IT per month for this country, with provenance."""
    c = d["colocation"]
    iso, region = country.get("iso3"), (country.get("region") or "").strip()
    q = (country.get("_quotes") or {}).get("colo_usd_per_kw_month")
    if q:
        return dict(value=q, src="client quote", small=False)
    mk = c["wholesale_by_country"].get(iso) if iso else None
    rg = c["wholesale_by_region"].get(region)
    if mk:
        v, src = mk["value"], f'{mk["market"]} [{mk["source"]}]'
    elif rg:
        v, src = rg["value"], f'{region} proxy: {rg["note"]} [{rg["source"]}]'
    else:
        v, src = c["wholesale_default"]["value"], "global default"
    small = 0 < it_kw < c["small_deployment_kw"]["value"]
    f = c["small_deployment_factor"]["value"] if small else 1.0
    return dict(value=v * f * c["price_range"][scenario], wholesale=v, src=src, small=small)


def _factor(app_meta: dict, y: int) -> float:
    s, g = int(app_meta.get("start_year") or 1), float(app_meta.get("growth") or 0.0)
    return 0.0 if y < s else (1 + g) ** (y - s)


def _year_rows(dem, nt, meta, y):
    out_d = [dict(r, tier=POOL, **{k: r[k] * _factor(meta.get(r["id"], {}), y) for k in _SCALE if k in r}) for r in dem]
    out_n = [dict(w, tier=POOL, **{k: w[k] * _factor(meta.get(w["id"], {}), y) for k in _SCALE_NT if k in w}) for w in nt]
    return out_d, out_n


def _years(d):
    return range(1, int(d["horizon_years"]["value"]) + 1)


def evaluate(p, d, hw, api_prices, meta, scenario="base", ids=None) -> dict:
    """Year-by-year cost of each option for the applications in `ids` (all if None), pooled together."""
    um = d.get("throughput_uncertainty", {}).get(scenario, 1.0)
    dem_all, nt_all = demand_rows(p, d), nontoken_rows(p, d)
    dem = [r for r in dem_all if ids is None or r["id"] in ids]
    nt = [w for w in nt_all if ids is None or w["id"] in ids]
    cp = cost_params(p, d, scenario)
    q = p.quotes or {}
    r_, _, dec = finance(p, d)
    R = int(d["gpu_refresh_years"]["value"])
    idle = d["idle_power_fraction"]["value"]
    fac = facility_for(p.country, hw, d, scenario)
    pue = fac["pue"]
    fac_per_mw = q.get("facility_capex_usd_per_mw_it") or fac["capex_per_mw"]
    rate = (q.get("gpu_hour_usd") or hw["gpu_hour_usd"]) * cp["hour_mult"]
    capex_gpu = (q.get("gpu_capex_usd") or hw["capex_per_gpu_usd"]) * cp["capex_mult"]
    prices = q.get("api_prices") or api_prices
    k = hw.get("gpus_per_server", 1)
    kw_gpu = hw["kw_per_gpu"]
    fte_cost = d["cost_per_fte_usd"]["value"]
    maint = d["maintenance_share"]["value"]

    yrs = list(_years(d))
    sz = {}
    for y in yrs:
        dy, ny = _year_rows(dem, nt, meta, y)
        sz[y] = size_tier(POOL, dy, ny, hw, d, p.speed, p.country, um)
        sz[y]["api_llm"] = sum(x["annual_uncached_input_m"] * prices[x["model_class"]]["input"]
                               + x.get("annual_cached_input_m", 0) * prices[x["model_class"]]["input"] * cp["cache_share"]
                               + x["annual_output_m"] * prices[x["model_class"]]["output"] for x in dy) * cp["api_mult"]
        sz[y]["nt_gpus"] = (sz[y]["gpus_nontoken"] + sz[y]["gpus_batch_extra"])
        sz[y]["busy_h"] = sz[y]["utilisation"] * sz[y]["gpus"] * 24
    disc = {y: 1 / (1 + r_) ** (y - 1) for y in yrs}
    price = {y: (1 - dec) ** (y - 1) for y in yrs}

    # Owned fleet: whole servers bought when the pooled need exceeds what is installed; each cohort is replaced
    # after the refresh period if still needed. Servers are never sold.
    cohorts, fleet = [], {}
    for y in yrs:
        cohorts = [(b, n) for b, n in cohorts if y - b < R]
        need = math.ceil(sz[y]["gpus"] / k) if sz[y]["gpus"] else 0
        have = sum(n for _, n in cohorts)
        buy = max(0, need - have)
        if buy:
            cohorts.append((y, buy))
        active = have + buy if (need or have) else 0
        fleet[y] = dict(servers=active, gpus=active * k, buy=buy)
    peak_it_kw = max((f["gpus"] for f in fleet.values()), default=0) * kw_gpu
    first = next((y for y in yrs if fleet[y]["gpus"]), None)
    # Own data centre: built once, in the first year of use, for the peak installed IT load plus a spare buffer.
    design_kw = peak_it_kw * (1 + d["facility_buffer"]["value"])
    build = 0.0 if p.gov_dc == "ready" else design_kw / 1000 * fac_per_mw
    fac_ops = d["facility_opex_share"]["value"] * build      # an existing facility's running costs are already paid

    yearly = {o: {} for o in OPTIONS}
    parts = {o: {} for o in OPTIONS}
    for y in yrs:
        s, f = sz[y], fleet[y]
        # API: tokens priced per million; non-LLM rented as cloud GPU-hours
        api = s["api_llm"] + _roundup(s["nt_gpus"]) * 8760 * rate if s["gpus"] else 0.0
        yearly["API"][y] = api * price[y]
        # GPU-as-a-service: the GPUs needed this year, rented all year
        yearly["GPU-as-a-service"][y] = s["gpus"] * 8760 * rate * price[y]
        g = f["gpus"]
        util = min(1.0, s["busy_h"] / (g * 24)) if g else 0.0
        it_kwh = g * kw_gpu * (idle + (1 - idle) * util) * 8760
        gpu_capex = f["buy"] * k * capex_gpu * price[y]
        common = dict(gpu_servers=gpu_capex, software=g * hw["software_per_gpu_year_usd"],
                      maintenance_gpu=maint * g * capex_gpu, staff=staff_fte(g, d) * fte_cost if g else 0.0,
                      energy=it_kwh * pue * cp["kwh"])
        cpr = colo_price(dict(p.country, _quotes=q), d, scenario, peak_it_kw)
        colo = dict(common, colocation=g * kw_gpu * cpr["value"] * 12)
        fb = build if y == first else 0.0
        own = dict(common, facility_build=fb, facility_operations=fac_ops if first and y >= first else 0.0)
        parts["Owned + colocation"][y], parts["Owned + own data centre"][y] = colo, own
        yearly["Owned + colocation"][y] = sum(colo.values())
        yearly["Owned + own data centre"][y] = sum(own.values())
    pv = {o: sum(disc[y] * yearly[o][y] for y in yrs) for o in OPTIONS}
    pv_parts = {o: {} for o in ("Owned + colocation", "Owned + own data centre")}
    for o in pv_parts:
        for y in yrs:
            for kk, v in parts[o][y].items():
                pv_parts[o][kk] = pv_parts[o].get(kk, 0.0) + disc[y] * v
    return dict(pv=pv, yearly=yearly, pv_parts=pv_parts, fleet=fleet, sizing=sz, hardware=hw["id"],
                peak_it_kw=peak_it_kw, peak_facility_kw=peak_it_kw * pue, pue=pue, design_it_kw=design_kw,
                colo=colo_price(dict(p.country, _quotes=q), d, scenario, peak_it_kw),
                facility_capex=build, facility_opex_year=fac_ops,
                gpu_hour=rate, capex_gpu=capex_gpu, first_year=first,
                tokens_pv_m=sum(disc[y] * sz[y]["annual_eq_m"] for y in yrs))


def _hardware(p, catalogue, d, api_prices, meta, ids=None):
    """Hardware with the lowest cheapest-option cost for this set of applications."""
    hw_list = catalogue["hardware"]
    air = next(h for h in hw_list if h["weak_grid_ok"])
    dem = demand_rows(p, d)
    probe = size_tier(POOL, [dict(r, tier=POOL) for r in dem if ids is None or r["id"] in ids],
                      [dict(w, tier=POOL) for w in nontoken_rows(p, d) if ids is None or w["id"] in ids],
                      air, d, p.speed, p.country)
    best = None
    for h in candidate_hardware(p, hw_list, probe["it_kw"] / 1000, d):
        e = evaluate(p, d, h, api_prices, meta, "base", ids)
        key = min(e["pv"].values())
        if best is None or key < best[0]:
            best = (key, h)
    return best[1]


def compare(p, catalogue, d, api_prices=None, meta=None) -> dict:
    """Per application (standalone) and for the portfolio (pooled), each option with a Low / Base / High range."""
    api_prices = api_prices or d["api_prices_fallback"]
    meta = meta or {}
    ids = [a["id"] for a in p.apps] + [w["id"] for w in p.nontoken]

    def run_set(sel):
        hw = _hardware(p, catalogue, d, api_prices, meta, sel)
        res = {sc: evaluate(p, d, hw, api_prices, meta, sc, sel) for sc in SCENARIOS}
        return dict(base=res["base"], range={o: {sc: res[sc]["pv"][o] for sc in SCENARIOS} for o in OPTIONS},
                    cheapest=min(res["base"]["pv"], key=res["base"]["pv"].get))

    apps = {i: run_set({i}) for i in ids}
    total = run_set(set(ids)) if ids else None
    return dict(apps=apps, total=total,
                sum_standalone={o: sum(a["base"]["pv"][o] for a in apps.values()) for o in OPTIONS})


def with_no_placement(p):
    """All applications in one pool: placement does not apply in the options view."""
    return dataclasses.replace(p, class_to_tier={c: POOL for c in (1, 2, 3, 4)})
