"""Turn user-defined applications (type + volume + data class) into engine rows."""
from __future__ import annotations

from pathlib import Path

import yaml

from .model import Profile

ROOT = Path(__file__).resolve().parent.parent


def load_archetypes() -> dict:
    data = yaml.safe_load((ROOT / "data" / "catalogue" / "archetypes.yaml").read_text())
    return {a["id"]: a for a in data}


def is_llm(arch: dict) -> bool:
    return "isl" in arch


def to_engine_rows(apps: list[dict], archetypes: dict) -> tuple[list, list]:
    """apps: [{uid, name, type, volume, data_class, rate_override?, model_class?, traffic_split?}]"""
    llm, nt = [], []
    for a in apps:
        t = archetypes[a["type"]]
        vol = float(a.get("volume") or 0)
        cls = int(a.get("data_class") or t["data_class"])
        if is_llm(t):
            r = a.get("rate_override")
            rate = {"low": r, "base": r, "high": r} if r else rate_for(a, t)
            llm.append(dict(
                id=a["uid"], name=a["name"], include=1, stage="Production", driver="Fixed",
                eligible_share=1, fixed_base=vol, pilot_users=0, citizen_facing=0,
                adoption_low=rate["low"], adoption_base=rate["base"], adoption_high=rate["high"],
                tasks_per_user_day=1,
                isl=t["isl"], osl=t["osl"], reasoning_tokens=t["reasoning_tokens"],
                agent_steps=t["agent_steps"], retry=t["retry"],
                system_prompt_tokens=t["system_prompt_tokens"], cache_hit=t["cache_hit"],
                peak_share=t["peak_share"], peak_window_h=t["peak_window_h"], burst=t["burst"],
                sla_headroom=t["sla_headroom"], seasonal=t["seasonal"],
                model_class=a.get("model_class") or t["model_class"], data_class=cls,
                traffic_split=a.get("traffic_split") or None, type=a["type"],
                active_days_per_year=t.get("active_days_per_year", 365),
            ))
        else:
            per_day = vol / 365 if t["unit"] == "gpu_hours_year" else vol
            mode, api_price = processing_for(a, t)
            nt.append(dict(
                id=a["uid"], name=a["name"], include=1, unit=t["unit_label"], units_per_day=per_day,
                gpu_seconds_per_unit=t["gpu_seconds_per_unit"], mode=mode,
                peak_share=t["peak_share"], peak_window_h=t["peak_window_h"], burst=t["burst"],
                data_class=cls, type=a["type"], api_price=api_price,
            ))
    return llm, nt


def processing_key(app: dict, t: dict) -> str | None:
    """'batch' / 'realtime' for types that offer both (speech-to-text), else None.

    Missing or unknown values take the type default (v0.9.8)."""
    opts = t.get("processing")
    if not opts:
        return None
    k = app.get("processing")
    return k if k in opts and k != "default" else opts["default"]


def processing_for(app: dict, t: dict) -> tuple[str, dict | None]:
    """GPU sizing mode and per-unit API price for an application."""
    k = processing_key(app, t)
    if k is None:
        return t.get("mode"), t.get("api_price")
    o = t["processing"][k]
    return o["mode"], o["api_price"]


POPULATION_BASIS = {
    "eligible": "everyone eligible",
    "users": "service users",
}


def normalize_app(a: dict) -> dict:
    """Bring an application from any saved scenario version up to date.

    population_basis (v0.7): missing means "eligible", which reproduces earlier results.
    """
    a = dict(a)
    if a.get("processing") not in (None, "batch", "realtime"):
        a["processing"] = None
    if a.get("population_basis") not in POPULATION_BASIS:
        a["population_basis"] = "eligible"
    return a


def rate_for(app: dict, t: dict) -> dict:
    """Low / Base / High rate for an application, using the population basis when the type has one."""
    by = t.get("rate_by_basis")
    if by:
        return by[normalize_app(app)["population_basis"]]
    return t["rate"]


def basis_label(app: dict, archetypes: dict) -> str | None:
    """'everyone eligible' / 'service users' for types that distinguish them, else None."""
    t = archetypes[app["type"]]
    if t.get("rate_by_basis"):
        return POPULATION_BASIS[normalize_app(app)["population_basis"]]
    k = processing_key(app, t)
    if k:
        return {"batch": "batch", "realtime": "real-time"}[k]
    return None


