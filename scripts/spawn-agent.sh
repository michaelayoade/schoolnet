#!/usr/bin/env bash
# spawn-agent.sh — Spawn an isolated coding agent in tmux with git worktree
# Supports engines: codex (default), claude, claude-frontend, aider
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
SESSION_PREFIX="agent-${PROJECT_NAME}"
SEABONE_DIR="$PROJECT_DIR/.seabone"
ACTIVE_FILE="$SEABONE_DIR/active-tasks.json"
COMPLETED_FILE="$SEABONE_DIR/completed-tasks.json"
QUEUE_FILE="$SEABONE_DIR/queue.json"
MEMORY_FILE="$SEABONE_DIR/model-memory.json"
CONFIG_FILE="$SEABONE_DIR/config.json"
FINDINGS_DIR="$SEABONE_DIR/findings"
LOG_DIR="$SEABONE_DIR/logs"
EVENT_LOG="$LOG_DIR/events.log"
PROMPTS_DIR="$SEABONE_DIR/prompts"
export PATH="$HOME/.local/bin:$PATH"

source "$SCRIPT_DIR/json-lock.sh"

if [[ -f "$PROJECT_DIR/.env.agent-swarm" ]]; then
    set -a
    source "$PROJECT_DIR/.env.agent-swarm"
    set +a
fi

sanitize_task_id() {
    local value="$1"
    value="${value,,}"
    value="$(printf '%s' "$value" | sed -E 's#[^a-z0-9_-]+#-#g; s/^-+//; s/-+$//; s/--+/-/g')"
    printf '%s' "$value"
}

default_model_for_engine() {
    local engine="$1"
    case "$engine" in
        claude|claude-frontend) printf '%s' "sonnet" ;;
        codex|codex-test|codex-senior) printf '%s' "gpt-5.3-codex" ;;
        aider) jq -r '.model // "deepseek-chat"' "$CONFIG_FILE" 2>/dev/null || printf '%s' "deepseek-chat" ;;
        *) printf '%s' "" ;;
    esac
}

codex_only_execution_enabled() {
    local enabled
    enabled="${SEABONE_CODEX_ONLY_EXECUTION:-}"
    if [[ -z "$enabled" ]]; then
        enabled="$(jq -r '.codex_only_execution // false' "$CONFIG_FILE" 2>/dev/null || echo false)"
    fi
    enabled="$(printf '%s' "$enabled" | tr '[:upper:]' '[:lower:]')"
    case "$enabled" in
        1|true|yes|on) printf '%s' "true" ;;
        *) printf '%s' "false" ;;
    esac
}

is_frontend_task() {
    local text="${1,,}"
    printf '%s' "$text" | grep -Eiq '(^|[^a-z])(frontend|ui|ux|template|jinja|tailwind|css|html|alpine|htmx|component|layout|design|branding|responsive|accessibility|icon)([^a-z]|$)'
}

is_backend_task() {
    local text="${1,,}"
    printf '%s' "$text" | grep -Eiq '(^|[^a-z])(security|auth|oauth|jwt|token|csrf|ssrf|sql|database|migration|schema|dependency|deps|pytest|mypy|api|endpoint|celery|redis|orm|poetry|requirements|cve|rce|xss|sqli|rate[- ]?limit)([^a-z]|$)'
}

is_frontend_path() {
    local path="${1,,}"
    [[ -z "$path" || "$path" == "null" ]] && return 1
    printf '%s' "$path" | grep -Eiq '(^|/)(templates?|static|assets|frontend|ui|styles?|css|scss|sass|less|js|ts|tsx|jsx|vue|svelte|images?|icons?)(/|$)|\.(html?|jinja2?|j2|css|scss|sass|less|jsx|tsx|vue|svelte)$'
}

normalize_finding_id() {
    local task_id="$1"
    local normalized
    normalized="$(printf '%s' "$task_id" | sed -E 's/-v[0-9]+$//; s/-senior$//')"
    if [[ "$normalized" == fix-* ]]; then
        printf '%s' "${normalized#fix-}"
        return 0
    fi
    return 1
}

