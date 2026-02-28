#!/usr/bin/env bash
# json-lock.sh — Atomic JSON file operations with flock and basic file initialization
set -euo pipefail

LOCK_DIR="/tmp/seabone-locks"
mkdir -p "$LOCK_DIR"

_seabone_ensure_json_file() {
    local file="$1"
    local kind="${2:-array}"
    if [[ ! -f "$file" ]]; then
        case "$kind" in
            object)
                printf "{}\n" > "$file"
                ;;
            *)
                printf "[]\n" > "$file"
                ;;
        esac
        return
    fi

    if ! jq empty "$file" >/dev/null 2>&1; then
        case "$kind" in
            object)
                printf "{}\n" > "$file"
                ;;
            *)
                printf "[]\n" > "$file"
                ;;
        esac
    fi
}

_seabone_lock_file() {
    local file="$1"
    echo "$LOCK_DIR/$(printf %s "$file" | tr /:. ___).lock"
}

# json_update <file> <jq_expression> [kind]
json_update() {
    local file="$1"
    local expr="$2"
    local kind="${3:-auto}"
    local lockfile
    lockfile=$(_seabone_lock_file "$file")

    if [[ "$kind" == "object" ]]; then
        _seabone_ensure_json_file "$file" object
    else
        _seabone_ensure_json_file "$file" array
    fi

    (
        flock -w 10 200 || { echo "[ERROR] Could not acquire lock for $file" >&2; return 1; }
        local tmp
        tmp="${file}.tmp"
        jq "$expr" "$file" > "$tmp" && mv "$tmp" "$file"
    ) 200>"$lockfile"
}

# json_append <file> <json_object>
json_append() {
    local file="$1"
    local obj="$2"
    local lockfile
    lockfile=$(_seabone_lock_file "$file")

    _seabone_ensure_json_file "$file" array

    (
        flock -w 10 200 || { echo "[ERROR] Could not acquire lock for $file" >&2; return 1; }
        local tmp
        tmp="${file}.tmp"
        echo "$obj" | jq -s --slurpfile arr "$file" '$arr[0] + .' > "$tmp" && mv "$tmp" "$file"
    ) 200>"$lockfile"
}

# json_read <file> <jq_expression>
json_read() {
    local file="$1"
    local expr="${2:-.}"
    local lockfile
    lockfile=$(_seabone_lock_file "$file")

    _seabone_ensure_json_file "$file" array

    (
        flock -s -w 5 200 || { echo "[ERROR] Could not acquire read lock for $file" >&2; return 1; }
        jq -r "$expr" "$file"
    ) 200>"$lockfile"
}
