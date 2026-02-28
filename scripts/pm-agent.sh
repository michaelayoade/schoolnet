#!/usr/bin/env bash
# pm-agent.sh — Seabone Project Manager Agent
# Reads sentinel findings, triages tasks, assigns the right engine,
# manages priorities, and tracks project health.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
SEABONE_DIR="$PROJECT_DIR/.seabone"
CONFIG_FILE="$SEABONE_DIR/config.json"
LOG_DIR="$SEABONE_DIR/logs"
PM_LOG="$LOG_DIR/pm.log"
MEMORY_DIR="$SEABONE_DIR/memory"
MEMORY_FILE="$SEABONE_DIR/MEMORY.md"
FINDINGS_DIR="$SEABONE_DIR/findings"
REPORTS_DIR="$SEABONE_DIR/reports"
ACTIVE_FILE="$SEABONE_DIR/active-tasks.json"
COMPLETED_FILE="$SEABONE_DIR/completed-tasks.json"
QUEUE_FILE="$SEABONE_DIR/queue.json"
PM_STATE="$SEABONE_DIR/pm-state.json"
PROMPTS_DIR="$SEABONE_DIR/prompts"
LOCKFILE="/tmp/seabone-pm-${PROJECT_NAME}.lock"
export PATH="$HOME/.local/bin:$PATH"

if [[ -f "$PROJECT_DIR/.env.agent-swarm" ]]; then
    set -a
    source "$PROJECT_DIR/.env.agent-swarm"
    set +a
fi

mkdir -p "$LOG_DIR" "$FINDINGS_DIR" "$MEMORY_DIR" "$REPORTS_DIR"

# ---- Lock ----
exec 7>"$LOCKFILE"
if ! flock -n 7; then
    echo "Another PM instance is running."
    exit 0
fi

log() {
    local msg="[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
    echo "$msg"
    echo "$msg" >> "$PM_LOG"
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
    echo "$json" | jq --argjson limit "$limit" '[.[] | {id, status, engine, retries, priority, started_at}] | .[:$limit]' 2>/dev/null || echo '[]'
}

summarize_queue_tasks() {
    local json="${1:-[]}"
    local limit="${2:-30}"
    echo "$json" | jq --argjson limit "$limit" 'sort_by(.priority, .queued_at) | [.[] | {id, priority, engine, model, queued_at}] | .[:$limit]' 2>/dev/null || echo '[]'
}

summarize_untriaged_findings() {
    local json="${1:-[]}"
    local limit="${2:-80}"
    echo "$json" | jq --argjson limit "$limit" '[.[] | {id, severity, category, file, issue, task, auto_fixable, effort}] | .[:$limit]' 2>/dev/null || echo '[]'
}

run_pm_claude() {
    local prompt="$1"
    local max_turns="$2"
    local -a cmd
    cmd=(
        claude
        -p
        --dangerously-skip-permissions
        --output-format text
        --model sonnet
        --max-turns "$max_turns"
    )
    if command -v timeout >/dev/null 2>&1; then
        printf '%s\n' "$prompt" | timeout "$PM_CLAUDE_TIMEOUT_SEC" "${cmd[@]}" 2>&1
    else
        printf '%s\n' "$prompt" | "${cmd[@]}" 2>&1
    fi
}

task_exists_in_file() {
    local file="$1"
    local task_id="$2"
    [[ -f "$file" ]] || return 1
    jq -e --arg id "$task_id" '.[] | select(.id == $id)' "$file" >/dev/null 2>&1
}

spawn_frontend_audit_if_due() {
    local enabled task_id priority description

    enabled="$(jq -r '.frontend_audit_enabled // true' "$CONFIG_FILE" 2>/dev/null || echo true)"
    [[ "$enabled" == "true" ]] || return 0

    task_id="$(date -u +frontend-audit-%Y%m%d)"
    if task_exists_in_file "$ACTIVE_FILE" "$task_id" || \
       task_exists_in_file "$QUEUE_FILE" "$task_id" || \
       task_exists_in_file "$COMPLETED_FILE" "$task_id"; then
        return 0
    fi

    priority="$(jq -r '.frontend_audit_priority // 10' "$CONFIG_FILE" 2>/dev/null || echo 10)"
    [[ "$priority" =~ ^[0-9]+$ ]] || priority=10

    description="Frontend audit: review templates and styling for responsive behavior, accessibility, and visual consistency. Apply concrete UX/UI improvements and open a PR with summary notes."

    log "PM cycle $CYCLE: Scheduling daily frontend audit task ($task_id)"
    if "$SCRIPT_DIR/spawn-agent.sh" "$task_id" "$description" --engine claude-frontend --priority "$priority" >/dev/null 2>&1; then
        log "PM cycle $CYCLE: Frontend audit task scheduled ($task_id)"
        echo "- $(date +%H:%M) PM scheduled $task_id (claude-frontend)" >> "$DAILY_FILE" 2>/dev/null || true
    else
        log "PM cycle $CYCLE: Frontend audit scheduling failed ($task_id), will retry next cycle"
    fi
}