get_finding_metadata() {
    local task_id="$1"
    local finding_id
    local files
    finding_id="$(normalize_finding_id "$task_id" 2>/dev/null || true)"
    [[ -n "$finding_id" ]] || return 1
    [[ -d "$FINDINGS_DIR" ]] || return 1

    shopt -s nullglob
    files=("$FINDINGS_DIR"/*.json)
    shopt -u nullglob
    [[ ${#files[@]} -gt 0 ]] || return 1

    jq -c --arg id "$finding_id" '
        . as $root
        | if ($root | type) == "array" then .[] else empty end
        | select((.id // "") == $id)
        | {id, category:(.category // ""), file:(.file // ""), issue:(.issue // ""), task:(.task // "")}
    ' "${files[@]}" 2>/dev/null | head -n1
}

frontend_signal_from_metadata() {
    local task_id="$1"
    local finding_meta
    local category
    local file
    local context
    finding_meta="$(get_finding_metadata "$task_id" || true)"
    [[ -n "$finding_meta" ]] || { printf '%s' "unknown"; return; }

    category="$(echo "$finding_meta" | jq -r '.category // ""' | tr '[:upper:]' '[:lower:]')"
    file="$(echo "$finding_meta" | jq -r '.file // ""' | tr '[:upper:]' '[:lower:]')"
    context="$(echo "$finding_meta" | jq -r '[(.issue // ""), (.task // "")] | join(" ")' | tr '[:upper:]' '[:lower:]')"

    if is_frontend_path "$file"; then
        printf '%s' "frontend"
        return
    fi

    case "$category" in
        frontend|ui|ux|design)
            printf '%s' "frontend"
            return
            ;;
        security|deps|dependency|api|quality|backend|performance|database|infra)
            printf '%s' "non-frontend"
            return
            ;;
    esac

    if printf '%s' "$context" | grep -Eiq '(^|[^a-z])(tailwind|css|responsive|template|jinja|component|layout|accessibility|a11y|branding)([^a-z]|$)'; then
        printf '%s' "frontend"
        return
    fi

    printf '%s' "unknown"
}

frontend_signal() {
    local task_id="$1"
    local description="$2"
    local meta_signal
    meta_signal="$(frontend_signal_from_metadata "$task_id")"
    if [[ "$meta_signal" != "unknown" ]]; then
        printf '%s' "$meta_signal"
        return
    fi

    if is_frontend_task "$task_id $description"; then
        if is_backend_task "$task_id $description"; then
            printf '%s' "unknown"
        else
            printf '%s' "frontend"
        fi
        return
    fi

    if is_backend_task "$task_id $description"; then
        printf '%s' "non-frontend"
        return
    fi

    printf '%s' "unknown"
}

enforce_engine_policy() {
    local requested_engine="$1"
    local signal="$2"

    if [[ "${SEABONE_STRICT_ENGINE_ROUTING:-true}" != "true" ]]; then
        printf '%s' "$requested_engine"
        return
    fi

    case "$requested_engine" in
        codex-test|codex-senior)
            printf '%s' "$requested_engine"
            return
            ;;
    esac

    if [[ "$signal" == "frontend" ]]; then
        printf '%s' "claude-frontend"
        return
    fi

    if [[ "$signal" == "non-frontend" && "$requested_engine" == "claude-frontend" ]]; then
        printf '%s' "codex"
        return
    fi

    printf '%s' "$requested_engine"
}

log_event() {
    local task_id="$1"
    local event="$2"
    local status="$3"
    local detail="$4"
    mkdir -p "$LOG_DIR"
    local ts
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf '%s\n' "$(jq -n --arg ts "$ts" --arg project "$PROJECT_NAME" --arg task_id "$task_id" --arg event "$event" --arg status "$status" --arg detail "$detail" '{ts:$ts,project:$project,task_id:$task_id,event:$event,status:$status,detail:$detail}')" >> "$EVENT_LOG"
}

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

append_queue() {
    local task_id="$1"
    local description="$2"
    local engine="$3"
    local model="$4"
    local priority="$5"
    local queued_at
    queued_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    local queue_json
    queue_json=$(jq -n \
        --arg id "$task_id" \
        --arg desc "$description" \
        --arg engine "$engine" \
        --arg model "$model" \
        --arg ts "$queued_at" \
        --argjson priority "$priority" \
        '{id:$id, description:$desc, engine:$engine, model:$model, priority:$priority, queued_at:$ts, status:"queued"}')
    json_append "$QUEUE_FILE" "$queue_json"
}

# ---- Parse arguments ----
TASK_ID_RAW="${1:?Usage: spawn-agent.sh <task-id> <description> [--engine claude|codex|claude-frontend|aider] [--model model] [--priority n] [--retries n] [--force] [--resolve-only]}"
DESCRIPTION="${2:?Usage: spawn-agent.sh <task-id> <description> [--engine claude|codex|claude-frontend|aider] [--model model] [--priority n] [--retries n] [--force] [--resolve-only]}"
shift 2

ENGINE=""
REQUESTED_MODEL=""
PRIORITY=5
INITIAL_RETRIES=0
FORCE_REPLACE="false"
MODEL_EXPLICIT="false"
RESOLVE_ONLY="false"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --engine)
            shift
            ENGINE="${1:-}"
            ;;
        --model|--agent-model)
            shift
            REQUESTED_MODEL="${1:-}"
            MODEL_EXPLICIT="true"
            ;;
        --priority)
            shift
            PRIORITY="${1:-5}"
            ;;
        --retries)
            shift
            INITIAL_RETRIES="${1:-0}"
            ;;
        --urgent)    PRIORITY=1 ;;
        --high-priority) PRIORITY=2 ;;
        --low-priority)  PRIORITY=10 ;;
        --force) FORCE_REPLACE="true" ;;
        --resolve-only) RESOLVE_ONLY="true" ;;
        *)
            echo "[WARN] Unknown arg ignored: $1"
            ;;
    esac
    shift || true
    [[ $# -lt 0 ]] && break
done

# Default engine from config, fallback to codex
if [[ -z "$ENGINE" ]]; then
    ENGINE="$(jq -r '.engine // "codex"' "$CONFIG_FILE")"
fi

CODEX_ONLY_EXECUTION="$(codex_only_execution_enabled)"

ORIGINAL_ENGINE="$ENGINE"
ENGINE_POLICY_SIGNAL="$(frontend_signal "$TASK_ID_RAW" "$DESCRIPTION")"
ENGINE="$(enforce_engine_policy "$ENGINE" "$ENGINE_POLICY_SIGNAL")"
if [[ "$ENGINE" != "$ORIGINAL_ENGINE" && "$RESOLVE_ONLY" != "true" ]]; then
    echo "[INFO] Engine policy override: $ORIGINAL_ENGINE -> $ENGINE (signal: $ENGINE_POLICY_SIGNAL)"
fi

if [[ "$CODEX_ONLY_EXECUTION" == "true" && "$ENGINE" != "codex" ]]; then
    if [[ "$RESOLVE_ONLY" != "true" ]]; then
        echo "[INFO] Codex-only policy override: $ENGINE -> codex"
    fi
    ENGINE="codex"
fi

# Validate engine
case "$ENGINE" in
    claude|codex|aider|claude-frontend|codex-test|codex-senior) ;;
    *) echo "[ERROR] Unknown engine: $ENGINE (use claude, codex, claude-frontend, codex-test, codex-senior, or aider)"; exit 1 ;;
esac

if [[ "$ENGINE" != "$ORIGINAL_ENGINE" && "$MODEL_EXPLICIT" == "true" ]]; then
    ORIGINAL_DEFAULT_MODEL="$(default_model_for_engine "$ORIGINAL_ENGINE")"
    RESOLVED_DEFAULT_MODEL="$(default_model_for_engine "$ENGINE")"
    if [[ -n "$ORIGINAL_DEFAULT_MODEL" && -n "$RESOLVED_DEFAULT_MODEL" && "$REQUESTED_MODEL" == "$ORIGINAL_DEFAULT_MODEL" && "$REQUESTED_MODEL" != "$RESOLVED_DEFAULT_MODEL" ]]; then
        if [[ "$RESOLVE_ONLY" != "true" ]]; then
            echo "[INFO] Dropping inherited model '$REQUESTED_MODEL' after engine override."
        fi
        REQUESTED_MODEL=""
        MODEL_EXPLICIT="false"
    fi
fi

# Set model based on engine if not explicitly requested
if [[ -z "$REQUESTED_MODEL" ]]; then
    case "$ENGINE" in
        claude)          REQUESTED_MODEL="$(default_model_for_engine claude)" ;;
        claude-frontend) REQUESTED_MODEL="$(default_model_for_engine claude-frontend)" ;;
        codex|codex-test|codex-senior) REQUESTED_MODEL="$(default_model_for_engine codex)" ;;
        aider)           REQUESTED_MODEL="$(default_model_for_engine aider)" ;;
    esac
fi
MODEL="$REQUESTED_MODEL"

TASK_ID="$(sanitize_task_id "$TASK_ID_RAW")"
if [[ -z "$TASK_ID" ]]; then
    echo "[ERROR] Task id is invalid after sanitization"
    exit 1
fi

if ! [[ "$PRIORITY" =~ ^[0-9]+$ ]]; then
    echo "[ERROR] Priority must be a non-negative integer"
    exit 1
fi

if ! [[ "$INITIAL_RETRIES" =~ ^[0-9]+$ ]]; then
    echo "[ERROR] Retries must be a non-negative integer"
    exit 1
fi

if [[ "$RESOLVE_ONLY" == "true" ]]; then
    jq -n \
        --arg task_id "$TASK_ID" \
        --arg engine "$ENGINE" \
        --arg model "$MODEL" \
        --arg signal "$ENGINE_POLICY_SIGNAL" \
        '{task_id:$task_id, engine:$engine, model:$model, signal:$signal}'
    exit 0
fi

mkdir -p "$LOG_DIR" "$PROMPTS_DIR"
ensure_state_file "$ACTIVE_FILE" array
ensure_state_file "$COMPLETED_FILE" array
ensure_state_file "$QUEUE_FILE" array
ensure_state_file "$MEMORY_FILE" object

if [[ "$FORCE_REPLACE" == "true" ]]; then
    # Keep active/completed state until spawn succeeds; drop only queue duplicate now.
    json_update "$QUEUE_FILE" "map(select(.id != \"$TASK_ID\"))"
fi

MAX_AGENTS="$(jq -r '.max_concurrent_agents // 3' "$CONFIG_FILE")"
QUEUE_ENABLED="$(jq -r '.queue_enabled // true' "$CONFIG_FILE")"
MAX_QUEUE="$(jq -r '.max_queue_size // 50' "$CONFIG_FILE")"
RUNNING_COUNT="$(json_read "$ACTIVE_FILE" '[.[] | select(.status == "running" or .status == "stale")] | length' 2>/dev/null || echo 0)"

BRANCH="agent/${TASK_ID}"
SESSION_NAME="${SESSION_PREFIX}-${TASK_ID}"
WORKTREE_DIR="$PROJECT_DIR/.worktrees/${TASK_ID}"
LOG_FILE="$LOG_DIR/${TASK_ID}.log"

# ---- Concurrency / queue checks ----
if (( RUNNING_COUNT >= MAX_AGENTS )); then
    if [[ "$QUEUE_ENABLED" == "true" ]]; then
        QUEUE_COUNT="$(json_read "$QUEUE_FILE" 'length' 2>/dev/null || echo 0)"
        if (( QUEUE_COUNT >= MAX_QUEUE )); then
            echo "[ERROR] Queue is full (${QUEUE_COUNT}/${MAX_QUEUE})"
            exit 1
        fi
        if json_read "$QUEUE_FILE" ".[] | select(.id == \"$TASK_ID\")" 2>/dev/null | grep -q . || \
           json_read "$ACTIVE_FILE" ".[] | select(.id == \"$TASK_ID\")" 2>/dev/null | grep -q . || \
           json_read "$COMPLETED_FILE" ".[] | select(.id == \"$TASK_ID\")" 2>/dev/null | grep -q .; then
            echo "[ERROR] Task '$TASK_ID' already exists."
            exit 1
        fi
        append_queue "$TASK_ID" "$DESCRIPTION" "$ENGINE" "$MODEL" "$PRIORITY"
        log_event "$TASK_ID" "queued" "queued" "max concurrency reached"
        echo "[INFO] Max concurrency reached (${RUNNING_COUNT}/${MAX_AGENTS}); queued task '$TASK_ID'."
        exit 0
    fi
    echo "[ERROR] Max concurrent agents ($MAX_AGENTS) reached."
    exit 1
fi

if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "[ERROR] tmux session '$SESSION_NAME' already exists."
    exit 1
fi

if [[ "$FORCE_REPLACE" != "true" ]] && \
   { json_read "$ACTIVE_FILE" ".[] | select(.id == \"$TASK_ID\")" 2>/dev/null | grep -q . || \
     json_read "$COMPLETED_FILE" ".[] | select(.id == \"$TASK_ID\")" 2>/dev/null | grep -q .; }; then
    echo "[ERROR] Task '$TASK_ID' already exists."
    exit 1
fi

[[ -d "$WORKTREE_DIR" ]] && rm -rf "$WORKTREE_DIR"

# ---- Step 1: Create worktree ----
echo "[1/5] Creating git worktree: $BRANCH"
cd "$PROJECT_DIR"
git worktree add "$WORKTREE_DIR" -b "$BRANCH" 2>/dev/null || {
    git worktree add "$WORKTREE_DIR" "$BRANCH" 2>/dev/null || {
        echo "[ERROR] Failed to create worktree for branch $BRANCH"
        exit 1
    }
}

# Keep runtime script out of commits for this worktree.
WORKTREE_GIT_DIR="$(git -C "$WORKTREE_DIR" rev-parse --git-dir 2>/dev/null || true)"
if [[ -n "$WORKTREE_GIT_DIR" ]]; then
    WORKTREE_EXCLUDE_FILE="$WORKTREE_GIT_DIR/info/exclude"
    mkdir -p "$(dirname "$WORKTREE_EXCLUDE_FILE")"
    grep -qxF '.agent-run.sh' "$WORKTREE_EXCLUDE_FILE" 2>/dev/null || printf '%s\n' '.agent-run.sh' >> "$WORKTREE_EXCLUDE_FILE"
fi

# ---- Step 2: Register task ----
echo "[2/5] Registering task"
if [[ "$FORCE_REPLACE" == "true" ]]; then
    json_update "$ACTIVE_FILE" "map(select(.id != \"$TASK_ID\"))"
    json_update "$COMPLETED_FILE" "map(select(.id != \"$TASK_ID\"))"
fi
TASK_JSON=$(jq -n \
    --arg id "$TASK_ID" \
    --arg desc "$DESCRIPTION" \
    --arg branch "$BRANCH" \
    --arg engine "$ENGINE" \
    --arg model "$MODEL" \
    --arg session "$SESSION_NAME" \
    --arg worktree "$WORKTREE_DIR" \
    --arg started "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --argjson retries "$INITIAL_RETRIES" \
    '{id:$id, description:$desc, branch:$branch, engine:$engine, model:$model, session:$session, worktree:$worktree, status:"running", retries:$retries, started_at:$started, last_heartbeat:$started}')

json_append "$ACTIVE_FILE" "$TASK_JSON"

# ---- Step 3: Create agent runtime script ----
echo "[3/5] Creating agent runtime script (engine: $ENGINE)"
AGENT_SCRIPT="$WORKTREE_DIR/.agent-run.sh"
{
cat <<'INNER'
#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"

# ---- Injected at spawn time ----
INNER

printf 'WORKTREE_DIR=%q\n' "$WORKTREE_DIR"
printf 'PROJECT_DIR=%q\n' "$PROJECT_DIR"
printf 'SCRIPT_DIR=%q\n' "$SCRIPT_DIR"
printf 'ACTIVE_FILE=%q\n' "$ACTIVE_FILE"
printf 'LOG_FILE=%q\n' "$LOG_FILE"
printf 'TASK_ID=%q\n' "$TASK_ID"
printf 'DESCRIPTION=%q\n' "$DESCRIPTION"
printf 'BRANCH=%q\n' "$BRANCH"
printf 'ENGINE=%q\n' "$ENGINE"
printf 'MODEL=%q\n' "$MODEL"
printf 'EVENT_LOG=%q\n' "$EVENT_LOG"
printf 'CONFIG_FILE=%q\n' "$CONFIG_FILE"
printf 'PROJECT_NAME=%q\n' "$PROJECT_NAME"
printf 'PROMPTS_DIR=%q\n' "$PROMPTS_DIR"

cat <<'INNER'

if [[ -f "$PROJECT_DIR/.env.agent-swarm" ]]; then
    set -a
    source "$PROJECT_DIR/.env.agent-swarm"
    set +a
fi
source "$SCRIPT_DIR/json-lock.sh"

log_event() {
    local event="$1" status="$2" detail="$3"
    local ts project_slug
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    project_slug="${PROJECT_NAME:-}"
    if [[ -z "$project_slug" || "$project_slug" == */* ]]; then
        project_slug="$(basename "$PROJECT_DIR")"
    fi
    printf '%s\n' "$(jq -n --arg ts "$ts" --arg project "$project_slug" --arg task_id "$TASK_ID" --arg event "$event" --arg status "$status" --arg detail "$detail" '{ts:$ts,project:$project,task_id:$task_id,event:$event,status:$status,detail:$detail}')" >> "$EVENT_LOG"
}

