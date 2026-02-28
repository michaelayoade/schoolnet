#!/usr/bin/env bash
# seabone — Main CLI for the Seabone agent swarm
# Usage: seabone <command> [args]
set -euo pipefail

REAL_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$REAL_PATH")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_NAME="$(basename "$PROJECT_DIR")"

# Session names for all agents
ORCH_SESSION="seabone-orchestrator-${PROJECT_NAME}"
COORD_SESSION="seabone-coordinator-${PROJECT_NAME}"
SENTINEL_SESSION="seabone-sentinel-${PROJECT_NAME}"
PM_SESSION="seabone-pm-${PROJECT_NAME}"
CI_SESSION="seabone-ci-${PROJECT_NAME}"
CONFLICT_SESSION="seabone-conflict-${PROJECT_NAME}"
DOCS_SESSION="seabone-docs-${PROJECT_NAME}"
DEPS_SESSION="seabone-deps-${PROJECT_NAME}"
METRICS_SESSION="seabone-metrics-${PROJECT_NAME}"

usage() {
    cat <<EOF
Seabone Agent Swarm CLI

Usage: seabone <command> [args]

Orchestration:
  up                            Start ALL agents (orchestrator manages everything)
  down                          Stop ALL agents gracefully
  status                        Show full system status
  health                        Quick health check

Agent Control:
  spawn <id> <desc> [--engine]  Spawn a single coding agent
  batch <file>                  Spawn agents from a tasks file

Analysis:
  analyse [type]                One-shot analysis (full|security|quality|api|deps)
  findings                      Show latest findings
  report                        Show latest improvement report

Monitoring:
  logs [agent]                  Tail logs (coordinator|sentinel|pm|ci|docs|deps|metrics|orch)
  agent-logs <task-id>          Tail a specific coding agent's log
  prs                           List open PRs
  memory                        Show today's activity + persistent memory
  metrics                       Show latest metrics snapshot

Individual Agent Control:
  start <agent>                 Start a specific agent
  stop <agent>                  Stop a specific agent
  attach                        Attach to the coordinator tmux session

Agents: coordinator, sentinel, pm, ci-monitor, conflict-detector, docs-agent, deps-agent, metrics, orchestrator

Engines:
  codex (default)      General-purpose coding (gpt-5.3-codex)
  claude               Complex reasoning tasks (sonnet)
  claude-frontend      UI/UX design specialist (sonnet)
  codex-test           Testing specialist — writes & runs tests (gpt-5.3-codex)
  codex-senior         Senior dev escalation — fixes what others can't (gpt-5.3-codex)
  aider                Budget tasks with self-review (deepseek-chat)
EOF
    exit 1
}

# Helper: get session name for agent
get_session() {
    case "$1" in
        orchestrator|orch)      echo "$ORCH_SESSION" ;;
        coordinator|coord)      echo "$COORD_SESSION" ;;
        sentinel)               echo "$SENTINEL_SESSION" ;;
        pm)                     echo "$PM_SESSION" ;;
        ci-monitor|ci)          echo "$CI_SESSION" ;;
        conflict-detector|conflict) echo "$CONFLICT_SESSION" ;;
        docs-agent|docs)        echo "$DOCS_SESSION" ;;
        deps-agent|deps)        echo "$DEPS_SESSION" ;;
        metrics)                echo "$METRICS_SESSION" ;;
        *) echo "" ;;
    esac
}

# Helper: get script for agent
get_script() {
    case "$1" in
        orchestrator|orch)      echo "orchestrator.sh" ;;
        coordinator|coord)      echo "coordinator.sh" ;;
        sentinel)               echo "sentinel.sh" ;;
        pm)                     echo "pm-agent.sh" ;;
        ci-monitor|ci)          echo "ci-monitor.sh" ;;
        conflict-detector|conflict) echo "conflict-detector.sh" ;;
        docs-agent|docs)        echo "docs-agent.sh" ;;
        deps-agent|deps)        echo "deps-agent.sh" ;;
        metrics)                echo "metrics-agent.sh" ;;
        *) echo "" ;;
    esac
}

