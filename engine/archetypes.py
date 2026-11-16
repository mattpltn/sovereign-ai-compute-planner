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
            rate = {"low": r, "base": r, "high": r} if r else t["rate"]
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
            ))
        else:
            per_day = vol / 365 if t["unit"] == "gpu_hours_year" else vol
            nt.append(dict(
                id=a["uid"], name=a["name"], include=1, unit=t["unit_label"], units_per_day=per_day,
                gpu_seconds_per_unit=t["gpu_seconds_per_unit"], mode=t["mode"],
                peak_share=t["peak_share"], peak_window_h=t["peak_window_h"], burst=t["burst"],
                data_class=cls, type=a["type"],
            ))
    return llm, nt


def build_profile(country: dict, ambition: str, apps: list, archetypes: dict, class_to_tier: dict,
                  quotes: dict | None = None, hardware_choice: str = "auto") -> Profile:
    llm, nt = to_engine_rows(apps, archetypes)
    return Profile(country=country, ambition=ambition, apps=llm, nontoken=nt,
                   class_to_tier=class_to_tier, quotes=quotes or {}, hardware_choice=hardware_choice)


EXAMPLE_PORTFOLIO = [
    dict(name="Civil servant copilot", type="staff_copilot", volume=40000, data_class=3),
    dict(name="National services assistant", type="citizen_assistant", volume=9000000, data_class=2),
    dict(name="Land registry intake", type="document_extraction", volume=10000, data_class=3),
    dict(name="Customs risk agent", type="process_agent", volume=2000, data_class=4),
    dict(name="Legal research", type="research_agent", volume=200, data_class=2),
    dict(name="Court transcription", type="speech_to_text", volume=500, data_class=3),
    dict(name="ID enrolment deduplication", type="biometric_dedup", volume=5000, data_class=4),
]