set_status() {
    local status="$1"
    json_update "$ACTIVE_FILE" "(.[] | select(.id == \"$TASK_ID\") | .status) = \"$status\""
    json_update "$ACTIVE_FILE" "(.[] | select(.id == \"$TASK_ID\") | .last_heartbeat) = \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\""
    log_event "status" "$status" "updated"
}

cd "$WORKTREE_DIR"

echo "=== Seabone Agent: $TASK_ID ==="
echo "Engine: $ENGINE"
echo "Model: $MODEL"
echo "Task: $DESCRIPTION"
echo "Branch: $BRANCH"
echo "Started: $(date)"
echo "================================"

# =========================================
#  ENGINE: Claude Code
# =========================================
if [[ "$ENGINE" == "claude" ]]; then
    echo "[RUN] Claude Code (headless)..."

    CLAUDE_ARGS=(
        -p "$DESCRIPTION"
        --dangerously-skip-permissions
        --output-format stream-json
        --model "$MODEL"
        --verbose
    )

    if [[ -f "$PROJECT_DIR/CLAUDE.md" ]]; then
        CLAUDE_ARGS+=(--append-system-prompt "$(cat "$PROJECT_DIR/CLAUDE.md")")
    fi

    claude "${CLAUDE_ARGS[@]}" 2>&1 | tee -a "$LOG_FILE"
    AGENT_EXIT=${PIPESTATUS[0]}

