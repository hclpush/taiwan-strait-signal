#!/usr/bin/env python3
"""Phase C — deterministic apply. Validates the model's proposal, enforces
guardrails, updates data/, rebuilds the site, deploys, and flags level changes
(local runs email; with STRAIT_NOTIFY=github it writes runs/<date>/level-change.json
and the GitHub Actions workflow opens an Issue). The model never touches this phase.

Guardrails (spec §6):
  G1  proposal must be valid JSON matching the schema, all 14 ids exactly once
  G2  cited URLs must exist among this run's fetched snippets (no invented sources)
  G3  an indicator moves at most ONE step per run (up or down)
  G4  any escalation needs >=2 cited sources from distinct domains
  Any violation for an indicator -> that indicator keeps its previous state
  (logged); a malformed proposal -> the whole run is a no-op.

Usage:
  apply.py <run_dir>            full apply (build + deploy + email)
  apply.py <run_dir> --dry-run  validate + report only, change nothing
  apply.py --rollback           restore data/ from the latest run snapshot
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "site"))
from levels import compute_level  # noqa: E402

NOTE_ZH_MAX = 120
NOTE_EN_MAX = 300
VALID_STATUS = {0, 1, 2}


class Reject(Exception):
    """A per-indicator guardrail rejection (indicator keeps previous state)."""


def extract_json(raw: str) -> dict:
    """Pull the first JSON object out of the model's reply (fenced or bare)."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    text = m.group(1) if m else raw[raw.find("{") : raw.rfind("}") + 1]
    return json.loads(text)


def sanitize_note(s: str, cap: int) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()[:cap]


def validate_proposal(prop: dict, ids: list[str]) -> dict[str, dict]:
    if not isinstance(prop, dict) or "proposals" not in prop:
        raise ValueError("proposal missing 'proposals' key")
    entries = prop["proposals"]
    if not isinstance(entries, list):
        raise ValueError("'proposals' is not a list")
    seen = {}
    for e in entries:
        if not isinstance(e, dict) or "id" not in e:
            raise ValueError("entry without id")
        if e["id"] in seen:
            raise ValueError(f"duplicate id {e['id']}")
        seen[e["id"]] = e
    missing = [i for i in ids if i not in seen]
    extra = [i for i in seen if i not in ids]
    if missing or extra:
        raise ValueError(f"id mismatch — missing {missing}, unknown {extra}")
    return seen


def check_entry(
    entry: dict, prev: dict, run_urls: dict[str, str]
) -> tuple[int, str, str, list[dict]]:
    """Apply G2–G4 to one proposal entry. Returns the accepted new state."""
    status = entry.get("status")
    if status not in VALID_STATUS:
        raise Reject(f"invalid status {status!r}")

    urls = entry.get("evidence_urls", [])
    if not isinstance(urls, list) or not all(isinstance(u, str) for u in urls):
        raise Reject("evidence_urls malformed")
    unknown = [u for u in urls if u not in run_urls]
    if unknown:
        raise Reject(f"cited URL(s) not in this run's snippets: {unknown[:2]}")

    old = prev["status"]
    if abs(status - old) > 1:  # G3 — one step per run
        raise Reject(f"step {old}->{status} exceeds one-step damping")
    if status > old:  # G4 — escalation needs 2 distinct-domain sources
        domains = {run_urls[u] for u in urls}
        if len(domains) < 2:
            raise Reject(
                f"escalation {old}->{status} needs >=2 distinct-domain sources, got {sorted(domains)}"
            )

    note_zh = sanitize_note(entry.get("note_zh", prev["note_zh"]), NOTE_ZH_MAX)
    note_en = sanitize_note(entry.get("note_en", prev["note_en"]), NOTE_EN_MAX)
    if not note_zh or not note_en:
        raise Reject("empty note")
    sources = [{"url": u, "domain": run_urls[u]} for u in urls]
    return status, note_zh, note_en, sources


