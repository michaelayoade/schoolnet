#!/usr/bin/env bash
# orchestrator.sh — Seabone Master Orchestrator
# The brain of the swarm. Manages all other agents, ensures system health,
# handles lifecycle, reacts to events, and makes strategic decisions.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
SEABONE_DIR="$PROJECT_DIR/.seabone"
CONFIG_FILE="$SEABONE_DIR/config.json"
LOG_DIR="$SEABONE_DIR/logs"
ORCH_LOG="$LOG_DIR/orchestrator.log"
MEMORY_DIR="$SEABONE_DIR/memory"
MEMORY_FILE="$SEABONE_DIR/MEMORY.md"
SOUL_FILE="$SEABONE_DIR/SOUL.md"
ACTIVE_FILE="$SEABONE_DIR/active-tasks.json"
COMPLETED_FILE="$SEABONE_DIR/completed-tasks.json"
FINDINGS_DIR="$SEABONE_DIR/findings"
REPORTS_DIR="$SEABONE_DIR/reports"
METRICS_DIR="$SEABONE_DIR/metrics"
PM_STATE="$SEABONE_DIR/pm-state.json"
CI_STATE="$SEABONE_DIR/ci-state.json"
ORCH_STATE="$SEABONE_DIR/orchestrator-state.json"
LOCKFILE="/tmp/seabone-orchestrator-${PROJECT_NAME}.lock"
export PATH="$HOME/.local/bin:$PATH"

if [[ -f "$PROJECT_DIR/.env.agent-swarm" ]]; then
    set -a; source "$PROJECT_DIR/.env.agent-swarm"; set +a
fi

mkdir -p "$LOG_DIR" "$MEMORY_DIR" "$METRICS_DIR" "$REPORTS_DIR"

exec 200>"$LOCKFILE"
if ! flock -n 200 2>/dev/null; then echo "Another orchestrator running."; exit 0; fi

