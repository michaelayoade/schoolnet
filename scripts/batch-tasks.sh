#!/usr/bin/env bash
# batch-tasks.sh — Process a task queue file, spawning agents 3-at-a-time
# Usage: ./batch-tasks.sh [tasks-file]
# Task file format (one per line): task-id | description | model (optional)
# Example: fix-login | Fix the login validation bug | deepseek-reasoner
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SEABONE_DIR="$PROJECT_DIR/.seabone"
ACTIVE_FILE="$SEABONE_DIR/active-tasks.json"
CONFIG_FILE="$SEABONE_DIR/config.json"
export PATH="$HOME/.local/bin:$PATH"

source "$SCRIPT_DIR/json-lock.sh"

if [[ -f "$PROJECT_DIR/.env.agent-swarm" ]]; then
    set -a; source "$PROJECT_DIR/.env.agent-swarm"; set +a
fi

TASKS_FILE="${1:-$PROJECT_DIR/tasks.txt}"
MAX_AGENTS=$(jq -r '.max_concurrent_agents // 3' "$CONFIG_FILE")
POLL_INTERVAL=30

if [[ ! -f "$TASKS_FILE" ]]; then
    echo "[ERROR] Task file not found: $TASKS_FILE"
    echo "Create it with format: task-id | description | model (optional)"
    exit 1
fi

# Count tasks
TOTAL=$(grep -cve '^\s*$\|^\s*#' "$TASKS_FILE" || echo 0)
echo "=== Seabone Batch Processor ==="
echo "Task file: $TASKS_FILE"
echo "Total tasks: $TOTAL"
echo "Max concurrent: $MAX_AGENTS"
echo ""

SPAWNED=0
SKIPPED=0

while IFS='|' read -r TASK_ID DESCRIPTION MODEL; do
    # Skip empty lines and comments
    [[ -z "$TASK_ID" || "$TASK_ID" =~ ^[[:space:]]*# ]] && continue

    # Trim whitespace
    TASK_ID=$(echo "$TASK_ID" | xargs)
    DESCRIPTION=$(echo "$DESCRIPTION" | xargs)
    MODEL=$(echo "${MODEL:-}" | xargs)

    # Skip already-completed tasks
    if json_read "$SEABONE_DIR/completed-tasks.json" ".[] | select(.id == \"$TASK_ID\")" 2>/dev/null | grep -q .; then
        echo "[SKIP] $TASK_ID — already completed"
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    # Skip active tasks
    if json_read "$ACTIVE_FILE" ".[] | select(.id == \"$TASK_ID\")" | grep -q .; then
        echo "[SKIP] $TASK_ID — already active"
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    # Wait for a free slot
    while true; do
        ACTIVE_COUNT=$(json_read "$ACTIVE_FILE" '[.[] | select(.status == "running")] | length')
        if [[ "$ACTIVE_COUNT" -lt "$MAX_AGENTS" ]]; then
            break
        fi
        echo "[WAIT] $ACTIVE_COUNT/$MAX_AGENTS agents running. Waiting ${POLL_INTERVAL}s..."
        sleep "$POLL_INTERVAL"

        # Run health check to archive finished tasks
        "$SCRIPT_DIR/check-agents.sh" > /dev/null 2>&1 || true
    done

    # Spawn
    echo "[SPAWN] $TASK_ID — $DESCRIPTION ${MODEL:+(model: $MODEL)}"
    if [[ -n "$MODEL" ]]; then
        "$SCRIPT_DIR/spawn-agent.sh" "$TASK_ID" "$DESCRIPTION" "$MODEL" || {
            echo "[ERROR] Failed to spawn $TASK_ID"
            continue
        }
    else
        "$SCRIPT_DIR/spawn-agent.sh" "$TASK_ID" "$DESCRIPTION" || {
            echo "[ERROR] Failed to spawn $TASK_ID"
            continue
        }
    fi
    SPAWNED=$((SPAWNED + 1))

    # Brief pause between spawns to stagger API calls
    sleep 3

done < "$TASKS_FILE"

echo ""
echo "=== Batch Complete ==="
echo "Spawned: $SPAWNED"
echo "Skipped: $SKIPPED"
echo "Total: $TOTAL"

"$SCRIPT_DIR/notify-telegram.sh" "📋 *Seabone Batch*: $SPAWNED/$TOTAL tasks spawned ($SKIPPED skipped)" 2>/dev/null || true
