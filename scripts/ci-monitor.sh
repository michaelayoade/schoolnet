#!/usr/bin/env bash
# ci-monitor.sh — Seabone CI/CD Monitor Agent
# Watches GitHub Actions, alerts on failures, auto-spawns hotfixes.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
SEABONE_DIR="$PROJECT_DIR/.seabone"
CONFIG_FILE="$SEABONE_DIR/config.json"
LOG_DIR="$SEABONE_DIR/logs"
CI_LOG="$LOG_DIR/ci-monitor.log"
MEMORY_DIR="$SEABONE_DIR/memory"
MEMORY_FILE="$SEABONE_DIR/MEMORY.md"
ACTIVE_FILE="$SEABONE_DIR/active-tasks.json"
COMPLETED_FILE="$SEABONE_DIR/completed-tasks.json"
CI_STATE="$SEABONE_DIR/ci-state.json"
LOCKFILE="/tmp/seabone-ci-${PROJECT_NAME}.lock"
export PATH="$HOME/.local/bin:$PATH"

if [[ -f "$PROJECT_DIR/.env.agent-swarm" ]]; then
    set -a; source "$PROJECT_DIR/.env.agent-swarm"; set +a
fi

mkdir -p "$LOG_DIR" "$MEMORY_DIR"

exec 6>"$LOCKFILE"
if ! flock -n 6; then echo "Another CI monitor running."; exit 0; fi

log() { local msg="[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; echo "$msg"; echo "$msg" >> "$CI_LOG"; }
notify() { "$SCRIPT_DIR/notify-telegram.sh" "$1" 2>/dev/null || true; }

CI_INTERVAL="${SEABONE_CI_INTERVAL:-180}"

if [[ ! -f "$CI_STATE" ]]; then
    echo '{"seen_runs":[],"failures":[],"last_green":"unknown"}' > "$CI_STATE"
fi

log "=========================================="
log "Seabone CI Monitor started"
log "Project: $PROJECT_NAME"
log "Poll interval: ${CI_INTERVAL}s"
log "=========================================="

notify "🔄 *Seabone CI Monitor* started on \`$PROJECT_NAME\`"

TODAY=$(date +%Y-%m-%d)
DAILY_FILE="$MEMORY_DIR/${TODAY}.md"

while true; do
    NEW_TODAY=$(date +%Y-%m-%d)
    if [[ "$NEW_TODAY" != "$TODAY" ]]; then TODAY="$NEW_TODAY"; DAILY_FILE="$MEMORY_DIR/${TODAY}.md"; fi

    cd "$PROJECT_DIR"

    # Get recent workflow runs
    RUNS=$(gh run list --limit 10 --json databaseId,status,conclusion,headBranch,name,createdAt 2>/dev/null || echo '[]')
    SEEN=$(jq -r '.seen_runs // [] | .[]' "$CI_STATE" 2>/dev/null || echo "")

    # Check for new failures
    FAILED_RUNS=$(echo "$RUNS" | jq -r '[.[] | select(.conclusion == "failure")]' 2>/dev/null || echo '[]')
    FAILED_COUNT=$(echo "$FAILED_RUNS" | jq 'length' 2>/dev/null || echo 0)

    if [[ "$FAILED_COUNT" -gt 0 ]]; then
        echo "$FAILED_RUNS" | jq -r '.[] | .databaseId' | while read -r run_id; do
            if echo "$SEEN" | grep -q "^${run_id}$"; then continue; fi

            BRANCH=$(echo "$FAILED_RUNS" | jq -r ".[] | select(.databaseId == $run_id) | .headBranch")
            WORKFLOW=$(echo "$FAILED_RUNS" | jq -r ".[] | select(.databaseId == $run_id) | .name")
            HANDLED=1

            log "CI FAILURE: run $run_id on branch $BRANCH ($WORKFLOW)"

            # Get failure details
            FAIL_LOG=$(gh run view "$run_id" --log-failed 2>/dev/null | tail -50 || echo "Could not fetch logs")

            # If it's main branch, this is critical — spawn hotfix
            if [[ "$BRANCH" == "main" || "$BRANCH" == "master" ]]; then
                notify "🚨 *CI FAILURE on main!*
Run: $run_id
Workflow: $WORKFLOW
Spawning hotfix agent..."

                if ! "$SCRIPT_DIR/spawn-agent.sh" \
                    "hotfix-ci-${run_id}" \
                    "HOTFIX: CI failure on main branch. Workflow: ${WORKFLOW}. Error log: ${FAIL_LOG}" \
                    --engine codex-senior --urgent --force >/dev/null 2>&1; then
                    HANDLED=0
                    log "Hotfix spawn failed for CI run $run_id (branch=$BRANCH)"
                    notify "❌ *CI hotfix spawn failed* for run \`$run_id\` on \`$BRANCH\`.
Will retry on next poll."
                fi
            else
                notify "⚠️ *CI failure*: branch \`$BRANCH\`
Run: $run_id
Workflow: $WORKFLOW"
            fi

            # Mark as seen only when handled successfully.
            if [[ "$HANDLED" -eq 1 ]]; then
                jq ".seen_runs += [${run_id}] | .seen_runs |= unique" "$CI_STATE" > "${CI_STATE}.tmp" && mv "${CI_STATE}.tmp" "$CI_STATE"
            fi
        done
    fi

    # Check for recoveries (failure → success on same branch)
    SUCCESS_RUNS=$(echo "$RUNS" | jq -r '[.[] | select(.conclusion == "success")]' 2>/dev/null || echo '[]')
    LATEST_MAIN=$(echo "$SUCCESS_RUNS" | jq -r '[.[] | select(.headBranch == "main" or .headBranch == "master")] | .[0].createdAt // "unknown"')

    if [[ "$LATEST_MAIN" != "unknown" ]]; then
        PREV_GREEN=$(jq -r '.last_green // "unknown"' "$CI_STATE")
        if [[ "$LATEST_MAIN" != "$PREV_GREEN" ]]; then
            jq --arg lg "$LATEST_MAIN" '.last_green = $lg' "$CI_STATE" > "${CI_STATE}.tmp" && mv "${CI_STATE}.tmp" "$CI_STATE"
        fi
    fi

    # Trim seen_runs to last 100
    jq '.seen_runs = (.seen_runs | .[-100:])' "$CI_STATE" > "${CI_STATE}.tmp" && mv "${CI_STATE}.tmp" "$CI_STATE" 2>/dev/null || true

    sleep "$CI_INTERVAL"
done
