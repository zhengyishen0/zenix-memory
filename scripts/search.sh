#!/bin/bash
# Search Claude sessions
# Simple mode: "word1 word2 word3" → OR-all, ranked by keyword hits
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
LIB_DIR="$SKILL_DIR/lib"

: "${CLAUDE_DIR:=$HOME/.claude}"

DATA_DIR="$SKILL_DIR/data"
SESSION_DIR="$CLAUDE_DIR/projects"
INDEX_FILE="$DATA_DIR/memory-index.tsv"
NLP_INDEX_FILE="$DATA_DIR/memory-index-nlp.tsv"

# Parse args
# Debug options (not shown in help): --sessions, --messages, --context, --topics
SESSIONS=5
MESSAGES=5
CONTEXT=500
QUERY=""
RECALL_QUESTION=""
SHOW_TOPICS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sessions)
      SESSIONS="$2"
      shift 2
      ;;
    --messages)
      MESSAGES="$2"
      shift 2
      ;;
    --context)
      CONTEXT="$2"
      shift 2
      ;;
    --recall)
      RECALL_QUESTION="$2"
      shift 2
      ;;
    --topics)
      SHOW_TOPICS="--topics"
      shift
      ;;
    -*)
      echo "Error: Unknown flag '$1'" >&2
      exit 1
      ;;
    *)
      QUERY="$1"
      shift
      ;;
  esac
done

# Validation
if [ -z "$QUERY" ]; then
  echo "Usage: memory search \"<keywords>\" [--recall \"question\"]" >&2
  echo "" >&2
  echo "IMPORTANT: Use 4+ keywords. Order matters - put most important first!" >&2
  echo "  First keyword = highest weight, last = lowest weight" >&2
  echo "" >&2
  echo "NLP matching is always enabled (ran→run, specifications→specification)" >&2
  echo "" >&2
  echo "Options:" >&2
  echo "  --recall Q    Ask matched sessions a follow-up question" >&2
  echo "" >&2
  echo "Examples:" >&2
  echo "  memory search \"bandwidth M4 MacBook LLM slow\"     # 'bandwidth' weighted highest" >&2
  echo "  memory search \"CoreML Neural Engine performance\"  # 'CoreML' weighted highest" >&2
  echo "  memory search \"browser\" --recall \"how to click?\"" >&2
  exit 1
fi

[ ! -d "$SESSION_DIR" ] && { echo "Error: No Claude sessions found" >&2; exit 1; }