# =========================================
#  ENGINE: Claude Frontend Design Specialist
# =========================================
elif [[ "$ENGINE" == "claude-frontend" ]]; then
    echo "[RUN] Claude Frontend Design Specialist..."

    # Load the frontend design system prompt
    FRONTEND_PROMPT=""
    if [[ -f "$PROMPTS_DIR/frontend-design.md" ]]; then
        FRONTEND_PROMPT=$(cat "$PROMPTS_DIR/frontend-design.md")
    fi

    # Build the full prompt: system context + task
    FULL_TASK="$FRONTEND_PROMPT

---

## Your Task

$DESCRIPTION

## Project Context
- Stack: Python 3.12, FastAPI, Jinja2 templates, Tailwind CSS, Alpine.js, HTMX
- Templates: app/templates/ (Jinja2 .html files)
- Static: app/static/css/, app/static/js/, app/static/img/
- Base template: app/templates/base.html (extend this)
- Use CDN for Tailwind, Alpine.js, HTMX unless local files exist already

## Requirements
- Create working, production-grade frontend code
- Every file must be complete and functional — no placeholders
- Follow existing project patterns for template structure
- Responsive design (mobile-first)
- Dark mode support
- Accessible (ARIA labels, semantic HTML)
- Distinctive design — no generic Bootstrap/AI-slop aesthetics"

    CLAUDE_ARGS=(
        -p "$FULL_TASK"
        --dangerously-skip-permissions
        --output-format stream-json
        --model "$MODEL"
        --max-turns 50
        --verbose
    )

    if [[ -f "$PROJECT_DIR/CLAUDE.md" ]]; then
        CLAUDE_ARGS+=(--append-system-prompt "$(cat "$PROJECT_DIR/CLAUDE.md")")
    fi

    claude "${CLAUDE_ARGS[@]}" 2>&1 | tee -a "$LOG_FILE"
    AGENT_EXIT=${PIPESTATUS[0]}

