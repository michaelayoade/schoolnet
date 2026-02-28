#!/usr/bin/env bash
# coordinator.sh — Seabone Coordinator (stateful orchestration agent)
# Persists tool calls to JSONL, assembles layered prompts,
# writes daily memory, reconstructs context across restarts.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
SEABONE_DIR="$PROJECT_DIR/.seabone"
CONFIG_FILE="$SEABONE_DIR/config.json"
LOG_DIR="$SEABONE_DIR/logs"
COORDINATOR_LOG="$LOG_DIR/coordinator.log"
TRANSCRIPT_DIR="$SEABONE_DIR/transcripts"
MEMORY_DIR="$SEABONE_DIR/memory"
SOUL_FILE="$SEABONE_DIR/SOUL.md"
MEMORY_FILE="$SEABONE_DIR/MEMORY.md"
LOCKFILE="/tmp/seabone-coordinator-${PROJECT_NAME}.lock"
LOCK_META="/tmp/seabone-coordinator-${PROJECT_NAME}.meta"
LOCK_STALE_SEC="${SEABONE_COORD_LOCK_STALE_SEC:-1800}"
export PATH="$HOME/.local/bin:$PATH"

if [[ -f "$PROJECT_DIR/.env.agent-swarm" ]]; then
    set -a
    source "$PROJECT_DIR/.env.agent-swarm"
    set +a
fi

fleet_enabled() {
    local enabled
    enabled="${SEABONE_FLEET_ENABLED:-}"
    if [[ -z "$enabled" ]]; then
        enabled="$(jq -r '.fleet_enabled // true' "$CONFIG_FILE" 2>/dev/null || echo true)"
    fi
    enabled="$(printf '%s' "$enabled" | tr '[:upper:]' '[:lower:]')"
    case "$enabled" in
        1|true|yes|on) printf '%s' "true" ;;
        *) printf '%s' "false" ;;
    esac
}

single_executor_mode_enabled() {
    local mode
    mode="${SEABONE_SINGLE_EXECUTOR_MODE:-}"
    if [[ -z "$mode" ]]; then
        mode="$(jq -r '.single_executor_mode // .single_coder_mode // false' "$CONFIG_FILE" 2>/dev/null || echo false)"
    fi
    mode="$(printf '%s' "$mode" | tr '[:upper:]' '[:lower:]')"
    case "$mode" in
        1|true|yes|on) printf '%s' "true" ;;
        *) printf '%s' "false" ;;
    esac
}

single_executor_engine() {
    local engine
    engine="${SEABONE_SINGLE_EXECUTOR_ENGINE:-}"
    if [[ -z "$engine" ]]; then
        engine="$(jq -r '.single_executor_engine // "codex"' "$CONFIG_FILE" 2>/dev/null || echo codex)"
    fi
    case "$engine" in
        claude|codex|aider|claude-frontend|codex-test|codex-senior) ;;
        *) engine="codex" ;;
    esac
    printf '%s' "$engine"
}

effective_max_agents() {
    local configured="$1"
    local single_executor="$2"

    if ! [[ "$configured" =~ ^[0-9]+$ ]]; then
        configured=1
    fi
    if (( configured < 1 )); then
        configured=1
    fi

    if [[ "$single_executor" == "true" ]]; then
        printf '%s' "1"
    else
        printf '%s' "$configured"
    fi
}

coordinator_engine() {
    local engine
    engine="${SEABONE_COORDINATOR_ENGINE:-}"
    if [[ -z "$engine" ]]; then
        engine="$(jq -r '.coordinator_engine // "claude"' "$CONFIG_FILE" 2>/dev/null || echo claude)"
    fi
    engine="$(printf '%s' "$engine" | tr '[:upper:]' '[:lower:]')"
    case "$engine" in
        claude|codex) ;;
        *) engine="claude" ;;
    esac
    printf '%s' "$engine"
}

default_coordinator_model() {
    local engine="$1"
    case "$engine" in
        codex) printf '%s' "gpt-5.3-codex" ;;
        *) printf '%s' "sonnet" ;;
    esac
}

coordinator_model() {
    local engine="$1"
    local model
    model="${SEABONE_COORDINATOR_MODEL:-}"
    if [[ -z "$model" ]]; then
        model="$(jq -r '.coordinator_model // empty' "$CONFIG_FILE" 2>/dev/null || echo "")"
    fi
    if [[ -z "$model" || "$model" == "null" ]]; then
        model="$(default_coordinator_model "$engine")"
    fi
    printf '%s' "$model"
}