def build_profile(country: dict, ambition: str, apps: list, archetypes: dict, class_to_tier: dict,
                  quotes: dict | None = None, hardware_choice: str = "auto") -> Profile:
    llm, nt = to_engine_rows(apps, archetypes)
    return Profile(country=country, ambition=ambition, apps=llm, nontoken=nt,
                   class_to_tier=class_to_tier, quotes=quotes or {}, hardware_choice=hardware_choice)


EXAMPLE_PORTFOLIO = [
    dict(name="Civil servant copilot", type="staff_copilot", volume=40000, data_class=3, start_year=1, growth=0.10),
    dict(name="National services assistant", type="citizen_assistant", volume=9000000, data_class=2, start_year=2, growth=0.20),
    dict(name="Land registry intake", type="document_extraction", volume=10000, data_class=3, start_year=1, growth=0.0),
    dict(name="Customs risk agent", type="process_agent", volume=2000, data_class=4, start_year=2, growth=0.05),
    dict(name="Legal research", type="research_agent", volume=200, data_class=2, start_year=3, growth=0.10),
    dict(name="Court transcription", type="speech_to_text", volume=500, data_class=3, start_year=1, growth=0.0),
    dict(name="ID enrolment deduplication", type="biometric_dedup", volume=5000, data_class=4, start_year=1, growth=0.0),
]


# Plausibility limits for volumes, as a share of a country reference population.
# (reference, max share, what the reference is called)
VOLUME_LIMITS = {
    "staff_copilot": ("civil_servants", 1.0, "civil servants"),
    "coding_assistant": ("civil_servants", 0.02, "civil servants"),
    "research_agent": ("civil_servants", 0.01, "civil servants"),
    "frontline_health": ("population", 0.005, "population"),
    "citizen_assistant": ("population", 1.0, "population"),
    "tutor": ("population", 0.3, "population"),
    # agriculture_advisory: checked against agricultural workers with a tolerance from the global defaults.
}

# Types where the volume can be "everyone eligible" rather than service users; very low usage is flagged.
POPULATION_TYPES = ("citizen_assistant", "agriculture_advisory", "tutor")
LOW_USAGE_REQUESTS_PER_DAY = 100
DATA_MIN_YEAR_AGRI = 2015


def reference_sizes(country: dict) -> dict:
    """Civil servants from data, else a rough fallback (2% of population), flagged."""
    pop = country.get("population")
    cs = country.get("civil_servants")
    if not cs and country.get("labour_force") and country.get("public_employment_share"):
        cs = country["labour_force"] * (1 - country.get("unemployment_share", 0)) * country["public_employment_share"]
    agri, agri_year = country.get("agri_workers_est"), None
    if agri:
        import re
        yrs = re.findall(r"\b(19\d\d|20\d\d)\b", country.get("_sources", {}).get("agri_workers_est", ""))
        agri_year = int(yrs[-1]) if yrs else None
        if agri_year is None or agri_year < DATA_MIN_YEAR_AGRI:
            agri = None   # unknown: missing or older than 2015, no check
    return {"population": pop, "civil_servants": cs or (0.02 * pop if pop else None),
            "civil_servants_estimated": not country.get("civil_servants"),
            "agri_workers": agri, "agri_year": agri_year}


def volume_warning(app: dict, country: dict, archetypes: dict, agri_tolerance: float = 1.5) -> str | None:
    if app["type"] == "agriculture_advisory":
        ref = reference_sizes(country)
        n, vol = ref["agri_workers"], float(app.get("volume") or 0)
        if not n or vol <= agri_tolerance * n:
            return None
        return (f'This is about {vol / n:.0f}× the estimated number of agricultural workers in '
                f'{country.get("name", "this country")} (~{n:,.0f}, ILO modeled, {ref["agri_year"]}). Check the figure.')
    lim = VOLUME_LIMITS.get(app["type"])
    if not lim:
        return None
    ref_key, share, label = lim
    ref = reference_sizes(country).get(ref_key)
    if not ref:
        return None
    vol = float(app.get("volume") or 0)
    if vol > share * ref:
        unit = archetypes[app["type"]]["unit_label"].lower()
        return (f'{vol:,.0f} {unit} is {vol / ref:.1%} of {label} ({ref:,.0f}); '
                f'the plausible maximum for this type is about {share:.0%}. Check the number.')
    return None


