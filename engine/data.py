"""Load catalogue, defaults and synced snapshots."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import yaml

from .model import Profile

ROOT = Path(__file__).resolve().parent.parent
CAT = ROOT / "data" / "catalogue"
SNAP = ROOT / "data" / "snapshots"


def _y(name):
    return yaml.safe_load((CAT / f"{name}.yaml").read_text())


def load_catalogue() -> dict:
    return {k: _y(k) for k in ("use_cases", "nontoken", "hardware", "sources")}


def load_defaults() -> dict:
    d = _y("defaults")
    d["facility"] = _y("facility")
    d["class_to_tier"] = {int(k): v for k, v in d["class_to_tier"].items()}
    return d


def load_countries() -> dict:
    data = json.loads((SNAP / "countries.json").read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


def load_api_prices(defaults: dict) -> tuple[dict, str]:
    """Synced prices if present, else fallback. Returns (prices, provenance)."""
    p = SNAP / "api_prices.json"
    if p.exists():
        data = json.loads(p.read_text())
        synced = {k: v for k, v in data.items() if k in ("S", "M", "L")}
        if synced:
            prices = {**defaults["api_prices_fallback"], **synced}
            missing = [k for k in ("S", "M", "L") if k not in synced]
            note = f" (fallback for {', '.join(missing)})" if missing else ""
            return prices, f"OpenRouter, synced {data.get('_meta', {}).get('synced_at')}{note}"
    return defaults["api_prices_fallback"], "fallback defaults (not yet synced)"


def default_profile(iso3: str = "XEX", ambition: str = "Base") -> Profile:
    cat, d = load_catalogue(), load_defaults()
    return Profile(country=load_countries()[iso3], ambition=ambition,
                   apps=deepcopy(cat["use_cases"]), nontoken=deepcopy(cat["nontoken"]),
                   class_to_tier=dict(d["class_to_tier"]))
