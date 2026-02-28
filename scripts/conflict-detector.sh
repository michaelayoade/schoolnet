#!/usr/bin/env bash
# conflict-detector.sh — Seabone Conflict Detection Agent
# Checks parallel agent branches for merge conflicts before PRs pile up.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
SEABONE_DIR="$PROJECT_DIR/.seabone"
LOG_DIR="$SEABONE_DIR/logs"
CONFLICT_LOG="$LOG_DIR/conflict-detector.log"
ACTIVE_FILE="$SEABONE_DIR/active-tasks.json"
MEMORY_DIR="$SEABONE_DIR/memory"
LOCKFILE="/tmp/seabone-conflict-${PROJECT_NAME}.lock"
STATE_FILE="$SEABONE_DIR/conflict-state.json"
export PATH="$HOME/.local/bin:$PATH"

source "$SCRIPT_DIR/json-lock.sh"

if [[ -f "$PROJECT_DIR/.env.agent-swarm" ]]; then
    set -a; source "$PROJECT_DIR/.env.agent-swarm"; set +a
fi

mkdir -p "$LOG_DIR" "$MEMORY_DIR"

exec 3>"$LOCKFILE"
if ! flock -n 3; then echo "Another conflict detector running."; exit 0; fi

log() { local msg="[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; echo "$msg"; echo "$msg" >> "$CONFLICT_LOG"; }
notify() { "$SCRIPT_DIR/notify-telegram.sh" "$1" 2>/dev/null || true; }
filter_conflict_files() {
    local ignore_re
    ignore_re="${SEABONE_CONFLICT_IGNORE_REGEX:-(^|/)\\.agent-run\\.sh$}"
    # Ignore runtime artifacts that should not drive merge-order decisions.
    sed '/^$/d' | grep -Ev "$ignore_re" || true
}
init_conflict_state() {
    if [[ ! -f "$STATE_FILE" ]] || ! jq empty "$STATE_FILE" >/dev/null 2>&1; then
        printf '%s\n' '{"last_fingerprint":"","last_count":0,"updated_at":""}' > "$STATE_FILE"
    fi
}
get_last_fingerprint() {
    jq -r '.last_fingerprint // ""' "$STATE_FILE" 2>/dev/null || echo ""
}
set_last_fingerprint() {
    local fingerprint="$1"
    local count="$2"
    local ts tmp
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    tmp="$(mktemp)"
    jq --arg fp "$fingerprint" --arg ts "$ts" --argjson c "$count" \
        '.last_fingerprint = $fp | .last_count = $c | .updated_at = $ts' \
        "$STATE_FILE" > "$tmp" && mv "$tmp" "$STATE_FILE"
}
init_conflict_state

# Check every 10 minutes
CONFLICT_INTERVAL="${SEABONE_CONFLICT_INTERVAL:-600}"

log "=========================================="
log "Seabone Conflict Detector started"
log "Project: $PROJECT_NAME"
log "=========================================="

notify "🔀 *Conflict Detector* started on \`$PROJECT_NAME\`"

TODAY=$(date +%Y-%m-%d)
DAILY_FILE="$MEMORY_DIR/${TODAY}.md"

while true; do
    NEW_TODAY=$(date +%Y-%m-%d)
    if [[ "$NEW_TODAY" != "$TODAY" ]]; then TODAY="$NEW_TODAY"; DAILY_FILE="$MEMORY_DIR/${TODAY}.md"; fi

    cd "$PROJECT_DIR"

    # Get all agent branches with PRs
    AGENT_BRANCHES=$(gh pr list --state open --json headRefName -q '.[].headRefName' 2>/dev/null || echo "")

    if [[ -z "$AGENT_BRANCHES" ]]; then
        sleep "$CONFLICT_INTERVAL"
        continue
    fi

    BRANCH_COUNT=$(echo "$AGENT_BRANCHES" | wc -l | tr -d ' ')
    if [[ "$BRANCH_COUNT" -lt 2 ]]; then
        sleep "$CONFLICT_INTERVAL"
        continue
    fi

    log "Checking $BRANCH_COUNT branches for conflicts..."

    # Fetch all remote branches
    git fetch --all --quiet 2>/dev/null || true

    CONFLICTS_FOUND=0
    CONFLICT_REPORT=""

    # Check each branch against main (or master) for conflicts
    MAIN_REF=""
    if git rev-parse --verify origin/main >/dev/null 2>&1; then
        MAIN_REF="origin/main"
    elif git rev-parse --verify origin/master >/dev/null 2>&1; then
        MAIN_REF="origin/master"
    fi
    if [[ -z "$MAIN_REF" ]]; then
        sleep "$CONFLICT_INTERVAL"
        continue
    fi

    for branch in $AGENT_BRANCHES; do
        MERGE_BASE=$(git merge-base "$MAIN_REF" "origin/$branch" 2>/dev/null || echo "")
        [[ -n "$MERGE_BASE" ]] || continue

        MERGE_RESULT=$(git merge-tree "$MERGE_BASE" "$MAIN_REF" "origin/$branch" 2>/dev/null || echo "")
        HAS_CONFLICT=$(echo "$MERGE_RESULT" | grep -c '^<<<<<<< ' || echo 0)

        if [[ "$HAS_CONFLICT" -gt 0 ]]; then
            CONFLICTING_FILES_RAW=$(echo "$MERGE_RESULT" | grep '^<<<<<<< ' | sed 's/^<<<<<<< //' | sort -u || echo "")
            CONFLICTING_FILES=$(printf '%s\n' "$CONFLICTING_FILES_RAW" | filter_conflict_files)
            if [[ -z "$CONFLICTING_FILES" ]]; then
                continue
            fi
            CONFLICTS_FOUND=$((CONFLICTS_FOUND + 1))
            CONFLICT_REPORT="${CONFLICT_REPORT}
  - ${branch}: conflicts in ${CONFLICTING_FILES}"
            log "CONFLICT: $branch has conflicts with main in: $CONFLICTING_FILES"
        fi
    done

    # Also check branches against each other (pairwise)
    BRANCH_ARRAY=($AGENT_BRANCHES)
    for ((i=0; i<${#BRANCH_ARRAY[@]}; i++)); do
        for ((j=i+1; j<${#BRANCH_ARRAY[@]}; j++)); do
            B1="${BRANCH_ARRAY[$i]}"
            B2="${BRANCH_ARRAY[$j]}"

            # Check if they modify the same files
            FILES_B1=$(git diff --name-only "${MAIN_REF}...origin/$B1" 2>/dev/null | filter_conflict_files || echo "")
            FILES_B2=$(git diff --name-only "${MAIN_REF}...origin/$B2" 2>/dev/null | filter_conflict_files || echo "")

            OVERLAP=$(comm -12 <(echo "$FILES_B1" | sort) <(echo "$FILES_B2" | sort) 2>/dev/null || echo "")
            if [[ -n "$OVERLAP" ]]; then
                CONFLICTS_FOUND=$((CONFLICTS_FOUND + 1))
                CONFLICT_REPORT="${CONFLICT_REPORT}
  - ${B1} vs ${B2}: both modify $(echo "$OVERLAP" | wc -l | tr -d ' ') files: $(echo "$OVERLAP" | head -3 | tr '\n' ', ')"
                log "OVERLAP: $B1 and $B2 modify same files: $OVERLAP"
            fi
        done
    done

    if [[ "$CONFLICTS_FOUND" -gt 0 ]]; then
        fingerprint="$(printf '%s\n' "$CONFLICT_REPORT" | sha256sum | awk '{print $1}')"
        last_fingerprint="$(get_last_fingerprint)"

        if [[ "$fingerprint" != "$last_fingerprint" ]]; then
            notify "🔀 *Conflict Detector*: $CONFLICTS_FOUND conflicts found!
${CONFLICT_REPORT}

Recommend: merge PRs in order to avoid conflicts."

            echo "- $(date +%H:%M) Conflict detector: $CONFLICTS_FOUND conflicts found" >> "$DAILY_FILE" 2>/dev/null || true
            set_last_fingerprint "$fingerprint" "$CONFLICTS_FOUND"
        else
            log "Conflict set unchanged ($CONFLICTS_FOUND); suppressing duplicate notification."
        fi
    else
        if [[ -n "$(get_last_fingerprint)" ]]; then
            set_last_fingerprint "" 0
        fi
    fi

    sleep "$CONFLICT_INTERVAL"
done
