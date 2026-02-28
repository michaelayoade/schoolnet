#!/usr/bin/env bash
# review-pr.sh — AI code review on a PR via DeepSeek
# Usage: ./review-pr.sh <pr-number>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
export PATH="$HOME/.local/bin:$PATH"

if [[ -f "$PROJECT_DIR/.env.agent-swarm" ]]; then
    set -a; source "$PROJECT_DIR/.env.agent-swarm"; set +a
fi

PR_NUMBER="${1:?Usage: review-pr.sh <pr-number>}"

echo "[1/4] Fetching PR #$PR_NUMBER..."
PR_DIFF=$(gh pr diff "$PR_NUMBER" 2>/dev/null) || { echo "[ERROR] Could not fetch PR diff"; exit 1; }
PR_TITLE=$(gh pr view "$PR_NUMBER" --json title --jq '.title' 2>/dev/null || echo "Unknown")

[[ -z "$PR_DIFF" ]] && { echo "[WARN] Empty diff"; exit 0; }

echo "[2/4] Reviewing with DeepSeek..."
REVIEW_PROMPT="You are a senior code reviewer for a FastAPI platform (Python 3.12, SQLAlchemy 2.0, Pydantic v2).

PR: $PR_TITLE

Review covering:
1. Correctness — bugs, logic errors
2. Security — injection, XSS, secrets exposure
3. Performance — N+1 queries, unnecessary allocations
4. Style — consistent with FastAPI/SQLAlchemy conventions
5. Verdict — approve / request changes

Reference file names and line numbers. Under 500 words.

--- DIFF ---
$(echo "$PR_DIFF" | head -3000)
--- END ---"

REVIEW=$(curl -s "https://api.deepseek.com/chat/completions" \
    -H "Authorization: Bearer ${DEEPSEEK_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg p "$REVIEW_PROMPT" '{model:"deepseek-chat", messages:[{role:"user",content:$p}], temperature:0.3, max_tokens:1500}')" \
    | jq -r '.choices[0].message.content // "Review failed"')

echo "[3/4] Posting review..."
gh pr comment "$PR_NUMBER" --body "## 🤖 Seabone Review

$REVIEW

---
*Seabone Agent Swarm (DeepSeek)*" 2>/dev/null || { echo "[ERROR] Failed to post"; echo "$REVIEW"; exit 1; }

echo "[4/4] Review posted to PR #$PR_NUMBER"
"$SCRIPT_DIR/notify-telegram.sh" "🔍 *Seabone Review* on PR #$PR_NUMBER: $PR_TITLE" 2>/dev/null || true
