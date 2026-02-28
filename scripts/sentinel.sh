#!/usr/bin/env bash
# sentinel.sh — Seabone Continuous Improvement Agent
# Runs on a loop (or via cron): analyses the codebase, spawns fix agents,
# tracks improvement over time, and writes reports.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
SEABONE_DIR="$PROJECT_DIR/.seabone"
CONFIG_FILE="$SEABONE_DIR/config.json"
LOG_DIR="$SEABONE_DIR/logs"
SENTINEL_LOG="$LOG_DIR/sentinel.log"
MEMORY_DIR="$SEABONE_DIR/memory"
MEMORY_FILE="$SEABONE_DIR/MEMORY.md"
FINDINGS_DIR="$SEABONE_DIR/findings"
REPORTS_DIR="$SEABONE_DIR/reports"
ACTIVE_FILE="$SEABONE_DIR/active-tasks.json"
COMPLETED_FILE="$SEABONE_DIR/completed-tasks.json"
LOCKFILE="/tmp/seabone-sentinel-${PROJECT_NAME}.lock"
export PATH="$HOME/.local/bin:$PATH"

if [[ -f "$PROJECT_DIR/.env.agent-swarm" ]]; then
    set -a
    source "$PROJECT_DIR/.env.agent-swarm"
    set +a
fi

mkdir -p "$LOG_DIR" "$FINDINGS_DIR" "$MEMORY_DIR" "$REPORTS_DIR"

# ---- Lock ----
exec 8>"$LOCKFILE"
if ! flock -n 8; then
    echo "Another sentinel instance is running."
    exit 0
fi

log() {
    local msg="[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
    echo "$msg"
    echo "$msg" >> "$SENTINEL_LOG"
}

notify() {
    "$SCRIPT_DIR/notify-telegram.sh" "$1" 2>/dev/null || true
}

# How long to wait between scan cycles (default 2 hours)
SCAN_INTERVAL="${SEABONE_SENTINEL_INTERVAL:-7200}"

# Max fix agents to spawn per cycle
MAX_FIXES_PER_CYCLE="${SEABONE_SENTINEL_MAX_FIXES:-3}"

# Scan types to rotate through
SCAN_TYPES=("security" "quality" "api" "deps")

TODAY=$(date +%Y-%m-%d)
DAILY_FILE="$MEMORY_DIR/${TODAY}.md"

log "=========================================="
log "Seabone Sentinel — Continuous Improvement"
log "Project: $PROJECT_NAME"
log "Scan interval: ${SCAN_INTERVAL}s"
log "Max fixes/cycle: $MAX_FIXES_PER_CYCLE"
log "=========================================="