# Helper: get log file for agent
get_log() {
    case "$1" in
        orchestrator|orch)      echo "orchestrator.log" ;;
        coordinator|coord)      echo "coordinator.log" ;;
        sentinel)               echo "sentinel.log" ;;
        pm)                     echo "pm.log" ;;
        ci-monitor|ci)          echo "ci-monitor.log" ;;
        conflict-detector|conflict) echo "conflict-detector.log" ;;
        docs-agent|docs)        echo "docs-agent.log" ;;
        deps-agent|deps)        echo "deps-agent.log" ;;
        metrics)                echo "metrics.log" ;;
        *) echo "coordinator.log" ;;
    esac
}

CMD="${1:-}"
shift || true

case "$CMD" in

    # ============================================
    #  ORCHESTRATION
    # ============================================
    up)
        SESSION="$ORCH_SESSION"
        if tmux has-session -t "$SESSION" 2>/dev/null; then
            echo "Orchestrator already running. It manages all agents."
            echo "  Status: seabone status"
            echo "  Logs:   seabone logs orch"
            exit 0
        fi
        echo "Starting Seabone Orchestrator (manages all agents)..."
        tmux new-session -d -s "$SESSION" "bash $SCRIPT_DIR/orchestrator.sh"
        echo "Orchestrator started. It will launch all required agents."
        echo ""
        echo "  Status:  seabone status"
        echo "  Health:  seabone health"
        echo "  Logs:    seabone logs orch"
        echo "  Stop:    seabone down"
        ;;

    down)
        echo "Stopping all Seabone agents..."
        ALL_AGENTS="orchestrator coordinator sentinel pm ci-monitor conflict-detector docs-agent deps-agent metrics"
        for agent in $ALL_AGENTS; do
            session=$(get_session "$agent")
            if tmux has-session -t "$session" 2>/dev/null; then
                tmux kill-session -t "$session" 2>/dev/null || true
                echo "  Stopped: $agent"
            fi
        done
        echo "All agents stopped."
        ;;

    health)
        echo "=== Seabone Health Check ==="
        ALL_AGENTS="orchestrator coordinator sentinel pm ci-monitor conflict-detector docs-agent deps-agent metrics"
        HEALTHY=0
        TOTAL=0
        for agent in $ALL_AGENTS; do
            TOTAL=$((TOTAL + 1))
            session=$(get_session "$agent")
            if tmux has-session -t "$session" 2>/dev/null; then
                printf "  %-20s UP\n" "$agent"
                HEALTHY=$((HEALTHY + 1))
            else
                printf "  %-20s DOWN\n" "$agent"
            fi
        done
        echo ""
        echo "$HEALTHY/$TOTAL agents running"
        ;;

    status)
        echo "=== Seabone Status ==="
        echo ""

        # System agents
        echo "=== System Agents ==="
        ALL_AGENTS="orchestrator coordinator sentinel pm ci-monitor conflict-detector docs-agent deps-agent metrics"
        for agent in $ALL_AGENTS; do
            session=$(get_session "$agent")
            if tmux has-session -t "$session" 2>/dev/null; then
                printf "  %-20s RUNNING\n" "$agent"
            else
                printf "  %-20s STOPPED\n" "$agent"
            fi
        done
        echo ""

        # Active coding agents
        sa_active="$PROJECT_DIR/.seabone/active-tasks.json"
        sa_queue="$PROJECT_DIR/.seabone/queue.json"
        sa_completed="$PROJECT_DIR/.seabone/completed-tasks.json"

        echo "=== Coding Agents ==="
        if [[ -f "$sa_active" ]]; then
            active_count=$(jq 'length' "$sa_active" 2>/dev/null || echo 0)
            if [[ "$active_count" -gt 0 ]]; then
                jq -r '.[] | "  \(.id) | \(.engine // "codex") | \(.status)"' "$sa_active" 2>/dev/null
            else
                echo "  (none active)"
            fi
        else
            echo "  (none active)"
        fi
        echo ""

        echo "=== Queue ==="
        if [[ -f "$sa_queue" ]]; then
            qlen="$(jq 'length' "$sa_queue" 2>/dev/null || echo 0)"
            echo "  $qlen tasks queued"
        else
            echo "  0 tasks queued"
        fi
        echo ""

        echo "=== Completed ==="
        if [[ -f "$sa_completed" ]]; then
            clen="$(jq 'length' "$sa_completed" 2>/dev/null || echo 0)"
            merged="$(jq '[.[] | select(.status == "merged")] | length' "$sa_completed" 2>/dev/null || echo 0)"
            echo "  $clen total ($merged merged)"
        else
            echo "  0 tasks completed"
        fi
        echo ""

        # Latest findings
        FINDINGS_DIR="$PROJECT_DIR/.seabone/findings"
        LATEST_FINDING=$(ls -t "$FINDINGS_DIR"/*.json 2>/dev/null | head -1)
        if [[ -n "${LATEST_FINDING:-}" ]]; then
            echo "=== Latest Scan ==="
            echo "  File: $(basename "$LATEST_FINDING")"
            echo "  Findings: $(jq 'length' "$LATEST_FINDING" 2>/dev/null || echo 0)"
            crit=$(jq '[.[] | select(.severity == "critical")] | length' "$LATEST_FINDING" 2>/dev/null || echo 0)
            high=$(jq '[.[] | select(.severity == "high")] | length' "$LATEST_FINDING" 2>/dev/null || echo 0)
            echo "  Critical: $crit | High: $high"
            echo ""
        fi

        # Metrics
        METRICS_DIR="$PROJECT_DIR/.seabone/metrics"
        LATEST_METRIC=$(ls -t "$METRICS_DIR"/*.json 2>/dev/null | head -1)
        if [[ -n "${LATEST_METRIC:-}" ]]; then
            echo "=== Metrics ==="
            success=$(jq -r '.agents.success_rate // "?"' "$LATEST_METRIC" 2>/dev/null || echo "?")
            echo "  Success rate: ${success}%"
            echo "  Engines: codex=$(jq '.engines.codex' "$LATEST_METRIC" 2>/dev/null) claude=$(jq '.engines.claude' "$LATEST_METRIC" 2>/dev/null) aider=$(jq '.engines.aider' "$LATEST_METRIC" 2>/dev/null)"
            echo ""
        fi
        ;;

    # ============================================
    #  INDIVIDUAL AGENT CONTROL
    # ============================================
    start)
        AGENT="${1:?Usage: seabone start <agent>}"
        session=$(get_session "$AGENT")
        script=$(get_script "$AGENT")
        if [[ -z "$session" || -z "$script" ]]; then
            echo "Unknown agent: $AGENT"
            echo "Available: orchestrator, coordinator, sentinel, pm, ci-monitor, conflict-detector, docs-agent, deps-agent, metrics"
            exit 1
        fi
        if tmux has-session -t "$session" 2>/dev/null; then
            echo "$AGENT already running."
            exit 0
        fi
        echo "Starting $AGENT..."
        tmux new-session -d -s "$session" "bash $SCRIPT_DIR/$script"
        echo "$AGENT started."
        ;;

    stop)
        AGENT="${1:?Usage: seabone stop <agent>}"
        session=$(get_session "$AGENT")
        if [[ -z "$session" ]]; then
            echo "Unknown agent: $AGENT"
            exit 1
        fi
        if tmux has-session -t "$session" 2>/dev/null; then
            tmux kill-session -t "$session"
            echo "$AGENT stopped."
        else
            echo "$AGENT not running."
        fi
        ;;

    # ============================================
    #  CODING AGENTS
    # ============================================
    spawn)
        "$SCRIPT_DIR/spawn-agent.sh" "$@"
        ;;

    batch)
        BATCH_FILE="${1:?Usage: seabone batch <tasks-file>}"
        if [[ ! -f "$BATCH_FILE" ]]; then
            echo "File not found: $BATCH_FILE"
            exit 1
        fi
        while IFS='|' read -r task_id description engine_flag; do
            task_id="$(echo "$task_id" | xargs)"
            description="$(echo "$description" | xargs)"
            engine_flag="$(echo "${engine_flag:-}" | xargs)"
            [[ -z "$task_id" || "$task_id" == \#* ]] && continue
            echo ">>> Spawning: $task_id"
            if [[ -n "$engine_flag" ]]; then
                "$SCRIPT_DIR/spawn-agent.sh" "$task_id" "$description" --engine "$engine_flag" || echo "[WARN] Failed: $task_id"
            else
                "$SCRIPT_DIR/spawn-agent.sh" "$task_id" "$description" || echo "[WARN] Failed: $task_id"
            fi
        done < "$BATCH_FILE"
        echo "Batch complete."
        ;;

    # ============================================
    #  ANALYSIS
    # ============================================
    analyse|analyze|scan)
        SCAN_TYPE="${1:-full}"
        ANALYST_SESSION="seabone-analyst-${PROJECT_NAME}"
        if tmux has-session -t "$ANALYST_SESSION" 2>/dev/null; then
            echo "Analyst already running."
            exit 0
        fi
        echo "Starting analyst ($SCAN_TYPE scan)..."
        tmux new-session -d -s "$ANALYST_SESSION" "bash $SCRIPT_DIR/analyst.sh $SCAN_TYPE"
        echo "Analyst running. Tail: seabone logs analyst"
        ;;

    findings)
        FINDINGS_DIR="$PROJECT_DIR/.seabone/findings"
        LATEST=$(ls -t "$FINDINGS_DIR"/*.json 2>/dev/null | head -1)
        if [[ -z "${LATEST:-}" ]]; then
            echo "No findings yet. Run: seabone analyse"
            exit 0
        fi
        echo "=== Latest Findings: $(basename "$LATEST") ==="
        echo ""
        jq -r '.[] | "[\(.severity | ascii_upcase)] \(.file):\(.line // "?") — \(.issue)"' "$LATEST" 2>/dev/null
        echo ""
        echo "--- Summary ---"
        echo "Total:    $(jq 'length' "$LATEST")"
        echo "Critical: $(jq '[.[] | select(.severity == "critical")] | length' "$LATEST")"
        echo "High:     $(jq '[.[] | select(.severity == "high")] | length' "$LATEST")"
        echo "Medium:   $(jq '[.[] | select(.severity == "medium")] | length' "$LATEST")"
        echo "Low:      $(jq '[.[] | select(.severity == "low")] | length' "$LATEST")"
        echo ""
        echo "Auto-fixable: $(jq '[.[] | select(.auto_fixable == true)] | length' "$LATEST")"
        ;;

    report)
        REPORTS_DIR="$PROJECT_DIR/.seabone/reports"
        LATEST=$(ls -t "$REPORTS_DIR"/*.md 2>/dev/null | head -1)
        if [[ -z "${LATEST:-}" ]]; then
            echo "No reports yet."
            exit 0
        fi
        echo "=== Latest Report: $(basename "$LATEST") ==="
        echo ""
        cat "$LATEST"
        ;;

    # ============================================
    #  MONITORING
    # ============================================
    logs)
        AGENT="${1:-coordinator}"
        logfile=$(get_log "$AGENT")
        # Also handle analyst
        if [[ "$AGENT" == "analyst" ]]; then logfile="analyst.log"; fi
        tail -f "$PROJECT_DIR/.seabone/logs/$logfile"
        ;;

    agent-logs)
        TASK_ID="${1:?Usage: seabone agent-logs <task-id>}"
        tail -f "$PROJECT_DIR/.seabone/logs/${TASK_ID}.log"
        ;;

    prs)
        cd "$PROJECT_DIR"
        gh pr list --state open
        ;;

    memory)
        echo "=== Persistent Memory ==="
        cat "$PROJECT_DIR/.seabone/MEMORY.md" 2>/dev/null || echo "(empty)"
        echo ""
        echo "=== Today's Activity ==="
        cat "$PROJECT_DIR/.seabone/memory/$(date +%Y-%m-%d).md" 2>/dev/null || echo "(none today)"
        ;;

    metrics)
        METRICS_DIR="$PROJECT_DIR/.seabone/metrics"
        LATEST=$(ls -t "$METRICS_DIR"/*.json 2>/dev/null | head -1)
        if [[ -z "${LATEST:-}" ]]; then
            echo "No metrics yet."
            exit 0
        fi
        echo "=== Latest Metrics: $(basename "$LATEST") ==="
        jq '.' "$LATEST"
        ;;

    attach)
        if tmux has-session -t "$COORD_SESSION" 2>/dev/null; then
            tmux attach -t "$COORD_SESSION"
        else
            echo "Coordinator not running. Start with: seabone up"
        fi
        ;;

    # ============================================
    #  ROLLBACK (on-demand)
    # ============================================
    rollback)
        MODE="${1:-auto}"
        shift || true
        bash "$SCRIPT_DIR/rollback-agent.sh" "$MODE" "$@"
        ;;

    *)
        usage
        ;;
esac
