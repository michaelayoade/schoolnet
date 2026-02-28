#!/usr/bin/env bash
# check-agents.sh — Monitor agent health, schedule queue, and record outcomes
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SEABONE_DIR="$PROJECT_DIR/.seabone"
ACTIVE_FILE="$SEABONE_DIR/active-tasks.json"
COMPLETED_FILE="$SEABONE_DIR/completed-tasks.json"
QUEUE_FILE="$SEABONE_DIR/queue.json"
MEMORY_FILE="$SEABONE_DIR/model-memory.json"
CONFIG_FILE="$SEABONE_DIR/config.json"
FINDINGS_DIR="$SEABONE_DIR/findings"
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

log_event() {
    local task_id="$1"
    local event="$2"
    local status="$3"
    local detail="$4"

    mkdir -p "$LOG_DIR"
    local ts
    ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf '%s\n' "$(jq -n --arg ts "$ts" --arg project "$(basename "$PROJECT_DIR")" --arg task_id "$task_id" --arg event "$event" --arg status "$status" --arg detail "$detail" '{ts:$ts,project:$project,task_id:$task_id,event:$event,status:$status,detail:$detail}')" >> "$EVENT_LOG"
}

record_model_memory() {
    local model="$1"
    local success="$2" # 1 success, 0 failure

    if [[ ! -f "$MEMORY_FILE" ]]; then
        printf '%s\n' '{"models":{}}' > "$MEMORY_FILE"
    fi

    if (( success == 1 )); then
        local expr="(.models[\"$model\"].success //= 0 | .models[\"$model\"].success += 1)"
        json_update "$MEMORY_FILE" "$expr" object
    else
        local expr="(.models[\"$model\"].failure //= 0 | .models[\"$model\"].failure += 1)"
        json_update "$MEMORY_FILE" "$expr" object
    fi
}

terminal_statuses() {
    local status="$1"

    case "$status" in
        pr_created|no_changes|completed|quality_failed|max_retries_exceeded|timeout|error|failed|killed)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

status_success() {
    local status="$1"
    case "$status" in
        pr_created|no_changes)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

archive_task() {
    local i="$1"
    local task_json status model

    task_json="$(json_read "$ACTIVE_FILE" ".[$i]")"
    status="$(json_read "$ACTIVE_FILE" ".[$i].status // \"unknown\"")"
    model="$(json_read "$ACTIVE_FILE" ".[$i].model // \"deepseek-chat\"")"

    task_json=$(echo "$task_json" | jq ". + {\"completed_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}")
    json_append "$COMPLETED_FILE" "$task_json"
    json_update "$ACTIVE_FILE" "del(.[$i])"

    if status_success "$status"; then
        record_model_memory "$model" 1
    else
        record_model_memory "$model" 0
    fi

    log_event "$(echo "$task_json" | jq -r '.id // "unknown"')" "task-archive" "$status" "moved-to-completed"
}

