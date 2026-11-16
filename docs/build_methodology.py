"""Build docs/METHODOLOGY.md from the hand-written text in docs/methodology_text.md and the live catalogue.

Tables (application types, defaults, hardware, sources, worked example) are generated from the YAML files and
the engine, so the document cannot drift from the code. CI runs `python docs/build_methodology.py --check`.

    python docs/build_methodology.py          # rewrite docs/METHODOLOGY.md
    python docs/build_methodology.py --check  # fail if it is out of date
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import load_catalogue, load_countries, load_defaults, run  # noqa: E402
from engine.archetypes import build_profile, is_llm, load_archetypes  # noqa: E402

OUT = ROOT / "docs" / "METHODOLOGY.md"
TEXT = ROOT / "docs" / "methodology_text.md"


def esc(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def table(headers, rows) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def gen_types(arch) -> str:
    llm = [a for a in arch.values() if is_llm(a)]
    nt = [a for a in arch.values() if not is_llm(a)]
    t1 = table(
        ["Type", "Volume entered by user", "Requests per unit per day (Low / Base / High)", "Input + system / output / reasoning tokens per call",
         "Calls per task", "Model", "Peak share / window (h)", "Burst", "Default data class", "Confidence (volume / size)"],
        [[a["label"], a["unit_label"], f'{a["rate"]["low"]:g} / {a["rate"]["base"]:g} / {a["rate"]["high"]:g}',
          f'{a["isl"]:,} + {a["system_prompt_tokens"]:,} / {a["osl"]:,} / {a["reasoning_tokens"]:,}',
          f'{a["agent_steps"]} x retry {a["retry"]}', a["model_class"], f'{a["peak_share"]:.0%} / {a["peak_window_h"]}',
          a["burst"], a["data_class"], f'{a["confidence"]["volume"]} / {a["confidence"]["tokens"]}'] for a in llm])
    t2 = table(["Type", "Volume entered by user", "GPU-seconds per unit", "Mode", "Default data class", "Confidence"],
               [[a["label"], a["unit_label"], f'{a["gpu_seconds_per_unit"]:g}', a["mode"], a["data_class"],
                 a["confidence"]["tokens"]] for a in nt])
    ev = []
    for a in arch.values():
        ev.append(f'**{a["label"]}**\n')
        ev += [f"- *{k}*: {v}" for k, v in a["evidence"].items()]
        ev.append("")
    return ("### Generative AI types\n\n" + t1 + "\n\n### Other AI types (non-LLM)\n\n" + t2 +
            "\n\n### Evidence for each type\n\n" + "\n".join(ev))


def gen_defaults(d) -> str:
    rows = [[k, v["value"], v.get("source", ""), v.get("note", "")] for k, v in d.items()
            if isinstance(v, dict) and "value" in v]
    t1 = table(["Parameter", "Value", "Source", "Note"], rows)
    t2 = table(["Cost item", "Low", "Base", "High", "Source", "Note"],
               [[k, v["low"], v["base"], v["high"], v.get("source", ""), v.get("note", "")] for k, v in d["costs"].items()])
    t3 = table(["Model class", "Fallback API input ($/M tokens)", "Fallback API output ($/M tokens)", "Reference models (synced from OpenRouter)"],
               [[c, d["api_prices_fallback"][c]["input"], d["api_prices_fallback"][c]["output"],
                 ", ".join(d["api_reference_models"][c])] for c in ("S", "M", "L")])
    t4 = table(["Tier", "Description", "API / managed", "GPU-as-a-service", "Owned"],
               [[t, v["name"], "yes" if v["api"] else "no", "yes" if v["gpuaas"] else "no", "yes" if v["owned"] else "no"]
                for t, v in d["tiers"].items()])
    t5 = table(["Data class", "Default tier"], [[k, v] for k, v in d["class_to_tier"].items()])
    return (t1 + "\n\n**Cost ranges (replaced by client quotes when entered)**\n\n" + t2 +
            "\n\n**API prices**\n\n" + t3 + "\n\n**Tiers and allowed buying modes**\n\n" + t4 +
            "\n\n**Default placement rules**\n\n" + t5)


def gen_hardware(cat) -> str:
    return table(["ID", "Profile", "Cooling", "Rack kW", "kW per GPU (all-in)", "Tokens/s per GPU S / M / L", "$/GPU-hour",
                  "Capex per GPU", "Software $/GPU/yr", "Weak-grid suitable"],
                 [[h["id"], h["name"], h["cooling"], h["rack_kw"], h["kw_per_gpu"],
                   " / ".join(f'{h["tokens_per_s_per_gpu"][c]:,}' for c in "SML"), h["gpu_hour_usd"],
                   f'{h["capex_per_gpu_usd"]:,}', h["software_per_gpu_year_usd"], "yes" if h["weak_grid_ok"] else "no"]
                  for h in cat["hardware"]])


def gen_hardware_evidence(cat) -> str:
    out = []
    for h in cat["hardware"]:
        out.append(f'**{h["id"]} · {h["name"]}**\n')
        out += [f"- *{k}*: {v}" for k, v in h.get("evidence", {}).items()]
        out.append("")
    return "\n".join(out)


def gen_sources(cat) -> str:
    return table(["ID", "Source", "Publisher", "Used for", "Link"],
                 [[s["id"], s["title"], s["publisher"], s["used_for"], s["url"]] for s in cat["sources"]])


def gen_example(cat, d, arch) -> str:
    c = dict(load_countries()["XEX"])
    p = build_profile(c, "Base", [dict(uid="ex", name="Copilot", type="staff_copilot", volume=1000, data_class=3)],
                      arch, dict(d["class_to_tier"]), hardware_choice="P1")
    r = run(p, cat, d)
    x = r["demand"][0]
    s = r["tiers"]["T3"]["sizing"]
    t = arch["staff_copilot"]
    hw = next(h for h in cat["hardware"] if h["id"] == "P1")
    pre = d["prefill_weight"]["value"]
    k = t["agent_steps"] * t["retry"]
    lines = [
        f"A staff copilot for **1,000 staff with access**, data class 3, Base scenario, hardware P1.",
        "",
        "| Step | Calculation | Result |",
        "|---|---|---|",
        f'| Requests per day | 1,000 x {t["rate"]["base"]:g} | {x["sessions"]:,.0f} |',
        f'| Input tokens per request | ({t["isl"]:,} + {t["system_prompt_tokens"]:,}) x {k:g} | {(t["isl"] + t["system_prompt_tokens"]) * k:,.0f} |',
        f'| Cached input per request | {t["system_prompt_tokens"]:,} x {t["cache_hit"]:g} x {k:g} | {t["system_prompt_tokens"] * t["cache_hit"] * k:,.0f} |',
        f'| Output tokens per request | ({t["osl"]:,} + {t["reasoning_tokens"]:,}) x {k:g} | {(t["osl"] + t["reasoning_tokens"]) * k:,.0f} |',
        f'| Daily equivalent tokens | output + (input - cached) x {pre:g} | {x["daily_eq"]:,.0f} |',
        f'| Peak equivalent tokens/s | daily eq x {t["peak_share"]:g} / ({t["peak_window_h"]} x 3,600) x burst {t["burst"]:g} x SLA {t["sla_headroom"]:g} x seasonal {t["seasonal"]:g} | {x["peak_eq_tps"]:,.1f} |',
        f'| Diversified peak in tier T3 | x D {d["diversity_factor"]["value"]:g} | {s["peak_eq_tps"]["M"]:,.1f} |',
        f'| GPUs | roundup(peak / ({hw["tokens_per_s_per_gpu"]["M"]:,} tok/s x derating {d["production_derating"]["value"]:g})) | {s["gpus"]} |',
        f'| IT load / facility | GPUs x {hw["kw_per_gpu"]:g} kW; x PUE {d["pue"]["value"]:g} | {s["it_kw"]:.1f} kW / {s["facility_mw"] * 1000:.1f} kW |',
        f'| Cheapest eligible option (T3) | min(GPU-as-a-service, Owned) over 10 years | {r["tiers"]["T3"]["cheapest_mode"]}, ${r["tiers"]["T3"]["cheapest_cost"]:,.0f} |',
        "",
        f'Utilisation of that single GPU is {s["utilisation"]:.0%}: one copilot for 1,000 staff does not justify dedicated '
        "hardware on its own. Pooling several applications in a tier (diversity factor) is what makes local capacity efficient.",
    ]
    return "\n".join(lines)


def build() -> str:
    cat, d, arch = load_catalogue(), load_defaults(), load_archetypes()
    text = TEXT.read_text()
    for key, val in {"{{TYPES}}": gen_types(arch), "{{DEFAULTS}}": gen_defaults(d), "{{HARDWARE}}": gen_hardware(cat), "{{HARDWARE_EVIDENCE}}": gen_hardware_evidence(cat),
                     "{{SOURCES}}": gen_sources(cat), "{{EXAMPLE}}": gen_example(cat, d, arch)}.items():
        text = text.replace(key, val)
    return "<!-- Generated by docs/build_methodology.py from docs/methodology_text.md and the catalogue. Do not edit by hand. -->\n\n" + text


if __name__ == "__main__":
    new = build()
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text() != new:
            print("docs/METHODOLOGY.md is out of date: run python docs/build_methodology.py")
            sys.exit(1)
        print("METHODOLOGY.md up to date")
    else:
        OUT.write_text(new)
        print(f"wrote {OUT}")