# =========================================
#  ENGINE: Codex
# =========================================
elif [[ "$ENGINE" == "codex" ]]; then
    echo "[RUN] Codex CLI (full-auto)..."

    codex exec \
        --full-auto \
        --model "$MODEL" \
        "$DESCRIPTION" \
        2>&1 | tee -a "$LOG_FILE"
    AGENT_EXIT=${PIPESTATUS[0]}

# =========================================
#  ENGINE: Codex Testing Specialist
# =========================================
elif [[ "$ENGINE" == "codex-test" ]]; then
    echo "[RUN] Codex Testing Specialist..."

    # Load the testing system prompt
    TEST_PROMPT=""
    if [[ -f "$PROMPTS_DIR/testing-agent.md" ]]; then
        TEST_PROMPT=$(cat "$PROMPTS_DIR/testing-agent.md")
    fi

    FULL_TASK="${TEST_PROMPT}

---

## Your Task

${DESCRIPTION}

## Project Context
- Stack: Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2, PostgreSQL
- Test runner: pytest
- Test dir: tests/ (mirrors app/ structure)
- Fixtures: tests/conftest.py
- Run tests with: python -m pytest tests/ -v
- Do NOT import structlog — use stdlib logging only

## Requirements
- Write complete, runnable test files
- Run the tests after writing to verify they pass
- Fix any test failures before finishing
- Use pytest fixtures, not setUp/tearDown
- Use httpx.AsyncClient for API tests
- Mock external services, never call real APIs in tests"

    codex exec \
        --full-auto \
        --model "$MODEL" \
        "$FULL_TASK" \
        2>&1 | tee -a "$LOG_FILE"
    AGENT_EXIT=${PIPESTATUS[0]}

