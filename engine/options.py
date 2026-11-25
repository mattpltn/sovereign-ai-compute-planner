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


def build_cost_per_mw(design_mw: float, country: dict, hw: dict, d: dict, scenario: str = "base") -> dict:
    """Own data centre build cost, USD per MW of IT capacity, from the size curve scaled to the country."""
    f = d["facility"]
    pts = f["capex_scale_curve"]["points"]
    x = max(design_mw, 1e-6)
    if x <= pts[0][0]:
        base = pts[0][1]
    elif x >= pts[-1][0]:
        base = pts[-1][1]
    else:
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if x0 <= x <= x1:
                t = (math.log(x) - math.log(x0)) / (math.log(x1) - math.log(x0))
                base = y0 + t * (y1 - y0)
                break
    fac = facility_for(country, hw, d, scenario)          # country $/W x range x cooling, relative to the default
    rel = fac["capex_per_mw"] / (f["capex_usd_per_w_default"]["value"] * 1e6)
    return dict(value=base * 1e6 * rel, curve_musd_per_mw=base, country_factor=rel, src=fac["capex_src"])


def _factor(app_meta: dict, y: int) -> float:
    s, g = int(app_meta.get("start_year") or 1), float(app_meta.get("growth") or 0.0)
    return 0.0 if y < s else (1 + g) ** (y - s)


def _year_rows(dem, nt, meta, y):
    out_d = [dict(r, tier=POOL, **{k: r[k] * _factor(meta.get(r["id"], {}), y) for k in _SCALE if k in r}) for r in dem]
    out_n = [dict(w, tier=POOL, **{k: w[k] * _factor(meta.get(w["id"], {}), y) for k in _SCALE_NT if k in w}) for w in nt]
    return out_d, out_n


def _years(d):
    return range(1, int(d["horizon_years"]["value"]) + 1)


def api_reference_prices(d, ref, market):
    """Token prices per model class for the chosen API reference (v0.9.11).

    open_market: synced median of open models (OpenRouter); hyperscaler: the same kind of open models on a
    hyperscaler in a regional data centre; frontier: proprietary frontier models with the regional-processing uplift."""
    if ref == "open_market" or ref not in d["api_reference_prices"]:
        return market
    t = d["api_reference_prices"][ref]
    up = 1 + t.get("regional_uplift", 0.0)
    return {c: {"input": t[c]["input"] * up, "output": t[c]["output"] * up} for c in ("S", "M", "L")}


