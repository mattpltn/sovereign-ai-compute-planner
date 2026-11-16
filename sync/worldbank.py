"""Sync country inputs from the World Bank API into data/snapshots/countries.json.

Run by .github/workflows/sync.yml. Each value keeps its indicator code and year.
Indicator codes are checked on every run: a missing indicator is logged, never fatal.

    python sync/worldbank.py
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "snapshots" / "countries.json"
API = "https://api.worldbank.org/v2"

# field: (indicator, source id or None for WDI, transform)
INDICATORS = {
    "population": ("SP.POP.TOTL", None, lambda v: v),
    "internet_share": ("IT.NET.USER.ZS", None, lambda v: v / 100),
    "outages_per_month": ("IC.ELC.OUTG", None, lambda v: v),           # Enterprise Surveys, via WDI
    "labour_force": ("SL.TLF.TOTL.IN", None, lambda v: v),
    "unemployment_share": ("SL.UEM.TOTL.ZS", None, lambda v: v / 100),
    # Worldwide Bureaucracy Indicators: public sector employment as share of total employment.
    # VERIFY the code on first run (WWBI is API source 64).
    "public_employment_share": ("BI.EMP.TOTL.PB.ZS", 64, lambda v: v / 100),
}


def get(path: str, **params) -> list:
    params = {"format": "json", "per_page": 20000, **params}
    r = requests.get(f"{API}/{path}", params=params, timeout=60)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list) or len(data) < 2 or data[1] is None:
        raise ValueError(f"no data for {path}: {str(data)[:200]}")
    return data[1]


def countries() -> dict:
    out = {}
    for c in get("country"):
        if c["region"]["id"] == "NA":  # aggregates
            continue
        out[c["id"]] = {"name": c["name"], "region": c["region"]["value"], "income": c["incomeLevel"]["value"]}
    return out


def latest(code: str, source: int | None) -> dict:
    params = {"mrnev": 1}
    if source:
        params["source"] = source
    vals = {}
    for row in get(f"country/all/indicator/{code}", **params):
        if row["value"] is not None:
            vals[row["countryiso3code"]] = (row["value"], row["date"])
    return vals


def read_csv(name: str, field: str) -> dict:
    p = ROOT / "data" / name
    if not p.exists():
        return {}
    rows = [l for l in p.read_text().splitlines() if l and not l.startswith("#")]
    return {r["iso3"]: (float(r[field]), r.get("year", "")) for r in csv.DictReader(rows) if r.get(field)}


def main() -> int:
    meta = countries()
    data = {k: {**v, "_sources": {}} for k, v in meta.items()}
    log = []
    for field, (code, src, f) in INDICATORS.items():
        try:
            vals = latest(code, src)
        except Exception as e:  # noqa: BLE001
            log.append(f"{field} ({code}): FAILED {e}")
            continue
        for iso, (v, year) in vals.items():
            if iso in data:
                data[iso][field] = f(v)
                data[iso]["_sources"][field] = f"World Bank API {code}, {year}"
        log.append(f"{field} ({code}): {len(vals)} countries")

    # Derived: civil servants = labour force x (1 - unemployment) x public employment share
    for iso, c in data.items():
        if all(k in c for k in ("labour_force", "unemployment_share", "public_employment_share")):
            c["civil_servants"] = c["labour_force"] * (1 - c["unemployment_share"]) * c["public_employment_share"]
            c["_sources"]["civil_servants"] = "derived: labour force x (1 - unemployment) x WWBI public employment share"

    # Curated files (no free API): EGDI (UN, biennial) and electricity tariff.
    for field, fname, col, label in [("egdi", "egdi.csv", "egdi", "UN E-Government Survey"),
                                     ("electricity_usd_kwh", "electricity.csv", "usd_kwh", "curated tariff table")]:
        for iso, (v, year) in read_csv(fname, col).items():
            if iso in data:
                data[iso][field] = v
                data[iso]["_sources"][field] = f"{label} {year}".strip()

    # Keep the fictional test country.
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    if "XEX" in old:
        data["XEX"] = old["XEX"]

    data = {"_meta": {"synced_at": dt.date.today().isoformat(), "log": log}, **dict(sorted(data.items()))}
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print("\n".join(log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