coordinator_mode() {
    local mode
    mode="${SEABONE_COORDINATOR_MODE:-}"
    if [[ -z "$mode" ]]; then
        mode="$(jq -r '.coordinator_mode // "deterministic"' "$CONFIG_FILE" 2>/dev/null || echo deterministic)"
    fi
    mode="$(printf '%s' "$mode" | tr '[:upper:]' '[:lower:]')"
    case "$mode" in
        deterministic|llm) ;;
        *) mode="deterministic" ;;
    esac
    printf '%s' "$mode"
}

POLL_INTERVAL="${SEABONE_POLL_INTERVAL:-60}"
COORD_MAX_TURNS="${SEABONE_COORD_MAX_TURNS:-45}"
COORD_RETRY_MAX_TURNS="${SEABONE_COORD_RETRY_MAX_TURNS:-18}"
COORD_CLAUDE_TIMEOUT_SEC="${SEABONE_COORD_CLAUDE_TIMEOUT_SEC:-900}"
COORD_CODEX_TIMEOUT_SEC="${SEABONE_COORD_CODEX_TIMEOUT_SEC:-900}"
COORD_MEMORY_MAX_CHARS="${SEABONE_COORD_MEMORY_MAX_CHARS:-12000}"
COORD_DAILY_MAX_CHARS="${SEABONE_COORD_DAILY_MAX_CHARS:-8000}"
COORD_CONTEXT_MAX_CHARS="${SEABONE_COORD_CONTEXT_MAX_CHARS:-6000}"
COORD_STATE_LIMIT="${SEABONE_COORD_STATE_LIMIT:-30}"
COORDINATOR_ENGINE="$(coordinator_engine)"
COORDINATOR_MODEL="$(coordinator_model "$COORDINATOR_ENGINE")"
COORDINATOR_MODE="$(coordinator_mode)"
FLEET_ENABLED="$(fleet_enabled)"
FLEET_CLI="$SCRIPT_DIR/fleet-manager.sh"

mkdir -p "$LOG_DIR" "$TRANSCRIPT_DIR" "$MEMORY_DIR"

write_lock_meta() {
    cat > "$LOCK_META" <<EOF
pid=$$
updated_at=$(date +%s)
session_id=${SESSION_ID:-unknown}
EOF
}