# PM checks every 5 minutes
PM_INTERVAL="${SEABONE_PM_INTERVAL:-300}"
PM_MAX_TURNS="${SEABONE_PM_MAX_TURNS:-45}"
PM_RETRY_MAX_TURNS="${SEABONE_PM_RETRY_MAX_TURNS:-18}"
PM_CLAUDE_TIMEOUT_SEC="${SEABONE_PM_CLAUDE_TIMEOUT_SEC:-900}"
PM_MEMORY_MAX_CHARS="${SEABONE_PM_MEMORY_MAX_CHARS:-12000}"
PM_REPORT_MAX_CHARS="${SEABONE_PM_REPORT_MAX_CHARS:-12000}"
PM_FINDINGS_LIMIT="${SEABONE_PM_FINDINGS_LIMIT:-80}"
PM_STATE_LIMIT="${SEABONE_PM_STATE_LIMIT:-30}"

# Init PM state file (tracks what's been triaged)
if [[ ! -f "$PM_STATE" ]]; then
    echo '{"triaged_findings":[],"sprint":{"started":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","goals":[],"completed":[]}}' > "$PM_STATE"
fi

log "=========================================="
log "Seabone Project Manager started"
log "Project: $PROJECT_NAME"
log "Poll interval: ${PM_INTERVAL}s"
log "=========================================="