def evaluate(p, d, hw, api_prices, meta, scenario="base", ids=None) -> dict:
    """Year-by-year cost of each option for the applications in `ids` (all if None), pooled together."""
    f0 = p.finance or {}
    policy = f0.get("server_end_policy") or d["server_end_policy"]["value"]
    if policy == "auto":
        # The cheaper of keeping servers in service and replacing them at the refresh period with an auction sale.
        runs = []
        for pol in ("keep", "sell"):
            q_ = dataclasses.replace(p, finance=dict(f0, server_end_policy=pol))
            runs.append(evaluate(q_, d, hw, api_prices, meta, scenario, ids))
        best = min(runs, key=lambda e: e["pv"]["Owned + colocation"])
        best["end_policy_auto"] = True
        return best
    um = d.get("throughput_uncertainty", {}).get(scenario, 1.0)
    dem_all, nt_all = demand_rows(p, d), nontoken_rows(p, d)
    dem = [r for r in dem_all if ids is None or r["id"] in ids]
    nt = [w for w in nt_all if ids is None or w["id"] in ids]
    cp = cost_params(p, d, scenario)
    q = p.quotes or {}
    r_, _, _ = finance(p, d)
    f_ = p.finance or {}
    pick = lambda k: f_[k] if f_.get(k) is not None else d[k]["value"]
    dec_api, dec_hw = pick("api_price_decline"), pick("hw_price_decline")
    cg = pick("compute_gain_per_year")                       # inference capacity per GPU of a newer purchase
    infra = d["owned_infra_share"]["value"]
    spare = 1 if getattr(p, "redundancy", False) else 0      # N+1: one spare server whenever servers are needed
    R = int(d["gpu_refresh_years"]["value"])
    idle = d["idle_power_fraction"]["value"]
    fac = facility_for(p.country, hw, d, scenario)
    pue = fac["pue"]
    # GPU rental: the hardware profile price is a specialised (neocloud) on-demand price; a hyperscaler costs a
    # multiple of it, reserved (1-year commitment) or on demand (v0.9.11).
    base_rate = (q.get("gpu_hour_usd") or hw["gpu_hour_usd"]) * cp["hour_mult"]
    rent_ref, rent_mode = pick("gpu_rental_reference"), pick("gpu_rental_mode")
    rm = d["gpu_rental_multipliers"]["value"][rent_ref]
    rate = base_rate * (rm["reserved"] if not q.get("gpu_hour_usd") else 1.0)       # rented all year (and API fallback)
    rate_od = base_rate * (rm["on_demand"] if not q.get("gpu_hour_usd") else 1.0)   # rented only when needed
    od_util = d["on_demand_utilisation"]["value"]
    software_gpu = 0.0 if pick("software_stack") == "open_source" else hw["software_per_gpu_year_usd"]
    end_policy = policy                                      # keep in service, or replace and sell at auction
    life = int(pick("server_life_years")) if end_policy == "keep" else R
    resale = d["resale_share"]["value"] if end_policy == "sell" else 0.0
    maint_old = d["maintenance_after_warranty_multiplier"]["value"]
    share_night = pick("idle_sharing_share")                 # share of idle GPU-hours opened to universities/research
    night_rate = base_rate * d["idle_sharing_price_share"]["value"]
    capex_gpu = (q.get("gpu_capex_usd") or hw["capex_per_gpu_usd"]) * cp["capex_mult"]
    ref = pick("api_reference")
    prices = q.get("api_prices") or api_reference_prices(d, ref, api_prices)
    api_disc = 1 - pick("api_commit_discount")               # negotiated multi-year commitment
    k = hw.get("gpus_per_server", 1)
    kw_gpu = hw["kw_per_gpu"]
    fte_cost = d["cost_per_fte_usd"]["value"]
    maint = d["maintenance_share"]["value"]

    yrs = list(_years(d))
    nt_meta = {w["id"]: w for w in p.nontoken}
    sz = {}
    for y in yrs:
        dy, ny = _year_rows(dem, nt, meta, y)
        sz[y] = size_tier(POOL, dy, ny, hw, d, p.speed, p.country, um)
        sz[y]["api_llm"] = sum(x["annual_uncached_input_m"] * prices[x["model_class"]]["input"]
                               + x.get("annual_cached_input_m", 0) * prices[x["model_class"]]["input"] * cp["cache_share"]
                               + x["annual_output_m"] * prices[x["model_class"]]["output"] for x in dy) * cp["api_mult"]
        sz[y]["nt_gpus"] = (sz[y]["gpus_nontoken"] + sz[y]["gpus_batch_extra"])
        # Non-LLM work in the API option: per-unit cloud API prices where such an API exists, otherwise rented GPUs.
        api_nt, no_api_gpus = 0.0, 0.0
        for w in ny:
            ap = (nt_meta.get(w["id"]) or {}).get("api_price") or {}
            if ap.get("available", True) and scenario in ap:
                api_nt += w["units_per_day"] * 365 * ap[scenario]
            elif w["gpu_hours_day"]:
                no_api_gpus += w["peak_gpus"] if w["mode"] == "Interactive" else w["gpu_hours_day"] / 24
        below = no_api_gpus < d["gpu_threshold"]["value"]      # tiny work runs on existing servers, as elsewhere
        sz[y]["api_units"] = api_nt
        sz[y]["api_gpu_fallback"] = 0.0 if below else _roundup(no_api_gpus / (1 + cg) ** (y - 1)) * 8760 * rate
        sz[y]["api_nt"] = sz[y]["api_units"] + sz[y]["api_gpu_fallback"]
        sz[y]["busy_h"] = sz[y]["utilisation"] * sz[y]["gpus"] * 24
        sz[y]["below_threshold"] = bool(sz[y].get("below_threshold"))
    disc = {y: 1 / (1 + r_) ** (y - 1) for y in yrs}
    price = {y: (1 - dec_hw) ** (y - 1) for y in yrs}          # GPU rental and server purchases
    price_api = {y: (1 - dec_api) ** (y - 1) for y in yrs}     # API tokens and per-unit API prices

    # Hardware generations: a GPU bought (or rented) in year y does gain[y] times the work of a year-1 GPU,
    # at the same price per GPU. Sizing (sz[y]["gpus"]) is in year-1 GPUs.
    gain = {y: (1 + cg) ** (y - 1) for y in yrs}
    for y in yrs:
        sz[y]["gpus_rented"] = _roundup(sz[y]["gpus"] / gain[y]) if sz[y]["gpus"] else 0

    # Owned fleet: whole servers bought when the pooled need exceeds the installed capacity; each cohort is
    # replaced after the refresh period if still needed, by newer servers that do more per GPU. Never sold.
    cohorts, fleet, sold = [], {}, {}
    for y in yrs:
        sold[y] = sum(n * k * capex_gpu * price[b] for b, n in cohorts if y - b >= max(life, R)) * resale
        cohorts = [(b, n) for b, n in cohorts if y - b < max(life, R)]
        need_cap = (sz[y]["gpus"] + spare * k * gain[y]) if sz[y]["gpus"] else 0
        have_cap = sum(n * k * gain[b] for b, n in cohorts)
        buy = _roundup((need_cap - have_cap) / (k * gain[y])) if need_cap > have_cap + 1e-9 else 0
        if buy:
            cohorts.append((y, buy))
        active = sum(n for _, n in cohorts) if (need_cap or cohorts) else 0
        cap = sum(n * k * gain[b] for b, n in cohorts)
        old = sum(n for b, n in cohorts if y - b >= R)       # past the refresh period: kept, out of warranty
        fleet[y] = dict(servers=active, gpus=active * k, buy=buy, capacity=cap, gpus_old=old * k)
    peak_it_kw = max((f["gpus"] for f in fleet.values()), default=0) * kw_gpu
    first = next((y for y in yrs if fleet[y]["gpus"]), None)
    # Own data centre: built once, in the first year of use, for the peak installed IT load plus a spare buffer.
    design_kw = peak_it_kw * (1 + d["facility_buffer"]["value"])
    bc = build_cost_per_mw(design_kw / 1000, p.country, hw, d, scenario)
    per_mw = q.get("facility_capex_usd_per_mw_it") or bc["value"]
    build = 0.0 if p.gov_dc == "ready" else design_kw / 1000 * per_mw
    fac_maint = maint * build                                # facility maintenance, 5% of build per year

    yearly = {o: {} for o in OPTIONS}
    parts = {o: {} for o in OPTIONS}
    for y in yrs:
        s, f = sz[y], fleet[y]
        # API: tokens priced per million; non-LLM rented as cloud GPU-hours
        yearly["API"][y] = (s["api_llm"] + s["api_units"]) * price_api[y] * api_disc + s["api_gpu_fallback"] * price[y]
        # GPU-as-a-service: reserved = the GPUs needed this year, rented all year; on demand = only the GPU-hours
        # of work, with autoscaling headroom (od_util), never more than renting all year.
        work_h = s["busy_h"] * 365 / gain[y]                 # GPU-hours of work on GPUs of that year
        if rent_mode == "on_demand":
            rent = min(s["gpus_rented"] * 8760, work_h / od_util) * rate_od
            idle_rent = 0.0
        else:
            rent = s["gpus_rented"] * 8760 * rate
            idle_rent = max(0.0, s["gpus_rented"] * 8760 - work_h)
        night_rent = share_night * idle_rent
        yearly["GPU-as-a-service"][y] = (rent - night_rent * night_rate) * price[y]
        s["gpu_hours_billed"] = rent / (rate_od if rent_mode == "on_demand" else rate) if rent else 0.0
        g = f["gpus"]
        util = min(1.0, s["busy_h"] / (f["capacity"] * 24)) if g else 0.0   # busy share of installed capacity
        idle_h = (1 - util) * g * 8760                       # idle GPU-hours of the installed fleet
        night_h = share_night * idle_h                       # opened to universities and research (optional)
        it_kwh = g * kw_gpu * (idle + (1 - idle) * util) * 8760 + night_h * kw_gpu * (1 - idle)
        gpu_capex = f["buy"] * k * capex_gpu * price[y]
        common = dict(gpu_servers=gpu_capex, network_storage_security=infra * gpu_capex, software=g * software_gpu,
                      maintenance_gpu=maint * capex_gpu * ((g - f["gpus_old"]) + maint_old * f["gpus_old"]),
                      staff=staff_fte(g, d) * fte_cost if g else 0.0,
                      energy=it_kwh * pue * cp["kwh"])
        if resale:
            common["resale"] = -sold[y]
        if share_night:
            common["shared_capacity_value"] = -night_h * night_rate * price[y]
        s["night_hours"], s["night_hours_rented"] = night_h, night_rent
        cpr = colo_price(dict(p.country, _quotes=q), d, scenario, peak_it_kw)
        colo = dict(common, colocation=g * kw_gpu * cpr["value"] * 12)
        fb = build if y == first else 0.0
        own = dict(common, facility_build=fb, maintenance_facility=fac_maint if first and y >= first else 0.0)
        parts["Owned + colocation"][y], parts["Owned + own data centre"][y] = colo, own
        yearly["Owned + colocation"][y] = sum(colo.values())
        yearly["Owned + own data centre"][y] = sum(own.values())
    pv = {o: sum(disc[y] * yearly[o][y] for y in yrs) for o in OPTIONS}
    pv_parts = {o: {} for o in ("Owned + colocation", "Owned + own data centre")}
    for o in pv_parts:
        for y in yrs:
            for kk, v in parts[o][y].items():
                pv_parts[o][kk] = pv_parts[o].get(kk, 0.0) + disc[y] * v
    return dict(pv=pv, yearly=yearly, pv_parts=pv_parts, yearly_parts=parts, disc=disc, fleet=fleet, sizing=sz, hardware=hw["id"],
                peak_it_kw=peak_it_kw, peak_facility_kw=peak_it_kw * pue, pue=pue, design_it_kw=design_kw,
                colo=colo_price(dict(p.country, _quotes=q), d, scenario, peak_it_kw),
                facility_capex=build, facility_maint_year=fac_maint, build_per_mw=per_mw, build_curve=bc,
                gpu_hour=rate, gpu_hour_on_demand=rate_od, rental_reference=rent_ref, rental_mode=rent_mode,
                api_reference=ref, api_prices_used=prices, server_life=max(life, R),
                end_policy=end_policy, resale_share=resale, night_share=share_night, night_rate=night_rate,
                capex_gpu=capex_gpu, first_year=first, compute_gain=cg, gain=gain,
                tokens_pv_m=sum(disc[y] * sz[y]["annual_eq_m"] for y in yrs))