cleanup_stale_lock() {
    local now updated pid holder_pids
    now="$(date +%s)"
    if [[ -f "$LOCK_META" ]]; then
        # shellcheck disable=SC1090
        source "$LOCK_META" 2>/dev/null || true
    fi
    updated="${updated_at:-0}"
    pid="${pid:-0}"
    if [[ -n "$pid" && "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
        if (( now - updated < LOCK_STALE_SEC )); then
            return 0
        fi
    fi
    holder_pids="$(lsof -t "$LOCKFILE" 2>/dev/null | sort -u | tr '\n' ' ' || true)"
    if [[ -n "$holder_pids" ]]; then
        kill $holder_pids 2>/dev/null || true
        sleep 1
        kill -9 $holder_pids 2>/dev/null || true
    fi
    rm -f "$LOCKFILE" "$LOCK_META" 2>/dev/null || true
}

# ---- Session write lock ----
acquire_lock() {
    exec 9>"$LOCKFILE"
    if ! flock -n 9; then
        cleanup_stale_lock
        exec 9>"$LOCKFILE"
        if ! flock -n 9; then
            echo "[ERROR] Another coordinator instance is running (lock: $LOCKFILE)"
            exit 1
        fi
    fi
    write_lock_meta
}

# ---- Logging ----
log() {
    local msg="[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
    echo "$msg"
    echo "$msg" >> "$COORDINATOR_LOG"
}

notify() {
    "$SCRIPT_DIR/notify-telegram.sh" "$1" 2>/dev/null || true
}

trim_text() {
    local text="${1:-}"
    local max_chars="${2:-12000}"
    if ! [[ "$max_chars" =~ ^[0-9]+$ ]]; then
        max_chars=12000
    fi
    if (( ${#text} <= max_chars )); then
        printf '%s' "$text"
        return
    fi
    printf '%s\n\n[truncated to %s chars]' "${text:0:max_chars}" "$max_chars"
}

summarize_active_tasks() {
    local json="${1:-[]}"
    local limit="${2:-30}"
    echo "$json" | jq --argjson limit "$limit" '[.[] | {id, status, engine, retries, branch, started_at}] | .[:$limit]' 2>/dev/null || echo '[]'
}

summarize_queue_tasks() {
    local json="${1:-[]}"
    local limit="${2:-30}"
    echo "$json" | jq --argjson limit "$limit" '
        sort_by((-(.priority_score // 0)), (.priority // 5), (.queued_at // ""))
        | [.[] | {id, track:(.track // "reactive"), priority, priority_score:(.priority_score // null), engine, model, queued_at}]
        | .[:$limit]
    ' 2>/dev/null || echo '[]'
}

run_coordinator_agent() {
    local prompt="$1"
    local max_turns="$2"
    local -a cmd

    if [[ "$COORDINATOR_ENGINE" == "codex" ]]; then
        cmd=(
            codex
            exec
            --model "$COORDINATOR_MODEL"
            "$prompt"
        )
        if command -v timeout >/dev/null 2>&1; then
            timeout "$COORD_CODEX_TIMEOUT_SEC" "${cmd[@]}" 2>&1
        else
            "${cmd[@]}" 2>&1
        fi
        return
    fi

    cmd=(
        claude
        -p
        --dangerously-skip-permissions
        --output-format text
        --model "$COORDINATOR_MODEL"
        --max-turns "$max_turns"
    )
    if command -v timeout >/dev/null 2>&1; then
        printf '%s\n' "$prompt" | timeout "$COORD_CLAUDE_TIMEOUT_SEC" "${cmd[@]}" 2>&1
    else
        printf '%s\n' "$prompt" | "${cmd[@]}" 2>&1
    fi
}

# ---- JSONL Transcript ----
# Each coordinator cycle gets a JSONL entry with: timestamp, prompt, response, actions taken
SESSION_ID="session-$(date +%Y%m%d-%H%M%S)-$$"
TRANSCRIPT_FILE="$TRANSCRIPT_DIR/${SESSION_ID}.jsonl"

write_transcript() {
    local cycle="$1"
    local prompt_hash="$2"
    local response="$3"
    local actions="$4"

    jq -n -c \
        --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        --arg session "$SESSION_ID" \
        --argjson cycle "$cycle" \
        --arg prompt_hash "$prompt_hash" \
        --arg response "$response" \
        --arg actions "$actions" \
        '{ts:$ts, session:$session, cycle:$cycle, prompt_hash:$prompt_hash, response:$response, actions:$actions}' \
        >> "$TRANSCRIPT_FILE"
}

# ---- Reconstruct recent context from transcripts ----
# Loads the last N actions from recent transcripts so the agent knows what it already did
get_recent_context() {
    local max_entries="${SEABONE_COORD_TRANSCRIPT_ENTRIES:-8}"
    local context=""
    if ! [[ "$max_entries" =~ ^[0-9]+$ ]]; then
        max_entries=8
    fi

    # Get the most recent transcript entries across all sessions
    if [[ -d "$TRANSCRIPT_DIR" ]]; then
        context=$(find "$TRANSCRIPT_DIR" -name "*.jsonl" -mtime -1 -exec cat {} \; 2>/dev/null \
            | jq -r -s 'sort_by(.ts) | .[-'"$max_entries"':] | .[] | "[\(.ts)] Cycle \(.cycle): \((.actions // "" | tostring | gsub("\\s+";" ") | .[0:220]))"' 2>/dev/null || echo "")
    fi

    echo "$context"
}

# ---- Daily memory file ----
TODAY=$(date +%Y-%m-%d)
DAILY_FILE="$MEMORY_DIR/${TODAY}.md"

ensure_daily_file() {
    if [[ ! -f "$DAILY_FILE" ]]; then
        cat > "$DAILY_FILE" << EOF
# Seabone Activity — $TODAY

## Actions

EOF
    fi
}

append_daily() {
    ensure_daily_file
    echo "- $(date +%H:%M) $1" >> "$DAILY_FILE"
}

on_exit_cleanup() {
    rm -f "$LOCK_META" 2>/dev/null || true
}

# ---- Layered System Prompt Assembly ----
# Assembles: SOUL.md + MEMORY.md + today's activity + recent transcript context + current state
assemble_prompt() {
    local active_json="$1"
    local queue_json="$2"
    local max_agents="$3"
    local configured_max_agents="$4"
    local single_executor_mode="$5"
    local single_executor_engine="$6"
    local open_prs="$7"

    # Layer 1: Soul (identity)
    local soul=""
    if [[ -f "$SOUL_FILE" ]]; then
        soul=$(cat "$SOUL_FILE")
    fi

    # Layer 2: Persistent memory
    local memory=""
    if [[ -f "$MEMORY_FILE" ]]; then
        memory=$(cat "$MEMORY_FILE")
    fi
    memory="$(trim_text "$memory" "$COORD_MEMORY_MAX_CHARS")"

    # Layer 3: Today's activity
    local today_activity=""
    ensure_daily_file
    if [[ -f "$DAILY_FILE" ]]; then
        today_activity=$(cat "$DAILY_FILE")
    fi
    today_activity="$(trim_text "$today_activity" "$COORD_DAILY_MAX_CHARS")"

    # Layer 4: Recent transcript context (what you did in previous cycles)
    local recent_context
    recent_context=$(get_recent_context)
    recent_context="$(trim_text "$recent_context" "$COORD_CONTEXT_MAX_CHARS")"

    # Layer 5: Current state
    cat <<PROMPT
${soul}

---

## Persistent Memory
${memory}

---

## Today's Activity Log
${today_activity}

---

## Recent Actions (from previous cycles)
${recent_context:-No previous actions today.}

---

## Current State

Active tasks (.seabone/active-tasks.json, summarized):
${active_json}

Queue (.seabone/queue.json, summarized):
${queue_json}

Configured max concurrent agents: ${configured_max_agents}
Single-executor mode: ${single_executor_mode}
Single-executor engine: ${single_executor_engine}
Effective coding concurrency limit: ${max_agents}
Open PRs: ${open_prs}

---

## Instructions for This Cycle

Do ALL of these steps:

### 1. Review PRs (status: pr_created)
For each task with status "pr_created":
- Find PR number: gh pr list --state open --head <branch> --json number -q '.[0].number'
- Get diff: gh pr diff <number>
- READ the changed source files to verify imports and logic
- Decide: APPROVE or REJECT (only reject for runtime crashes)

### 2. Merge approved PRs
For EACH approved PR, do ALL of these steps in order:
- Remove worktree first: git worktree remove .worktrees/<task_id> --force 2>/dev/null || true
- Check mergeable status: gh pr view <number> --json mergeable -q '.mergeable'
  - If MERGEABLE: Use gh pr merge <number> --merge --delete-branch
  - If CONFLICTING: Check what files conflict. If the ONLY conflict is in .agent-run.sh (a throwaway bootstrap file), merge manually using a temporary worktree:
    1) git fetch origin main <branch>
    2) git worktree add .worktrees/_merge-tmp origin/main --detach
    3) cd .worktrees/_merge-tmp
    4) git merge --no-ff origin/<branch> -m "Merge <branch> (Seabone auto-merge)"
    5) If conflict: git checkout --ours .agent-run.sh && git add .agent-run.sh && git commit --no-edit
    6) git push origin HEAD:main
    7) cd - && git worktree remove .worktrees/_merge-tmp --force
    8) gh pr close <number>
    9) git push origin --delete <branch> 2>/dev/null || true
  - If conflict involves REAL source files (not just .agent-run.sh): REJECT the PR with a comment explaining which files conflict, and respawn the agent to rebase
- CRITICAL: Update BOTH JSON files:
  a) Remove task from .seabone/active-tasks.json: jq 'map(select(.id != "<task_id>"))' .seabone/active-tasks.json > /tmp/active.tmp && mv /tmp/active.tmp .seabone/active-tasks.json
  b) Update status in .seabone/completed-tasks.json: If the task exists there, update its status to "merged". If not, add it with status "merged".
     jq --arg id "<task_id>" '(.[] | select(.id == $id) | .status) = "merged"' .seabone/completed-tasks.json > /tmp/comp.tmp && mv /tmp/comp.tmp .seabone/completed-tasks.json
     If the task doesn't exist in completed-tasks.json yet:
     jq --arg id "<task_id>" '. + [{"id":$id,"status":"merged"}]' .seabone/completed-tasks.json > /tmp/comp.tmp && mv /tmp/comp.tmp .seabone/completed-tasks.json
- VERIFY: After updating, run jq '.[] | select(.id == "<task_id>") | .status' .seabone/completed-tasks.json to confirm it says "merged"
- Refresh local refs: git fetch origin main
- Notify: ${SCRIPT_DIR}/notify-telegram.sh "message"
- NOTE: Do NOT run "git checkout main" — other agents share this worktree. Use "git fetch" only.

### 3. Reject broken PRs
- Comment: gh pr comment <number> --body "review"
- Close: gh pr close <number>
- Remove from active-tasks.json
- When respawning, include a detailed implementation checklist in the task description.
- Check the task's retries count:
  - If retries < 2: Respawn with same engine: ${SCRIPT_DIR}/spawn-agent.sh "<id>-v2" "Fix: <desc>. Issues: <feedback>" --retries <retries+1>
  - If retries >= 2: ESCALATE to senior dev: ${SCRIPT_DIR}/spawn-agent.sh "<id>-senior" "ESCALATION: <desc>. Previous failures: <feedback>" --engine codex-senior --force
- Notify via telegram (include "ESCALATED" if senior dev was invoked)

### 4. Clean up dead agents
For status "running": check tmux has-session -t <session>
If gone:
- When respawning, include a detailed implementation checklist in the task description.
- Check retries count of the failed task
- If retries < 2: update status to "failed", respawn with --retries <retries+1>
- If retries >= 2: ESCALATE to senior dev: ${SCRIPT_DIR}/spawn-agent.sh "<id>-senior" "ESCALATION: <original desc>. Agent crashed <retries+1> times." --engine codex-senior --force
- Notify via telegram

### 5. Run tests on merged PRs
After merging PRs, if there are available agent slots:
- Spawn a testing agent: ${SCRIPT_DIR}/spawn-agent.sh "test-<merged-task-id>" "Write and run tests for the changes in <merged task description>" --engine codex-test
- Only spawn 1 test agent per cycle to avoid overwhelming the swarm

### 6. Process queue
If running < ${max_agents} and queue is not empty:
- Remove from queue.json, spawn with spawn-agent.sh

### 7. Write memory
After processing, append a one-line summary of what you did to: ${DAILY_FILE}
Format: "- HH:MM action summary"

If you learned something new about the codebase (a pattern, a common bug, a decision),
update ${MEMORY_FILE} in the appropriate section.

### 8. Summary
End with a one-line summary of actions taken.
PROMPT
}

