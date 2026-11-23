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
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "snapshots" / "countries.json"
API = "https://api.worldbank.org/v2"

# field: (indicator, source id or None for WDI, transform)
INDICATORS = {
    "population": ("SP.POP.TOTL", None, lambda v: v),
    "internet_share": ("IT.NET.USER.ZS", None, lambda v: v / 100),
    # Enterprise Surveys outages: archived from WDI in 2026; candidates tried in order (see CANDIDATES).
    "outages_per_month": ("IC.ELC.OUTG", None, lambda v: v),
    # Share of firms experiencing outages (% of firms). Fallback signal only: a different unit from outages per month.
    "firms_with_outages_share": ("IC.ELC.OUTG.ZS", None, lambda v: v / 100),
    "labour_force": ("SL.TLF.TOTL.IN", None, lambda v: v),
    "unemployment_share": ("SL.UEM.TOTL.ZS", None, lambda v: v / 100),
    # Worldwide Bureaucracy Indicators: public sector employment as share of total employment.
    # VERIFY the code on first run (WWBI is API source 64).
    # WWBI publishes shares as fractions (0-1), not percentages: no division by 100.
    "public_employment_share": ("BI.EMP.TOTL.PB.ZS", 64, lambda v: v),
    # Agriculture (v0.7): employment share is % of total employment, ILO modeled estimate.
    "agri_employment_share": ("SL.AGR.EMPL.ZS", None, lambda v: v / 100),
    "rural_population": ("SP.RUR.TOTL", None, lambda v: v),   # context only
}

# Indicators whose code is confirmed against live API metadata before use. If the name returned by the API
# does not match, the field is NOT stored and the sync log says STOPPED (code changed or missing).
VERIFY = {
    "labour_force": r"^labor force, total$",
    "agri_employment_share": r"^employment in agriculture \(% of total employment\)",
    "rural_population": r"^rural population$",
}
AGRI_MIN_YEAR = 2015


# Alternative (indicator, source) pairs tried when the first one fails.
CANDIDATES = {
    # IC.ELC.OUTG.ZS is NOT a candidate: it is % of firms, kept separately as firms_with_outages_share.
    "outages_per_month": [("IC.ELC.OUTG", 13), ("IC.ELC.OUTG", 1)],
}


SESSION = requests.Session()
SESSION.headers["User-Agent"] = "sovereign-ai-compute-planner data sync (World Bank; weekly, low volume)"
RETRY_STATUS = {429, 500, 502, 503, 504}
PAUSE_S = 1.0          # between successful calls, to stay under the API's rate limit
MAX_ATTEMPTS = 7       # waits 15, 30, 60, 120, 240, 300 s: about 13 minutes in total before giving up


def fetch(url: str, params: dict, sleep=time.sleep) -> requests.Response:
    """GET with retries on rate limits (429), server errors and timeouts.

    Honours the Retry-After header when the API sends one; otherwise backs off exponentially.
    """
    last = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            r = SESSION.get(url, params=params, timeout=180)
            if r.status_code in RETRY_STATUS:
                raise requests.HTTPError(f"{r.status_code} for {r.url}", response=r)
            r.raise_for_status()
            sleep(PAUSE_S)
            return r
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code is not None and code not in RETRY_STATUS:
                raise                                   # 404 and the like: retrying will not help
            last = e
            if attempt == MAX_ATTEMPTS - 1:
                break
            ra = getattr(getattr(e, "response", None), "headers", {}).get("Retry-After") if code else None
            wait = float(ra) if ra and str(ra).isdigit() else min(300, 15 * 2 ** attempt)
            print(f"  {code or type(e).__name__} on {url}: retry {attempt + 1}/{MAX_ATTEMPTS - 1} in {wait:.0f}s", flush=True)
            sleep(wait)
    raise last


def get(path: str, **params) -> list:
    params = {"format": "json", "per_page": 20000, **params}
    data = fetch(f"{API}/{path}", params).json()
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


def check_metadata(code: str, payload, pattern: str) -> dict:
    """Parse the API's /indicator/{code} response and confirm the name. Raises ValueError if it does not match."""
    import re
    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        raise ValueError(f"{code}: not found in API metadata")
    m = payload[1][0]
    name = m.get("name", "")
    if m.get("id") != code or not re.search(pattern, name, re.I):
        raise ValueError(f"{code}: API name '{name}' does not match the expected indicator")
    return {"code": code, "name": name, "source_id": int(m["source"]["id"]), "source": m["source"]["value"]}


