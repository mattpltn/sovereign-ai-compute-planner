"""The engine must reproduce Sovereign_AI_Compute_Planner_v0.1.xlsx on the example country.

Parity tests use the frozen v0.1 catalogue (tests/fixtures). The live catalogue has since moved to sourced defaults.
"""
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from engine import default_profile, load_catalogue, load_defaults, run

CAT, D = load_catalogue(), load_defaults()
V01 = yaml.safe_load((Path(__file__).parent / "fixtures" / "use_cases_v01.yaml").read_text())
HW01 = yaml.safe_load((Path(__file__).parent / "fixtures" / "hardware_v01.yaml").read_text())
CAT01 = {**CAT, "hardware": HW01}
# v0.1 parity: fixed diversity, flat staff, no discounting, free cached input.
D01 = deepcopy(D)
D01["diversity_mode"]["value"] = "fixed"
D01["staff_mode"]["value"] = "flat"
D01["facility_mode"]["value"] = "flat"
D01["throughput_uncertainty"] = {"low": 1.0, "base": 1.0, "high": 1.0}
for k in ("discount_rate", "demand_growth", "price_decline"):
    D01[k]["value"] = 0.0
for sc in ("low", "base", "high"):
    D01["costs"]["cached_input_price_share"][sc] = 0.0


def v01_profile():
    p = default_profile("XEX")
    p.apps = deepcopy(V01)
    p.shared_sovereign_site = False     # v0.1 had separate tiers
    return p


def base_run(**kw):
    p = v01_profile()
    p.hardware_choice = "P1"  # the Excel uses P1 for every tier
    for k, v in kw.items():
        setattr(p, k, v)
    return p, run(p, CAT01, D01)


def test_gpus_match_excel():
    _, r = base_run()
    assert [r["tiers"][t]["sizing"]["gpus"] for t in ("T1", "T2", "T3", "T4")] == [1, 184, 57, 31]


def test_facility_mw_matches_excel():
    _, r = base_run()
    assert r["totals"]["facility_mw"] == pytest.approx(0.74256, rel=1e-6)


def test_users_match_excel():
    _, r = base_run()
    u = {x["id"]: x["users"] for x in r["demand"]}
    assert u["UC01"] == pytest.approx(352664.6, rel=1e-5)
    assert u["UC02"] == 36000
    assert u["UC13"] == 0


def test_tco_matches_excel():
    _, r = base_run()
    t4 = r["tiers"]["T4"]
    assert t4["cheapest_mode"] == "Owned"
    assert t4["cheapest_cost"] == pytest.approx(8326258.896, rel=1e-6)
    assert r["tiers"]["T3"]["cheapest_mode"] == "GPU-as-a-service"
    assert r["tiers"]["T2"]["cheapest_cost"] == pytest.approx(3830173.497, rel=1e-6)


def test_ladder_steps():
    _, r = base_run()
    assert r["tiers"]["T2"]["step"].startswith("Step 0")
    assert r["tiers"]["T3"]["step"].startswith("Step 1")


def test_split_moves_traffic_between_tiers():
    p = v01_profile()
    p.hardware_choice = "P1"
    uc09 = next(a for a in p.apps if a["id"] == "UC09")
    uc09["traffic_split"] = {2: 0.5, 3: 0.5}
    r = run(p, CAT01, D01)
    _, r0 = base_run()
    assert r["tiers"]["T2"]["sizing"]["gpus"] < r0["tiers"]["T2"]["sizing"]["gpus"]
    assert r["tiers"]["T3"]["sizing"]["gpus"] > r0["tiers"]["T3"]["sizing"]["gpus"]


def test_weak_grid_forces_air_cooled():
    p = default_profile("XEX")
    r = run(p, CAT, D)  # auto hardware, 5 outages/month
    air = {h["id"] for h in CAT["hardware"] if h["weak_grid_ok"]}
    assert all(r["tiers"][t]["hardware"] in air for t in r["tiers"])


def test_quote_overrides_range():
    p = default_profile("XEX")
    p.quotes = {"gpu_hour_usd": 3.0}
    dq = deepcopy(D)
    dq["throughput_uncertainty"] = {"low": 1.0, "base": 1.0, "high": 1.0}
    r = run(p, CAT, dq)
    tco = r["tiers"]["T3"]["tco"]
    # with a quoted GPU-hour, the GPUaaS cost no longer varies across scenarios
    assert tco["low"]["GPU-as-a-service"] == pytest.approx(tco["high"]["GPU-as-a-service"])


def test_tco_range_ordered():
    _, r = base_run()
    rng = r["tiers"]["T4"]["cost_range"]
    assert rng["low"] < rng["base"] < rng["high"]


# ---------------------------------------------------------------- sourced defaults
def chat_task_tokens(a):
    k = a["agent_steps"] * a["retry"]
    return (a["isl"] + a["system_prompt_tokens"] + a["osl"] + a["reasoning_tokens"]) * k


