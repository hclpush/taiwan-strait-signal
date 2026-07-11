"""Deterministic level rule — the ONLY place the signal level is computed.

Statuses: 0 = not triggered, 1 = signs appearing, 2 = triggered.
Classes:  normal | evac | final (final is also evacuation-class).

Rule (mirrored in data/levels.json rule_zh/rule_en and rendered on the site):
  L5  any final-class triggered, or >=2 evacuation-class triggered
  L4  >=1 evacuation-class triggered
  L3  >=1 normal-class triggered, or >=4 indicators showing signs
  L2  >=1 indicator showing signs
  L1  otherwise

The signs threshold is 4, not 3, by explicit calibration (2026-07-11): the
strait's chronic baseline (drill tempo + intel warnings + cabinet rhetoric)
already yields 3 signs, and Level 3 must mean deterioration is SPREADING
beyond that chronic trio — otherwise the site pins at 3/5 forever.
"""
from __future__ import annotations

EVAC_CLASSES = {"evac", "final"}


def counts(indicators: list[dict]) -> dict:
    """Counts used by the hero 'why this level' line and the alert email."""
    return {
        "signs": sum(1 for i in indicators if i["status"] == 1),
        "triggered": sum(1 for i in indicators if i["status"] == 2),
        "evac_triggered": sum(
            1 for i in indicators if i["status"] == 2 and i["class"] in EVAC_CLASSES
        ),
        "total": len(indicators),
    }


def compute_level(indicators: list[dict]) -> int:
    c = counts(indicators)
    final_triggered = any(
        i["status"] == 2 and i["class"] == "final" for i in indicators
    )
    normal_triggered = any(
        i["status"] == 2 and i["class"] == "normal" for i in indicators
    )
    if final_triggered or c["evac_triggered"] >= 2:
        return 5
    if c["evac_triggered"] >= 1:
        return 4
    if normal_triggered or c["signs"] >= 4:
        return 3
    if c["signs"] >= 1:
        return 2
    return 1