def verify(code: str, pattern: str) -> dict:
    r = fetch(f"{API}/indicator/{code}", {"format": "json"})
    return check_metadata(code, r.json(), pattern)


def store(data: dict, field: str, code: str, vals: dict, f) -> None:
    """Store latest values with indicator code and year."""
    for iso, (v, year) in vals.items():
        if iso in data:
            data[iso][field] = f(v)
            data[iso]["_sources"][field] = f"World Bank API {code}, {year}"


def year_of(src: str) -> int | None:
    import re
    y = re.findall(r"\b(19\d\d|20\d\d)\b", src or "")
    return int(y[-1]) if y else None


def derive_agri(c: dict) -> None:
    """agri_workers_est = employed labour force x agriculture share of employment.

    The ILO share is a share of EMPLOYMENT, so it is applied to labour force x (1 - unemployment) when unemployment
    is known (labour force alone otherwise). Missing data or a share older than 2015: unknown, no value stored.
    """
    s, lf = c.get("agri_employment_share"), c.get("labour_force")
    y = year_of(c.get("_sources", {}).get("agri_employment_share", ""))
    if s is None or lf is None or y is None or y < AGRI_MIN_YEAR:
        c.pop("agri_workers_est", None)
        c.get("_sources", {}).pop("agri_workers_est", None)
        return
    employed = lf * (1 - c.get("unemployment_share", 0))
    c["agri_workers_est"] = employed * s
    c["_sources"]["agri_workers_est"] = f"derived: employed labour force x ILO modeled agriculture share of employment, {y}"


def read_csv(name: str, field: str) -> dict:
    p = ROOT / "data" / name
    if not p.exists():
        return {}
    rows = [l for l in p.read_text().splitlines() if l and not l.startswith("#")]
    return {r["iso3"]: (float(r[field]), r.get("year", "")) for r in csv.DictReader(rows) if r.get(field)}


def discover(pattern: str) -> list[tuple[str, int | None]]:
    """Find indicator codes and their API source by name, across all World Bank databases.

    Used when a known code has been archived or moved (e.g. Enterprise Surveys outages left WDI in 2026).
    """
    import re
    found = []
    page, pages = 1, 1
    while page <= pages and page <= 40:
        r = fetch(f"{API}/indicator", {"format": "json", "per_page": 1000, "page": page})
        head, rows = r.json()
        pages = head.get("pages", 1)
        for x in rows or []:
            if re.search(pattern, x.get("name", ""), re.I):
                found.append((x["id"], int(x["source"]["id"]) if x.get("source", {}).get("id") else None))
        page += 1
    return found


def main() -> int:
    meta = countries()
    data = {k: {**v, "_sources": {}} for k, v in meta.items()}
    log = []
    checked = {}
    for field, (code, src, f) in INDICATORS.items():
        vals = None
        if field in VERIFY:
            try:
                checked[code] = verify(code, VERIFY[field])
                log.append(f"{field}: confirmed {code} = '{checked[code]['name']}' (source {checked[code]['source_id']})")
            except Exception as e:  # noqa: BLE001
                log.append(f"{field}: STOPPED, not stored. {str(e)[:200]}")
                continue
        cands = [(code, src)] + CANDIDATES.get(field, [])
        if field == "outages_per_month":
            try:
                cands += [x for x in discover(r"outages in a typical month") if not x[0].endswith(".ZS")]
                log.append(f"outages: discovered {cands[len(CANDIDATES.get(field, [])) + 1:]}")
            except Exception as e:  # noqa: BLE001
                log.append(f"outages: discovery FAILED {str(e)[:120]}")
        for c, s_ in cands:
            try:
                vals = latest(c, s_)
                code = c
                break
            except Exception as e:  # noqa: BLE001
                log.append(f"{field} ({c}, source {s_}): FAILED {str(e)[:160]}")
        if vals is None:
            continue
        store(data, field, code, vals, f)
        log.append(f"{field} ({code}): {len(vals)} countries")

    # Derived: civil servants = labour force x (1 - unemployment) x public employment share
    for iso, c in data.items():
        if all(k in c for k in ("labour_force", "unemployment_share", "public_employment_share")):
            c["civil_servants"] = c["labour_force"] * (1 - c["unemployment_share"]) * c["public_employment_share"]
            c["_sources"]["civil_servants"] = "derived: labour force x (1 - unemployment) x WWBI public employment share"

    for c in data.values():
        derive_agri(c)

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

    data = {"_meta": {"synced_at": dt.date.today().isoformat(), "log": log, "indicators": checked}, **dict(sorted(data.items()))}
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print("\n".join(log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