def test_every_default_has_evidence_and_confidence():
    for a in CAT["use_cases"]:
        assert a.get("evidence"), a["id"]
        assert set(a["confidence"]) == {"volume", "tokens"}, a["id"]


def test_agent_multipliers_match_anthropic_ranges():
    by = {a["id"]: a for a in CAT["use_cases"]}
    chat = chat_task_tokens(by["UC02"])
    assert 3 <= chat_task_tokens(by["UC08"]) / chat <= 7        # single agent ~4x [S35]
    for uid in ("UC09", "UC12"):
        assert 8 <= chat_task_tokens(by[uid]) / chat <= 20      # multi-agent ~15x [S35]


def test_citizen_rate_matches_calibration():
    p = default_profile("XEX")
    p.country = dict(p.country, egdi=D["global_egdi_average"]["value"])  # no EGDI adjustment
    r = run(p, CAT, D)
    uc01 = next(x for x in r["demand"] if x["id"] == "UC01")
    per_10k = uc01["sessions"] / p.country["population"] * 10000
    assert per_10k == pytest.approx(5, rel=0.02)


# ---------------------------------------------------------------- archetypes (v0.2 builder)
from engine.archetypes import build_profile, load_archetypes  # noqa: E402

ARCH = load_archetypes()


def test_copilot_volume_from_user_input():
    p = build_profile(default_profile("XEX").country, "Base",
                      [dict(uid="a", name="x", type="staff_copilot", volume=1000, data_class=3)],
                      ARCH, dict(D["class_to_tier"]))
    r = run(p, CAT, D)
    assert r["demand"][0]["sessions"] == pytest.approx(1400)   # 1.4 requests per person with access [S36]
    assert r["demand"][0]["tier"] == "T3"


def test_scenario_and_override_change_result():
    c = default_profile("XEX").country
    app = dict(uid="a", name="x", type="staff_copilot", volume=50000, data_class=3)
    g = lambda amb, a: run(build_profile(c, amb, [a], ARCH, dict(D["class_to_tier"])), CAT, D)["totals"]["gpus"]
    assert g("Low", app) < g("Base", app) < g("High", app)
    assert g("Base", dict(app, rate_override=10)) > g("Base", app)


def test_nontoken_archetype_and_fine_tuning():
    c = default_profile("XEX").country
    apps = [dict(uid="s", name="stt", type="speech_to_text", volume=500, data_class=3),
            dict(uid="f", name="ft", type="fine_tuning", volume=36500, data_class=3)]
    r = run(build_profile(c, "Base", apps, ARCH, dict(D["class_to_tier"])), CAT, D)
    ft = next(x for x in r["nontoken"] if x["id"] == "f")
    assert ft["gpu_hours_day"] == pytest.approx(100 / D["production_derating"]["value"])
    assert r["tiers"]["T3"]["sizing"]["gpus"] > 0


def test_all_archetypes_have_evidence():
    for a in ARCH.values():
        assert a["evidence"] and set(a["confidence"]) == {"volume", "tokens"}


def test_liquid_vs_air_gap_matches_independent_benchmarks():
    hw = {h["id"]: h for h in CAT["hardware"]}
    ratio_L = hw["P2"]["tokens_per_s_per_gpu"]["L"]["base"] / hw["P1"]["tokens_per_s_per_gpu"]["L"]["base"]
    assert 5 <= ratio_L <= 9          # InferenceX: 4.6-7.3x at 65-130 tok/s/user [S44], not NVIDIA's 65x [S02]


def test_reliable_grid_and_large_load_allows_liquid():
    c = dict(default_profile("XEX").country, outages_per_month=0)
    apps = [dict(uid="a", name="x", type="research_agent", volume=400000, data_class=3)]
    r = run(build_profile(c, "Base", apps, ARCH, dict(D["class_to_tier"])), CAT, D)
    assert r["tiers"]["T3"]["hardware"] == "P2"


# ---------------------------------------------------------------- v0.3 review items
from engine.archetypes import volume_warning  # noqa: E402
from engine.model import diversity, staff_fte  # noqa: E402


def one(apps, **kw):
    c = dict(default_profile("XEX").country, **kw.pop("country", {}))
    p = build_profile(c, "Base", apps, ARCH, dict(D["class_to_tier"]), hardware_choice=kw.pop("hw", "auto"))
    for k, v in kw.items():
        setattr(p, k, v)
    return run(p, CAT, D)


COP = dict(uid="a", name="cop", type="staff_copilot", volume=50000, data_class=3)
DOC = dict(uid="b", name="doc", type="document_extraction", volume=20000, data_class=3)


