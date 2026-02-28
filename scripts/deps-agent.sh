#!/usr/bin/env bash
# deps-agent.sh — Seabone Dependency Update Agent
# Checks for outdated packages, security advisories, spawns update PRs.
# Runs daily or on-demand.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
SEABONE_DIR="$PROJECT_DIR/.seabone"
CONFIG_FILE="$SEABONE_DIR/config.json"
LOG_DIR="$SEABONE_DIR/logs"
DEPS_LOG="$LOG_DIR/deps-agent.log"
MEMORY_DIR="$SEABONE_DIR/memory"
MEMORY_FILE="$SEABONE_DIR/MEMORY.md"
FINDINGS_DIR="$SEABONE_DIR/findings"
LOCKFILE="/tmp/seabone-deps-${PROJECT_NAME}.lock"
export PATH="$HOME/.local/bin:$PATH"

if [[ -f "$PROJECT_DIR/.env.agent-swarm" ]]; then
    set -a; source "$PROJECT_DIR/.env.agent-swarm"; set +a
fi

mkdir -p "$LOG_DIR" "$MEMORY_DIR" "$FINDINGS_DIR"

exec 5>"$LOCKFILE"
if ! flock -n 5; then echo "Another deps agent running."; exit 0; fi

log() { local msg="[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; echo "$msg"; echo "$msg" >> "$DEPS_LOG"; }
notify() { "$SCRIPT_DIR/notify-telegram.sh" "$1" 2>/dev/null || true; }

# Run daily (86400s) by default
DEPS_INTERVAL="${SEABONE_DEPS_INTERVAL:-86400}"

log "=========================================="
log "Seabone Dependency Agent started"
log "Project: $PROJECT_NAME"
log "=========================================="

notify "📦 *Seabone Deps Agent* started on \`$PROJECT_NAME\`"

TODAY=$(date +%Y-%m-%d)
DAILY_FILE="$MEMORY_DIR/${TODAY}.md"

while true; do
    NEW_TODAY=$(date +%Y-%m-%d)
    if [[ "$NEW_TODAY" != "$TODAY" ]]; then TODAY="$NEW_TODAY"; DAILY_FILE="$MEMORY_DIR/${TODAY}.md"; fi

    cd "$PROJECT_DIR"

    # Use a dedicated read-only worktree to avoid racing other agents on git checkout
    DEPS_WORKTREE="$PROJECT_DIR/.worktrees/_deps-read"
    git fetch origin main --quiet 2>/dev/null || true
    if [[ ! -d "$DEPS_WORKTREE" ]]; then
        git worktree add "$DEPS_WORKTREE" origin/main --detach --quiet 2>/dev/null || true
    fi
    if [[ -d "$DEPS_WORKTREE" ]]; then
        cd "$DEPS_WORKTREE"
        git checkout --detach origin/main --quiet 2>/dev/null || true
    fi

    MEMORY=""
    [[ -f "$MEMORY_FILE" ]] && MEMORY=$(cat "$MEMORY_FILE")

    FINDING_FILE="$FINDINGS_DIR/${TODAY}-deps-audit.json"

    # Gather dependency info
    PIP_OUTDATED=""
    if command -v pip &>/dev/null; then
        PIP_OUTDATED=$(pip list --outdated --format=json 2>/dev/null || echo "[]")
    fi

    PIP_AUDIT=""
    if command -v pip-audit &>/dev/null; then
        PIP_AUDIT=$(pip-audit --format=json 2>/dev/null || echo "[]")
    fi

    REQUIREMENTS=""
    [[ -f "$PROJECT_DIR/requirements.txt" ]] && REQUIREMENTS=$(cat "$PROJECT_DIR/requirements.txt")
    [[ -f "$PROJECT_DIR/pyproject.toml" ]] && REQUIREMENTS=$(cat "$PROJECT_DIR/pyproject.toml")

    PROMPT="You are the Seabone Dependency Agent for $PROJECT_NAME.

## Memory
${MEMORY}

## Your Job
Analyse the project's dependencies for security vulnerabilities, outdated packages, and compatibility issues.

## Current Dependency Data

### pip list --outdated
${PIP_OUTDATED:-Not available}

### pip-audit results
${PIP_AUDIT:-Not available (pip-audit not installed)}

### Requirements/pyproject.toml
${REQUIREMENTS:-Not found}

## Instructions

### 1. Analyse Dependencies
- Check requirements file for pinned vs unpinned versions
- Identify packages with known CVEs from pip-audit
- Flag major version updates that may have breaking changes
- Check for unused dependencies (imported but not used in code)

### 2. Write Findings
Write findings to: ${FINDING_FILE}

Each finding:
{
  \"id\": \"deps-<number>\",
  \"severity\": \"critical|high|medium|low\",
  \"category\": \"deps\",
  \"file\": \"requirements.txt or pyproject.toml\",
  \"line\": null,
  \"issue\": \"<description>\",
  \"task\": \"<fix instruction>\",
  \"auto_fixable\": true|false,
  \"effort\": \"trivial|small|medium|large\",
  \"package\": \"<package name>\",
  \"current_version\": \"<current>\",
  \"latest_version\": \"<latest>\"
}

Severity rules:
- critical: Known CVE with exploit available
- high: Known CVE or major security update
- medium: Outdated by 2+ major versions
- low: Minor/patch update available

### 3. Summary
Write a summary to ${DAILY_FILE}:
\"- HH:MM Deps audit: <n> outdated, <n> CVEs, <n> updates recommended\"

### 4. End with one-line summary."

    log "Running Claude deps analysis..."
    CLAUDE_OUTPUT=$(claude \
        -p "$PROMPT" \
        --dangerously-skip-permissions \
        --output-format text \
        --model sonnet \
        --max-turns 25 \
        2>&1) || true

    echo "$CLAUDE_OUTPUT" >> "$DEPS_LOG"

    SUMMARY=$(echo "$CLAUDE_OUTPUT" | grep -v '^$' | tail -1)
    log "Deps result: $SUMMARY"

    if [[ -f "$FINDING_FILE" ]]; then
        TOTAL=$(jq 'length' "$FINDING_FILE" 2>/dev/null || echo 0)
        CRITICAL=$(jq '[.[] | select(.severity == "critical")] | length' "$FINDING_FILE" 2>/dev/null || echo 0)
        notify "📦 *Deps Audit*: $TOTAL findings ($CRITICAL critical)"
    fi

    log "Next deps scan in ${DEPS_INTERVAL}s..."
    sleep "$DEPS_INTERVAL"
done
