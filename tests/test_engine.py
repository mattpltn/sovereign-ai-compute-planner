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


def v01_profile():
    p = default_profile("XEX")
    p.apps = deepcopy(V01)
    return p


def base_run(**kw):
    p = v01_profile()
    p.hardware_choice = "P1"  # the Excel uses P1 for every tier
    for k, v in kw.items():
        setattr(p, k, v)
    return p, run(p, CAT, D)


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
    r = run(p, CAT, D)
    _, r0 = base_run()
    assert r["tiers"]["T2"]["sizing"]["gpus"] < r0["tiers"]["T2"]["sizing"]["gpus"]
    assert r["tiers"]["T3"]["sizing"]["gpus"] > r0["tiers"]["T3"]["sizing"]["gpus"]


def test_weak_grid_forces_air_cooled():
    p = default_profile("XEX")
    r = run(p, CAT, D)  # auto hardware, 5 outages/month
    assert all(r["tiers"][t]["hardware"] == "P1" for t in r["tiers"])


def test_quote_overrides_range():
    p = default_profile("XEX")
    p.quotes = {"gpu_hour_usd": 3.0}
    r = run(p, CAT, D)
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