notify "📋 *Seabone PM* started
Project: \`$PROJECT_NAME\`
Interval: ${PM_INTERVAL}s"

TODAY=$(date +%Y-%m-%d)
DAILY_FILE="$MEMORY_DIR/${TODAY}.md"
CYCLE=0

while true; do
    CYCLE=$((CYCLE + 1))

    # Date rollover
    NEW_TODAY=$(date +%Y-%m-%d)
    if [[ "$NEW_TODAY" != "$TODAY" ]]; then
        TODAY="$NEW_TODAY"
        DAILY_FILE="$MEMORY_DIR/${TODAY}.md"
    fi

    cd "$PROJECT_DIR"
    spawn_frontend_audit_if_due

    # ---- Gather current state ----
    ACTIVE_JSON=$(cat "$ACTIVE_FILE" 2>/dev/null || echo '[]')
    COMPLETED_JSON=$(cat "$COMPLETED_FILE" 2>/dev/null || echo '[]')
    QUEUE_JSON=$(cat "$QUEUE_FILE" 2>/dev/null || echo '[]')
    PM_STATE_JSON=$(cat "$PM_STATE" 2>/dev/null || echo '{}')
    MAX_AGENTS=$(jq -r '.max_concurrent_agents // 10' "$CONFIG_FILE" 2>/dev/null || echo 10)
    RUNNING=$(echo "$ACTIVE_JSON" | jq '[.[] | select(.status == "running")] | length' 2>/dev/null || echo 0)
    AVAILABLE_SLOTS=$(( MAX_AGENTS - RUNNING ))
    QUEUE_SIZE=$(echo "$QUEUE_JSON" | jq 'length' 2>/dev/null || echo 0)

    # ---- Collect ALL unprocessed findings ----
    ALL_FINDINGS="[]"
    TRIAGED_IDS=$(echo "$PM_STATE_JSON" | jq -r '.triaged_findings // [] | .[]' 2>/dev/null || echo "")

    for f in "$FINDINGS_DIR"/*.json; do
        [[ -f "$f" ]] || continue
        ALL_FINDINGS=$(echo "$ALL_FINDINGS" | jq --slurpfile new "$f" '. + $new[0]' 2>/dev/null || echo "$ALL_FINDINGS")
    done

    # Filter out already-triaged findings
    UNTRIAGED=$(echo "$ALL_FINDINGS" | jq --argjson triaged "$(echo "$PM_STATE_JSON" | jq '.triaged_findings // []')" '[.[] | select(.id as $id | $triaged | index($id) | not)]' 2>/dev/null || echo '[]')
    UNTRIAGED_COUNT=$(echo "$UNTRIAGED" | jq 'length' 2>/dev/null || echo 0)

    # ---- Collect completed task IDs ----
    COMPLETED_IDS=$(echo "$COMPLETED_JSON" | jq -r '.[].id' 2>/dev/null || echo "")
    ACTIVE_IDS=$(echo "$ACTIVE_JSON" | jq -r '.[].id' 2>/dev/null || echo "")
    QUEUE_IDS=$(echo "$QUEUE_JSON" | jq -r '.[].id' 2>/dev/null || echo "")
    ACTIVE_SUMMARY_JSON="$(summarize_active_tasks "$ACTIVE_JSON" "$PM_STATE_LIMIT")"
    QUEUE_SUMMARY_JSON="$(summarize_queue_tasks "$QUEUE_JSON" "$PM_STATE_LIMIT")"
    UNTRIAGED_SUMMARY_JSON="$(summarize_untriaged_findings "$UNTRIAGED" "$PM_FINDINGS_LIMIT")"

    # Skip if nothing to triage and no active work
    if [[ "$UNTRIAGED_COUNT" -eq 0 && "$RUNNING" -eq 0 && "$QUEUE_SIZE" -eq 0 ]]; then
        sleep "$PM_INTERVAL"
        continue
    fi

    log "PM cycle $CYCLE: $UNTRIAGED_COUNT untriaged findings, $RUNNING running, $QUEUE_SIZE queued, $AVAILABLE_SLOTS slots"

    # ---- Load memory ----
    MEMORY=""
    if [[ -f "$MEMORY_FILE" ]]; then
        MEMORY=$(cat "$MEMORY_FILE")
    fi
    MEMORY="$(trim_text "$MEMORY" "$PM_MEMORY_MAX_CHARS")"

    # ---- Latest report for health context ----
    LATEST_REPORT=""
    LATEST_REPORT_FILE=$(ls -t "$REPORTS_DIR"/*.md 2>/dev/null | head -1)
    if [[ -n "${LATEST_REPORT_FILE:-}" ]]; then
        LATEST_REPORT=$(cat "$LATEST_REPORT_FILE" 2>/dev/null || echo "")
    fi
    LATEST_REPORT="$(trim_text "$LATEST_REPORT" "$PM_REPORT_MAX_CHARS")"

    # ---- Build PM prompt ----
    PROMPT="You are the Seabone Project Manager for $PROJECT_NAME.

## Your Memory
${MEMORY}

## Your Role
You are the engineering manager who decides WHAT gets worked on, by WHOM, and in what ORDER.
You don't write code. You triage, prioritize, assign, and track.

## Available Engines
| Engine | Best For | Cost | Speed |
|--------|----------|------|-------|
| codex | General backend fixes, simple features | Medium | Fast |
| claude | Complex reasoning, architecture, multi-file refactors | High | Medium |
| claude-frontend | UI/UX, templates, CSS, design work | High | Medium |
| codex-test | Writing & running tests, test coverage | Medium | Fast |
| codex-senior | Escalation — fixes what others can't, root cause analysis | Medium | Slow (thorough) |
| aider | Budget tasks, simple one-file fixes | Low | Fast |

## Engine Selection Rules
- **Security fixes** (SQL injection, auth bypass, secrets): \`codex\` for simple, \`codex-senior\` for complex
- **API fixes** (missing validation, response models): \`codex\` — straightforward pattern work
- **Quality fixes** (dead code, error handling): \`aider\` for trivial, \`codex\` for moderate
- **Frontend work** (templates, CSS, component/layout, UX/accessibility): \`claude-frontend\`
- **Do not use \`claude-frontend\` for backend/security tasks in Python files**, even if text mentions HTML/XSS
- **Testing tasks** (write tests, fix tests): \`codex-test\` always
- **Architecture changes** (refactors, new patterns): \`claude\` for planning, \`codex\` for execution
- **Multi-file complex bugs**: \`codex-senior\` — needs deep context reading
- **Dependency issues** (imports, circular deps): \`codex\` for simple, \`codex-senior\` if circular

## Priority Rules
- \`--urgent\` (priority 1): Critical security, data loss risk
- \`--high-priority\` (priority 2): High severity, user-facing bugs
- Default (priority 5): Normal work
- \`--low-priority\` (priority 10): Nice-to-have, cleanup

## Current State

### Active Agents ($RUNNING / $MAX_AGENTS, summarized)
${ACTIVE_SUMMARY_JSON}

### Queue ($QUEUE_SIZE tasks, summarized)
${QUEUE_SUMMARY_JSON}

### Completed Tasks
$(echo "$COMPLETED_JSON" | jq -r '.[].id' 2>/dev/null | tail -20 || echo "(none)")

### Already Active/Queued Task IDs (do NOT re-assign)
${ACTIVE_IDS}
${QUEUE_IDS}

### Latest Health Report
${LATEST_REPORT:-No reports yet.}

---

## Untriaged Findings ($UNTRIAGED_COUNT new)

${UNTRIAGED_SUMMARY_JSON}

---

## Your Instructions

### 1. Triage each untriaged finding
For each finding, decide:
- **Skip** if: already fixed (in completed tasks), duplicate of active task, too low impact, or not auto_fixable
- **Assign** if: actionable, not already being worked on

### 2. For each finding you assign, spawn an agent
Use this exact command format:
\`\`\`
${SCRIPT_DIR}/spawn-agent.sh \"<task-id>\" \"<clear task description>\" --engine <engine> --priority <n>
\`\`\`

Task ID format: \`fix-<finding-id>\` (e.g., \`fix-security-c1-3\`)

Rules:
- Only spawn up to $AVAILABLE_SLOTS agents (available slots right now)
- If no slots available, the spawn script will auto-queue them
- Choose the RIGHT engine for each task (see Engine Selection Rules)
- Write a clear, specific task description — the agent has no other context
- Set priority based on severity
- Keep task descriptions concise (do not paste giant blobs)
- **Batch tiny related findings** (same category/area, trivial effort) into one task when safe.
  Use task IDs like \`batch-<category>-<short-scope>-<n>\`.
  Include the source finding IDs in the description checklist.

### 3. Update PM state
After triaging, write the updated PM state to ${PM_STATE}:
\`\`\`json
{
  \"triaged_findings\": [<all triaged finding IDs, old + new>],
  \"last_triage\": \"<timestamp>\",
  \"sprint\": {
    \"started\": \"<sprint start>\",
    \"goals\": [\"<top 3 goals for current sprint>\"],
    \"completed\": [\"<completed goal descriptions>\"]
  },
  \"health_score\": <0-100>,
  \"stats\": {
    \"total_triaged\": <n>,
    \"assigned\": <n>,
    \"skipped\": <n>,
    \"by_engine\": {\"codex\": <n>, \"claude\": <n>, ...}
  }
}
\`\`\`

### 4. Write daily summary
Append to ${DAILY_FILE}:
\`- HH:MM PM triage: <assigned>/<total> findings assigned, engines: <breakdown>\`

### 5. Notify
Send a Telegram summary: ${SCRIPT_DIR}/notify-telegram.sh \"message\"
Include: findings triaged, agents spawned, engine breakdown, health score.

### 6. One-line summary
End with a summary of actions."

    log "Running Claude PM (cycle $CYCLE)..."
    CLAUDE_OUTPUT="$(run_pm_claude "$PROMPT" "$PM_MAX_TURNS")" || true
    if printf '%s' "$CLAUDE_OUTPUT" | grep -q "Reached max turns"; then
        log "PM cycle $CYCLE: Claude hit max turns ($PM_MAX_TURNS). Retrying with compact fallback."
        FALLBACK_PROMPT="You are the Seabone PM in fallback mode for $PROJECT_NAME.

Active summary:
${ACTIVE_SUMMARY_JSON}

Queue summary:
${QUEUE_SUMMARY_JSON}

Untriaged findings summary:
${UNTRIAGED_SUMMARY_JSON}

Instructions:
1. Spawn only the highest-priority missing tasks (up to $AVAILABLE_SLOTS) with ${SCRIPT_DIR}/spawn-agent.sh.
2. Prefer codex/codex-senior for backend/security; only use claude-frontend for real template/style/component work.
3. Update ${PM_STATE}, append ${DAILY_FILE}, notify via ${SCRIPT_DIR}/notify-telegram.sh.
4. End with a single-line summary."
        CLAUDE_OUTPUT="$(run_pm_claude "$FALLBACK_PROMPT" "$PM_RETRY_MAX_TURNS")" || true
    fi

    echo "$CLAUDE_OUTPUT" >> "$PM_LOG"

    SUMMARY=$(echo "$CLAUDE_OUTPUT" | grep -v '^$' | tail -1)
    log "PM cycle $CYCLE: $SUMMARY"

    sleep "$PM_INTERVAL"
done