log() { local msg="[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; echo "$msg"; echo "$msg" >> "$ORCH_LOG"; }
notify() { "$SCRIPT_DIR/notify-telegram.sh" "$1" 2>/dev/null || true; }

# Orchestrator checks every 2 minutes
ORCH_INTERVAL="${SEABONE_ORCH_INTERVAL:-120}"

# ---- Agent Registry ----
# All managed agents with their tmux session names and scripts
declare -A AGENT_SESSIONS=(
    [coordinator]="seabone-coordinator-${PROJECT_NAME}"
    [sentinel]="seabone-sentinel-${PROJECT_NAME}"
    [pm]="seabone-pm-${PROJECT_NAME}"
    [ci-monitor]="seabone-ci-${PROJECT_NAME}"
    [conflict-detector]="seabone-conflict-${PROJECT_NAME}"
    [docs-agent]="seabone-docs-${PROJECT_NAME}"
    [deps-agent]="seabone-deps-${PROJECT_NAME}"
    [metrics]="seabone-metrics-${PROJECT_NAME}"
)

declare -A AGENT_SCRIPTS=(
    [coordinator]="coordinator.sh"
    [sentinel]="sentinel.sh"
    [pm]="pm-agent.sh"
    [ci-monitor]="ci-monitor.sh"
    [conflict-detector]="conflict-detector.sh"
    [docs-agent]="docs-agent.sh"
    [deps-agent]="deps-agent.sh"
    [metrics]="metrics-agent.sh"
)

# Which agents are REQUIRED (always running)
REQUIRED_AGENTS="coordinator sentinel pm ci-monitor metrics"
# Which agents are OPTIONAL (start on demand or based on conditions)
OPTIONAL_AGENTS="conflict-detector docs-agent deps-agent"

# Init orchestrator state
if [[ ! -f "$ORCH_STATE" ]]; then
    echo '{"started_at":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","restarts":{},"health_checks":0,"last_health":"unknown"}' > "$ORCH_STATE"
fi

# ---- Agent lifecycle functions ----
is_running() {
    local agent="$1"
    local session="${AGENT_SESSIONS[$agent]}"
    tmux has-session -t "$session" 2>/dev/null
}

start_agent() {
    local agent="$1"
    local session="${AGENT_SESSIONS[$agent]}"
    local script="${AGENT_SCRIPTS[$agent]}"

    if is_running "$agent"; then
        return 0
    fi

    log "Starting agent: $agent"
    tmux new-session -d -s "$session" "bash $SCRIPT_DIR/$script"

    # Track restart count
    local restarts
    restarts=$(jq -r ".restarts[\"$agent\"] // 0" "$ORCH_STATE" 2>/dev/null || echo 0)
    restarts=$((restarts + 1))
    jq --arg a "$agent" --argjson r "$restarts" '.restarts[$a] = $r' "$ORCH_STATE" > "${ORCH_STATE}.tmp" && mv "${ORCH_STATE}.tmp" "$ORCH_STATE"

    return 0
}

stop_agent() {
    local agent="$1"
    local session="${AGENT_SESSIONS[$agent]}"

    if is_running "$agent"; then
        tmux kill-session -t "$session" 2>/dev/null || true
        log "Stopped agent: $agent"
    fi
}

# ---- Health check ----
check_system_health() {
    local issues=""
    local healthy=0
    local total=0

    # Check required agents
    for agent in $REQUIRED_AGENTS; do
        total=$((total + 1))
        if is_running "$agent"; then
            healthy=$((healthy + 1))
        else
            issues="${issues}\n  - $agent is DOWN"
        fi
    done

    # Check optional agents
    for agent in $OPTIONAL_AGENTS; do
        if is_running "$agent"; then
            healthy=$((healthy + 1))
        fi
        total=$((total + 1))
    done

    # Check disk space
    DISK_PCT=$(df "$PROJECT_DIR" | awk 'NR==2 {print $5}' | tr -d '%' 2>/dev/null || echo 0)
    if [[ "$DISK_PCT" -gt 90 ]]; then
        issues="${issues}\n  - Disk usage at ${DISK_PCT}%"
    fi

    # Check memory
    MEM_AVAIL=$(free -m 2>/dev/null | awk '/Mem:/ {print $7}' || echo 9999)
    if [[ "$MEM_AVAIL" -lt 500 ]]; then
        issues="${issues}\n  - Low memory: ${MEM_AVAIL}MB available"
    fi

    # Check log file sizes (prevent unbounded growth)
    for logfile in "$LOG_DIR"/*.log; do
        [[ -f "$logfile" ]] || continue
        SIZE_MB=$(du -m "$logfile" 2>/dev/null | cut -f1)
        if [[ "${SIZE_MB:-0}" -gt 100 ]]; then
            # Rotate: keep last 1000 lines
            tail -1000 "$logfile" > "${logfile}.tmp" && mv "${logfile}.tmp" "$logfile"
            log "Rotated log: $(basename "$logfile") (was ${SIZE_MB}MB)"
        fi
    done

    echo "$healthy/$total agents healthy${issues}"
}

# ---- Smart start: decide which optional agents to run ----
decide_optional_agents() {
    local active_count
    active_count=$(jq 'length' "$ACTIVE_FILE" 2>/dev/null || echo 0)
    local open_prs
    open_prs=$(gh pr list --state open --json number -q 'length' 2>/dev/null || echo 0)

    # Start conflict detector if 3+ PRs open
    if [[ "$open_prs" -ge 3 ]]; then
        start_agent "conflict-detector"
    fi

    # Start docs agent if tasks completed today
    local completed
    completed=$(jq 'length' "$COMPLETED_FILE" 2>/dev/null || echo 0)
    local docs_last
    docs_last=$(jq -r '.last_documented_count // 0' "$SEABONE_DIR/docs-state.json" 2>/dev/null || echo 0)
    if [[ "$completed" -gt "$docs_last" ]]; then
        start_agent "docs-agent"
    fi

    # Start deps agent once daily (check if ran today)
    local deps_ran_today
    deps_ran_today=$(grep -c "Deps audit" "$MEMORY_DIR/${TODAY}.md" 2>/dev/null || echo 0)
    if [[ "$deps_ran_today" -eq 0 ]]; then
        start_agent "deps-agent"
    fi
}

# ============================================
#  MAIN LOOP
# ============================================

TODAY=$(date +%Y-%m-%d)
DAILY_FILE="$MEMORY_DIR/${TODAY}.md"

log "=========================================="
log "Seabone Orchestrator — Master Control"
log "Project: $PROJECT_NAME"
log "Required agents: $REQUIRED_AGENTS"
log "Optional agents: $OPTIONAL_AGENTS"
log "Poll interval: ${ORCH_INTERVAL}s"
log "=========================================="

notify "🧠 *Seabone Orchestrator* started
Project: \`$PROJECT_NAME\`
Managing: coordinator, sentinel, PM, CI, metrics, docs, deps, conflict-detector"

# ---- Initial startup: ensure all required agents are running ----
log "Initial startup: launching required agents..."
for agent in $REQUIRED_AGENTS; do
    start_agent "$agent"
    sleep 2  # Stagger startups
done

CYCLE=0
while true; do
    CYCLE=$((CYCLE + 1))

    # Date rollover
    NEW_TODAY=$(date +%Y-%m-%d)
    if [[ "$NEW_TODAY" != "$TODAY" ]]; then
        TODAY="$NEW_TODAY"
        DAILY_FILE="$MEMORY_DIR/${TODAY}.md"
    fi
    TODAY=$(date +%Y-%m-%d)
    DAILY_FILE="$MEMORY_DIR/${TODAY}.md"

    cd "$PROJECT_DIR"

    # ---- 1. Health check: restart crashed required agents ----
    for agent in $REQUIRED_AGENTS; do
        if ! is_running "$agent"; then
            log "ALERT: Required agent '$agent' is down. Restarting..."
            start_agent "$agent"
            notify "⚠️ *Orchestrator*: restarted \`$agent\` (was down)"
            sleep 2
        fi
    done

    # ---- 2. Smart optional agent management ----
    decide_optional_agents

    # ---- 3. System health check ----
    HEALTH=$(check_system_health)
    if echo "$HEALTH" | grep -q "DOWN\|Low memory\|Disk usage"; then
        log "HEALTH WARNING: $HEALTH"
        # Only notify every 10 cycles to avoid spam
        if (( CYCLE % 10 == 0 )); then
            notify "⚠️ *Orchestrator Health*: $HEALTH"
        fi
    fi

    # Update health check count
    CHECKS=$(jq -r '.health_checks // 0' "$ORCH_STATE" 2>/dev/null || echo 0)
    jq --argjson c "$((CHECKS + 1))" --arg h "$HEALTH" '.health_checks = $c | .last_health = $h' "$ORCH_STATE" > "${ORCH_STATE}.tmp" && mv "${ORCH_STATE}.tmp" "$ORCH_STATE" 2>/dev/null || true

    # ---- 4. Stale agent cleanup ----
    # Check for coding agents that have been running too long (>2 hours)
    CUTOFF_TS=$(date -u -d '2 hours ago' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v-2H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo '2000-01-01T00:00:00Z')
    STALE_AGENTS=$(jq -r --arg cutoff "$CUTOFF_TS" \
        '[.[] | select(.status == "running" and .started_at < $cutoff)] | .[].id' "$ACTIVE_FILE" 2>/dev/null || echo "")

    for stale_id in $STALE_AGENTS; do
        [[ -z "$stale_id" ]] && continue
        log "STALE: Agent $stale_id running >2h. Checking..."
        SESSION=$(jq -r --arg id "$stale_id" '.[] | select(.id == $id) | .session' "$ACTIVE_FILE" 2>/dev/null || echo "")
        if [[ -n "$SESSION" ]] && ! tmux has-session -t "$SESSION" 2>/dev/null; then
            log "Stale agent $stale_id: tmux gone. Marking failed."
            jq --arg id "$stale_id" '(.[] | select(.id == $id) | .status) = "failed"' "$ACTIVE_FILE" > "${ACTIVE_FILE}.tmp" && mv "${ACTIVE_FILE}.tmp" "$ACTIVE_FILE" 2>/dev/null || true
            notify "⏰ *Orchestrator*: marked \`$stale_id\` as failed (stale >2h, tmux gone)"
        fi
    done

    # ---- 5. Daily report (once at end of day) ----
    HOUR=$(date +%H)
    if [[ "$HOUR" == "23" ]] && (( CYCLE % 30 == 0 )); then
        ACTIVE=$(jq 'length' "$ACTIVE_FILE" 2>/dev/null || echo 0)
        COMPLETED=$(jq 'length' "$COMPLETED_FILE" 2>/dev/null || echo 0)
        MERGED=$(jq '[.[] | select(.status == "merged")] | length' "$COMPLETED_FILE" 2>/dev/null || echo 0)
        RESTARTS=$(jq '.restarts | to_entries | map("\(.key): \(.value)") | join(", ")' "$ORCH_STATE" 2>/dev/null || echo "none")

        notify "📊 *Daily Orchestrator Report* — $PROJECT_NAME
Date: $TODAY
Tasks: $COMPLETED completed ($MERGED merged)
Active: $ACTIVE
Agent restarts: $RESTARTS
System: $HEALTH"
    fi

    # ---- 6. Log rotation check (keep last 7 days of metrics) ----
    if (( CYCLE % 360 == 0 )); then  # Every ~12 hours
        find "$METRICS_DIR" -name "*.json" -mtime +7 -delete 2>/dev/null || true
        find "$SEABONE_DIR/transcripts" -name "*.jsonl" -mtime +7 -delete 2>/dev/null || true
        log "Housekeeping: cleaned old metrics and transcripts"
    fi

    sleep "$ORCH_INTERVAL"
done