# ============================================
#  MAIN LOOP
# ============================================
acquire_lock
trap on_exit_cleanup EXIT

log "=========================================="
log "Seabone Coordinator started"
log "Session: $SESSION_ID"
log "Project: $PROJECT_NAME"
log "Mode: $COORDINATOR_MODE"
log "Engine: $COORDINATOR_ENGINE"
log "Model: $COORDINATOR_MODEL"
log "Poll interval: ${POLL_INTERVAL}s"
log "Transcript: $TRANSCRIPT_FILE"
log "=========================================="

notify "🧠 *Seabone Coordinator* started
Session: \`$SESSION_ID\`
Project: \`$PROJECT_NAME\`
Mode: \`$COORDINATOR_MODE\`
Engine: \`$COORDINATOR_ENGINE\`"

CYCLE=0
while true; do
    CYCLE=$((CYCLE + 1))
    write_lock_meta

    # Refresh daily file reference at midnight
    NEW_TODAY=$(date +%Y-%m-%d)
    if [[ "$NEW_TODAY" != "$TODAY" ]]; then
        TODAY="$NEW_TODAY"
        DAILY_FILE="$MEMORY_DIR/${TODAY}.md"
    fi

    cd "$PROJECT_DIR"
    if [[ "$FLEET_ENABLED" == "true" && -x "$FLEET_CLI" ]]; then
        "$FLEET_CLI" heartbeat "$PROJECT_NAME" "coordinator" "$SESSION_ID" 300 >/dev/null 2>&1 || true
    fi

    # Check if there's work to do
    ACTIVE_COUNT=$(jq 'length' "$SEABONE_DIR/active-tasks.json" 2>/dev/null || echo 0)
    QUEUE_COUNT=$(jq 'length' "$SEABONE_DIR/queue.json" 2>/dev/null || echo 0)
    OPEN_PRS=$(gh pr list --state open --json number -q 'length' 2>/dev/null || echo 0)

    if [[ "$ACTIVE_COUNT" -eq 0 && "$QUEUE_COUNT" -eq 0 && "$OPEN_PRS" -eq 0 ]]; then
        sleep "$POLL_INTERVAL"
        continue
    fi

    log "Cycle $CYCLE: $ACTIVE_COUNT active, $QUEUE_COUNT queued, $OPEN_PRS open PRs"

    if [[ "$COORDINATOR_MODE" == "deterministic" ]]; then
        CHECK_OUTPUT="$("$SCRIPT_DIR/check-agents.sh" 2>&1 || true)"
        SUMMARY="$(echo "$CHECK_OUTPUT" | grep -E '\\[DONE\\]|Queue items:' | tr '\n' ' ' | sed -E 's/[[:space:]]+/ /g' | sed -E 's/^ //; s/ $//')"
        if [[ -z "$SUMMARY" ]]; then
            SUMMARY="Deterministic cycle: ran check-agents."
        fi
        append_daily "Coordinator deterministic cycle: $SUMMARY"
        log "Cycle $CYCLE result: $SUMMARY"
        PROMPT_HASH="deterministic"
        ESCAPED_SUMMARY="$(echo "$SUMMARY" | tr '\n' ' ' | cut -c1-500)"
        write_transcript "$CYCLE" "$PROMPT_HASH" "deterministic" "$ESCAPED_SUMMARY"
        sleep "$POLL_INTERVAL"
        continue
    fi

    # Read current state
    ACTIVE_JSON_RAW=$(cat "$SEABONE_DIR/active-tasks.json" 2>/dev/null || echo '[]')
    QUEUE_JSON_RAW=$(cat "$SEABONE_DIR/queue.json" 2>/dev/null || echo '[]')
    ACTIVE_JSON="$(summarize_active_tasks "$ACTIVE_JSON_RAW" "$COORD_STATE_LIMIT")"
    QUEUE_JSON="$(summarize_queue_tasks "$QUEUE_JSON_RAW" "$COORD_STATE_LIMIT")"
    CONFIG_MAX_AGENTS=$(jq -r '.max_concurrent_agents // 10' "$CONFIG_FILE" 2>/dev/null || echo 10)
    SINGLE_EXECUTOR_MODE="$(single_executor_mode_enabled)"
    SINGLE_EXECUTOR_ENGINE="$(single_executor_engine)"
    MAX_AGENTS="$(effective_max_agents "$CONFIG_MAX_AGENTS" "$SINGLE_EXECUTOR_MODE")"

    # Assemble layered prompt
    FULL_PROMPT=$(assemble_prompt "$ACTIVE_JSON" "$QUEUE_JSON" "$MAX_AGENTS" "$CONFIG_MAX_AGENTS" "$SINGLE_EXECUTOR_MODE" "$SINGLE_EXECUTOR_ENGINE" "$OPEN_PRS")

    # Hash the prompt for transcript dedup
    PROMPT_HASH=$(echo "$FULL_PROMPT" | md5sum | cut -d' ' -f1)

    # Run coordinator agent.
    log "Running ${COORDINATOR_ENGINE} coordinator (cycle $CYCLE)..."
    COORD_OUTPUT="$(run_coordinator_agent "$FULL_PROMPT" "$COORD_MAX_TURNS")" || true
    if [[ "$COORDINATOR_ENGINE" == "claude" ]] && printf '%s' "$COORD_OUTPUT" | grep -q "Reached max turns"; then
        log "Cycle $CYCLE: Claude hit max turns ($COORD_MAX_TURNS). Retrying with compact fallback."
        FALLBACK_PROMPT="You are the Seabone coordinator in fallback mode for $PROJECT_NAME.

Active summary:
${ACTIVE_JSON}

Queue summary:
${QUEUE_JSON}

Open PRs: ${OPEN_PRS}
Single-executor mode: ${SINGLE_EXECUTOR_MODE}
Single-executor engine: ${SINGLE_EXECUTOR_ENGINE}
Effective coding concurrency limit: ${MAX_AGENTS}

Instructions:
1. Execute only one highest-priority safe action this cycle (merge, reject, respawn, or queue dispatch).
2. Keep JSON state files consistent after any action.
3. Append one-line action summary to ${DAILY_FILE}.
4. End with a single-line summary."
        COORD_OUTPUT="$(run_coordinator_agent "$FALLBACK_PROMPT" "$COORD_RETRY_MAX_TURNS")" || true
    fi

    # Extract summary
    SUMMARY=$(echo "$COORD_OUTPUT" | grep -v '^$' | tail -1)
    log "Cycle $CYCLE result: $SUMMARY"

    # Write transcript
    ESCAPED_SUMMARY=$(echo "$SUMMARY" | tr '\n' ' ' | cut -c1-500)
    write_transcript "$CYCLE" "$PROMPT_HASH" "completed" "$ESCAPED_SUMMARY"

    # Log full output for debugging
    echo "=== CYCLE $CYCLE FULL OUTPUT ===" >> "$COORDINATOR_LOG"
    echo "$COORD_OUTPUT" >> "$COORDINATOR_LOG"
    echo "=== END CYCLE $CYCLE ===" >> "$COORDINATOR_LOG"

    sleep "$POLL_INTERVAL"
done
