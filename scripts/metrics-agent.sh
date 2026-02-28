#!/usr/bin/env bash
# metrics-agent.sh — Seabone Metrics & Dashboard Agent
# Tracks health trends, agent success rates, engine performance, costs.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
SEABONE_DIR="$PROJECT_DIR/.seabone"
LOG_DIR="$SEABONE_DIR/logs"
METRICS_LOG="$LOG_DIR/metrics.log"
METRICS_DIR="$SEABONE_DIR/metrics"
MEMORY_DIR="$SEABONE_DIR/memory"
MEMORY_FILE="$SEABONE_DIR/MEMORY.md"
ACTIVE_FILE="$SEABONE_DIR/active-tasks.json"
COMPLETED_FILE="$SEABONE_DIR/completed-tasks.json"
FINDINGS_DIR="$SEABONE_DIR/findings"
REPORTS_DIR="$SEABONE_DIR/reports"
EVENT_LOG="$LOG_DIR/events.log"
LOCKFILE="/tmp/seabone-metrics-${PROJECT_NAME}.lock"
export PATH="$HOME/.local/bin:$PATH"

if [[ -f "$PROJECT_DIR/.env.agent-swarm" ]]; then
    set -a; source "$PROJECT_DIR/.env.agent-swarm"; set +a
fi

mkdir -p "$LOG_DIR" "$METRICS_DIR" "$MEMORY_DIR"

exec 201>"$LOCKFILE"
if ! flock -n 201; then echo "Another metrics agent running."; exit 0; fi

