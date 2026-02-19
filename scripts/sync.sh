#!/usr/bin/env zsh
#
# sync.sh - Manual sync session to unified YAML
#
# Usage:
#   memory sync [session-id] [--framework <name>]
#
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FRAMEWORK="claude-code"  # Default framework

# Parse args
session_id=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --framework|-f)
            FRAMEWORK="$2"
            shift 2
            ;;
        *)
            session_id="$1"
            shift
            ;;
    esac
done

MEMORY_DIR="${ZENIX_DATA:-$HOME/.zenix/data}/memory/sessions/$FRAMEWORK"
mkdir -p "$MEMORY_DIR"

# If no session ID, find most recent
if [[ -z "$session_id" ]]; then
    if [[ -n "${CLAUDE_SESSION_ID:-}" ]]; then
        session_id="$CLAUDE_SESSION_ID"
    else
        latest=$(find ~/.claude/projects -name "*.jsonl" -type f 2>/dev/null | xargs ls -t 2>/dev/null | head -1)
        if [[ -n "$latest" ]]; then
            session_id=$(basename "$latest" .jsonl)
            echo "Found: ${session_id:0:12}..." >&2
        else
            echo "Usage: memory sync [session-id] [--framework <name>]" >&2
            exit 1
        fi
    fi
fi

output="$MEMORY_DIR/${session_id}.yaml"
echo "Syncing → $output" >&2

if python3 "$SKILL_DIR/lib/convert.py" jsonl2yaml "$session_id" > "$output"; then
    size=$(stat -f "%z" "$output" 2>/dev/null || stat --format="%s" "$output" 2>/dev/null)
    echo "✓ Done ($(( size / 1024 ))KB)" >&2
else
    rm -f "$output"
    echo "✗ Failed" >&2
    exit 1
fi
