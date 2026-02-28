#!/usr/bin/env bash
# rollback-agent.sh — Seabone Rollback/Hotfix Agent
# Monitors for broken deployments, auto-reverts or creates hotfixes.
# Triggered by CI monitor or run on-demand.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
SEABONE_DIR="$PROJECT_DIR/.seabone"
LOG_DIR="$SEABONE_DIR/logs"
ROLLBACK_LOG="$LOG_DIR/rollback.log"
MEMORY_FILE="$SEABONE_DIR/MEMORY.md"
MEMORY_DIR="$SEABONE_DIR/memory"
export PATH="$HOME/.local/bin:$PATH"

if [[ -f "$PROJECT_DIR/.env.agent-swarm" ]]; then
    set -a; source "$PROJECT_DIR/.env.agent-swarm"; set +a
fi

mkdir -p "$LOG_DIR" "$MEMORY_DIR"

log() { local msg="[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; echo "$msg"; echo "$msg" >> "$ROLLBACK_LOG"; }
notify() { "$SCRIPT_DIR/notify-telegram.sh" "$1" 2>/dev/null || true; }

# Can be called with: rollback-agent.sh <mode> [commit-sha]
# Modes: auto (assess and decide), revert <sha>, hotfix <description>
MODE="${1:-auto}"
TARGET="${2:-}"

TODAY=$(date +%Y-%m-%d)
DAILY_FILE="$MEMORY_DIR/${TODAY}.md"

log "=========================================="
log "Seabone Rollback Agent: mode=$MODE"
log "=========================================="

cd "$PROJECT_DIR"
git checkout main 2>/dev/null && git pull origin main 2>/dev/null || true

MEMORY=""
[[ -f "$MEMORY_FILE" ]] && MEMORY=$(cat "$MEMORY_FILE")

RECENT_COMMITS=$(git log --oneline -10 2>/dev/null || echo "")
RECENT_MERGES=$(git log --merges --oneline -5 2>/dev/null || echo "")
CI_STATUS=$(gh run list --limit 5 --json databaseId,status,conclusion,headBranch --jq '.[] | "\(.databaseId) \(.conclusion) \(.headBranch)"' 2>/dev/null || echo "unknown")

case "$MODE" in
    auto)
        PROMPT="You are the Seabone Rollback Agent for $PROJECT_NAME.

## Memory
${MEMORY}

## Recent Commits
${RECENT_COMMITS}

## Recent Merges
${RECENT_MERGES}

## CI Status (last 5 runs)
${CI_STATUS}

## Your Job
Assess whether a rollback is needed:

1. Check CI status — if main is RED, identify the breaking commit
2. Check the last few merges — did any introduce obvious breakage?
3. If rollback IS needed:
   - Create a safety tag: git tag pre-revert-\$(date +%Y%m%d-%H%M%S) HEAD
   - Create a revert branch: git checkout -b revert/\$(date +%Y%m%d-%H%M%S)
   - Revert the bad commit: git revert <bad-commit-sha> --no-edit
   - Push the revert branch: git push -u origin HEAD
   - Create a PR: gh pr create --title \"revert: rollback <bad-commit>\" --body \"Automated revert by Seabone Rollback Agent. Safety tag: pre-revert-...\"
   - Return to main: git checkout main
   - Notify via ${SCRIPT_DIR}/notify-telegram.sh (include PR URL)
4. If no rollback needed, just report status
5. DO NOT push directly to main. Always create a PR for reverts.

Write summary to ${DAILY_FILE}.
End with one-line summary."
        ;;

    revert)
        if [[ -z "$TARGET" ]]; then
            echo "Usage: rollback-agent.sh revert <commit-sha>"
            exit 1
        fi
        PROMPT="You are the Seabone Rollback Agent. Revert commit ${TARGET} on main.

## SAFETY PROTOCOL — follow these steps exactly:
1. Verify the commit exists and is on main: git log --oneline main | grep ${TARGET}
2. If the commit is NOT found on main, STOP and report the error. Do NOT revert anything.
3. Create a safety tag: git tag pre-revert-\$(date +%Y%m%d-%H%M%S) HEAD
4. Create a revert branch: git checkout -b revert/${TARGET}
5. Revert: git revert ${TARGET} --no-edit
6. Push: git push -u origin HEAD
7. Create PR: gh pr create --title \"revert: rollback ${TARGET}\" --body \"Automated revert by Seabone Rollback Agent\"
8. Return to main: git checkout main
9. Notify: ${SCRIPT_DIR}/notify-telegram.sh \"Revert PR created for ${TARGET}\"
10. Write to ${DAILY_FILE}

DO NOT push directly to main. Always use a PR.
End with one-line summary."
        ;;

    hotfix)
        PROMPT="You are the Seabone Rollback Agent creating a HOTFIX.

## Memory
${MEMORY}

## Description
${TARGET:-Fix the latest CI failure on main}

## Recent Commits
${RECENT_COMMITS}

## SAFETY PROTOCOL — DO NOT modify main directly
1. Read the failing CI logs: gh run list --limit 1 --json databaseId -q '.[0].databaseId' then gh run view <id> --log-failed
2. Identify the root cause
3. Create a hotfix branch: git checkout -b hotfix/\$(date +%Y%m%d-%H%M%S)
4. Create the minimal fix
5. Commit with message: \"hotfix: <description>\"
6. Push: git push -u origin HEAD
7. Create PR with --label urgent: gh pr create --title \"hotfix: <description>\" --body \"Emergency hotfix by Seabone. CI failure root cause: <summary>\"
8. Notify: ${SCRIPT_DIR}/notify-telegram.sh \"Hotfix PR created\"
9. Return to main: git checkout main
10. Write to ${DAILY_FILE}

DO NOT push directly to main. Create a PR so the coordinator can review and merge.
End with one-line summary."
        ;;
esac

log "Running Claude rollback agent (mode=$MODE)..."
CLAUDE_OUTPUT=$(claude \
    -p "$PROMPT" \
    --dangerously-skip-permissions \
    --output-format text \
    --model sonnet \
    --max-turns 30 \
    2>&1) || true

echo "$CLAUDE_OUTPUT" >> "$ROLLBACK_LOG"

SUMMARY=$(echo "$CLAUDE_OUTPUT" | grep -v '^$' | tail -1)
log "Rollback result: $SUMMARY"