def test_diversity_scales_with_number_of_apps():
    assert diversity(1, D) == 1.0
    assert diversity(2, D) == pytest.approx(0.6 + 0.4 / 2 ** 0.5)
    assert diversity(16, D) == pytest.approx(0.7)
    assert one([COP])["tiers"]["T3"]["sizing"]["diversity"] == 1.0
    assert one([COP, DOC])["tiers"]["T3"]["sizing"]["n_apps"] == 2


def test_response_speed_changes_gpus():
    fast = one([COP], speed="low")["tiers"]["T3"]["sizing"]["gpus"]
    relaxed = one([COP], speed="high")["tiers"]["T3"]["sizing"]["gpus"]
    assert fast > relaxed


def test_all_modes_and_winner_flag_present():
    t = one([COP])["tiers"]["T3"]
    assert set(t["tco"]["base"]) == {"GPU-as-a-service", "Owned"}
    assert isinstance(t["winner_changes"], bool) and set(t["winners"]) == {"low", "base", "high"}


def test_discounting_and_growth():
    base = one([COP])["tiers"]["T3"]["tco"]["base"]["GPU-as-a-service"]
    undisc = one([COP], finance={"discount_rate": 0.0})["tiers"]["T3"]["tco"]["base"]["GPU-as-a-service"]
    grown = one([COP], finance={"demand_growth": 0.2})["tiers"]["T3"]["tco"]["base"]["GPU-as-a-service"]
    cheaper = one([COP], finance={"price_decline": 0.2})["tiers"]["T3"]["tco"]["base"]["GPU-as-a-service"]
    assert base < undisc and grown > base and cheaper < base


def test_staff_scales_with_gpus():
    assert staff_fte(0, D) == 0
    assert staff_fte(1, D) == pytest.approx(2.01)
    assert staff_fte(300, D) == pytest.approx(5)


def test_below_gpu_threshold():
    r = one([dict(uid="f", name="face", type="face_verification", volume=100000, data_class=4)])
    t4 = r["tiers"]["T4"]
    assert t4["sizing"]["below_threshold"] and t4["sizing"]["gpus"] == 0
    assert t4["step"].startswith("Below GPU threshold")


def test_steps_thresholds():
    from engine.model import step_for
    sz = dict(below_threshold=False, gpus=10, facility_mw=5)
    assert step_for("T3", sz, D, "Owned", {"facility_kw": 5000, "servers": 3}).startswith("Step 2: own 3 servers in a colocation")
    assert step_for("T3", sz, D, "Owned", {"facility_kw": 12000, "servers": 90}).startswith("Step 3")
    assert step_for("T4", sz, D, "Owned", {"facility_kw": 500, "servers": 1}).startswith("Step 1: own 1 server")
    assert step_for("T3", sz, D, "GPU-as-a-service").startswith("Step 1: rent GPUs from an in-country provider")
    assert step_for("T2", sz, D, "API / managed").startswith("Step 0: buy as an API service")


def test_unknown_grid_never_ok():
    r = one([COP], country={"outages_per_month": None})
    t = r["tiers"]["T3"]
    assert t["grid"].startswith("Unknown")
    assert t["hardware"] in {h["id"] for h in CAT["hardware"] if h["weak_grid_ok"]}


def test_cached_input_is_priced():
    cit = dict(uid="c", name="cit", type="citizen_assistant", volume=5_000_000, data_class=2)
    with_cache = one([cit])["tiers"]["T2"]["tco"]["base"]["API / managed"]
    d0 = deepcopy(D)
    d0["costs"]["cached_input_price_share"]["base"] = 0.0
    c = dict(default_profile("XEX").country)
    free = run(build_profile(c, "Base", [cit], ARCH, dict(D["class_to_tier"])), CAT, d0)["tiers"]["T2"]["tco"]["base"]["API / managed"]
    assert with_cache > free


def test_volume_warning():
    c = default_profile("XEX").country   # 400,000 civil servants
    assert volume_warning(dict(type="research_agent", volume=20000), c, ARCH)
    assert volume_warning(dict(type="research_agent", volume=200), c, ARCH) is None
    assert volume_warning(dict(type="staff_copilot", volume=500000), c, ARCH)


# ---------------------------------------------------------------- facility, rent vs own, allocation
from engine.model import facility_for  # noqa: E402


def test_facility_by_country_and_cooling():
    hw = {h["id"]: h for h in CAT["hardware"]}
    ken = dict(iso3="KEN", region="Sub-Saharan Africa")
    air, liq = facility_for(ken, hw["P1"], D), facility_for(ken, hw["P2"], D)
    assert air["pue"] == pytest.approx(1.79) and liq["pue"] < air["pue"]
    assert air["capex_per_mw"] == pytest.approx(10.03e6)
    assert liq["capex_per_mw"] == pytest.approx(10.03e6 * 1.085)
    assert facility_for(dict(iso3="TZA", region="Sub-Saharan Africa"), hw["P1"], D)["capex_src"].startswith("Sub-Saharan Africa proxy")