# =========================================
#  ENGINE: Codex Senior Dev (Escalation)
# =========================================
elif [[ "$ENGINE" == "codex-senior" ]]; then
    echo "[RUN] Codex Senior Dev (Escalation)..."

    # Load the senior dev system prompt
    SENIOR_PROMPT=""
    if [[ -f "$PROMPTS_DIR/senior-dev.md" ]]; then
        SENIOR_PROMPT=$(cat "$PROMPTS_DIR/senior-dev.md")
    fi

    # Check for previous agent logs to provide context
    PREV_LOG_CONTEXT=""
    # Extract base task ID (strip -v2, -v3 suffixes for escalation lookups)
    BASE_TASK_ID=$(echo "$TASK_ID" | sed -E 's/-v[0-9]+$//')
    for prev_log in "$LOG_DIR/${BASE_TASK_ID}"*.log; do
        if [[ -f "$prev_log" && "$prev_log" != "$LOG_FILE" ]]; then
            # Get last 80 lines of previous attempts
            PREV_LOG_CONTEXT="${PREV_LOG_CONTEXT}

--- Previous attempt log: $(basename "$prev_log") ---
$(tail -80 "$prev_log" 2>/dev/null || echo "(empty)")"
        fi
    done

    FULL_TASK="${SENIOR_PROMPT}

---

## Your Task

${DESCRIPTION}

## Project Context
- Stack: Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2, PostgreSQL, Redis
- Do NOT import structlog — use stdlib logging only
- Health/status endpoints are intentionally unauthenticated
- Services use serialize() methods that return dicts
- Schemas use Pydantic BaseModel with org_id as UUID

## Previous Attempts
${PREV_LOG_CONTEXT:-No previous attempts — this is a first escalation.}

## Requirements
- Read the previous agent's log above to understand what went wrong
- Read at least 5-10 relevant source files before making changes
- Fix the root cause, not just the symptom
- Run tests after fixing to verify
- If the task is fundamentally impossible, document why and exit cleanly"

    codex exec \
        --full-auto \
        --model "$MODEL" \
        "$FULL_TASK" \
        2>&1 | tee -a "$LOG_FILE"
    AGENT_EXIT=${PIPESTATUS[0]}

