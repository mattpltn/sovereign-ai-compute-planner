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