def _hardware(p, catalogue, d, api_prices, meta, ids=None):
    """Hardware with the lowest cost among the GPU options (rental and owned) for this set of applications.

    The API option does not depend on the hardware, so it is left out of the choice (v0.9.11: when the API was the
    cheapest, every profile tied and the first one was kept)."""
    hw_list = catalogue["hardware"]
    air = next(h for h in hw_list if h["weak_grid_ok"])
    dem = demand_rows(p, d)
    probe = size_tier(POOL, [dict(r, tier=POOL) for r in dem if ids is None or r["id"] in ids],
                      [dict(w, tier=POOL) for w in nontoken_rows(p, d) if ids is None or w["id"] in ids],
                      air, d, p.speed, p.country)
    best = None
    for h in candidate_hardware(p, hw_list, probe["it_kw"] / 1000, d):
        e = evaluate(p, d, h, api_prices, meta, "base", ids)
        key = min(v for o, v in e["pv"].items() if o != "API")
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
        pv = res["base"]["pv"]
        # Below the GPU threshold the GPU options cost nothing extra: the work fits on spare capacity of GPUs bought
        # for other applications. That is not a price, so the cheapest priced option is the API.
        spare = pv["API"] > 0 and not any(pv[o] for o in OPTIONS if o != "API")
        return dict(base=res["base"], range={o: {sc: res[sc]["pv"][o] for sc in SCENARIOS} for o in OPTIONS},
                    cheapest="API" if spare else min(pv, key=pv.get), spare_capacity=spare)

    apps = {i: run_set({i}) for i in ids}
    total = run_set(set(ids)) if ids else None
    return dict(apps=apps, total=total,
                sum_standalone={o: sum(a["base"]["pv"][o] for a in apps.values()) for o in OPTIONS})


def with_no_placement(p):
    """All applications in one pool: placement does not apply in the options view."""
    return dataclasses.replace(p, class_to_tier={c: POOL for c in (1, 2, 3, 4)})
