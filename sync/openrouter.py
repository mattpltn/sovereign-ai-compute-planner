"""Sync API prices per model class from OpenRouter into data/snapshots/api_prices.json.

Price per class = median over the reference models listed in data/catalogue/defaults.yaml.
OpenRouter returns prices in USD per token; stored here in USD per million tokens.

    python sync/openrouter.py
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
import sys
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "snapshots" / "api_prices.json"


def main() -> int:
    refs = yaml.safe_load((ROOT / "data" / "catalogue" / "defaults.yaml").read_text())["api_reference_models"]
    r = requests.get("https://openrouter.ai/api/v1/models", timeout=60)
    r.raise_for_status()
    models = {m["id"]: m for m in r.json()["data"]}
    out = {"_meta": {"synced_at": dt.date.today().isoformat(), "source": "S21 OpenRouter /api/v1/models", "models": {}}}
    for cls, ids in refs.items():
        ins, outs = [], []
        matched = [m for pref in ids for k, m in models.items()
                   if k == pref or (k.startswith(pref) and ":free" not in k)]
        for m in {x["id"]: x for x in matched}.values():
            mid = m["id"]
            pi, po = float(m["pricing"]["prompt"]) * 1e6, float(m["pricing"]["completion"]) * 1e6
            if pi > 0 and po > 0:
                ins.append(pi)
                outs.append(po)
                out["_meta"]["models"][mid] = {"input": pi, "output": po}
        if ins:
            out[cls] = {"input": statistics.median(ins), "output": statistics.median(outs)}
            print(f"{cls}: in {out[cls]['input']:.3f} out {out[cls]['output']:.3f} $/M from {len(ins)} models")
        else:
            print(f"{cls}: no reference model found, engine will use fallback")
    OUT.write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