respawn_task() {
    local task_id description engine model
    local new_retries

    task_id="$1"
    description="$2"
    engine="$3"
    model="$4"
    new_retries="$5"

    local spawn_cmd
    spawn_cmd=("$SCRIPT_DIR/spawn-agent.sh" "$task_id" "$description" --force --retries "$new_retries")
    if [[ -n "$engine" ]]; then
        spawn_cmd+=(--engine "$engine")
    fi
    if [[ -n "$model" ]]; then
        spawn_cmd+=(--model "$model")
    fi

    log_event "$task_id" "respawn" "retry-$new_retries" "engine=${engine:-default},model=${model:-default}"
    if "${spawn_cmd[@]}" >/dev/null 2>&1; then
        return 0
    fi

    if ! json_read "$ACTIVE_FILE" ".[] | select(.id == \"$task_id\")" 2>/dev/null | grep -q .; then
        log_event "$task_id" "respawn" "failed" "spawn-command-failed-task-not-active"
    else
        log_event "$task_id" "respawn" "failed" "spawn-command-failed"
    fi
    return 1
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

lookup_finding_meta() {
    local task_id="$1"
    local finding_id files
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
        | {
            effort: (.effort // ""),
            severity: (.severity // ""),
            category: (.category // ""),
            auto_fixable: (.auto_fixable // false),
            file: (.file // "")
          }
    ' "${files[@]}" 2>/dev/null | head -n1
}

task_bundle_key() {
    local task_id="$1"
    local engine="$2"
    local finding_meta="$3"
    local category=""

    if [[ -n "$finding_meta" ]]; then
        category="$(echo "$finding_meta" | jq -r '.category // ""' | tr '[:upper:]' '[:lower:]')"
    fi

    if [[ -z "$category" ]]; then
        case "$task_id" in
            fix-deps-*|deps-*) category="deps" ;;
            fix-quality-*|quality-*) category="quality" ;;
            fix-api-*|api-*) category="api" ;;
            fix-lint-*|lint-*|format-*|cleanup-*) category="maintenance" ;;
            *) category="" ;;
        esac
    fi

    [[ -n "$category" ]] || return 1
    printf '%s:%s' "$engine" "$category"
}

task_conflict_scope() {
    local task_id="$1"
    local description="$2"
    local engine="$3"
    local finding_meta="${4:-}"
    local file category text

    if [[ -z "$finding_meta" ]]; then
        finding_meta="$(lookup_finding_meta "$task_id" || true)"
    fi

    if [[ -n "$finding_meta" ]]; then
        file="$(echo "$finding_meta" | jq -r '.file // ""' | tr '[:upper:]' '[:lower:]')"
        category="$(echo "$finding_meta" | jq -r '.category // ""' | tr '[:upper:]' '[:lower:]')"

        if [[ -n "$file" && "$file" != "null" ]]; then
            case "$file" in
                .agent-run.sh|*/.agent-run.sh) ;;
                *) printf 'file:%s' "$file"; return 0 ;;
            esac
        fi

        if [[ -n "$category" && "$category" != "null" ]]; then
            printf 'cat:%s:%s' "$engine" "$category"
            return 0
        fi
    fi

    text="${task_id} ${description}"
    if printf '%s' "$text" | grep -Eiq '(pyproject\.toml|poetry\.lock|requirements(\.txt)?|package\.json|package-lock\.json|uv\.lock|pdm\.lock)'; then
        printf '%s' "file:dependency-manifests"
        return 0
    fi

    case "$task_id" in
        fix-deps-*|deps-*|batch-*deps*) printf '%s' "file:dependency-manifests"; return 0 ;;
        fix-api-*|api-*) printf 'cat:%s:api' "$engine"; return 0 ;;
        fix-quality-*|quality-*) printf 'cat:%s:quality' "$engine"; return 0 ;;
    esac

    return 1
}

build_active_conflict_scopes() {
    local active_entries entry item task_id task_desc task_engine scope
    local scopes=""

    active_entries="$(json_read "$ACTIVE_FILE" '[.[] | select(.status == "running" or .status == "stale")] | .[] | @base64' 2>/dev/null || true)"
    [[ -n "$active_entries" ]] || { printf '%s' ""; return 0; }

    while IFS= read -r entry; do
        [[ -z "$entry" ]] && continue
        item="$(printf '%s' "$entry" | base64 -d 2>/dev/null || true)"
        [[ -n "$item" ]] || continue
        task_id="$(echo "$item" | jq -r '.id // empty')"
        task_desc="$(echo "$item" | jq -r '.description // empty')"
        task_engine="$(echo "$item" | jq -r '.engine // empty')"
        scope="$(task_conflict_scope "$task_id" "$task_desc" "$task_engine" "$(lookup_finding_meta "$task_id" || true)" 2>/dev/null || true)"
        [[ -n "$scope" ]] || continue
        scopes="${scopes}
${scope}"
    done <<< "$active_entries"

    printf '%s\n' "$scopes" | sed '/^$/d' | sort -u
}

