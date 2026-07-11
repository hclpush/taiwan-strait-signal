# 🚦 台海燈號 Strait Signal

**A public, bilingual (繁中/EN) signal for Taiwan-strait war risk, computed
transparently from open-source indicators.** Born from the article
〈戰爭從未突然爆發〉: line up the pre-war Ukraine headlines by date and you see
war approaching step by step — this site does that continuously for the strait,
so ordinary people can judge without inside information.

Five levels (1 平時 → 5 撤離), each with a plain "what to do now." The level is
**never chosen by a model or a person** — it's computed by a fixed public rule
over 14 indicators (military mobilization, diplomatic/evacuation signals,
official warnings, economy/information), each mapped to the actual pre-invasion
Ukraine event with its D-countdown (眷屬撤離 → 烏克蘭 D−31).

## Quickstart

```bash
python3 site/build.py                  # data/*.json → site/dist/index.html
python3 -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python -m pytest tests/ -q   # 30 tests, no network needed
```

## How the weekly update works — three isolated phases

```
GitHub Actions cron (Mon 10:30 台北 · .github/workflows/weekly.yml)
  A  pipeline/fetch.py      deterministic · Firecrawl REST search+scrape,
                            domain whitelist ONLY (Reuters/AP/BBC/CNA/官方頁面)
  B  claude --print         headless classify: prompt in → JSON out.
                            ZERO tools, MCP disabled, subscription OAuth token
                            (no API key). Snippets are data, not instructions.
  C  pipeline/apply.py      deterministic guardrails → data/ → build → deploy
                            to GitHub Pages → GitHub Issue on level change
```

Guardrails in apply.py (all code, no model judgment): cited URLs must exist in
this run's fetched snippets · one status step per indicator per run · any
escalation needs ≥2 distinct-domain sources · malformed proposal = no-op ·
`apply.py --rollback` restores the previous state and redeploys.

Level rule (also rendered on the site): L5 embassies close or 2+ evac-class
triggered · L4 any evac-class triggered · L3 any other indicator triggered or
4+ showing signs · L2 any sign · L1 otherwise. The signs threshold is 4 by
deliberate calibration — the strait's chronic baseline (drill tempo, intel
warnings, cabinet rhetoric) is already 3 signs, and Level 3 must mean spread
beyond it.

## Operations

**Production (GitHub Actions):**
- `weekly-signal-update` — Mon 10:30 台北 cron; also runnable from the Actions
  tab (workflow_dispatch, with a dry-run option). Commits `data/` changes as
  github-actions[bot] and deploys Pages itself.
- `test-and-deploy` — tests + Pages deploy on every push to main.
- Level change → the workflow opens a GitHub Issue (which emails the
  maintainer). Failed runs email automatically via GitHub notifications.
- Evidence: each run uploads `runs/<date>/` as a workflow artifact (90 days);
  the durable ledger is the git history of `data/`.
- Secrets (repo Settings → Secrets and variables → Actions):
  `FIRECRAWL_API_KEY` · `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`).

**Local (dev / supervised runs):**

```bash
ops/run-weekly.sh                # manual full run on this machine
DRY_RUN=1 ops/run-weekly.sh      # supervised: report only, change nothing
python3 pipeline/apply.py --rollback   # restore previous state (then push)
```

## What this site cannot tell you

Public information lags; the strait may not follow the Ukraine script (an
amphibious war may lean on surprise, with less warning); deterrence theater can
trip indicators without war — false alarms are preferred to silence; and this
is not official, not a prediction, not advice. It does one thing: arrange the
public signals so you can judge for yourself.

---
*Maintained by [Lezbyte](https://github.com/hclpush) with Claude Code. Unofficial;
analyzes publicly available reporting for informational purposes only.*
