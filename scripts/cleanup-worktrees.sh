#!/usr/bin/env bash
# cleanup-worktrees.sh — Archive finished tasks, process queue backlog, prune resources
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
SESSION_PREFIX="agent-${PROJECT_NAME}"
SEABONE_DIR="$PROJECT_DIR/.seabone"
ACTIVE_FILE="$SEABONE_DIR/active-tasks.json"
COMPLETED_FILE="$SEABONE_DIR/completed-tasks.json"
QUEUE_FILE="$SEABONE_DIR/queue.json"
CONFIG_FILE="$SEABONE_DIR/config.json"
LOG_DIR="$SEABONE_DIR/logs"
EVENT_LOG="$LOG_DIR/events.log"
export PATH="$HOME/.local/bin:$PATH"

source "$SCRIPT_DIR/json-lock.sh"

if [[ -f "$PROJECT_DIR/.env.agent-swarm" ]]; then
    set -a
    source "$PROJECT_DIR/.env.agent-swarm"
    set +a
fi

ensure_state_file() {
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

ensure_state_file "$ACTIVE_FILE" array
ensure_state_file "$COMPLETED_FILE" array
ensure_state_file "$QUEUE_FILE" array

CLEANUP_DAYS="$(jq -r '.auto_cleanup_days // 7' "$CONFIG_FILE")"
LOG_RETENTION_DAYS="$(jq -r '.log_retention_days // 14' "$CONFIG_FILE")"

CUTOFF_SECONDS=$(( CLEANUP_DAYS * 86400 ))
LOG_CUTOFF_SECONDS=$(( LOG_RETENTION_DAYS * 86400 ))
NOW=$(date +%s)

ARCHIVED=0
KILLED=0
REMOVED=0
QUEUE_REMOVED=0

move_finished_tasks() {
    local count status task
    count=$(json_read "$ACTIVE_FILE" 'length' 2>/dev/null || echo 0)
    for i in $(seq $((count - 1)) -1 0); do
        task=$(json_read "$ACTIVE_FILE" ".[$i]")
        status=$(json_read "$ACTIVE_FILE" ".[$i].status // empty")

        case "$status" in
            pr_created|no_changes|completed|max_retries_exceeded|error|timeout|quality_failed|failed|killed)
                json_append "$COMPLETED_FILE" "$(echo "$task" | jq ". + {\"completed_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}")"
                json_update "$ACTIVE_FILE" "del(.[$i])"
                ARCHIVED=$((ARCHIVED + 1))
                ;;
        esac
    done
}

cleanup_orphan_sessions() {
    for s in $(tmux list-sessions -F "#{session_name}" 2>/dev/null | grep "^${SESSION_PREFIX}-" || true); do
        local task_id
        task_id="${s#${SESSION_PREFIX}-}"
        if ! json_read "$ACTIVE_FILE" ".[] | select(.id == \"$task_id\")" 2>/dev/null | grep -q .; then
            tmux kill-session -t "$s" 2>/dev/null || true
            KILLED=$((KILLED + 1))
        fi
    done
}

cleanup_worktrees() {
    local base="$PROJECT_DIR/.worktrees"
    if [[ ! -d "$base" ]]; then
        return
    fi

    for wt in "$base"/*/; do
        [[ -d "$wt" ]] || continue
        task_id="$(basename "$wt")"

        if [[ -n "$(json_read "$ACTIVE_FILE" ".[] | select(.id == \"$task_id\" and .status == \"running\") // empty")" ]]; then
            continue
        fi

        if [[ -f "$wt/.agent-run.sh" ]]; then
            mtime=$(stat -c %Y "$wt/.agent-run.sh" 2>/dev/null || echo 0)
            age=$((NOW - mtime))
            if (( age < CUTOFF_SECONDS )); then
                continue
            fi
        fi

        git worktree remove "$wt" --force >/dev/null 2>&1 || rm -rf "$wt"
        REMOVED=$((REMOVED + 1))
    done
}

cleanup_queue() {
    local now_ts age cutoff
    now_ts=$(date +%s)
    cutoff=$((now_ts - CUTOFF_SECONDS))

    local stale_ids
    stale_ids=$(json_read "$QUEUE_FILE" "map(select((.queued_at | fromdateiso8601) < $cutoff) | .id)" 2>/dev/null || echo '[]')
    for id in $(echo "$stale_ids" | jq -r '.[]?'); do
        [[ -z "$id" ]] && continue
        json_update "$QUEUE_FILE" "map(select(.id != \"$id\"))"
        QUEUE_REMOVED=$((QUEUE_REMOVED + 1))
    done

    # Keep only latest priority/arrival ordering
    json_update "$QUEUE_FILE" "sort_by(.priority, .queued_at)"
}

cleanup_logs() {
    [[ -d "$LOG_DIR" ]] || return
    local now_ts
    now_ts=$(date +%s)
    local file
    local mtime

    find "$LOG_DIR" -type f -name '*.log' -print0 | while IFS= read -r -d '' file; do
        mtime=$(stat -c %Y "$file" 2>/dev/null || echo 0)
        if (( now_ts - mtime > LOG_CUTOFF_SECONDS )); then
            rm -f "$file"
        fi
    done
}

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Running Seabone cleanup"

move_finished_tasks
cleanup_orphan_sessions
cleanup_worktrees
cleanup_queue
cleanup_logs

git worktree prune 2>/dev/null || true

git gc --auto --quiet 2>/dev/null || true

echo "[DONE] Archived:$ARCHIVED  Killed:$KILLED  Worktrees:$REMOVED  Queue:$QUEUE_REMOVED"

echo "Cleanup complete" >> "$EVENT_LOG"