def apply_run(run_dir: Path, dry: bool) -> int:
    data_path = ROOT / "data" / "indicators.json"
    meta_path = ROOT / "data" / "meta.json"
    data = json.loads(data_path.read_text())
    meta = json.loads(meta_path.read_text())
    inds = data["indicators"]
    ids = [i["id"] for i in inds]
    by_id = {i["id"]: i for i in inds}
    old_level = compute_level(inds)

    snippets = json.loads((run_dir / "snippets.json").read_text())
    run_urls = {
        s["url"]: s["domain"]
        for block in snippets["indicators"]
        for s in block["snippets"]
    }

    raw = (run_dir / "proposal-raw.txt").read_text()
    try:
        proposals = validate_proposal(extract_json(raw), ids)  # G1
    except (ValueError, json.JSONDecodeError) as e:
        print(f"REJECTED RUN (G1): {e}", file=sys.stderr)
        log_run(run_dir, old_level, old_level, {}, {"_run": str(e)}, dry)
        return 2

    changes, rejections = {}, {}
    today = snippets["run_date"]
    for ind in inds:
        entry = proposals[ind["id"]]
        try:
            status, note_zh, note_en, sources = check_entry(entry, ind, run_urls)
        except Reject as e:
            rejections[ind["id"]] = str(e)
            continue
        if (status, note_zh, note_en) != (ind["status"], ind["note_zh"], ind["note_en"]):
            changes[ind["id"]] = {"from": ind["status"], "to": status, "note_zh": note_zh}
        if status != ind["status"]:
            ind["history"].append({"date": today, "from": ind["status"], "to": status, "note_zh": note_zh})
        ind["status"], ind["note_zh"], ind["note_en"] = status, note_zh, note_en
        if sources:
            ind["sources"] = sources

    new_level = compute_level(inds)
    print(f"level: {old_level} -> {new_level} · {len(changes)} change(s), {len(rejections)} rejection(s)")
    for k, v in changes.items():
        print(f"  CHANGE {k}: {v['from']} -> {v['to']} · {v['note_zh']}")
    for k, v in rejections.items():
        print(f"  REJECT {k}: {v}")

    if dry:
        print("dry-run: nothing written, nothing deployed")
        return 0

    # snapshot for rollback, then persist
    prev = run_dir / "prev-data"
    prev.mkdir(exist_ok=True)
    for f in (ROOT / "data").glob("*.json"):
        shutil.copy2(f, prev / f.name)
    meta["lastReviewed"] = today
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1))

    from build import build  # site/build.py

    build()
    deploy()
    if new_level != old_level:
        from email_alert import level_change_message, send_level_change

        title, body = level_change_message(old_level, new_level, changes, meta)
        (run_dir / "level-change.json").write_text(
            json.dumps({"title": title, "body": body}, ensure_ascii=False, indent=1)
        )
        if os.environ.get("STRAIT_NOTIFY") == "github":
            print("level change: level-change.json written — CI opens the GitHub Issue")
        else:
            send_level_change(old_level, new_level, changes, meta)
    log_run(run_dir, old_level, new_level, changes, rejections, dry)
    return 0


def deploy() -> None:
    script = ROOT / "ops" / "deploy.sh"
    if not script.exists():
        print("deploy: ops/deploy.sh not present — skipping (site built locally only)")
        return
    r = subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=600)
    print(r.stdout[-2000:])
    if r.returncode != 0:
        raise RuntimeError(f"deploy failed: {r.stderr[-2000:]}")


def log_run(run_dir, old_level, new_level, changes, rejections, dry) -> None:
    line = {
        "date": date.today().isoformat(),
        "run": run_dir.name,
        "old_level": old_level,
        "new_level": new_level,
        "changes": changes,
        "rejections": rejections,
        "dry": dry,
    }
    with open(ROOT / "runs" / "log.jsonl", "a") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def rollback() -> int:
    snaps = sorted(ROOT.glob("runs/*/prev-data"))
    if not snaps:
        print("no snapshot to roll back to", file=sys.stderr)
        return 1
    src = snaps[-1]
    for f in src.glob("*.json"):
        shutil.copy2(f, ROOT / "data" / f.name)
    from build import build

    build()
    deploy()
    print(f"rolled back to snapshot {src.parent.name} and redeployed")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", nargs="?", help="runs/<date> directory")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rollback", action="store_true")
    args = ap.parse_args()
    if args.rollback:
        sys.exit(rollback())
    if not args.run_dir:
        ap.error("run_dir required unless --rollback")
    sys.exit(apply_run(Path(args.run_dir), args.dry_run))
