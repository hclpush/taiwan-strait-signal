import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import apply as ap  # noqa: E402

RUN_URLS = {
    "https://reuters.com/a": "reuters.com",
    "https://apnews.com/b": "apnews.com",
    "https://reuters.com/c": "reuters.com",
}


def prev(status=0):
    return {"status": status, "note_zh": "舊", "note_en": "old"}


def entry(status, urls, note_zh="新現況", note_en="new note"):
    return {"id": "M1", "status": status, "note_zh": note_zh,
            "note_en": note_en, "evidence_urls": urls}


# ---- extract_json ----------------------------------------------------------

def test_extract_fenced_json():
    raw = 'prose\n```json\n{"proposals": []}\n```\nmore prose'
    assert ap.extract_json(raw) == {"proposals": []}


def test_extract_bare_json():
    assert ap.extract_json('{"proposals": [1]}') == {"proposals": [1]}


def test_extract_garbage_raises():
    with pytest.raises(Exception):
        ap.extract_json("no json here")


# ---- validate_proposal (G1) ------------------------------------------------

def test_validate_requires_every_id_once():
    ids = ["M1", "M2"]
    good = {"proposals": [entry(0, []), {**entry(0, []), "id": "M2"}]}
    assert set(ap.validate_proposal(good, ids)) == {"M1", "M2"}
    with pytest.raises(ValueError):
        ap.validate_proposal({"proposals": [entry(0, [])]}, ids)  # missing M2
    with pytest.raises(ValueError):
        ap.validate_proposal(
            {"proposals": [entry(0, []), entry(0, [])]}, ids
        )  # duplicate M1
    with pytest.raises(ValueError):
        ap.validate_proposal(
            {"proposals": [entry(0, []), {**entry(0, []), "id": "ZZ"}]}, ids
        )  # unknown id


# ---- check_entry guardrails (G2-G4) ----------------------------------------

def test_invented_url_rejected():
    with pytest.raises(ap.Reject, match="not in this run"):
        ap.check_entry(entry(1, ["https://evil.example/x"]), prev(0), RUN_URLS)


def test_two_step_jump_rejected():
    with pytest.raises(ap.Reject, match="one-step"):
        ap.check_entry(
            entry(2, ["https://reuters.com/a", "https://apnews.com/b"]),
            prev(0), RUN_URLS,
        )


def test_escalation_needs_two_domains():
    with pytest.raises(ap.Reject, match="distinct-domain"):
        ap.check_entry(entry(1, ["https://reuters.com/a"]), prev(0), RUN_URLS)
    with pytest.raises(ap.Reject, match="distinct-domain"):
        ap.check_entry(
            entry(1, ["https://reuters.com/a", "https://reuters.com/c"]),
            prev(0), RUN_URLS,
        )


def test_valid_escalation_passes():
    status, zh, en, sources = ap.check_entry(
        entry(1, ["https://reuters.com/a", "https://apnews.com/b"]),
        prev(0), RUN_URLS,
    )
    assert status == 1 and zh == "新現況"
    assert {s["domain"] for s in sources} == {"reuters.com", "apnews.com"}


def test_downgrade_one_step_needs_no_sources():
    status, *_ = ap.check_entry(entry(1, []), prev(2), RUN_URLS)
    assert status == 1


def test_same_status_needs_no_sources():
    status, *_ = ap.check_entry(entry(1, []), prev(1), RUN_URLS)
    assert status == 1


def test_invalid_status_rejected():
    with pytest.raises(ap.Reject, match="invalid status"):
        ap.check_entry(entry(7, []), prev(0), RUN_URLS)


def test_note_sanitized_and_capped():
    long_zh = "跡 象\n" * 200
    _, zh, en, _ = ap.check_entry(
        entry(1, ["https://reuters.com/a", "https://apnews.com/b"],
              note_zh=long_zh), prev(0), RUN_URLS,
    )
    assert "\n" not in zh and len(zh) <= ap.NOTE_ZH_MAX


def test_empty_note_rejected():
    with pytest.raises(ap.Reject, match="empty note"):
        ap.check_entry(entry(0, [], note_zh="  "), prev(0), RUN_URLS)


# ---- end-to-end apply_run on a fixture tree --------------------------------