# Build full index with jq
build_full_index() {
  echo "Building index..." >&2
  find "$SESSION_DIR" -name "*.jsonl" -type f 2>/dev/null | while read -r file; do
    if ! head -1 "$file" | jq -e 'select(.type == "queue-operation")' >/dev/null 2>&1; then
      echo "$file"
    fi
  done | xargs -I{} rg -N --json '"type":"(user|assistant)"' {} 2>/dev/null | \
    jq -r '
      select(.type == "match") |
      .data.path.text as $filepath |
      .data.lines.text | fromjson |
      select(.type == "user" or .type == "assistant") |
      (.message.content |
        if type == "array" then
          [.[] | select(.type == "text") | .text] | join(" ")
        elif type == "string" then .
        else "" end
      ) as $text |
      select($text | length > 10) |
      select($text | test("<ide_|\\[Request interrupted|New environment|API Error|Limit reached|Caveat:|<bash-|<function_calls|<invoke|</invoke|<parameter|</parameter|</function_calls") | not) |
      select($text | test("^\\[[0-9]+/[0-9]+\\]\\s+[a-f0-9]{7}\\s+•") | not) |
      ($filepath | split("/") | last | split(".jsonl") | first) as $session_id |
      select($session_id | startswith("agent-") | not) |
      [$session_id, .timestamp, .type, $text, .cwd // "unknown"] | @tsv
    ' 2>/dev/null > "$INDEX_FILE"
  echo "Index built: $(wc -l < "$INDEX_FILE" | tr -d ' ') messages" >&2
  # Build NLP index with normalized text
  build_nlp_index
}

# Build NLP index with normalized text column
build_nlp_index() {
  echo "Building NLP index..." >&2
  python3 "$LIB_DIR/build_index.py" "$INDEX_FILE" "$NLP_INDEX_FILE"
  # Auto-discover domain keywords from co-occurrence (silent)
  python3 "$LIB_DIR/build_custom_keywords.py" --write >/dev/null 2>&1 || true
}

# Incremental update
update_index() {
  local new_files="$1"
  local non_fork_files=$(echo "$new_files" | while read -r file; do
    if [ -f "$file" ] && ! head -1 "$file" | jq -e 'select(.type == "queue-operation")' >/dev/null 2>&1; then
      echo "$file"
    fi
  done)

  if [ -z "$non_fork_files" ]; then
    return
  fi

  local count=$(echo "$non_fork_files" | wc -l | tr -d ' ')
  echo "Updating index ($count files)..." >&2

  # Create temp file for new entries
  local temp_file=$(mktemp)

  echo "$non_fork_files" | xargs -I{} rg -N --json '"type":"(user|assistant)"' {} 2>/dev/null | \
    jq -r '
      select(.type == "match") |
      .data.path.text as $filepath |
      .data.lines.text | fromjson |
      select(.type == "user" or .type == "assistant") |
      (.message.content |
        if type == "array" then
          [.[] | select(.type == "text") | .text] | join(" ")
        elif type == "string" then .
        else "" end
      ) as $text |
      select($text | length > 10) |
      select($text | test("<ide_|\\[Request interrupted|New environment|API Error|Limit reached|Caveat:|<bash-|<function_calls|<invoke|</invoke|<parameter|</parameter|</function_calls") | not) |
      select($text | test("^\\[[0-9]+/[0-9]+\\]\\s+[a-f0-9]{7}\\s+•") | not) |
      ($filepath | split("/") | last | split(".jsonl") | first) as $session_id |
      select($session_id | startswith("agent-") | not) |
      [$session_id, .timestamp, .type, $text, .cwd // "unknown"] | @tsv
    ' 2>/dev/null > "$temp_file" || true

  if [ -s "$temp_file" ]; then
    # Append to base index
    cat "$temp_file" >> "$INDEX_FILE"
    # Normalize and append to NLP index
    python3 "$LIB_DIR/build_index.py" "$temp_file" /dev/stdout >> "$NLP_INDEX_FILE"
    # Mark that keywords need refresh (will run after search completes)
    touch "$DATA_DIR/.keywords_stale"
  fi

  rm -f "$temp_file"
}

# Check if index needs update
if [ ! -f "$INDEX_FILE" ]; then
  build_full_index
elif [ ! -f "$NLP_INDEX_FILE" ]; then
  # Base index exists but NLP index doesn't - build it
  build_nlp_index
else
  NEW_FILES=$(find "$SESSION_DIR" -name "*.jsonl" -newer "$INDEX_FILE" 2>/dev/null || true)
  if [ -n "$NEW_FILES" ]; then
    update_index "$NEW_FILES"
  fi
fi

# Fast query normalization (no NLTK dependency)
normalize_query() {
  python3 "$LIB_DIR/normalize_query.py" "$1"
}

# Simple search: OR all normalized keywords with word boundaries
run_search() {
  # Normalize the query
  QUERY_NORMALIZED=$(normalize_query "$QUERY")

  read -ra KEYWORDS <<< "$QUERY_NORMALIZED"

  # Build word-boundary patterns for each normalized keyword
  OR_PATTERNS=()
  for keyword in "${KEYWORDS[@]}"; do
    # Word boundary pattern: \b<word>\b
    OR_PATTERNS+=("\\b${keyword}\\b")
  done

  if [ ${#OR_PATTERNS[@]} -eq 1 ]; then
    PATTERN="${OR_PATTERNS[0]}"
  else
    PATTERN=$(IFS='|'; echo "${OR_PATTERNS[*]}")
    PATTERN="($PATTERN)"
  fi

  # Search on normalized column (column 5, 0-indexed) in NLP index
  rg -i "$PATTERN" "$NLP_INDEX_FILE" 2>/dev/null || true
}

# Execute search
QUERY_NORMALIZED=$(normalize_query "$QUERY")
RESULTS=$(run_search | sort -u || true)

if [ -z "$RESULTS" ]; then
  echo "No matches found for: $QUERY"
  exit 0
fi

# Format results and capture session IDs from stderr
TEMP_IDS=$(mktemp)
OUTPUT=$(echo "$RESULTS" | python3 "$LIB_DIR/format-results.py" "$SESSIONS" "$MESSAGES" "$CONTEXT" "$QUERY" "simple" "$QUERY_NORMALIZED" $SHOW_TOPICS 2>"$TEMP_IDS")
SESSION_IDS=$(cat "$TEMP_IDS")
rm -f "$TEMP_IDS"

# If --recall, run parallel recall on matching sessions
if [ -n "$RECALL_QUESTION" ]; then
  if [ -z "$SESSION_IDS" ]; then
    echo "No sessions to recall."
    exit 0
  fi

  # Convert comma-separated IDs to array
  IFS=',' read -ra ID_ARRAY <<< "$SESSION_IDS"

  # Call recall.sh with session IDs and question
  "$SCRIPT_DIR/recall.sh" "${ID_ARRAY[@]}" "$RECALL_QUESTION"
else
  # Normal search output with footer tip
  echo "$OUTPUT"
  echo ""
  echo "Tip: If snippets above answer your question, you're done. Otherwise use --recall \"question\" for deeper answers."
fi

# Background: refresh keywords if stale (runs after output, non-blocking)
if [ -f "$DATA_DIR/.keywords_stale" ]; then
  rm -f "$DATA_DIR/.keywords_stale"
  (python3 "$LIB_DIR/build_custom_keywords.py" --write >/dev/null 2>&1 &)
fi