def test_rent_vs_own_details_and_allocation():
    r = one([COP, DOC])
    t = r["tiers"]["T3"]
    own = t["detail"]["base"]["Owned"]
    assert own["upfront"] == pytest.approx(own["facility_capex"] + own["gpu_capex_y1"])
    assert t["detail"]["base"]["GPU-as-a-service"]["annual_y1"] > 0
    total = sum(sum(v.values()) for v in r["by_app"].values())
    assert total == pytest.approx(r["totals"]["cost"])


def test_throughput_uncertainty_widens_gpu_range():
    r = one([COP, DOC])
    g = r["totals"]["gpus_range"]
    assert g["low"] <= g["base"] <= g["high"] and g["low"] < g["high"]


# ---------------------------------------------------------------- v0.5: servers, shared site, local provider
def test_owned_capacity_in_whole_servers():
    r = one([dict(uid="t", name="tax", type="process_agent", volume=2000, data_class=4)])
    cap = r["tiers"]["T4"]["capacity"]
    assert cap["kind"] == "build" and cap["gpus"] % 8 == 0 and cap["servers"] == cap["gpus"] // 8


def test_api_tiers_build_nothing():
    r = one([dict(uid="c", name="cit", type="citizen_assistant", volume=5_000_000, data_class=2)])
    t2 = r["tiers"]["T2"]
    if t2["cheapest_mode"] == "API / managed":
        assert t2["capacity"]["kind"] == "service" and t2["capacity"]["gpus"] is None


def test_no_local_provider_forces_owned_t3_and_shared_site():
    apps = [COP, dict(uid="t", name="tax", type="process_agent", volume=2000, data_class=4)]
    r = one(apps, local_gpu_provider=False)
    assert r["tiers"]["T3"]["merged_into"] == "T4"
    assert r["tiers"]["T3"]["sizing"]["gpus"] == 0 and r["tiers"]["T4"]["shared_site"]
    sep = one(apps, local_gpu_provider=False, shared_sovereign_site=False)
    assert "GPU-as-a-service" not in sep["tiers"]["T3"]["tco"]["base"]
    assert r["totals"]["cost"] < sep["totals"]["cost"]          # one team, pooled servers


def test_server_rounding_reaches_physical_figures():
    r = one([dict(uid="t", name="tax", type="process_agent", volume=2000, data_class=4)])
    t4 = r["tiers"]["T4"]
    assert t4["cheapest_mode"] == "Owned"
    sz, cap = t4["sizing"], t4["capacity"]
    assert sz["gpus"] % 8 == 0 and sz["gpus"] == cap["gpus"]
    assert sz["it_kw"] == pytest.approx(cap["it_kw"])
    assert sz["facility_mw"] * 1000 == pytest.approx(cap["facility_kw"])


def test_active_days_scale_annual_not_peak():
    # Rates are per active day: annual tokens use active days, peak sizing uses the active-day rate.
    r = one([COP])
    x = r["demand"][0]
    assert x["active_days"] == 250
    assert x["annual_eq_m"] == pytest.approx(x["daily_eq"] * 250 / 1e6)
    full = dict(ARCH["staff_copilot"], active_days_per_year=365)
    p = build_profile(default_profile("XEX").country, "Base", [COP], dict(ARCH, staff_copilot=full), dict(D["class_to_tier"]))
    y = run(p, CAT, D)["demand"][0]
    assert y["peak_eq_tps"] == pytest.approx(x["peak_eq_tps"])
    assert y["annual_eq_m"] == pytest.approx(x["annual_eq_m"] * 365 / 250)


def test_every_archetype_states_its_basis():
    for t in ARCH.values():
        assert t.get("basis"), t["id"]
        if "rate" in t:
            assert t.get("active_days_per_year") in (190, 250, 300, 365), t["id"]


def test_evidence_based_rates():
    # OpenEvidence 37.1 queries per active physician-month [S62]; EEF/NFER ~1.7 AI-assisted preparations per week [S63]
    assert ARCH["frontline_health"]["rate"]["base"] == pytest.approx(37.1 * 12 / 365, rel=0.25)
    assert ARCH["teacher_assistant"]["rate"]["base"] == pytest.approx(1.7 / 5 * 3, rel=0.05)
    assert ARCH["ocr"]["gpu_seconds_per_unit"] == pytest.approx(0.74, rel=0.05)   # PP-OCRv5 on A10 [S64]


def test_agent_token_totals_include_retry():
    tok = lambda t: (t["isl"] + t["system_prompt_tokens"] + t["osl"] + t["reasoning_tokens"]) * t["agent_steps"] * t["retry"]
    assert tok(ARCH["staff_copilot"]) == pytest.approx(3740)     # 3,400 before the x1.1 retry
    assert tok(ARCH["research_agent"]) == pytest.approx(55000)   # 50,000 before the x1.1 retry


