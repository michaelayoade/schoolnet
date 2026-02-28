#!/usr/bin/env bash
# list-tasks.sh — Detailed Seabone task status viewer
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SEABONE_DIR="$PROJECT_DIR/.seabone"
ACTIVE_FILE="$SEABONE_DIR/active-tasks.json"
COMPLETED_FILE="$SEABONE_DIR/completed-tasks.json"
QUEUE_FILE="$SEABONE_DIR/queue.json"
MEMORY_FILE="$SEABONE_DIR/model-memory.json"
CONFIG_FILE="$SEABONE_DIR/config.json"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
SESSION_PREFIX="agent-${PROJECT_NAME}"

if [[ -f "$PROJECT_DIR/.env.agent-swarm" ]]; then
    set -a
    source "$PROJECT_DIR/.env.agent-swarm"
    set +a
fi

source "$SCRIPT_DIR/json-lock.sh"

ensure_file() {
    local file="$1"
    local expected="${2:-array}"

    if [[ ! -f "$file" ]]; then
        if [[ "$expected" == "object" ]]; then
            printf '%s\n' '{"models":{}}' > "$file"
        else
            printf '%s\n' '[]' > "$file"
        fi
        return
    fi

    if ! jq -e "type == \"$expected\"" "$file" >/dev/null 2>&1; then
        if [[ "$expected" == "object" ]]; then
            printf '%s\n' '{"models":{}}' > "$file"
        else
            printf '%s\n' '[]' > "$file"
        fi
    fi
}

ensure_file "$ACTIVE_FILE" array
ensure_file "$COMPLETED_FILE" array
ensure_file "$QUEUE_FILE" array
ensure_file "$MEMORY_FILE" object

ACTIVE_COUNT="$(json_read "$ACTIVE_FILE" 'length' 2>/dev/null || echo 0)"
QUEUED_COUNT="$(json_read "$QUEUE_FILE" 'length' 2>/dev/null || echo 0)"
COMPLETED_COUNT="$(json_read "$COMPLETED_FILE" 'length' 2>/dev/null || echo 0)"
QUEUE_ENABLED="$(jq -r '.queue_enabled // true' "$CONFIG_FILE" 2>/dev/null || echo true)"

printf '=== SEABONE AGENT SWARM STATUS ===\n'
printf 'Project: %s\n' "$PROJECT_NAME"
printf 'Active: %s | Queued: %s | Completed: %s\n' "$ACTIVE_COUNT" "$QUEUED_COUNT" "$COMPLETED_COUNT"
printf 'Queue enabled: %s\n' "$QUEUE_ENABLED"
printf '\n'

printf 'Active Tasks:\n'
printf '%s\n' "---"
if [[ "$ACTIVE_COUNT" -gt 0 ]]; then
    echo "  [status] id | retries | model | branch | started_at | last_heartbeat"
    json_read "$ACTIVE_FILE" '.[] | ("  [" + (.status // "-") + "] " + (.id // "-") + " | retries=" + ((.retries // 0) | tostring) + " | model=" + (.model // "-") + " | branch=" + (.branch // "-") + " | started=" + (.started_at // "-") + " | heartbeat=" + (.last_heartbeat // "-"))' 2>/dev/null
else
    echo "  (none)"
fi

printf '\n'
printf 'Queued Tasks:\n'
printf '%s\n' "---"
if [[ "$QUEUED_COUNT" -gt 0 ]]; then
    json_read "$QUEUE_FILE" 'sort_by(.priority, .queued_at) | .[] | ("  [" + (.model // "-") + "] p=" + ((.priority // 0) | tostring) + " id=" + (.id // "-") + " queued=" + (.queued_at // "-") + " desc=" + (.description // "-"))' 2>/dev/null
else
    echo "  (none)"
fi

printf '\n'
printf 'Tmux Agent Sessions:\n'
printf '%s\n' "---"
SESSIONS="$(tmux list-sessions -F '#{session_name}' 2>/dev/null | grep "^${SESSION_PREFIX}-" || true)"
if [[ -n "$SESSIONS" ]]; then
    echo "$SESSIONS" | sed 's/^/  /'
else
    echo "  (none)"
fi

printf '\n'
printf 'Model Memory:\n'
printf '%s\n' "---"
MEMORY_COUNT="$(jq '.models | length' "$MEMORY_FILE" 2>/dev/null || echo 0)"
if [[ "$MEMORY_COUNT" -gt 0 ]]; then
    jq -r '.models | to_entries | map(.value.total = ((.value.success // 0) + (.value.failure // 0))) | sort_by(-(.value.total // 0), .key) | .[:10][] | ("  " + .key + ": success=" + ((.value.success // 0) | tostring) + " failure=" + ((.value.failure // 0) | tostring) + " total=" + ((.value.total // 0) | tostring))' "$MEMORY_FILE" 2>/dev/null
else
    echo "  (no model memory yet)"
fi

printf '\n'
printf 'Completed Tasks (latest 5):\n'
printf '%s\n' "---"
if [[ "$COMPLETED_COUNT" -gt 0 ]]; then
    json_read "$COMPLETED_FILE" '.[-5:] | .[] | ("  [" + (.status // "-") + "] " + (.id // "-") + " completed=" + (.completed_at // "n/a"))' 2>/dev/null
    if [[ "$COMPLETED_COUNT" -gt 5 ]]; then
        echo "  ... and $((COMPLETED_COUNT - 5)) more"
    fi
else
    echo "  (none)"
fi

printf '\n'
printf 'Open PRs (agent branches):\n'
printf '%s\n' "---"
echo "  (gh unavailable or timeout)"

printf '\n'
date -u +'Last checked: %Y-%m-%d %H:%M:%S UTC'