notify "🛡️ *Seabone Sentinel* started
Project: \`$PROJECT_NAME\`
Interval: ${SCAN_INTERVAL}s
Scans: ${SCAN_TYPES[*]}"

CYCLE=0
SCAN_INDEX=0

while true; do
    CYCLE=$((CYCLE + 1))

    # Refresh date at midnight
    NEW_TODAY=$(date +%Y-%m-%d)
    if [[ "$NEW_TODAY" != "$TODAY" ]]; then
        TODAY="$NEW_TODAY"
        DAILY_FILE="$MEMORY_DIR/${TODAY}.md"
        SCAN_INDEX=0  # Reset rotation daily
    fi

    # Pick scan type (rotate through them)
    SCAN_TYPE="${SCAN_TYPES[$SCAN_INDEX]}"
    SCAN_INDEX=$(( (SCAN_INDEX + 1) % ${#SCAN_TYPES[@]} ))

    log "--- Sentinel cycle $CYCLE: $SCAN_TYPE scan ---"

    cd "$PROJECT_DIR"

    # Pull latest main first
    git checkout main 2>/dev/null && git pull origin main 2>/dev/null || true

    # Check how many agents are currently running
    RUNNING=$(jq '[.[] | select(.status == "running")] | length' "$ACTIVE_FILE" 2>/dev/null || echo 0)
    MAX_AGENTS=$(jq -r '.max_concurrent_agents // 10' "$CONFIG_FILE" 2>/dev/null || echo 10)
    AVAILABLE_SLOTS=$(( MAX_AGENTS - RUNNING ))

    if (( AVAILABLE_SLOTS <= 0 )); then
        log "No agent slots available ($RUNNING/$MAX_AGENTS running). Skipping scan."
        sleep "$SCAN_INTERVAL"
        continue
    fi

    # Cap fixes to available slots
    FIXES_THIS_CYCLE=$MAX_FIXES_PER_CYCLE
    if (( FIXES_THIS_CYCLE > AVAILABLE_SLOTS )); then
        FIXES_THIS_CYCLE=$AVAILABLE_SLOTS
    fi

    # Load persistent memory
    MEMORY=""
    if [[ -f "$MEMORY_FILE" ]]; then
        MEMORY=$(cat "$MEMORY_FILE")
    fi

    # Load previous findings to avoid duplicates
    PREVIOUS_FINDINGS=""
    LATEST_FINDING=$(ls -t "$FINDINGS_DIR"/*.json 2>/dev/null | head -1)
    if [[ -n "${LATEST_FINDING:-}" ]]; then
        PREVIOUS_FINDINGS=$(cat "$LATEST_FINDING" 2>/dev/null || echo "[]")
    fi

    # Load completed task IDs to avoid re-fixing
    COMPLETED_IDS=""
    if [[ -f "$COMPLETED_FILE" ]]; then
        COMPLETED_IDS=$(jq -r '.[].id' "$COMPLETED_FILE" 2>/dev/null || echo "")
    fi

    FINDING_FILE="$FINDINGS_DIR/${TODAY}-${SCAN_TYPE}-cycle${CYCLE}.json"
    REPORT_FILE="$REPORTS_DIR/${TODAY}-${SCAN_TYPE}-cycle${CYCLE}.md"

    # Build the analysis + fix prompt
    PROMPT="You are Seabone Sentinel, a continuous improvement agent for the $PROJECT_NAME codebase.

## Your Memory
${MEMORY}

## Scan Type: ${SCAN_TYPE}

## Previous Findings (avoid duplicates)
${PREVIOUS_FINDINGS:-None yet.}

## Already Fixed (do NOT re-report these)
${COMPLETED_IDS:-None yet.}

## Your Job

### Step 1: Deep Scan
Thoroughly scan the codebase for ${SCAN_TYPE} issues.

$(case "$SCAN_TYPE" in
    security)
        echo "Focus on:
- SQL injection (raw queries, string formatting)
- Missing authentication on sensitive endpoints
- Hardcoded secrets, API keys, passwords
- Missing input validation
- CSRF/XSS vulnerabilities
- SSRF, path traversal, insecure deserialization
- Missing rate limiting on auth endpoints
- Weak cryptography or hashing"
        ;;
    quality)
        echo "Focus on:
- Dead code (unused functions, unreachable branches)
- Missing error handling (bare except, swallowed exceptions)
- Type mismatches (wrong return types, schema vs model)
- Functions too long (>80 lines)
- Duplicate logic that should be extracted
- Missing or broken tests
- Inconsistent patterns across similar files
- Memory leaks, resource cleanup issues"
        ;;
    api)
        echo "Focus on:
- Endpoints missing response_model declarations
- Inconsistent error response formats
- Missing query parameter validation
- Endpoints returning raw dicts instead of Pydantic models
- Missing pagination on list endpoints
- Inconsistent URL naming conventions
- Missing OpenAPI descriptions
- N+1 query patterns in endpoint handlers"
        ;;
    deps)
        echo "Focus on:
- Unused imports in Python files
- Missing __init__.py files
- Circular import risks
- Dependencies imported but not in requirements/pyproject.toml
- Deprecated API usage
- Outdated package versions with known CVEs
- Missing type stubs for typed packages"
        ;;
esac)

### Step 2: Write Findings
Write findings as JSON array to: ${FINDING_FILE}

Each finding:
{
  \"id\": \"${SCAN_TYPE}-c${CYCLE}-<number>\",
  \"severity\": \"critical|high|medium|low\",
  \"category\": \"${SCAN_TYPE}\",
  \"file\": \"path/to/file.py\",
  \"line\": <line number or null>,
  \"issue\": \"<one sentence problem description>\",
  \"task\": \"<one sentence fix instruction for a coding agent>\",
  \"auto_fixable\": true|false,
  \"effort\": \"trivial|small|medium|large\"
}

Sort by severity (critical first), then by effort (trivial first).

### Step 3: Write Improvement Report
Write a markdown report to: ${REPORT_FILE}

Include:
- Summary of scan results
- Comparison with previous findings (what's new, what's still open, what was fixed)
- Top 3 priority fixes
- Codebase health score (0-100) based on findings
- Trend: improving, stable, or degrading vs last scan

### Step 4: DO NOT spawn agents
Do NOT spawn fix agents. The Project Manager agent handles task assignment and engine selection.
Just write findings and the report — the PM will pick them up.

### Step 5: Update Memory
- Append a summary line to: ${DAILY_FILE}
  Format: \"- HH:MM Sentinel ${SCAN_TYPE} scan: <count> findings\"
- If you discovered new patterns, update ${MEMORY_FILE} under '## Known Patterns'

### Step 6: Summary
End with a one-line summary."

    log "Running Claude sentinel scan ($SCAN_TYPE)..."
    CLAUDE_OUTPUT=$(claude \
        -p "$PROMPT" \
        --dangerously-skip-permissions \
        --output-format text \
        --model sonnet \
        --max-turns 60 \
        2>&1) || true

    echo "$CLAUDE_OUTPUT" >> "$SENTINEL_LOG"

    SUMMARY=$(echo "$CLAUDE_OUTPUT" | grep -v '^$' | tail -1)
    log "Cycle $CYCLE result: $SUMMARY"

    # Count findings
    if [[ -f "$FINDING_FILE" ]]; then
        TOTAL=$(jq 'length' "$FINDING_FILE" 2>/dev/null || echo 0)
        CRITICAL=$(jq '[.[] | select(.severity == "critical")] | length' "$FINDING_FILE" 2>/dev/null || echo 0)
        HIGH=$(jq '[.[] | select(.severity == "high")] | length' "$FINDING_FILE" 2>/dev/null || echo 0)

        log "Findings: $TOTAL total ($CRITICAL critical, $HIGH high)"

        # Build health score notification
        HEALTH_SCORE=""
        if [[ -f "$REPORT_FILE" ]]; then
            HEALTH_SCORE=$(grep -i "health score" "$REPORT_FILE" | head -1 || echo "")
        fi

        notify "🛡️ *Seabone Sentinel*: \`$SCAN_TYPE\` scan #${CYCLE}
Findings: $TOTAL ($CRITICAL crit, $HIGH high)
${HEALTH_SCORE}
Fixes spawned: up to $FIXES_THIS_CYCLE"
    else
        log "No findings file generated."
        notify "🛡️ *Seabone Sentinel*: \`$SCAN_TYPE\` scan #${CYCLE} — clean ✨"
    fi

    log "Next scan in ${SCAN_INTERVAL}s..."
    sleep "$SCAN_INTERVAL"
done