def low_usage_note(app: dict, archetypes: dict, ambition: str = "Base") -> str | None:
    """Information only: population-based types with very few requests per day."""
    if app["type"] not in POPULATION_TYPES:
        return None
    t = archetypes[app["type"]]
    r = app.get("rate_override") or rate_for(app, t)[{"Low": "low", "Base": "base", "High": "high"}.get(ambition, "base")]
    per_day = float(app.get("volume") or 0) * r
    if per_day < LOW_USAGE_REQUESTS_PER_DAY:
        return (f'{app["name"]}: about {per_day:,.0f} requests per day. Very low usage: check whether the volume '
                'is the whole eligible population or service users.')
    return None


# ---------------------------------------------------------------- custom application types (uploaded CSV)
CUSTOM_TEMPLATE = Path(__file__).resolve().parent.parent / "data" / "templates" / "custom_application_types.csv"
CONF = ("High", "Medium", "Low")
BASIS = ("observed", "derived", "assumption", "uncalibrated", "client")
_LLM_NUM = ("rate_low", "rate_base", "rate_high", "active_days_per_year", "isl", "system_prompt_tokens", "osl",
            "reasoning_tokens", "agent_steps", "retry", "cache_hit", "peak_share", "peak_window_h", "burst",
            "sla_headroom", "seasonal")
_NT_NUM = ("gpu_seconds_per_unit", "peak_share", "peak_window_h", "burst")


def parse_custom_types(text: str, existing: dict | None = None) -> tuple[dict, list]:
    """Read custom application types from the CSV template. Returns ({id: archetype}, [errors]).

    One row per type. kind = llm (token-based) or other (GPU-seconds per unit). Rows with errors are skipped and
    reported; nothing is guessed. Ids get the prefix custom_ so they never replace a catalogue type.
    """
    import csv
    import io
    out, errs = {}, []
    rows = [r for r in csv.DictReader(io.StringIO(text.lstrip("﻿"))) if any((v or "").strip() for v in r.values())]
    if not rows:
        return {}, ["The file has no rows. Use the template: one row per application type."]
    for n, r in enumerate(rows, start=2):
        r = {k.strip(): (v or "").strip() for k, v in r.items() if k}
        where = f"Row {n} ({r.get('label') or r.get('id') or '?'})"
        try:
            kind = r.get("kind", "").lower()
            if kind not in ("llm", "other"):
                raise ValueError("kind must be llm or other")
            if not r.get("id") or not r.get("label") or not r.get("unit_label"):
                raise ValueError("id, label and unit_label are required")
            tid = "custom_" + "".join(ch if ch.isalnum() else "_" for ch in r["id"].lower()).strip("_")
            if tid in out or (existing and tid in existing):
                raise ValueError(f"id {r['id']} is used twice")
            num = {}
            for f in (_LLM_NUM if kind == "llm" else _NT_NUM):
                if not r.get(f):
                    raise ValueError(f"{f} is required for kind={kind}")
                num[f] = float(r[f])
                if num[f] < 0:
                    raise ValueError(f"{f} must not be negative")
            dc = int(r.get("data_class") or 0)
            if dc not in (1, 2, 3, 4):
                raise ValueError("data_class must be 1, 2, 3 or 4")
            cv, cs = r.get("confidence_volume", "Low").capitalize(), r.get("confidence_size", "Low").capitalize()
            if cv not in CONF or cs not in CONF:
                raise ValueError("confidence must be High, Medium or Low")
            br, bs = r.get("basis_rate", "assumption").lower(), r.get("basis_size", "assumption").lower()
            if br not in BASIS or bs not in BASIS:
                raise ValueError(f"basis must be one of {', '.join(BASIS)}")
            ev = {k: r[f"evidence_{k}"] for k in ("rate", "size", "gpu") if r.get(f"evidence_{k}")}
            ev = ev or {"rate": "Custom type uploaded by the user: no evidence given."}
            common = dict(id=tid, label=r["label"] + " (custom)", unit_label=r["unit_label"], data_class=dc,
                          peak_share=num["peak_share"], peak_window_h=num["peak_window_h"], burst=num["burst"],
                          confidence={"volume": cv, "tokens": cs}, evidence=ev, custom=True)
            if not 0 < num["peak_share"] <= 1 or not 0 < num["peak_window_h"] <= 24:
                raise ValueError("peak_share must be in (0, 1] and peak_window_h in (0, 24]")
            if kind == "llm":
                if r.get("unit") not in ("users", "items"):
                    raise ValueError("unit must be users or items")
                if r.get("model_class") not in ("S", "M", "L"):
                    raise ValueError("model_class must be S, M or L")
                if not 1 <= num["active_days_per_year"] <= 366 or num["agent_steps"] < 1 or num["retry"] < 1 or num["cache_hit"] > 1:
                    raise ValueError("check active_days_per_year (1-366), agent_steps (>= 1), retry (>= 1), cache_hit (0-1)")
                if not num["rate_low"] <= num["rate_base"] <= num["rate_high"]:
                    raise ValueError("rates must satisfy low <= base <= high")
                out[tid] = dict(common, group="Custom (uploaded)", unit=r["unit"], model_class=r["model_class"],
                                rate={"low": num["rate_low"], "base": num["rate_base"], "high": num["rate_high"]},
                                active_days_per_year=int(num["active_days_per_year"]),
                                isl=int(num["isl"]), system_prompt_tokens=int(num["system_prompt_tokens"]),
                                osl=int(num["osl"]), reasoning_tokens=int(num["reasoning_tokens"]),
                                agent_steps=int(num["agent_steps"]), retry=num["retry"], cache_hit=num["cache_hit"],
                                sla_headroom=num["sla_headroom"], seasonal=num["seasonal"],
                                basis={"rate": br, "size": bs})
            else:
                mode = r.get("mode", "Batch").capitalize()
                if mode not in ("Batch", "Interactive"):
                    raise ValueError("mode must be Batch or Interactive")
                out[tid] = dict(common, group="Custom (uploaded)", unit="items", mode=mode,
                                gpu_seconds_per_unit=num["gpu_seconds_per_unit"], basis={"gpu": bs})
        except (ValueError, TypeError) as e:
            errs.append(f"{where}: {e}")
    return out, errs