# =========================================
#  ENGINE: Aider + DeepSeek
# =========================================
elif [[ "$ENGINE" == "aider" ]]; then
    echo "[RUN] Aider + DeepSeek..."

    if [[ -n "${DEEPSEEK_API_KEY:-}" ]]; then
        export OPENAI_API_KEY="${OPENAI_API_KEY:-$DEEPSEEK_API_KEY}"
        export OPENAI_API_BASE="${OPENAI_API_BASE:-https://api.deepseek.com}"
    fi

    cp "$PROJECT_DIR/.aider.model.settings.yml" "$WORKTREE_DIR/" 2>/dev/null || true
    cp "$PROJECT_DIR/.aider.model.metadata.json" "$WORKTREE_DIR/" 2>/dev/null || true
    cp "$PROJECT_DIR/.aider.conf.yml" "$WORKTREE_DIR/" 2>/dev/null || true
    cp "$PROJECT_DIR/.aiderignore" "$WORKTREE_DIR/" 2>/dev/null || true

    if [[ -z "${OPENAI_API_KEY:-}" ]]; then
        echo "[ERROR] OPENAI_API_KEY is not set. Configure OPENAI_API_KEY or DEEPSEEK_API_KEY in .env.agent-swarm." | tee -a "$LOG_FILE"
        AGENT_EXIT=2
    else
        aider --model "openai/$MODEL" \
            --no-auto-commits \
            --yes-always \
            --no-show-model-warnings \
            --no-detect-urls \
            --subtree-only \
            --map-tokens 1024 \
            --model-settings-file "$WORKTREE_DIR/.aider.model.settings.yml" \
            --model-metadata-file "$WORKTREE_DIR/.aider.model.metadata.json" \
            --message "$DESCRIPTION" \
            2>&1 | tee -a "$LOG_FILE"
        AGENT_EXIT=${PIPESTATUS[0]}
    fi

    # Self-review loop for aider only
    if [[ $AGENT_EXIT -eq 0 && -n "${DEEPSEEK_API_KEY:-}" ]]; then
        cd "$WORKTREE_DIR"
        if ! git diff --quiet || ! git diff --cached --quiet; then
            for cycle in 1 2; do
                echo ""
                echo "[REVIEW] Self-review cycle $cycle/2..."
                DIFF=$(git diff)
                [[ -z "$DIFF" ]] && DIFF=$(git diff --cached)
                [[ -z "$DIFF" ]] && break

                REVIEW=$(curl -s "https://api.deepseek.com/chat/completions" \
                    -H "Authorization: Bearer ${DEEPSEEK_API_KEY}" \
                    -H "Content-Type: application/json" \
                    -d "$(jq -n --arg p "Review this diff for bugs, missing imports, security issues. If correct respond LGTM. Otherwise describe fixes concisely.

DIFF:
$DIFF" '{model:"deepseek-chat", messages:[{role:"user",content:$p}], temperature:0.2, max_tokens:1500}')" \
                    | jq -r '.choices[0].message.content // "Review failed"')

                echo "Review: $REVIEW" | tee -a "$LOG_FILE"
                echo "$REVIEW" | grep -qi "LGTM" && break

                aider --model "openai/$MODEL" \
                    --no-auto-commits --yes-always --no-show-model-warnings --no-detect-urls \
                    --subtree-only --map-tokens 1024 \
                    --model-settings-file "$WORKTREE_DIR/.aider.model.settings.yml" \
                    --model-metadata-file "$WORKTREE_DIR/.aider.model.metadata.json" \
                    --message "Fix these issues: $REVIEW" \
                    2>&1 | tee -a "$LOG_FILE"
                cd "$WORKTREE_DIR"
            done
        fi
    fi
fi

# =========================================
#  Common: check result, commit, push, PR
# =========================================
if [[ ${AGENT_EXIT:-1} -ne 0 ]]; then
    set_status failed
    log_event "agent" "failed" "exit-${AGENT_EXIT}"
    "$SCRIPT_DIR/notify-telegram.sh" "❌ *Seabone*: \`$TASK_ID\` failed (${ENGINE}, exit ${AGENT_EXIT})." 2>/dev/null || true
    exit 1
fi

cd "$WORKTREE_DIR"
if git diff --quiet && git diff --cached --quiet && [[ -z "$(git ls-files --others --exclude-standard)" ]]; then
    set_status no_changes
    log_event "completion" "no_changes" "No diff produced"
    "$SCRIPT_DIR/notify-telegram.sh" "⚠️ *Seabone*: \`$TASK_ID\` no changes (${ENGINE})." 2>/dev/null || true
    exit 0
fi