def test_grid_from_outages_then_firm_share():
    from engine.model import grid_weak
    assert grid_weak({"outages_per_month": 5}, D) is True
    assert grid_weak({"outages_per_month": 0.5, "firms_with_outages_share": 0.9}, D) is False   # per-month figure wins
    assert grid_weak({"firms_with_outages_share": 0.74}, D) is True    # e.g. Ghana, 74% of firms
    assert grid_weak({"firms_with_outages_share": 0.15}, D) is False
    assert grid_weak({}, D) is None
    r = one([COP], country={"outages_per_month": None, "firms_with_outages_share": 0.74})
    assert all(t["hardware"] in {h["id"] for h in CAT["hardware"] if h["weak_grid_ok"]} for t in r["tiers"].values() if t.get("hardware"))


def test_snapshot_units_are_sane():
    import json
    snap = json.loads((Path(__file__).resolve().parent.parent / "data/snapshots/countries.json").read_text())
    for iso, c in snap.items():
        if iso == "_meta":
            continue
        assert "IC.ELC.OUTG.ZS" not in c.get("_sources", {}).get("outages_per_month", ""), iso
        s = c.get("public_employment_share")
        assert s is None or 0.005 < s < 0.6, (iso, s)


# ---------------------------------------------------------------- agriculture advisory (v0.7)
import json  # noqa: E402

from engine.archetypes import low_usage_note, normalize_app, volume_warning  # noqa: E402
from sync.worldbank import check_metadata, derive_agri, store  # noqa: E402

SNAP = json.loads((Path(__file__).resolve().parent.parent / "data/snapshots/countries.json").read_text())
TOL = D["agri_volume_tolerance"]["value"]


def _est(share=0.03, year=2025):
    """Estonia: synced labour force and unemployment; ILO agriculture share supplied here (~3%) so the test
    does not depend on the next sync."""
    c = json.loads(json.dumps(SNAP["EST"]))
    c.pop("agri_employment_share", None)              # ignore whatever the last sync stored
    c["_sources"].pop("agri_employment_share", None)
    if share is not None:
        c["agri_employment_share"] = share
        c["_sources"]["agri_employment_share"] = f"World Bank API SL.AGR.EMPL.ZS, {year}"
    derive_agri(c)
    return c


def _agri(volume, basis=None):
    a = dict(uid="g", name="Agri", type="agriculture_advisory", volume=volume, data_class=2)
    if basis:
        a["population_basis"] = basis
    return a


def test_sync_agri_parse_store_and_unknown():
    meta = [{"page": 1}, [{"id": "SL.AGR.EMPL.ZS", "name": "Employment in agriculture (% of total employment) (modeled ILO estimate)",
                           "source": {"id": "2", "value": "World Development Indicators"}}]]
    m = check_metadata("SL.AGR.EMPL.ZS", meta, r"^employment in agriculture \(% of total employment\)")
    assert m["source_id"] == 2 and "modeled ILO" in m["name"]
    with pytest.raises(ValueError):   # code renamed or repurposed: stop
        check_metadata("SL.AGR.EMPL.ZS", [{}, [{"id": "SL.AGR.EMPL.ZS", "name": "Something else", "source": {"id": "2", "value": ""}}]],
                       r"^employment in agriculture")
    with pytest.raises(ValueError):   # missing
        check_metadata("SL.AGR.EMPL.ZS", [{"message": "not found"}], r".")
    data = {"EST": {"_sources": {}}}
    store(data, "agri_employment_share", "SL.AGR.EMPL.ZS", {"EST": (3.0, "2025")}, lambda v: v / 100)
    assert data["EST"]["agri_employment_share"] == pytest.approx(0.03)
    assert data["EST"]["_sources"]["agri_employment_share"] == "World Bank API SL.AGR.EMPL.ZS, 2025"
    assert "agri_workers_est" not in _est(share=None)          # missing: unknown
    assert "agri_workers_est" not in _est(year=2012)           # older than 2015: unknown


def test_estonia_150k_farmers_warns():
    c = _est()
    assert 15000 < c["agri_workers_est"] < 25000
    w = volume_warning(_agri(150000), c, ARCH, TOL)
    assert w and "7×" in w and "Estonia" in w and "ILO modeled" in w


def test_estonia_15k_farmers_no_warning():
    assert volume_warning(_agri(15000), _est(), ARCH, TOL) is None


def test_unknown_agri_data_no_warning():
    assert volume_warning(_agri(150000), _est(share=None), ARCH, TOL) is None
    assert volume_warning(_agri(150000), {"name": "Nowhere"}, ARCH, TOL) is None