log() { local msg="[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; echo "$msg"; echo "$msg" >> "$METRICS_LOG"; }
notify() { "$SCRIPT_DIR/notify-telegram.sh" "$1" 2>/dev/null || true; }

# Generate metrics every hour
METRICS_INTERVAL="${SEABONE_METRICS_INTERVAL:-3600}"

log "=========================================="
log "Seabone Metrics Agent started"
log "Project: $PROJECT_NAME"
log "=========================================="

TODAY=$(date +%Y-%m-%d)
DAILY_FILE="$MEMORY_DIR/${TODAY}.md"

while true; do
    NEW_TODAY=$(date +%Y-%m-%d)
    if [[ "$NEW_TODAY" != "$TODAY" ]]; then TODAY="$NEW_TODAY"; DAILY_FILE="$MEMORY_DIR/${TODAY}.md"; fi

    cd "$PROJECT_DIR"

    SNAPSHOT_FILE="$METRICS_DIR/${TODAY}-$(date +%H%M).json"

    # ---- Gather metrics ----

    # Agent stats
    COMPLETED_COUNT=$(jq 'length' "$COMPLETED_FILE" 2>/dev/null || echo 0)
    ACTIVE_COUNT=$(jq 'length' "$ACTIVE_FILE" 2>/dev/null || echo 0)

    # Success/failure from completed
    MERGED_COUNT=$(jq '[.[] | select(.status == "merged")] | length' "$COMPLETED_FILE" 2>/dev/null || echo 0)
    REJECTED_COUNT=$(jq '[.[] | select(.status == "rejected")] | length' "$COMPLETED_FILE" 2>/dev/null || echo 0)
    FAILED_COUNT=$(jq '[.[] | select(.status == "failed")] | length' "$COMPLETED_FILE" 2>/dev/null || echo 0)

    # By engine
    CODEX_TASKS=$(jq '[.[] | select(.engine == "codex")] | length' "$COMPLETED_FILE" 2>/dev/null || echo 0)
    CLAUDE_TASKS=$(jq '[.[] | select(.engine == "claude" or .engine == "claude-frontend")] | length' "$COMPLETED_FILE" 2>/dev/null || echo 0)
    AIDER_TASKS=$(jq '[.[] | select(.engine == "aider")] | length' "$COMPLETED_FILE" 2>/dev/null || echo 0)
    SENIOR_TASKS=$(jq '[.[] | select(.engine == "codex-senior")] | length' "$COMPLETED_FILE" 2>/dev/null || echo 0)
    TEST_TASKS=$(jq '[.[] | select(.engine == "codex-test")] | length' "$COMPLETED_FILE" 2>/dev/null || echo 0)

    # Success rates by engine
    CODEX_MERGED=$(jq '[.[] | select(.engine == "codex" and .status == "merged")] | length' "$COMPLETED_FILE" 2>/dev/null || echo 0)
    CLAUDE_MERGED=$(jq '[.[] | select((.engine == "claude" or .engine == "claude-frontend") and .status == "merged")] | length' "$COMPLETED_FILE" 2>/dev/null || echo 0)
    AIDER_MERGED=$(jq '[.[] | select(.engine == "aider" and .status == "merged")] | length' "$COMPLETED_FILE" 2>/dev/null || echo 0)

    # Findings trend
    TOTAL_FINDINGS=0
    LATEST_FINDING=$(ls -t "$FINDINGS_DIR"/*.json 2>/dev/null | head -1)
    if [[ -n "${LATEST_FINDING:-}" ]]; then
        TOTAL_FINDINGS=$(jq 'length' "$LATEST_FINDING" 2>/dev/null || echo 0)
    fi

    # Open PRs
    OPEN_PRS=$(gh pr list --state open --json number -q 'length' 2>/dev/null || echo 0)

    # Git stats
    TOTAL_COMMITS=$(git rev-list --count main 2>/dev/null || echo 0)
    TODAY_COMMITS=$(git log --oneline --since="$TODAY" 2>/dev/null | wc -l | tr -d ' ')

    # Calculate success rate
    if [[ "$COMPLETED_COUNT" -gt 0 ]]; then
        SUCCESS_RATE=$(echo "scale=1; $MERGED_COUNT * 100 / $COMPLETED_COUNT" | bc 2>/dev/null || echo "0")
    else
        SUCCESS_RATE="0"
    fi

    # Write snapshot
    jq -n \
        --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        --argjson completed "$COMPLETED_COUNT" \
        --argjson active "$ACTIVE_COUNT" \
        --argjson merged "$MERGED_COUNT" \
        --argjson rejected "$REJECTED_COUNT" \
        --argjson failed "$FAILED_COUNT" \
        --arg success_rate "$SUCCESS_RATE" \
        --argjson codex "$CODEX_TASKS" \
        --argjson claude "$CLAUDE_TASKS" \
        --argjson aider "$AIDER_TASKS" \
        --argjson senior "$SENIOR_TASKS" \
        --argjson test_tasks "$TEST_TASKS" \
        --argjson codex_merged "$CODEX_MERGED" \
        --argjson claude_merged "$CLAUDE_MERGED" \
        --argjson aider_merged "$AIDER_MERGED" \
        --argjson findings "$TOTAL_FINDINGS" \
        --argjson open_prs "$OPEN_PRS" \
        --argjson total_commits "$TOTAL_COMMITS" \
        --argjson today_commits "$TODAY_COMMITS" \
        '{
            timestamp: $ts,
            agents: {completed: $completed, active: $active, merged: $merged, rejected: $rejected, failed: $failed, success_rate: $success_rate},
            engines: {codex: $codex, claude: $claude, aider: $aider, senior: $senior, test: $test_tasks},
            engine_success: {codex_merged: $codex_merged, claude_merged: $claude_merged, aider_merged: $aider_merged},
            codebase: {findings: $findings, open_prs: $open_prs, total_commits: $total_commits, today_commits: $today_commits}
        }' > "$SNAPSHOT_FILE"

    log "Metrics snapshot: completed=$COMPLETED_COUNT merged=$MERGED_COUNT success=${SUCCESS_RATE}% findings=$TOTAL_FINDINGS"

    # Daily summary notification (only at top of hour)
    HOUR=$(date +%H)
    if [[ "$HOUR" == "09" || "$HOUR" == "18" ]]; then
        notify "📊 *Seabone Metrics* — $PROJECT_NAME
Tasks: $COMPLETED_COUNT total ($MERGED_COUNT merged, $REJECTED_COUNT rejected, $FAILED_COUNT failed)
Success rate: ${SUCCESS_RATE}%
Engines: codex=$CODEX_TASKS claude=$CLAUDE_TASKS aider=$AIDER_TASKS
Active: $ACTIVE_COUNT | Open PRs: $OPEN_PRS
Findings: $TOTAL_FINDINGS | Commits today: $TODAY_COMMITS"
    fi

    sleep "$METRICS_INTERVAL"
done