scope_is_blocked() {
    local scope="$1"
    local scopes_blob="$2"
    [[ -n "$scope" ]] || return 1
    [[ -n "$scopes_blob" ]] || return 1
    printf '%s\n' "$scopes_blob" | grep -Fxq "$scope"
}

is_aggregate_candidate() {
    local task_id="$1"
    local description="$2"
    local engine="$3"
    local priority="$4"
    local finding_meta="$5"
    local effort severity category auto_fixable desc_len

    case "$engine" in
        codex|aider) ;;
        *) return 1 ;;
    esac

    [[ "$priority" =~ ^[0-9]+$ ]] || return 1
    (( priority >= 5 )) || return 1

    case "$task_id" in
        batch-*|frontend-audit-*|security-tests-*|test-*) return 1 ;;
    esac

    desc_len="${#description}"

    if [[ -n "$finding_meta" ]]; then
        effort="$(echo "$finding_meta" | jq -r '.effort // ""' | tr '[:upper:]' '[:lower:]')"
        severity="$(echo "$finding_meta" | jq -r '.severity // ""' | tr '[:upper:]' '[:lower:]')"
        category="$(echo "$finding_meta" | jq -r '.category // ""' | tr '[:upper:]' '[:lower:]')"
        auto_fixable="$(echo "$finding_meta" | jq -r '.auto_fixable // false')"

        [[ "$auto_fixable" == "true" ]] || return 1
        [[ "$effort" == "trivial" ]] || return 1
        case "$severity" in
            critical|high) return 1 ;;
        esac
        case "$category" in
            security) return 1 ;;
        esac
        return 0
    fi

    if (( desc_len > 380 )); then
        return 1
    fi

    if printf '%s %s' "$task_id" "$description" | grep -Eiq '(single-file|trivial|minor|version bump|lint|format|cleanup|dependency bump|low severity)'; then
        return 0
    fi

    case "$task_id" in
        fix-deps-*|deps-*|fix-lint-*|lint-*|format-*|cleanup-*) return 0 ;;
    esac

    return 1
}

