#!/bin/bash
# Recall sessions - ask session(s) a question using haiku
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
INDEX_FILE="$SKILL_DIR/data/memory-index.tsv"

show_help() {
  cat << 'EOF'
memory recall - Ask session(s) a question

USAGE
  memory recall <session-id> "<question>"
  memory recall <id1> <id2> ... "<question>"

EXAMPLES
  memory recall b8546b08 "how was the bug fixed?"
  memory recall b8546b08 6c2c0b4c "what was discussed?"

NOTES
  - Session IDs can be partial (first 7+ chars)
  - Multiple sessions run in parallel
  - Uses haiku model for speed

EOF
}

# Resolve partial session ID to full ID
resolve_session_id() {
  local partial="$1"
  local full_id=$(grep "^$partial" "$INDEX_FILE" 2>/dev/null | head -1 | cut -f1)
  echo "$full_id"
}

# Get session date from index
get_session_date() {
  local session_id="$1"
  local timestamp=$(grep "^$session_id" "$INDEX_FILE" 2>/dev/null | head -1 | cut -f2)
  echo "$timestamp" | cut -d'T' -f1 | awk -F'-' '{
    months["01"]="Jan"; months["02"]="Feb"; months["03"]="Mar"; months["04"]="Apr";
    months["05"]="May"; months["06"]="Jun"; months["07"]="Jul"; months["08"]="Aug";
    months["09"]="Sep"; months["10"]="Oct"; months["11"]="Nov"; months["12"]="Dec";
    print months[$2] " " int($3)
  }'
}

# Recall a single session
recall_session() {
  local session_id="$1"
  local question="$2"

  local formatted_prompt="Answer concisely:

[One sentence summary]

• Key point 1
• Key point 2
• Key point 3 (max 5 bullets)

Rules:
- No headers or markdown sections
- Keep under 150 tokens
- If no relevant info, respond ONLY: \"I don't have information about that.\"

Question: $question"

  agent --model haiku -r "$session_id" -p "$formatted_prompt" --no-session-persistence --output-format json 2>/dev/null | jq -r '.result // empty'
}

# Main
if [ $# -eq 0 ] || [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
  show_help
  exit 0
fi

if [ $# -lt 2 ]; then
  echo "Error: Need at least one session ID and a question" >&2
  echo "Usage: memory recall <session-id> \"<question>\"" >&2
  exit 1
fi

# Last argument is the question, rest are session IDs
QUESTION="${!#}"
SESSION_IDS=("${@:1:$#-1}")

# Resolve and validate session IDs
RESOLVED_IDS=()
for partial_id in "${SESSION_IDS[@]}"; do
  full_id=$(resolve_session_id "$partial_id")
  if [ -z "$full_id" ]; then
    echo "Error: Session not found: $partial_id" >&2
    exit 1
  fi
  RESOLVED_IDS+=("$full_id")
done

# Single session - direct call
if [ ${#RESOLVED_IDS[@]} -eq 1 ]; then
  recall_session "${RESOLVED_IDS[0]}" "$QUESTION"
  exit 0
fi

# Multiple sessions - parallel execution
echo "Q: $QUESTION"
echo ""

TIMEOUT=15
PIDS=()
TEMP_FILES=()

# Start all in parallel
for i in "${!RESOLVED_IDS[@]}"; do
  session_id="${RESOLVED_IDS[$i]}"
  temp_file="/tmp/memory-$$-$i.txt"
  TEMP_FILES+=("$temp_file")

  (recall_session "$session_id" "$QUESTION") > "$temp_file" 2>&1 &
  PIDS+=($!)
done

# Wait with timeout
elapsed=0
while [ $elapsed -lt $TIMEOUT ]; do
  all_done=true
  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      all_done=false
      break
    fi
  done
  $all_done && break
  sleep 1
  ((elapsed++))
done

# Kill remaining
for pid in "${PIDS[@]}"; do
  kill -9 "$pid" 2>/dev/null || true
done

# Collect results
GOOD_IDS=()
GOOD_CONTENTS=()
GOOD_DATES=()
NO_INFO=0
ERRORS=0

for i in "${!TEMP_FILES[@]}"; do
  temp_file="${TEMP_FILES[$i]}"
  session_id="${RESOLVED_IDS[$i]}"

  if [ -f "$temp_file" ] && [ -s "$temp_file" ]; then
    content=$(cat "$temp_file")
    if echo "$content" | grep -qiE "(I don't have (enough )?information|no information about)"; then
      ((NO_INFO++))
    elif echo "$content" | grep -qiE "^Error:"; then
      ((ERRORS++))
    else
      GOOD_IDS+=("${session_id:0:7}")
      GOOD_CONTENTS+=("$content")
      GOOD_DATES+=("$(get_session_date "$session_id")")
    fi
  else
    ((ERRORS++))
  fi
done

# Output results
TOTAL_GOOD=${#GOOD_IDS[@]}
if [ $TOTAL_GOOD -gt 0 ]; then
  for i in "${!GOOD_IDS[@]}"; do
    echo "[$((i+1))/$TOTAL_GOOD] ${GOOD_IDS[$i]} • ${GOOD_DATES[$i]}"
    echo "${GOOD_CONTENTS[$i]}"
    echo ""
  done
  [ $NO_INFO -gt 0 ] || [ $ERRORS -gt 0 ] && echo "($NO_INFO no info, $ERRORS errors)" >&2
else
  echo "No relevant answers found." >&2
fi

rm -f "${TEMP_FILES[@]}"
