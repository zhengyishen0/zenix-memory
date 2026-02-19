#!/usr/bin/env zsh
#
# list.sh - List recent sessions from memory
#
# Usage:
#   list.sh [limit]                    # Formatted output (default)
#   list.sh --raw [limit]              # TSV output: full_id\tsource\tdate\tsummary
#   list.sh --framework <name> [limit] # Filter by framework
#
set -euo pipefail

MEMORY_BASE="${ZENIX_DATA:-$HOME/.zenix/data}/memory/sessions"

# Parse args
RAW_MODE=false
FRAMEWORK=""
limit=10

while [[ $# -gt 0 ]]; do
    case "$1" in
        --raw)
            RAW_MODE=true
            shift
            ;;
        --framework|-f)
            FRAMEWORK="$2"
            shift 2
            ;;
        *)
            limit="$1"
            shift
            ;;
    esac
done

# Determine search path
if [[ -n "$FRAMEWORK" ]]; then
    MEMORY_DIR="$MEMORY_BASE/$FRAMEWORK"
else
    MEMORY_DIR="$MEMORY_BASE"
fi

if [[ ! -d "$MEMORY_DIR" ]]; then
    [[ "$RAW_MODE" == false ]] && echo "No memory files found" >&2
    exit 0
fi

# Colors (only for formatted output)
DIM=$'\033[0;90m'
CYAN=$'\033[0;36m'
NC=$'\033[0m'

count=0
while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    [[ $count -ge $limit ]] && break
    ((count++))

    # Get session info from YAML header
    id=$(grep -m1 "^id:" "$file" 2>/dev/null | cut -d: -f2- | xargs) || continue
    created=$(grep -m1 "^created:" "$file" 2>/dev/null | cut -d: -f2- | xargs) || true
    summary=$(grep -m1 "^summary:" "$file" 2>/dev/null | cut -d: -f2- | xargs) || true
    source=$(grep -m1 "^source:" "$file" 2>/dev/null | cut -d: -f2- | xargs) || true

    # Format date (YYYY-MM-DD from ISO timestamp)
    date="${created:0:10}"

    if [[ "$RAW_MODE" == true ]]; then
        # TSV output for programmatic use
        printf '%s\t%s\t%s\t%s\n' "$id" "$source" "$date" "$summary"
    else
        # Formatted output for humans
        short_id="${id:0:12}"
        [[ ${#summary} -gt 50 ]] && summary="${summary:0:47}..."
        [[ -z "$summary" ]] && summary="(no summary)"
        printf "${CYAN}%s${NC}  ${DIM}%s  %s${NC}  %s\n" "$short_id" "$source" "$date" "$summary"
    fi
done < <(find "$MEMORY_DIR" -name "*.yaml" -type f 2>/dev/null | xargs ls -t 2>/dev/null)

if [[ $count -eq 0 && "$RAW_MODE" == false ]]; then
    echo "No sessions in memory" >&2
    echo "Run 'memory sync' after a session to populate" >&2
fi