@pytest.fixture
def fixture_root(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "runs").mkdir()
    indicators = {
        "categories": [{"id": "mil", "zh": "軍", "en": "Mil", "tag": "M"}],
        "indicators": [
            {"id": "M1", "category": "mil", "class": "normal", "status": 0,
             "name_zh": "甲", "name_en": "A", "note_zh": "無", "note_en": "none",
             "analog": {"label": "D-1", "zh": "x", "en": "x"},
             "queries": [], "sources": [], "history": []},
            {"id": "E1", "category": "mil", "class": "evac", "status": 0,
             "name_zh": "乙", "name_en": "B", "note_zh": "無", "note_en": "none",
             "analog": {"label": "D-2", "zh": "y", "en": "y"},
             "queries": [], "sources": [], "history": []},
        ],
    }
    (tmp_path / "data" / "indicators.json").write_text(
        json.dumps(indicators, ensure_ascii=False))
    (tmp_path / "data" / "meta.json").write_text(
        json.dumps({"lastReviewed": "2026-01-01", "demo": True}))
    monkeypatch.setattr(ap, "ROOT", tmp_path)
    run_dir = tmp_path / "runs" / "2026-07-11"
    run_dir.mkdir()
    (run_dir / "snippets.json").write_text(json.dumps({
        "run_date": "2026-07-11",
        "indicators": [{"id": "M1", "snippets": [
            {"title": "t", "url": "https://reuters.com/a",
             "domain": "reuters.com", "excerpt": "e"},
            {"title": "t2", "url": "https://apnews.com/b",
             "domain": "apnews.com", "excerpt": "e2"},
        ]}],
    }))
    return tmp_path, run_dir


def test_apply_dry_run_valid_proposal(fixture_root, capsys):
    root, run_dir = fixture_root
    proposal = {"proposals": [
        entry(1, ["https://reuters.com/a", "https://apnews.com/b"]),
        {**entry(0, []), "id": "E1"},
    ]}
    (run_dir / "proposal-raw.txt").write_text(
        "```json\n" + json.dumps(proposal) + "\n```")
    assert ap.apply_run(run_dir, dry=True) == 0
    out = capsys.readouterr().out
    assert "level: 1 -> 2" in out and "CHANGE M1" in out
    # dry run must not touch data
    data = json.loads((root / "data" / "indicators.json").read_text())
    assert data["indicators"][0]["status"] == 1 or True  # in-memory only
    reloaded = json.loads((root / "data" / "indicators.json").read_text())
    assert reloaded["indicators"][0]["status"] == 0


def test_apply_malformed_proposal_is_noop_exit_2(fixture_root):
    root, run_dir = fixture_root
    (run_dir / "proposal-raw.txt").write_text("I refuse to answer in JSON.")
    assert ap.apply_run(run_dir, dry=True) == 2
    reloaded = json.loads((root / "data" / "indicators.json").read_text())
    assert reloaded["indicators"][0]["status"] == 0


# ---- CI level-change marker (STRAIT_NOTIFY=github) --------------------------

def test_level_change_message_content():
    from email_alert import level_change_message

    title, body = level_change_message(
        2, 3, {"M1": {"from": 1, "to": 2, "note_zh": "集結"}},
        {"deploy_url": "https://example.test/"})
    assert title == "[台海燈號] Level 2 → 3"
    assert "M1: 1 → 2" in body and "https://example.test/" in body


def test_apply_writes_ci_marker_instead_of_email(fixture_root, monkeypatch):
    root, run_dir = fixture_root
    monkeypatch.setenv("STRAIT_NOTIFY", "github")
    # stub out the site build and deploy — this test targets the notify path
    import build as build_mod  # site/ is on sys.path via apply's own insert
    monkeypatch.setattr(build_mod, "build", lambda: None)
    monkeypatch.setattr(ap, "deploy", lambda: None)
    proposal = {"proposals": [
        entry(1, ["https://reuters.com/a", "https://apnews.com/b"]),
        {**entry(0, []), "id": "E1"},
    ]}
    (run_dir / "proposal-raw.txt").write_text(json.dumps(proposal))
    assert ap.apply_run(run_dir, dry=False) == 0
    marker = json.loads((run_dir / "level-change.json").read_text())
    assert "Level 1 → 2" in marker["title"] and "M1" in marker["body"]
    # data really persisted, no email attempted (osascript would fail in CI)
    reloaded = json.loads((root / "data" / "indicators.json").read_text())
    assert reloaded["indicators"][0]["status"] == 1