echo ""
echo "[COMMIT] Staging and committing..."
# Exclude .agent-run.sh from commits (it is a local-only bootstrap file)
git add -A
git reset HEAD .agent-run.sh 2>/dev/null || true
git commit -m "feat($TASK_ID): $DESCRIPTION

Automated by Seabone ($ENGINE + $MODEL)"

# ---- Run tests before pushing ----
echo ""
echo "[TEST] Running pre-push checks..."
TEST_PASSED=true
TEST_OUTPUT=""

# Try common test/check commands in order of preference
if [[ -f Makefile ]]; then
    if grep -q "^check:" Makefile 2>/dev/null; then
        echo "  Running: make check..."
        TEST_OUTPUT=$(make check 2>&1) || TEST_PASSED=false
    elif grep -q "^lint:" Makefile 2>/dev/null; then
        echo "  Running: make lint..."
        TEST_OUTPUT=$(make lint 2>&1) || TEST_PASSED=false
    fi

    if [[ "$TEST_PASSED" == "true" ]] && grep -q "^test:" Makefile 2>/dev/null; then
        echo "  Running: make test..."
        TEST_OUTPUT="${TEST_OUTPUT}
$(make test 2>&1)" || TEST_PASSED=false
    fi
elif [[ -f pyproject.toml ]]; then
    echo "  Running: python -m pytest tests/ -x -q --tb=short..."
    TEST_OUTPUT=$(python -m pytest tests/ -x -q --tb=short 2>&1) || TEST_PASSED=false
elif [[ -f package.json ]]; then
    echo "  Running: npm test..."
    TEST_OUTPUT=$(npm test 2>&1) || TEST_PASSED=false
fi

# Also verify the app can import (Python/FastAPI projects)
if [[ "$TEST_PASSED" == "true" && -f pyproject.toml ]]; then
    echo "  Running: import check..."
    python -c "from app.main import app" 2>/dev/null || {
        echo "  [WARN] App import check failed (non-blocking)"
    }
fi

if [[ "$TEST_PASSED" == "false" ]]; then
    echo "[TEST] Tests FAILED. Pushing anyway but flagging PR."
    echo "$TEST_OUTPUT" | tail -30 | tee -a "$LOG_FILE"
    TEST_NOTE="\n\n> **Warning:** Pre-push tests failed. Review carefully.\n> \`\`\`\n> $(echo "$TEST_OUTPUT" | tail -10 | tr '\n' ' ')\n> \`\`\`"
else
    echo "[TEST] Tests PASSED."
    TEST_NOTE=""
fi

echo "[PUSH] Pushing to origin..."
git push -u origin "$BRANCH"

echo "[PR] Creating pull request..."
PR_URL=$(gh pr create \
    --title "[$TASK_ID] $DESCRIPTION" \
    --body "## Summary
Automated PR by Seabone agent swarm.

**Task:** $DESCRIPTION
**Engine:** \`$ENGINE\`
**Model:** \`$MODEL\`
**Branch:** \`$BRANCH\`
**Tests:** $([ \"$TEST_PASSED\" = true ] && echo '✅ Passed' || echo '⚠️ Failed')${TEST_NOTE}

---
🤖 Seabone Agent Swarm" \
    --head "$BRANCH" 2>&1) || PR_URL="PR creation failed"

if [[ "$PR_URL" == "PR creation failed" ]]; then
    set_status failed
    log_event "completion" "failed" "PR creation failed"
    "$SCRIPT_DIR/notify-telegram.sh" "❌ *Seabone*: \`$TASK_ID\` PR creation failed." 2>/dev/null || true
    exit 1
fi

echo "[OK] PR created: $PR_URL"
set_status pr_created
log_event "completion" "pr_created" "$PR_URL"
"$SCRIPT_DIR/notify-telegram.sh" "✅ *Seabone*: \`$TASK_ID\` done ($ENGINE)
PR: $PR_URL" 2>/dev/null || true
exit 0
INNER
} > "$AGENT_SCRIPT"
chmod +x "$AGENT_SCRIPT"

# ---- Step 4: Launch tmux ----
echo "[4/5] Launching tmux session: $SESSION_NAME"
tmux new-session -d -s "$SESSION_NAME" "bash $AGENT_SCRIPT"

log_event "$TASK_ID" "spawned" "running" "engine=$ENGINE session=$SESSION_NAME"

# ---- Step 5: Done ----
echo "[5/5] Agent spawned!"
echo "  Task:    $TASK_ID"
echo "  Engine:  $ENGINE ($MODEL)"
echo "  Branch:  $BRANCH"
echo "  Session: tmux attach -t $SESSION_NAME"
echo "  Log:     $LOG_FILE"
echo ""

"$SCRIPT_DIR/notify-telegram.sh" "🚀 *Seabone*: \`$TASK_ID\` spawned
Engine: $ENGINE ($MODEL)
Task: $DESCRIPTION" 2>/dev/null || true
