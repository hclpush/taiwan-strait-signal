#!/bin/bash
# strait-signal pipeline — LOCAL/manual runner for dev and supervised runs.
# Production runs on GitHub Actions: .github/workflows/weekly.yml (Mon 10:30 台北).
# Pattern follows ~/.claude/bin/compile-runner.sh (dynamic binary discovery,
# caffeinate wake-hold, watchdog, exit propagation, runner-status.jsonl).
#
# Three isolated phases:
#   A fetch.py     deterministic — Firecrawl REST, whitelist-only snippets
#   B claude       headless classify: stdin prompt -> stdout JSON. NO tools,
#                  NO --dangerously-skip-permissions, MCP disabled. The model
#                  can only emit text here.
#   C apply.py     deterministic — guardrails, build, deploy, email
#
# Manual usage:
#   ops/run-weekly.sh              full run
#   DRY_RUN=1 ops/run-weekly.sh    supervised: everything except write/deploy/email

set -u

REPO="$(cd "$(dirname "$0")/.." && pwd)"
CLAUDE_APP_ROOT="/Users/user/Library/Application Support/Claude/claude-code"
RUN_DIR="$REPO/runs/$(date +%F)"
LOGDIR="$HOME/.claude/logs"
FAILCOUNT_FILE="$REPO/runs/.failcount"
TIMEOUT=600  # classify is a single prompt->response; 10 min is generous
STRAIT_MODEL="${STRAIT_MODEL:-}"
MODEL_FLAG=()
[ -n "$STRAIT_MODEL" ] && MODEL_FLAG=(--model "$STRAIT_MODEL")
mkdir -p "$LOGDIR" "$RUN_DIR"

# ── Binary discovery (same as compile-runner) ────────────────────────────────
LATEST_VERSION=$(ls "$CLAUDE_APP_ROOT" 2>/dev/null | sort -V | tail -1)
REAL_CLAUDE="$CLAUDE_APP_ROOT/$LATEST_VERSION/claude.app/Contents/MacOS/claude"
if [ ! -x "$REAL_CLAUDE" ]; then
    echo "ERROR: claude binary not found under $CLAUDE_APP_ROOT" >&2
    exit 1
fi
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

cd "$REPO" || exit 1
echo "=== strait-signal run started: $(date) ==="

fail() {
    local reason="$1"
    local n=0
    [ -f "$FAILCOUNT_FILE" ] && n=$(cat "$FAILCOUNT_FILE")
    n=$((n + 1))
    echo "$n" > "$FAILCOUNT_FILE"
    echo "FAILED ($reason) — consecutive failures: $n"
    if [ "$n" -ge 2 ]; then
        python3 pipeline/email_alert.py --failure "$n" --detail "$reason" || \
            echo "WARN: failure email also failed" >&2
    fi
    printf '{"job":"strait-signal","end":"%s","exit":1,"secs":%d}\n' \
        "$(date +%Y-%m-%dT%H:%M:%S)" "$SECONDS" >> "$LOGDIR/runner-status.jsonl"
    /usr/bin/osascript -e "display notification \"strait-signal failed: $reason\" with title \"LifeOS\"" 2>/dev/null
    exit 1
}

# ── Watchdog (same pattern as compile-runner) ────────────────────────────────
wait_with_timeout() {
    local pid="$1" timeout="$2" label="$3"
    local start=$SECONDS timed_out=0
    while kill -0 "$pid" 2>/dev/null; do
        sleep 5
        if [ $(( SECONDS - start )) -ge "$timeout" ]; then
            timed_out=1
            echo "WARNING: $label still running after ${timeout}s — killing process tree"
            kill -TERM "$pid" 2>/dev/null; pkill -TERM -P "$pid" 2>/dev/null
            sleep 3
            kill -KILL "$pid" 2>/dev/null; pkill -KILL -P "$pid" 2>/dev/null
            break
        fi
    done
    wait "$pid" 2>/dev/null
    local exit_code=$?
    [ "$timed_out" -eq 1 ] && return 124
    return "$exit_code"
}

# ── Phase A: fetch ───────────────────────────────────────────────────────────
python3 pipeline/fetch.py --out "$RUN_DIR" || fail "fetch"

# ── Phase B: classify (text in -> text out; no tools, no permissions) ────────
"$REAL_CLAUDE" --print "${MODEL_FLAG[@]+"${MODEL_FLAG[@]}"}" \
    --strict-mcp-config --mcp-config "$REPO/ops/empty-mcp.json" \
    < "$RUN_DIR/classify-input.txt" > "$RUN_DIR/proposal-raw.txt" &
CLAUDE_PID=$!
caffeinate -s -i -w "$CLAUDE_PID" &
wait_with_timeout "$CLAUDE_PID" "$TIMEOUT" "classify" || fail "classify (timeout or error)"
[ -s "$RUN_DIR/proposal-raw.txt" ] || fail "classify produced empty output"

# ── Phase C: apply (guardrails, build, deploy, email) ────────────────────────
if [ "${DRY_RUN:-0}" = "1" ]; then
    python3 pipeline/apply.py "$RUN_DIR" --dry-run || fail "apply --dry-run"
else
    python3 pipeline/apply.py "$RUN_DIR" || fail "apply"
fi

rm -f "$FAILCOUNT_FILE"
echo "=== strait-signal run finished OK: $(date) ==="
printf '{"job":"strait-signal","end":"%s","exit":0,"secs":%d}\n' \
    "$(date +%Y-%m-%dT%H:%M:%S)" "$SECONDS" >> "$LOGDIR/runner-status.jsonl"
/usr/bin/osascript -e 'display notification "strait-signal weekly run complete ✓" with title "LifeOS"' 2>/dev/null
exit 0
