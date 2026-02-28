#!/usr/bin/env bash
# docs-agent.sh — Seabone Documentation Agent
# Updates API docs, changelog, and README after merges.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
SEABONE_DIR="$PROJECT_DIR/.seabone"
CONFIG_FILE="$SEABONE_DIR/config.json"
LOG_DIR="$SEABONE_DIR/logs"
DOCS_LOG="$LOG_DIR/docs-agent.log"
MEMORY_DIR="$SEABONE_DIR/memory"
MEMORY_FILE="$SEABONE_DIR/MEMORY.md"
COMPLETED_FILE="$SEABONE_DIR/completed-tasks.json"
DOCS_STATE="$SEABONE_DIR/docs-state.json"
LOCKFILE="/tmp/seabone-docs-${PROJECT_NAME}.lock"
export PATH="$HOME/.local/bin:$PATH"

if [[ -f "$PROJECT_DIR/.env.agent-swarm" ]]; then
    set -a; source "$PROJECT_DIR/.env.agent-swarm"; set +a
fi

mkdir -p "$LOG_DIR" "$MEMORY_DIR"

exec 4>"$LOCKFILE"
if ! flock -n 4; then echo "Another docs agent running."; exit 0; fi

log() { local msg="[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; echo "$msg"; echo "$msg" >> "$DOCS_LOG"; }
notify() { "$SCRIPT_DIR/notify-telegram.sh" "$1" 2>/dev/null || true; }

# Check every 30 minutes
DOCS_INTERVAL="${SEABONE_DOCS_INTERVAL:-1800}"

if [[ ! -f "$DOCS_STATE" ]]; then
    echo '{"last_documented_count":0,"changelog_entries":[]}' > "$DOCS_STATE"
fi

log "=========================================="
log "Seabone Docs Agent started"
log "Project: $PROJECT_NAME"
log "=========================================="

notify "📝 *Seabone Docs Agent* started on \`$PROJECT_NAME\`"

TODAY=$(date +%Y-%m-%d)
DAILY_FILE="$MEMORY_DIR/${TODAY}.md"

while true; do
    NEW_TODAY=$(date +%Y-%m-%d)
    if [[ "$NEW_TODAY" != "$TODAY" ]]; then TODAY="$NEW_TODAY"; DAILY_FILE="$MEMORY_DIR/${TODAY}.md"; fi

    cd "$PROJECT_DIR"

    # Use a dedicated worktree to avoid racing other agents on git checkout
    DOCS_WORKTREE="$PROJECT_DIR/.worktrees/_docs-agent"
    git fetch origin main --quiet 2>/dev/null || true
    if [[ ! -d "$DOCS_WORKTREE" ]]; then
        git worktree add "$DOCS_WORKTREE" origin/main --detach --quiet 2>/dev/null || true
    fi
    if [[ -d "$DOCS_WORKTREE" ]]; then
        cd "$DOCS_WORKTREE"
        git checkout --detach origin/main --quiet 2>/dev/null || true
    fi

    # Check if there are new completed tasks since last docs run
    COMPLETED_COUNT=$(jq 'length' "$COMPLETED_FILE" 2>/dev/null || echo 0)
    LAST_COUNT=$(jq -r '.last_documented_count // 0' "$DOCS_STATE" 2>/dev/null || echo 0)

    if [[ "$COMPLETED_COUNT" -le "$LAST_COUNT" ]]; then
        sleep "$DOCS_INTERVAL"
        continue
    fi

    NEW_TASKS=$((COMPLETED_COUNT - LAST_COUNT))
    log "Docs agent: $NEW_TASKS new completed tasks to document"

    # Get the new tasks
    NEW_TASK_JSON=$(jq ".[-${NEW_TASKS}:]" "$COMPLETED_FILE" 2>/dev/null || echo '[]')

    # Get recent git log for context
    RECENT_COMMITS=$(git log --oneline -20 2>/dev/null || echo "")

    MEMORY=""
    [[ -f "$MEMORY_FILE" ]] && MEMORY=$(cat "$MEMORY_FILE")

    PROMPT="You are the Seabone Documentation Agent for $PROJECT_NAME.

## Memory
${MEMORY}

## New Completed Tasks (need documentation)
${NEW_TASK_JSON}

## Recent Commits
${RECENT_COMMITS}

## Your Job

### 1. Update CHANGELOG.md
- Read the current CHANGELOG.md (create if missing)
- Add entries for each new completed task under today's date
- Format: \`- [category] description (PR #N)\`
- Categories: Added, Changed, Fixed, Security, Removed, Deprecated
- Keep existing entries, only append new ones

### 2. Update API Documentation
- If any new endpoints were added, update docs/API.md (create if missing)
- List endpoint, method, description, request/response examples
- Read the actual route files to get accurate info

### 3. Update README.md
- If significant features were added, update the Features section
- Keep it concise — README shouldn't grow unbounded
- Only update if the changes are user-facing

### 4. Create documentation PR (DO NOT push directly to main)
- You are running inside a git worktree. Create a branch from here:
  git checkout -b docs/update-\$(date +%Y%m%d-%H%M%S)
- Stage only documentation files (CHANGELOG.md, docs/, README.md)
- Commit: \"docs: update documentation for recent changes\"
- Push: git push -u origin HEAD
- Create PR: gh pr create --title \"docs: update documentation\" --body \"Automated documentation update by Seabone Docs Agent\"
- After pushing, detach back: git checkout --detach origin/main

### 5. Summary
Write to ${DAILY_FILE}:
\"- HH:MM Docs: updated changelog with <n> entries\"

End with one-line summary."

    log "Running Claude docs agent..."
    if ! CLAUDE_OUTPUT=$(claude \
        -p "$PROMPT" \
        --dangerously-skip-permissions \
        --output-format text \
        --model sonnet \
        --max-turns 30 \
        2>&1); then
        echo "$CLAUDE_OUTPUT" >> "$DOCS_LOG"
        log "Docs agent failed for this cycle; state not advanced"
        notify "❌ *Docs Agent*: failed to document $NEW_TASKS tasks. Will retry next cycle."
        sleep "$DOCS_INTERVAL"
        continue
    fi

    echo "$CLAUDE_OUTPUT" >> "$DOCS_LOG"

    SUMMARY=$(echo "$CLAUDE_OUTPUT" | grep -v '^$' | tail -1)
    log "Docs result: $SUMMARY"

    # Update state only after a successful docs run.
    jq --argjson count "$COMPLETED_COUNT" '.last_documented_count = $count' "$DOCS_STATE" > "${DOCS_STATE}.tmp" && mv "${DOCS_STATE}.tmp" "$DOCS_STATE"

    notify "📝 *Docs Agent*: documented $NEW_TASKS new tasks"

    sleep "$DOCS_INTERVAL"
done
