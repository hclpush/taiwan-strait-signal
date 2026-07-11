import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from levels import compute_level, counts  # noqa: E402


def mk(*specs):
    """specs: (class, status) tuples -> minimal indicator dicts."""
    return [{"class": c, "status": s} for c, s in specs]


BASE = [("normal", 0)] * 5 + [("evac", 0)] * 3 + [("final", 0)]


def with_(overrides):
    inds = mk(*BASE)
    for idx, (cls, st) in overrides.items():
        inds[idx] = {"class": cls, "status": st}
    return inds


def test_all_quiet_is_level_1():
    assert compute_level(mk(*BASE)) == 1


def test_one_sign_is_level_2():
    assert compute_level(with_({0: ("normal", 1)})) == 2


def test_two_signs_still_level_2():
    assert compute_level(with_({0: ("normal", 1), 1: ("normal", 1)})) == 2


def test_three_signs_still_level_2_chronic_baseline():
    # calibration 2026-07-11: the chronic trio (drills + intel warnings +
    # rhetoric) alone must not escalate — see levels.py docstring
    assert compute_level(with_({0: ("normal", 1), 1: ("normal", 1), 2: ("normal", 1)})) == 2


def test_four_signs_is_level_3():
    assert compute_level(with_(
        {0: ("normal", 1), 1: ("normal", 1), 2: ("normal", 1), 3: ("normal", 1)})) == 3


def test_normal_triggered_is_level_3():
    assert compute_level(with_({0: ("normal", 2)})) == 3


def test_evac_signs_count_as_signs_only():
    assert compute_level(with_({5: ("evac", 1)})) == 2


def test_one_evac_triggered_is_level_4():
    assert compute_level(with_({5: ("evac", 2)})) == 4


def test_two_evac_triggered_is_level_5():
    assert compute_level(with_({5: ("evac", 2), 6: ("evac", 2)})) == 5


def test_final_triggered_alone_is_level_5():
    assert compute_level(with_({8: ("final", 2)})) == 5


def test_evac_beats_normal_triggered():
    # evacuation-class trigger dominates: level 4 even alongside a normal trigger
    assert compute_level(with_({0: ("normal", 2), 5: ("evac", 2)})) == 4


def test_counts():
    c = counts(with_({0: ("normal", 1), 5: ("evac", 2)}))
    assert c == {"signs": 1, "triggered": 1, "evac_triggered": 1, "total": 9}
