#!/usr/bin/env bash
# analyst.sh — Seabone Codebase Analyst
# Runs Claude Code to scan the codebase, find issues, and queue fix tasks.
# Can be run manually or via cron.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
SEABONE_DIR="$PROJECT_DIR/.seabone"
CONFIG_FILE="$SEABONE_DIR/config.json"
LOG_DIR="$SEABONE_DIR/logs"
ANALYST_LOG="$LOG_DIR/analyst.log"
MEMORY_DIR="$SEABONE_DIR/memory"
MEMORY_FILE="$SEABONE_DIR/MEMORY.md"
SOUL_FILE="$SEABONE_DIR/SOUL.md"
FINDINGS_DIR="$SEABONE_DIR/findings"
export PATH="$HOME/.local/bin:$PATH"

if [[ -f "$PROJECT_DIR/.env.agent-swarm" ]]; then
    set -a
    source "$PROJECT_DIR/.env.agent-swarm"
    set +a
fi

mkdir -p "$LOG_DIR" "$FINDINGS_DIR" "$MEMORY_DIR"

log() {
    local msg="[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
    echo "$msg"
    echo "$msg" >> "$ANALYST_LOG"
}

notify() {
    "$SCRIPT_DIR/notify-telegram.sh" "$1" 2>/dev/null || true
}

# What kind of analysis to run
SCAN_TYPE="${1:-full}"
# full     — scan entire codebase for all issue types
# security — focus on auth, injection, secrets
# quality  — dead code, missing error handling, type issues
# api      — endpoint consistency, missing validation, schema gaps
# deps     — unused imports, missing dependencies, version issues

# Load persistent memory for context
MEMORY=""
if [[ -f "$MEMORY_FILE" ]]; then
    MEMORY=$(cat "$MEMORY_FILE")
fi

# Load previous findings to avoid duplicates
PREVIOUS_FINDINGS=""
LATEST_FINDING=$(ls -t "$FINDINGS_DIR"/*.json 2>/dev/null | head -1)
if [[ -n "$LATEST_FINDING" ]]; then
    PREVIOUS_FINDINGS=$(cat "$LATEST_FINDING" 2>/dev/null || echo "[]")
fi

TODAY=$(date +%Y-%m-%d)
FINDING_FILE="$FINDINGS_DIR/${TODAY}-${SCAN_TYPE}.json"

log "=========================================="
log "Seabone Analyst — $SCAN_TYPE scan"
log "Project: $PROJECT_NAME"
log "=========================================="

notify "🔍 *Seabone Analyst*: Starting \`$SCAN_TYPE\` scan on \`$PROJECT_NAME\`"

cd "$PROJECT_DIR"

PROMPT="You are a senior code analyst reviewing the dotmac-platform codebase.

## Your Memory
${MEMORY}

## Scan Type: ${SCAN_TYPE}

## Previous Findings (avoid duplicates)
${PREVIOUS_FINDINGS:-None yet.}

## Your Job

Thoroughly scan the codebase and produce a JSON findings report. For each issue found, assess severity and write a one-line task description that a coding agent can execute.

### What to scan for:

$(case "$SCAN_TYPE" in
    security)
        echo "- SQL injection (raw queries, string formatting in queries)
- Missing authentication on sensitive endpoints
- Hardcoded secrets, API keys, passwords
- Missing input validation on user-facing endpoints
- CSRF/XSS vulnerabilities
- Insecure deserialization
- Missing rate limiting on auth endpoints"
        ;;
    quality)
        echo "- Dead code (unused functions, unreachable branches)
- Missing error handling (bare except, swallowed exceptions)
- Type mismatches (wrong return types, schema vs model mismatches)
- Functions that are too long (>100 lines)
- Duplicate logic that should be extracted
- Missing docstrings on public API endpoints
- Inconsistent patterns across similar files"
        ;;
    api)
        echo "- Endpoints missing response_model declarations
- Inconsistent error response formats
- Missing query parameter validation (negative offset, limit > max)
- Endpoints that return raw dicts instead of Pydantic models
- Missing pagination on list endpoints
- Inconsistent URL naming conventions
- Missing OpenAPI descriptions/summaries"
        ;;
    deps)
        echo "- Unused imports in Python files
- Missing __init__.py files
- Circular import risks
- Dependencies imported but not in requirements/pyproject.toml
- Deprecated API usage"
        ;;
    *)
        echo "- Security issues (SQL injection, missing auth, hardcoded secrets)
- Missing error handling
- API consistency (missing response_model, validation)
- Dead or unreachable code
- Missing pagination on list endpoints
- Type safety issues
- Performance concerns (N+1 queries, missing indexes)"
        ;;
esac)

### How to scan
1. Read the project structure (ls app/api/, app/services/, app/schemas/, app/models/)
2. Read key files to understand patterns
3. For each area, read the relevant source files
4. Compare against best practices and internal consistency
5. Only report REAL issues — not style preferences

### Output Format
Write your findings as a JSON array to this exact file: ${FINDING_FILE}

Each finding should be an object with:
{
  \"id\": \"<scan_type>-<number>\",
  \"severity\": \"critical|high|medium|low\",
  \"category\": \"security|quality|api|deps|performance\",
  \"file\": \"path/to/file.py\",
  \"line\": <approximate line number or null>,
  \"issue\": \"<one sentence description of the problem>\",
  \"task\": \"<one sentence instruction for a coding agent to fix it>\",
  \"auto_fixable\": true|false
}

Sort by severity (critical first).

### After writing findings
1. Count findings by severity and category
2. Write a summary to ${SEABONE_DIR}/memory/${TODAY}.md (append, don't overwrite)
3. If you found patterns worth remembering, append them to ${MEMORY_FILE} under '## Known Patterns'

### Auto-queue option
For any finding marked auto_fixable AND severity critical or high:
- Queue it by running: ${SCRIPT_DIR}/spawn-agent.sh \"fix-<id>\" \"<task description>\"
- Only auto-spawn up to 3 fixes per scan to avoid overwhelming the swarm

Give a final summary line of total findings by severity."

log "Running Claude analyst..."
CLAUDE_OUTPUT=$(claude \
    -p "$PROMPT" \
    --dangerously-skip-permissions \
    --output-format text \
    --model sonnet \
    --max-turns 60 \
    2>&1) || true

# Log output
echo "$CLAUDE_OUTPUT" >> "$ANALYST_LOG"

# Extract summary
SUMMARY=$(echo "$CLAUDE_OUTPUT" | grep -v '^$' | tail -1)
log "Scan result: $SUMMARY"

# Count findings if file was created
if [[ -f "$FINDING_FILE" ]]; then
    TOTAL=$(jq 'length' "$FINDING_FILE" 2>/dev/null || echo 0)
    CRITICAL=$(jq '[.[] | select(.severity == "critical")] | length' "$FINDING_FILE" 2>/dev/null || echo 0)
    HIGH=$(jq '[.[] | select(.severity == "high")] | length' "$FINDING_FILE" 2>/dev/null || echo 0)

    log "Findings: $TOTAL total ($CRITICAL critical, $HIGH high)"

    notify "🔍 *Seabone Analyst*: \`$SCAN_TYPE\` scan complete
Findings: $TOTAL total
Critical: $CRITICAL | High: $HIGH
File: \`$FINDING_FILE\`"
else
    log "No findings file generated"
    notify "🔍 *Seabone Analyst*: \`$SCAN_TYPE\` scan complete — no findings file generated"
fi