def test_population_basis_rates():
    c = default_profile("XEX").country
    req = lambda a: run(build_profile(c, "Base", [a], ARCH, dict(D["class_to_tier"])), CAT, D)["demand"][0]["sessions"]
    assert req(_agri(150000, "eligible")) == pytest.approx(75)
    assert req(_agri(150000, "users")) == pytest.approx(15000)


def test_old_scenario_loads_as_eligible():
    old = _agri(150000)                       # saved before v0.7: no population_basis
    assert normalize_app(old)["population_basis"] == "eligible"
    c = default_profile("XEX").country
    r = lambda a: run(build_profile(c, "Base", [a], ARCH, dict(D["class_to_tier"])), CAT, D)["totals"]
    assert r(old) == r(normalize_app(old)) == r(_agri(150000, "eligible"))


def test_low_usage_note():
    assert low_usage_note(_agri(150000, "eligible"), ARCH, "Base")
    assert low_usage_note(_agri(150000, "users"), ARCH, "Base") is None
    assert low_usage_note(dict(COP), ARCH, "Base") is None    # not a population type


def test_owned_pv_breakdown_adds_up():
    r = one([COP], shared_sovereign_site=False, local_gpu_provider=False)
    for v in r["tiers"].values():
        own = v["detail"]["base"].get("Owned")
        if own and own["gpus"]:
            tot = v["tco"]["base"].get("Owned")
            pv = own["pv_breakdown"]
            assert all(x >= 0 for x in pv.values())
            assert pv["gpu_servers"] > 0 and pv["facility_build"] > 0
            if tot:
                assert sum(pv.values()) == pytest.approx(tot)


# ---------------------------------------------------------------- custom types, save links (v0.7)
from engine.archetypes import CUSTOM_TEMPLATE, parse_custom_types  # noqa: E402


def test_custom_template_parses_and_runs():
    types, errs = parse_custom_types(CUSTOM_TEMPLATE.read_text(), ARCH)
    assert not errs and len(types) == 2 and all(k.startswith("custom_") for k in types)
    arch = {**ARCH, **types}
    apps = [dict(uid="c1", name="Proc", type="custom_procurement_assistant", volume=1000, data_class=3),
            dict(uid="c2", name="Plates", type="custom_plate_recognition", volume=100000, data_class=3)]
    p = build_profile(default_profile("XEX").country, "Base", apps, arch, dict(D["class_to_tier"]))
    r = run(p, CAT, D)
    assert r["demand"][0]["sessions"] == pytest.approx(1500) and r["nontoken"]


def test_custom_template_rejects_bad_rows():
    bad = CUSTOM_TEMPLATE.read_text().splitlines()
    bad[1] = bad[1].replace(",M,", ",XL,")        # invalid model size
    types, errs = parse_custom_types("\n".join(bad), ARCH)
    assert len(types) == 1 and len(errs) == 1 and "model_class" in errs[0]


