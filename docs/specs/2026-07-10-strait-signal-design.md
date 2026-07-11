---
project: strait-signal
date: 2026-07-10
status: approved-design
author: Lezbyte
ai_assistant: Claude Code
---
# 台海燈號 Strait Signal — Design Spec
**Goal:** A public, bilingual (繁中/EN) website signaling the current risk level of a Chinese attack on Taiwan, computed transparently from open-source indicators — companion to the Threads article 〈戰爭從未突然爆發〉 and a portfolio piece.
**Approved mockup:** [[100_Todo/drafts/strait-signal-mockup.html]] (2026-07-10) — the built site must match it 1:1.
**Repo:** `~/Developer/taiwan-strait-signal/` → GitHub `hclpush/taiwan-strait-signal` · **Deploy:** GitHub Pages via Actions (the Zeabur plan originally written here was superseded 2026-07-11 — see README).

## 1. Product
- Five-level signal (1 平時 Calm → 5 撤離 Imminent), colors validated CVD-safe; L5 violet (AQI 紫爆 convention). Color never appears without number + name.
- Sections exactly as mockup: Hero (current level, meter, why, do-now chips) · 五級燈號 · 觀測指標 (14 indicators, each with Ukraine analog + D-countdown) · 烏克蘭時間軸 (13 clippings, red-circle motif) · 如何自己判讀 · 分級行動指南 · 本站不能告訴你的事 · footer credit → Lezbyte's Threads.
- Bilingual via CSS toggle (`data-lang` on `<body>`), zh-Hant default. Dark mode via `prefers-color-scheme`.
- Honesty surfaces: 最後審視 date in hero; every indicator shows sources + last-review; demo watermark removed only when real assessment ships.

## 2. Indicators (14) & classes
Statuses: `0` 未觸發 · `1` 出現跡象 · `2` 已觸發. Classes drive the level rule.
- **軍事 M** — M1 兵力異常集結 · M2 實彈演習頻率 · M3 醫療後勤動員（血漿）· M4 民用滾裝船徵用（台海特有）
- **外交與撤離 E (evacuation-class)** — E1 使館縮編 · E2 撤離眷屬／敦促離境 · E3 關閉使館 **(final-class)** · E4 企業與航空撤離（外商撤人、停飛、戰爭險飆升）
- **官方警告 W** — W1 情報體系公開警告 · W2 旅遊警示「勿前往」**(evacuation-class)** · W3 元首點名警告
- **經濟與資訊 X** — X1 戰略物資異常囤積 · X2 對台網攻激增 · X3 官媒戰爭動員敘事

## 3. Level rule (deterministic, shown on site)
- **L5** if E3 = 2, or ≥2 evacuation-class = 2
- **L4** if ≥1 evacuation-class = 2
- **L3** if ≥1 non-evacuation indicator = 2, or ≥4 indicators = 1 (calibrated 2026-07-11: the chronic trio of drills+warnings+rhetoric alone must not escalate)
- **L2** if ≥1 indicator = 1
- **L1** otherwise
Computed only by code (`levels.py`), never by the model. Rule text rendered on the site.

## 4. Repo layout
```
strait-signal/
├── data/        indicators.json · timeline.json · levels.json · meta.json
│                (single source of truth; history[] per indicator)
├── site/        template.html (mockup, data-bound) · build.py → dist/index.html
├── pipeline/    fetch.py · classify_prompt.md · apply.py · levels.py · email_alert.py
├── ops/         run-weekly.sh · com.lezbyte.strait-signal.weekly.plist
├── runs/        runs/YYYY-MM-DD/ snippets.json · proposal.json · run.log
├── tests/       level rule · guardrails · build smoke
└── docs/specs/  this spec + mockup copy
```

## 5. Weekly workflow — headless Claude Code, no API token
Runs via launchd **Monday 10:30 local time** (clears 08:00 daily-sync and Mon 09:00 security-audit). Three isolated phases chained by `run-weekly.sh`; the model never touches deploy or email:
- **A. fetch (deterministic Python)** — per-indicator query sets against the Firecrawl REST API (existing key), **domain whitelist only**: Reuters, AP, BBC, CNA 中央社, State Dept travel advisory, AIT, 國防部. Output: structured `snippets.json` (indicator_id, title, date, domain, excerpt ≤500 chars). Non-whitelisted content never enters the run.
- **B. classify (headless `claude --print`, real Mac binary, MCP-disabled, ZERO tools)** — fetch composes one prompt file (instructions + current states + snippets); the model reads stdin and emits a JSON proposal on stdout. It cannot touch files, network, or shell in this phase. Uses the Claude subscription — **no ANTHROPIC_API_KEY**. Snippets are treated as data; the prompt forbids following instructions found in them.
- **C. apply (deterministic Python)** — schema-validate proposal; **guardrails:** max one status step per indicator per run; any escalation needs ≥2 independent whitelisted sources; invalid proposal → keep last state, log, alert. Then: recompute level → update `data/` + history → `build.py` → deploy via Zeabur CLI → **email ycbxvn@gmail.com on any level change** (old→new, full diff, sources; sender: ZSend API, fallback osascript Mail.app) → failure email after 2 consecutive failed runs.
Manual run anytime: `ops/run-weekly.sh` by hand. Rollback: `apply.py --rollback` restores previous data state and redeploys.

## 6. Safety posture (full-auto publish)
Chosen mode is unattended publish; containment: whitelist-only inputs · phase isolation (agent classifies, code decides) · one-step damping · 2-source escalation rule · deterministic level rule · level-change email with rollback · stale-state visibility via 最後審視 date. First run is **supervised** (daily-brief precedent) before the schedule goes live. `000_Agent/scheduled/` registry updated in the same turn the launchd job is created.

## 7. Launch checklist
1. Scaffold repo, port mockup → template + build, visual 1:1 against approved mockup
2. Pipeline A/B/C + tests green
3. Supervised first run → real July 2026 assessment, sources reviewed by Lezbyte → remove demo watermark
4. Zeabur deploy + subdomain
5. launchd plist + scheduled-registry entries
6. Email path verified (test alert)

## Open items
- ZSend account/key exists? (else Mail.app fallback ships first)
- Final subdomain name if `strait-signal` is taken