# ---------------------------------------------------------------- example portfolio sized from country data (v0.9.6)
EXAMPLE_RULES = Path(__file__).resolve().parent.parent / "data" / "catalogue" / "example_portfolio.yaml"


def _sig2(v: float) -> float:
    import math
    if v <= 0:
        return 0.0
    k = 1 - int(math.floor(math.log10(v)))
    return round(v, k) if k > 0 else float(round(v, k))


def example_portfolio(country: dict) -> tuple[list, list]:
    """Example applications sized from the country's data. Returns (apps, one explanation line per app).

    Applications whose driver is unknown for the country are left out, and said so.
    """
    rules = yaml.safe_load(EXAMPLE_RULES.read_text())["apps"]
    ref = reference_sizes(country)
    pop = country.get("population")
    drivers = {
        "civil_servants": (ref["civil_servants"],
                           "civil servants" + (" (estimated as 2% of population)" if ref["civil_servants_estimated"] else "")),
        "population": (pop, "people"),
        "internet_users": (pop * country["internet_share"] if pop and country.get("internet_share") else None, "internet users"),
        "agri_workers": (ref["agri_workers"], "agricultural workers (ILO modeled)"),
        "merchandise_trade": ((country.get("merch_imports_usd") or 0) + (country.get("merch_exports_usd") or 0) or None,
                              "US$ of merchandise imports and exports a year"),
    }
    apps, notes = [], []
    for r in rules:
        base, what = drivers[r["driver"]]
        rule = r["rule"]
        if not base and r.get("fallback"):
            fb = r["fallback"]
            missing = what
            base, what = drivers[fb["driver"]]
            r = {**r, "share": fb["share"]}
            rule = f'{fb["rule"]} (no data on {missing})'
        if not base:
            notes.append(f'{r["name"]}: left out, no data on {what} for this country.')
            continue
        vol = max(1.0, _sig2(base * r["share"]))
        a = {k: r[k] for k in ("name", "type", "data_class", "start_year", "growth")}
        if r.get("processing"):
            a["processing"] = r["processing"]
        a["volume"] = int(vol) if vol >= 1 else vol
        if r.get("population_basis"):
            a["population_basis"] = r["population_basis"]
        apps.append(a)
        notes.append(f'{r["name"]}: {a["volume"]:,} = {rule} (~{_sig2(base):,.0f} {what}); '
                     f'starts year {r["start_year"]}, {r["growth"] * 100:+.0f}% per year.')
    return apps, notes
