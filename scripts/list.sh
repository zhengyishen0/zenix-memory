#!/usr/bin/env bash
#
# list.sh - List recent sessions from memory
#
set -euo pipefail

MEMORY_DIR="${ZENIX_DATA:-$HOME/.zenix/data}/memory/sessions"
limit="${1:-10}"

if [[ ! -d "$MEMORY_DIR" ]]; then
    echo "No memory files found" >&2
    exit 0
fi

# Colors
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

    # Format
    short_id="${id:0:12}"
    date="${created:1:10}"  # YYYY-MM-DD
    [[ ${#summary} -gt 50 ]] && summary="${summary:0:47}..."
    [[ -z "$summary" ]] && summary="(no summary)"

    printf "${CYAN}%s${NC}  ${DIM}%s  %s${NC}  %s\n" "$short_id" "$source" "$date" "$summary"
done < <(find "$MEMORY_DIR" -name "*.yaml" -type f 2>/dev/null | xargs ls -t 2>/dev/null)

if [[ $count -eq 0 ]]; then
    echo "No sessions in memory" >&2
    echo "Run 'memory sync' after a session to populate" >&2
fi
