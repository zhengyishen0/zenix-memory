#!/usr/bin/env bash
#
# Hook: Sync session to unified YAML on stop
#
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MEMORY_DIR="${ZENIX_DATA:-$HOME/.zenix/data}/memory/sessions"

mkdir -p "$MEMORY_DIR"

# Get session ID from Claude Code env
session_id="${CLAUDE_SESSION_ID:-}"
[[ -z "$session_id" ]] && exit 0

# Convert and save
output="$MEMORY_DIR/${session_id}.yaml"
python3 "$SKILL_DIR/lib/convert.py" jsonl2yaml "$session_id" > "$output" 2>/dev/null || true