def test_save_link_round_trip():
    import importlib.util
    spec = importlib.util.spec_from_file_location("app_mod", Path(__file__).resolve().parent.parent / "app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sc = {"iso": "GHA", "apps": [_agri(150000, "users")], "custom_types": parse_custom_types(CUSTOM_TEMPLATE.read_text())[0]}
    txt = mod.encode_state(sc)
    assert all(ch.isalnum() or ch in "-_" for ch in txt)
    assert mod.decode_state(txt) == json.loads(json.dumps(sc))


# ---------------------------------------------------------------- in-country capability (v0.8)
def test_no_residency_cloud_keeps_internal_data_in_country():
    app = dict(uid="t", name="Teach", type="teacher_assistant", volume=20000, data_class=2)
    r0 = one([app])
    assert r0["demand"][0]["tier"] == "T2" and r0["tiers"]["T2"]["location"].endswith("(API)")
    r1 = one([app], residency_cloud="none", local_gpu_provider=False)
    assert r1["demand"][0]["tier"] == "T3" and r1["placement_notes"]
    assert r1["tiers"]["T3"]["cheapest_mode"] == "Owned"
    assert r1["tiers"]["T3"]["location"] == "Government data centre"


def test_existing_government_dc_drops_facility_build():
    app = [dict(COP, data_class=4)]
    fit, ready = one(app, gov_dc="fitout"), one(app, gov_dc="ready")
    f = fit["tiers"]["T4"]["detail"]["base"]["Owned"]
    g = ready["tiers"]["T4"]["detail"]["base"]["Owned"]
    assert f["facility_capex"] > 0 and g["facility_capex"] == 0 and g["pv_breakdown"]["facility_build"] == 0
    assert ready["totals"]["cost"] < fit["totals"]["cost"]
    assert "existing government data centre" in ready["tiers"]["T4"]["step"]


def test_colocation_for_confidential_owned_servers():
    app = [dict(COP, data_class=3)]
    r = one(app, local_gpu_provider=False, colocation=True, gov_dc="ready")
    t = r["tiers"]["T3"]
    assert t["cheapest_mode"] == "Owned" and "colocation" in t["location"] and "colocation" in t["step"]
    assert t["detail"]["base"]["Owned"]["facility_capex"] > 0        # colocation is not the government's existing room


def test_shared_site_label():
    r = one([dict(COP, data_class=3), dict(DOC, data_class=4)], local_gpu_provider=False)
    assert r["tiers"]["T4"]["location"] == "Government data centre" and r["tiers"]["T4"]["shared_site"]
    assert "government data centre" in r["tiers"]["T3"]["step"]


# ---------------------------------------------------------------- four options, start year and growth (v0.9)
import math as _m  # noqa: E402

from engine.data import load_countries  # noqa: E402
from engine.options import OPTIONS, colo_price, compare, evaluate, with_no_placement  # noqa: E402

COUNTRIES_ = load_countries()


def _opts(apps, meta, iso="GHA", **kw):
    c = dict(COUNTRIES_[iso], iso3=iso)
    p = with_no_placement(build_profile(c, "Base", apps, ARCH, dict(D["class_to_tier"])))
    for k, v in kw.items():
        setattr(p, k, v)
    return compare(p, CAT, D, None, meta)


APPS3 = [dict(COP, uid="cop", volume=40000), dict(uid="tut", name="Tutor", type="tutor", volume=200000, data_class=2),
         dict(uid="doc", name="Docs", type="document_extraction", volume=10000, data_class=3)]
META3 = {"cop": {"start_year": 1, "growth": 0.1}, "tut": {"start_year": 3, "growth": 0.3}, "doc": {"start_year": 2, "growth": 0}}


def test_start_year_means_no_cost_before():
    r = _opts(APPS3, META3)
    y = r["apps"]["tut"]["base"]["yearly"]
    assert all(y[o][1] == 0 and y[o][2] == 0 and y[o][3] > 0 for o in ("API", "GPU-as-a-service"))
    assert r["apps"]["tut"]["base"]["fleet"][2]["servers"] == 0 and r["apps"]["tut"]["base"]["fleet"][3]["servers"] > 0


def test_growth_raises_cost():
    flat = _opts(APPS3[:1], {"cop": {"start_year": 1, "growth": 0}})["total"]["base"]["pv"]
    grow = _opts(APPS3[:1], {"cop": {"start_year": 1, "growth": 0.3}})["total"]["base"]["pv"]
    assert grow["API"] > flat["API"] * 1.5 and grow["GPU-as-a-service"] >= flat["GPU-as-a-service"]


def test_pooled_capacity_never_exceeds_sum_of_standalone():
    r = _opts(APPS3, META3)
    for o in OPTIONS:
        assert r["total"]["base"]["pv"][o] <= r["sum_standalone"][o] * 1.0001
    assert r["total"]["base"]["pv"]["API"] == pytest.approx(r["sum_standalone"]["API"], rel=0.01)   # tokens are additive
    assert r["total"]["base"]["pv"]["Owned + own data centre"] < 0.6 * r["sum_standalone"]["Owned + own data centre"]


def test_fleet_covers_need_and_refreshes():
    b = _opts(APPS3, META3)["total"]["base"]
    k = 8
    for y, f in b["fleet"].items():
        assert f["servers"] >= _m.ceil(b["sizing"][y]["gpus"] / k)
    assert b["fleet"][6]["buy"] >= b["fleet"][1]["buy"]          # year-1 servers replaced after 5 years


def test_colocation_price_lookup():
    usa = colo_price({"iso3": "USA", "region": "North America"}, D, "base", 1000)
    assert usa["value"] == 196 and not usa["small"]
    gha = colo_price(dict(COUNTRIES_["GHA"], iso3="GHA"), D, "base", 20)
    assert gha["small"] and gha["value"] == pytest.approx(250 * 1.8)
    assert colo_price({"iso3": "USA", "_quotes": {"colo_usd_per_kw_month": 150}}, D)["value"] == 150


def test_existing_data_centre_drops_build():
    a = _opts(APPS3, META3)["total"]["base"]
    b = _opts(APPS3, META3, gov_dc="ready")["total"]["base"]
    assert a["pv_parts"]["Owned + own data centre"]["facility_build"] > 0
    assert b["pv_parts"]["Owned + own data centre"]["facility_build"] == 0
    assert b["pv"]["Owned + colocation"] == pytest.approx(a["pv"]["Owned + colocation"])


def test_facility_buffer_and_operations():
    b = _opts(APPS3, META3)["total"]["base"]
    assert b["design_it_kw"] == pytest.approx(b["peak_it_kw"] * 1.3)
    assert b["facility_capex"] == pytest.approx(b["design_it_kw"] / 1000 * b["build_per_mw"])
    assert b["facility_maint_year"] == pytest.approx(0.05 * b["facility_capex"])
    assert b["pv_parts"]["Owned + own data centre"]["maintenance_facility"] > 0


def test_mena_region_has_its_own_facility_values():
    from engine.model import facility_for
    egy = [k for k, v in COUNTRIES_.items() if (v.get("region") or "").startswith("Middle East")][0]
    f = facility_for(dict(COUNTRIES_[egy], iso3="ZZZ"), {"cooling": "Air"}, D)
    assert "proxy" in f["capex_src"] and f["capex_per_mw"] == pytest.approx(10.25e6)


def test_build_cost_size_curve():
    from engine.options import build_cost_per_mw
    xex = {"region": "", "iso3": "XEX"}                    # global default country: factor 1
    air = {"cooling": "Air"}
    for mw, musd in [(0.1, 40), (0.5, 30), (1, 25), (5, 22), (10, 20), (20, 15), (50, 12)]:
        assert build_cost_per_mw(mw, xex, air, D)["value"] == pytest.approx(musd * 1e6)
    assert build_cost_per_mw(0.01, xex, air, D)["value"] == pytest.approx(40e6)      # flat below 0.1 MW
    assert build_cost_per_mw(200, xex, air, D)["value"] == pytest.approx(12e6)       # flat above 50 MW
    assert 25e6 < build_cost_per_mw(0.75, xex, air, D)["value"] < 30e6
    gha = build_cost_per_mw(1, dict(COUNTRIES_["GHA"], iso3="GHA"), air, D)
    assert gha["value"] == pytest.approx(25e6 * 10.51 / 11.0)


def test_api_option_uses_per_unit_prices_for_non_llm():
    stt = [dict(uid="stt", name="Courts", type="speech_to_text", volume=500, data_class=3)]
    r = _opts(stt, {"stt": {"start_year": 1, "growth": 0}})["total"]["base"]
    assert r["yearly"]["API"][1] == pytest.approx(500 * 365 * 0.36)             # $0.006 per minute
    ded = [dict(uid="bd", name="Dedup", type="biometric_dedup", volume=500000, data_class=4)]
    rb = _opts(ded, {"bd": {"start_year": 1, "growth": 0}})["total"]["base"]
    assert rb["yearly"]["API"][1] == pytest.approx(rb["yearly"]["GPU-as-a-service"][1])   # no API: rented GPUs


# ---------------------------------------------------------------- review fixes (v0.9.5)
def test_citizen_assistant_population_basis():
    c = default_profile("XEX").country
    req = lambda b: run(build_profile(c, "Base", [dict(uid="c", name="C", type="citizen_assistant", volume=9_000_000,
                                                       data_class=2, population_basis=b)], ARCH, dict(D["class_to_tier"])),
                        CAT, D)["demand"][0]["sessions"]
    assert req("eligible") == pytest.approx(4500) and req("users") == pytest.approx(900_000)


def test_api_and_hardware_price_declines_are_separate():
    meta = {"cop": {"start_year": 1, "growth": 0}}
    r = _opts(APPS3[:1], meta)["total"]["base"]
    assert r["yearly"]["API"][2] == pytest.approx(r["yearly"]["API"][1] * 0.8)                       # 20% default
    assert r["yearly"]["GPU-as-a-service"][2] == pytest.approx(r["yearly"]["GPU-as-a-service"][1])     # 0% default


def test_owned_infrastructure_share_and_redundancy():
    meta = {"cop": {"start_year": 1, "growth": 0}}
    a = _opts(APPS3[:1], meta)["total"]["base"]
    y1 = a["yearly_parts"]["Owned + colocation"][1]
    assert y1["network_storage_security"] == pytest.approx(0.15 * y1["gpu_servers"])
    b = _opts(APPS3[:1], meta, redundancy=True)["total"]["base"]
    assert b["fleet"][1]["servers"] == a["fleet"][1]["servers"] + 1


def test_example_portfolio_sized_from_country():
    from engine.archetypes import example_portfolio
    gha, notes = example_portfolio(dict(COUNTRIES_["GHA"], iso3="GHA"))
    by = {a["type"]: a for a in gha}
    cs = COUNTRIES_["GHA"]["civil_servants"]
    assert by["staff_copilot"]["volume"] == pytest.approx(0.5 * cs, rel=0.05) and by["staff_copilot"]["growth"] == 0.02
    assert by["citizen_assistant"]["population_basis"] == "users" and len(notes) == len(gha)
    est, _ = example_portfolio(dict(COUNTRIES_["EST"], iso3="EST"))
    assert {a["type"]: a for a in est}["staff_copilot"]["volume"] < by["staff_copilot"]["volume"] / 3
    xex, notes_x = example_portfolio(default_profile("XEX").country)
    assert "agriculture_advisory" not in {a["type"] for a in xex} and any("left out" in n for n in notes_x)