aggregate_queue_candidates() {
    local enabled min_tasks max_tasks max_desc_chars aggregated
    enabled="${SEABONE_QUEUE_AGGREGATION_ENABLED:-true}"
    [[ "$enabled" == "true" ]] || return 0
    min_tasks="${SEABONE_QUEUE_AGGREGATION_MIN_TASKS:-2}"
    max_tasks="${SEABONE_QUEUE_AGGREGATION_MAX_TASKS:-4}"
    max_desc_chars="${SEABONE_QUEUE_AGGREGATION_DESC_MAX_CHARS:-1800}"
    aggregated=0

    if ! [[ "$min_tasks" =~ ^[0-9]+$ ]]; then min_tasks=2; fi
    if ! [[ "$max_tasks" =~ ^[0-9]+$ ]]; then max_tasks=4; fi
    if ! [[ "$max_desc_chars" =~ ^[0-9]+$ ]]; then max_desc_chars=1800; fi
    (( max_tasks >= min_tasks )) || max_tasks="$min_tasks"

    local candidates
    candidates="$(json_read "$QUEUE_FILE" 'sort_by(.priority, .queued_at) | .[] | @base64' 2>/dev/null || true)"
    [[ -n "$candidates" ]] || return 0

    declare -A group_ids
    declare -A group_count
    declare -A group_engine
    declare -A group_model
    declare -A group_priority
    declare -A group_desc

    local line item task_id task_desc task_engine task_model task_priority meta key count
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        item="$(printf '%s' "$line" | base64 -d 2>/dev/null || true)"
        [[ -n "$item" ]] || continue

        task_id="$(echo "$item" | jq -r '.id // empty')"
        task_desc="$(echo "$item" | jq -r '.description // empty')"
        task_engine="$(echo "$item" | jq -r '.engine // empty')"
        task_model="$(echo "$item" | jq -r '.model // empty')"
        task_priority="$(echo "$item" | jq -r '.priority // 5')"
        [[ -n "$task_id" ]] || continue

        meta="$(lookup_finding_meta "$task_id" || true)"
        if ! is_aggregate_candidate "$task_id" "$task_desc" "$task_engine" "$task_priority" "$meta"; then
            continue
        fi

        key="$(task_bundle_key "$task_id" "$task_engine" "$meta" 2>/dev/null || true)"
        [[ -n "$key" ]] || continue

        count="${group_count[$key]:-0}"
        if (( count >= max_tasks )); then
            continue
        fi

        group_count[$key]=$((count + 1))
        group_ids[$key]="${group_ids[$key]:-} $task_id"
        group_engine[$key]="${group_engine[$key]:-$task_engine}"
        group_model[$key]="${group_model[$key]:-$task_model}"
        if [[ -z "${group_priority[$key]:-}" || "$task_priority" -lt "${group_priority[$key]:-99}" ]]; then
            group_priority[$key]="$task_priority"
        fi

        local snippet
        snippet="$task_desc"
        if (( ${#snippet} > 220 )); then
            snippet="${snippet:0:220}..."
        fi
        group_desc[$key]="${group_desc[$key]:-}
- ${task_id}: ${snippet}"
    done <<< "$candidates"

    local bundle created_now
    created_now=0
    for bundle in "${!group_count[@]}"; do
        local count ids_raw ids_clean engine model prio safe_key ts batch_id header combined_desc
        count="${group_count[$bundle]}"
        if (( count < min_tasks )); then
            continue
        fi

        ids_raw="${group_ids[$bundle]}"
        ids_clean="$(printf '%s\n' "$ids_raw" | xargs -n1 | sed '/^$/d' | sort -u)"
        engine="${group_engine[$bundle]}"
        model="${group_model[$bundle]}"
        prio="${group_priority[$bundle]:-5}"

        safe_key="$(printf '%s' "$bundle" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')"
        ts="$(date -u +%Y%m%d%H%M%S)"
        batch_id="batch-${safe_key}-${ts}"

        header="Batched queue task (${count} small related tasks) to reduce token usage and round-trips."
        combined_desc="${header}

Complete ALL items below in one branch/PR. Keep each fix isolated and include a short per-item verification note in the PR summary.
${group_desc[$bundle]}"

        if (( ${#combined_desc} > max_desc_chars )); then
            combined_desc="${combined_desc:0:max_desc_chars}

[description truncated to control token usage]"
        fi

        while IFS= read -r id; do
            [[ -z "$id" ]] && continue
            json_update "$QUEUE_FILE" "map(select(.id != \"$id\"))"
        done <<< "$ids_clean"

        local queue_json
        queue_json="$(jq -n \
            --arg id "$batch_id" \
            --arg desc "$combined_desc" \
            --arg engine "$engine" \
            --arg model "$model" \
            --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
            --argjson priority "$prio" \
            --argjson batched_from "$(printf '%s\n' "$ids_clean" | jq -Rsc 'split("\n") | map(select(length > 0))')" \
            '{id:$id, description:$desc, engine:$engine, model:$model, priority:$priority, queued_at:$ts, status:"queued", batched_from:$batched_from}')"
        json_append "$QUEUE_FILE" "$queue_json"

        log_event "$batch_id" "queue-aggregate" "queued" "group=$bundle count=$count"
        created_now=$((created_now + 1))
    done

    if (( created_now > 0 )); then
        aggregated=$((aggregated + created_now))
        echo "  Aggregated ${created_now} queue batch task(s) from tiny items."
        # Re-normalize order after batch creation.
        json_update "$QUEUE_FILE" "sort_by(.priority, .queued_at)"
    fi

    return 0
}

reconcile_queue_policy() {
    local queue_ids
    local reconciled
    reconciled=0
    queue_ids="$(json_read "$QUEUE_FILE" '.[] | .id // empty' 2>/dev/null || true)"
    [[ -n "$queue_ids" ]] || return 0

    while IFS= read -r task_id; do
        [[ -z "$task_id" ]] && continue

        local task_desc task_engine task_model
        task_desc="$(json_read "$QUEUE_FILE" ".[] | select(.id == \"$task_id\") | .description // empty" 2>/dev/null | head -n1)"
        task_engine="$(json_read "$QUEUE_FILE" ".[] | select(.id == \"$task_id\") | .engine // empty" 2>/dev/null | head -n1)"
        task_model="$(json_read "$QUEUE_FILE" ".[] | select(.id == \"$task_id\") | .model // empty" 2>/dev/null | head -n1)"

        local resolve_cmd resolved resolved_json resolved_engine resolved_model changed
        resolve_cmd=("$SCRIPT_DIR/spawn-agent.sh" "$task_id" "$task_desc" --resolve-only)
        if [[ -n "$task_engine" && "$task_engine" != "null" ]]; then
            resolve_cmd+=(--engine "$task_engine")
        fi
        if [[ -n "$task_model" && "$task_model" != "null" ]]; then
            resolve_cmd+=(--model "$task_model")
        fi

        resolved="$("${resolve_cmd[@]}" 2>/dev/null || true)"
        [[ -n "$resolved" ]] || continue

        resolved_json="$(printf '%s\n' "$resolved" | sed -n '/^{/,$p')"
        [[ -n "$resolved_json" ]] || continue

        resolved_engine="$(echo "$resolved_json" | jq -r '.engine // empty' 2>/dev/null || echo "")"
        resolved_model="$(echo "$resolved_json" | jq -r '.model // empty' 2>/dev/null || echo "")"
        if [[ -z "$resolved_engine" && -z "$resolved_model" ]]; then
            continue
        fi
        changed=0

        if [[ -n "$resolved_engine" && "$resolved_engine" != "$task_engine" ]]; then
            json_update "$QUEUE_FILE" "(.[] | select(.id == \"$task_id\") | .engine) = \"$resolved_engine\""
            changed=1
        fi
        if [[ -n "$resolved_model" && "$resolved_model" != "$task_model" ]]; then
            json_update "$QUEUE_FILE" "(.[] | select(.id == \"$task_id\") | .model) = \"$resolved_model\""
            changed=1
        fi

        if (( changed == 1 )); then
            reconciled=$((reconciled + 1))
            log_event "$task_id" "queue-reconcile" "updated" "engine=${task_engine:-default}->${resolved_engine:-default},model=${task_model:-default}->${resolved_model:-default}"
        fi
    done <<< "$queue_ids"

    if (( reconciled > 0 )); then
        echo "  Reconciled queue policy for ${reconciled} queued task(s)."
    fi
}

dispatch_queue() {
    local running_count max_agents
    local queue_size active_scopes blocked_count

    running_count="$(json_read "$ACTIVE_FILE" '[.[] | select(.status == "running" or .status == "stale")] | length' 2>/dev/null || echo 0)"
    max_agents="$(jq -r '.max_concurrent_agents // 3' "$CONFIG_FILE")"
    active_scopes="$(build_active_conflict_scopes)"

    while (( running_count < max_agents )); do
        queue_size="$(json_read "$QUEUE_FILE" 'length' 2>/dev/null || echo 0)"
        if [[ "$queue_size" -eq 0 ]]; then
            break
        fi

        local queue_entries selected_item selected_id selected_desc selected_engine selected_model selected_scope
        queue_entries="$(json_read "$QUEUE_FILE" 'sort_by(.priority, .queued_at) | .[] | @base64' 2>/dev/null || true)"
        [[ -n "$queue_entries" ]] || break

        selected_item=""
        selected_scope=""
        blocked_count=0

        local line item top_id top_desc top_engine top_model scope
        while IFS= read -r line; do
            [[ -z "$line" ]] && continue
            item="$(printf '%s' "$line" | base64 -d 2>/dev/null || true)"
            [[ -n "$item" ]] || continue

            top_id="$(echo "$item" | jq -r '.id // empty')"
            top_desc="$(echo "$item" | jq -r '.description // empty')"
            top_engine="$(echo "$item" | jq -r '.engine // empty')"
            top_model="$(echo "$item" | jq -r '.model // empty')"

            if [[ -z "$top_id" || "$top_id" == "null" ]]; then
                json_update "$QUEUE_FILE" "map(select(.id != null))"
                continue
            fi

            if json_read "$ACTIVE_FILE" ".[] | select(.id == \"$top_id\")" 2>/dev/null | grep -q .; then
                json_update "$QUEUE_FILE" "map(select(.id != \"$top_id\"))"
                continue
            fi

            scope="$(task_conflict_scope "$top_id" "$top_desc" "$top_engine" "$(lookup_finding_meta "$top_id" || true)" 2>/dev/null || true)"
            if scope_is_blocked "$scope" "$active_scopes"; then
                blocked_count=$((blocked_count + 1))
                continue
            fi

            selected_item="$item"
            selected_scope="$scope"
            break
        done <<< "$queue_entries"

        if [[ -z "$selected_item" ]]; then
            if (( blocked_count > 0 )); then
                log_event "-" "queue-dispatch" "deferred" "all-candidates-blocked-by-active-scopes blocked=$blocked_count"
            fi
            break
        fi

        selected_id="$(echo "$selected_item" | jq -r '.id // empty')"
        selected_desc="$(echo "$selected_item" | jq -r '.description // empty')"
        selected_engine="$(echo "$selected_item" | jq -r '.engine // empty')"
        selected_model="$(echo "$selected_item" | jq -r '.model // empty')"

        local spawn_cmd queue_spawned
        spawn_cmd=("$SCRIPT_DIR/spawn-agent.sh" "$selected_id" "$selected_desc")
        if [[ -n "$selected_engine" && "$selected_engine" != "null" ]]; then
            spawn_cmd+=(--engine "$selected_engine")
        fi
        if [[ -n "$selected_model" && "$selected_model" != "null" ]]; then
            spawn_cmd+=(--model "$selected_model")
        fi

        queue_spawned=0
        if "${spawn_cmd[@]}" >/dev/null 2>&1; then
            queue_spawned=1
        fi

        if (( queue_spawned == 1 )); then
            json_update "$QUEUE_FILE" "map(select(.id != \"$selected_id\"))"
            running_count=$((running_count + 1))
            if [[ -n "$selected_scope" ]]; then
                active_scopes="${active_scopes}
${selected_scope}"
            fi
            log_event "$selected_id" "queue-dispatch" "started" "engine=${selected_engine:-default},model=${selected_model:-default},scope=${selected_scope:-none}"
        else
            log_event "$selected_id" "queue-dispatch" "failed" "spawn returned non-zero; task left in queue"
            break
        fi
    done
}

MAX_RETRIES="$(jq -r '.max_retries // 3' "$CONFIG_FILE")"
TIMEOUT_MIN="$(jq -r '.agent_timeout_minutes // 30' "$CONFIG_FILE")"
HEARTBEAT_TIMEOUT="$(jq -r '.heartbeat_timeout_minutes // 15' "$CONFIG_FILE")"
STALE_THRESHOLD="$(jq -r '.stale_state_minutes // 30' "$CONFIG_FILE")"

ensure_state_file "$ACTIVE_FILE" array
ensure_state_file "$COMPLETED_FILE" array
ensure_state_file "$QUEUE_FILE" array
ensure_state_file "$MEMORY_FILE" object
reconcile_queue_policy
aggregate_queue_candidates

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Running Seabone health check"

ACTIVE_COUNT="$(json_read "$ACTIVE_FILE" 'length' 2>/dev/null || echo 0)"
if [[ "$ACTIVE_COUNT" -eq 0 ]]; then
    echo "  No active tasks."
    dispatch_queue
    exit 0
fi

ISSUES=0
RESPAWNED=0

for i in $(seq $((ACTIVE_COUNT - 1)) -1 0); do
    TASK_ID="$(json_read "$ACTIVE_FILE" ".[$i].id // empty")"
    SESSION="$(json_read "$ACTIVE_FILE" ".[$i].session // empty")"
    STATUS="$(json_read "$ACTIVE_FILE" ".[$i].status // empty")"
    RETRIES="$(json_read "$ACTIVE_FILE" ".[$i].retries // 0")"
    STARTED="$(json_read "$ACTIVE_FILE" ".[$i].started_at // empty")"
    DESC="$(json_read "$ACTIVE_FILE" ".[$i].description // empty")"
    ENGINE="$(json_read "$ACTIVE_FILE" ".[$i].engine // empty")"
    MODEL="$(json_read "$ACTIVE_FILE" ".[$i].model // empty")"
    HEARTBEAT="$(json_read "$ACTIVE_FILE" ".[$i].last_heartbeat // \"$STARTED\"")"

    if terminal_statuses "$STATUS"; then
        archive_task "$i"
        continue
    fi

    if tmux has-session -t "$SESSION" 2>/dev/null; then
        echo "  Active: $TASK_ID"
        json_update "$ACTIVE_FILE" "(.[$i].last_heartbeat) = \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\""

        if [[ -n "$HEARTBEAT" ]]; then
            HEART_BEAT_EPOCH=$(date -d "$HEARTBEAT" +%s 2>/dev/null || echo 0)
            NOW=$(date +%s)
            HEART_MIN=$(((NOW - HEART_BEAT_EPOCH) / 60))

            if (( HEART_MIN > STALE_THRESHOLD )); then
                log_event "$TASK_ID" "heartbeat-stale" "stale" "no heartbeat for ${HEART_MIN}m"
                json_update "$ACTIVE_FILE" "(.[$i].status) = \"stale\""
            fi
        fi

        if [[ -n "$STARTED" ]]; then
            STARTED_EPOCH=$(date -d "$STARTED" +%s 2>/dev/null || echo 0)
            NOW=$(date +%s)
            ELAPSED_MIN=$(((NOW - STARTED_EPOCH) / 60))

            if (( ELAPSED_MIN > TIMEOUT_MIN )); then
                echo "  Timeout: $TASK_ID (${ELAPSED_MIN}m)"
                tmux kill-session -t "$SESSION" 2>/dev/null || true
                json_update "$ACTIVE_FILE" "(.[$i].status) = \"timeout\""
                ISSUES=$((ISSUES + 1))
            fi
        fi
    else
        if [[ "$STATUS" == "running" || "$STATUS" == "stale" ]]; then
            if [[ "$RETRIES" -lt "$MAX_RETRIES" ]]; then
                NEW_RETRIES=$((RETRIES + 1))
                if respawn_task "$TASK_ID" "$DESC" "$ENGINE" "$MODEL" "$NEW_RETRIES"; then
                    RESPAWNED=$((RESPAWNED + 1))
                else
                    ISSUES=$((ISSUES + 1))
                fi
            else
                json_update "$ACTIVE_FILE" "(.[$i].status) = \"max_retries_exceeded\""
                ISSUES=$((ISSUES + 1))
            fi
        fi
    fi
done

dispatch_queue

echo "Queue items: $(json_read "$QUEUE_FILE" 'length' 2>/dev/null || echo 0)"

echo "[DONE] Checked $ACTIVE_COUNT tasks, issues: $ISSUES, respawned: $RESPAWNED"

if [[ -n "$(json_read "$COMPLETED_FILE" 'length' 2>/dev/null || true)" ]]; then
    log_event "-" "check-complete" "ok" "completed-updated"
fi

# Optional CI poll for agent PR failures
echo "Checking CI for agent PRs..."
gh pr list --search "head:agent/" --json number,headRefName,statusCheckRollup --jq '.[] | "\(.number) \(.headRefName)"' 2>/dev/null | while read -r PR_NUM BRANCH_NAME; do
    if gh pr view "$PR_NUM" --json statusCheckRollup --jq '.statusCheckRollup | map(select(.state == "FAILURE")) | length > 0' 2>/dev/null | grep -q '^true$'; then
        echo "CI failed for PR #$PR_NUM ($BRANCH_NAME)"
    fi
done || true
